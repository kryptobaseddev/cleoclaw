"""Board memory CRUD and streaming endpoints."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func
from sqlmodel import col
from sse_starlette.sse import EventSourceResponse

from app.api.deps import (
    ActorContext,
    get_board_for_actor_read,
    get_board_for_actor_write,
    require_user_or_agent,
)
from app.core.config import settings
from app.core.time import utcnow
from app.db.pagination import paginate
from app.db.session import async_session_maker, get_session
from app.models.agents import Agent
from app.models.board_memory import BoardMemory
from app.models.gateways import Gateway
from app.schemas.board_memory import BoardMemoryCreate, BoardMemoryRead
from app.schemas.pagination import DefaultLimitOffsetPage
from app.services.mentions import extract_mentions, matches_agent_mention
from app.services.openclaw.gateway_dispatch import GatewayDispatchService
from app.services.openclaw.gateway_rpc import GatewayConfig as GatewayClientConfig

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from fastapi_pagination.limit_offset import LimitOffsetPage
    from sqlmodel.ext.asyncio.session import AsyncSession

    from app.models.boards import Board

router = APIRouter(prefix="/boards/{board_id}/memory", tags=["board-memory"])
MAX_SNIPPET_LENGTH = 800
STREAM_POLL_SECONDS = 2
IS_CHAT_QUERY = Query(default=None)
SINCE_QUERY = Query(default=None)
BOARD_READ_DEP = Depends(get_board_for_actor_read)
BOARD_WRITE_DEP = Depends(get_board_for_actor_write)
SESSION_DEP = Depends(get_session)
ACTOR_DEP = Depends(require_user_or_agent)
_RUNTIME_TYPE_REFERENCES = (UUID,)


def _parse_since(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    normalized = normalized.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        return parsed.astimezone(UTC).replace(tzinfo=None)
    return parsed


def _serialize_memory(memory: BoardMemory) -> dict[str, object]:
    return BoardMemoryRead.model_validate(
        memory,
        from_attributes=True,
    ).model_dump(mode="json")


async def _fetch_memory_events(
    session: AsyncSession,
    board_id: UUID,
    since: datetime,
    is_chat: bool | None = None,
) -> list[BoardMemory]:
    statement = (
        BoardMemory.objects.filter_by(board_id=board_id)
        # Old/invalid rows (empty/whitespace-only content) can exist; exclude them to
        # satisfy the NonEmptyStr response schema.
        .filter(func.length(func.trim(col(BoardMemory.content))) > 0)
    )
    if is_chat is not None:
        statement = statement.filter(col(BoardMemory.is_chat) == is_chat)
    statement = statement.filter(col(BoardMemory.created_at) > since).order_by(
        col(BoardMemory.created_at),
    )
    return await statement.all(session)


async def _send_control_command(
    *,
    session: AsyncSession,
    board: Board,
    actor: ActorContext,
    dispatch: GatewayDispatchService,
    config: GatewayClientConfig,
    command: str,
) -> None:
    pause_targets: list[Agent] = await Agent.objects.filter_by(
        board_id=board.id,
    ).all(
        session,
    )
    for agent in pause_targets:
        if actor.actor_type == "agent" and actor.agent and agent.id == actor.agent.id:
            continue
        if not agent.openclaw_session_id:
            continue
        error = await dispatch.try_send_agent_message(
            session_key=agent.openclaw_session_id,
            config=config,
            agent_name=agent.name,
            message=command,
            deliver=True,
        )
        if error is not None:
            continue


def _chat_targets(
    *,
    agents: list[Agent],
    mentions: set[str],
    actor: ActorContext,
) -> dict[str, Agent]:
    targets: dict[str, Agent] = {}
    for agent in agents:
        if agent.is_board_lead:
            targets[str(agent.id)] = agent
            continue
        if mentions and matches_agent_mention(agent, mentions):
            targets[str(agent.id)] = agent
    if actor.actor_type == "agent" and actor.agent:
        targets.pop(str(actor.agent.id), None)
    return targets


def _actor_display_name(actor: ActorContext) -> str:
    if actor.actor_type == "agent" and actor.agent:
        return actor.agent.name
    if actor.user:
        return actor.user.preferred_name or actor.user.name or "User"
    return "User"


async def _dispatch_chat_to_agents(
    *,
    board_id: UUID,
    board_name: str,
    gateway_id: UUID | None,
    content: str | None,
    actor_name: str,
    actor_agent_id: UUID | None,
    board_agents: list[dict],
) -> None:
    """Background task: dispatch a board chat message to agents via OpenClaw RPC.

    Self-contained — uses its own DB session and SDK client.
    All parameters are primitives extracted before the request session closed.
    """
    import logging as _logging

    _log = _logging.getLogger("board_memory.chat")

    if not content or not content.strip() or not gateway_id:
        return

    # Get gateway config from DB.
    from app.db.session import async_session_maker

    async with async_session_maker() as db_session:
        gateway = await Gateway.objects.filter_by(id=gateway_id).first(db_session)

    if not gateway:
        _log.warning("_dispatch_chat: gateway %s not found", gateway_id)
        return

    from app.services.openclaw.gateway_resolver import optional_gateway_client_config

    config = optional_gateway_client_config(gateway)
    if not config:
        _log.warning("_dispatch_chat: no config for gateway %s", gateway_id)
        return

    # Filter targets: board leads always, workers only if mentioned.
    snippet = content.strip()
    if len(snippet) > MAX_SNIPPET_LENGTH:
        snippet = f"{snippet[: MAX_SNIPPET_LENGTH - 3]}..."

    targets = [
        a for a in board_agents
        if a["is_board_lead"] and str(a["id"]) != str(actor_agent_id)
    ]

    if not targets:
        _log.info("_dispatch_chat: no targets for board %s", board_id)
        return

    from app.services.openclaw.gateway_rpc import ensure_session, send_message

    for agent_info in targets:
        session_key = agent_info["session_key"]
        agent_name = agent_info["name"]
        message = (
            f"BOARD CHAT\n"
            f"Board: {board_name}\n"
            f"From: {actor_name}\n\n"
            f"{snippet}"
        )
        _log.info("_dispatch_chat: sending to %s session=%s", agent_name, session_key)
        try:
            await ensure_session(session_key, config=config)
            await send_message(message, session_key=session_key, config=config, deliver=True)
            _log.info("_dispatch_chat: sent to %s", agent_name)
        except Exception as exc:
            _log.error("_dispatch_chat: send failed %s: %s", agent_name, exc)
            continue

        # Start response poller.
        import asyncio as _asyncio

        _asyncio.create_task(
            _poll_agent_response(
                board_id=board_id,
                agent_name=agent_name,
                session_key=session_key,
                gateway_url=gateway.url,
                gateway_token=gateway.token,
                allow_insecure_tls=gateway.allow_insecure_tls,
                disable_device_pairing=gateway.disable_device_pairing,
            )
        )


async def _notify_chat_targets(
    *,
    session: AsyncSession,
    board: Board,
    memory: BoardMemory,
    actor: ActorContext,
) -> None:
    import logging as _logging
    _log = _logging.getLogger("board_memory.chat")
    _log.info("_notify_chat_targets called board=%s content=%s", board.id, (memory.content or "")[:50])
    if not memory.content:
        _log.info("_notify_chat_targets: no content, skipping")
        return
    dispatch = GatewayDispatchService(session)
    config = await dispatch.optional_gateway_config_for_board(board)
    if config is None:
        _log.warning("_notify_chat_targets: no gateway config for board %s", board.id)
        return

    normalized = memory.content.strip()
    command = normalized.lower()
    # Special-case control commands to reach all board agents.
    # These are intended to be parsed verbatim by agent runtimes.
    if command in {"/pause", "/resume"}:
        await _send_control_command(
            session=session,
            board=board,
            actor=actor,
            dispatch=dispatch,
            config=config,
            command=command,
        )
        return

    mentions = extract_mentions(memory.content)
    targets = _chat_targets(
        agents=await Agent.objects.filter_by(board_id=board.id).all(session),
        mentions=mentions,
        actor=actor,
    )
    if not targets:
        _log.warning("_notify_chat_targets: no targets found for board %s", board.id)
        return
    _log.info("_notify_chat_targets: %d targets found", len(targets))
    actor_name = _actor_display_name(actor)
    snippet = memory.content.strip()
    if len(snippet) > MAX_SNIPPET_LENGTH:
        snippet = f"{snippet[: MAX_SNIPPET_LENGTH - 3]}..."
    base_url = settings.base_url
    for agent in targets.values():
        if not agent.openclaw_session_id:
            continue
        mentioned = matches_agent_mention(agent, mentions)
        header = "BOARD CHAT MENTION" if mentioned else "BOARD CHAT"
        message = (
            f"{header}\n"
            f"Board: {board.name}\n"
            f"From: {actor_name}\n\n"
            f"{snippet}\n\n"
            "Reply via board chat:\n"
            f"POST {base_url}/api/v1/agent/boards/{board.id}/memory\n"
            'Body: {"content":"...","tags":["chat"]}'
        )
        _log.info("_notify_chat_targets: sending to agent=%s session=%s", agent.name, agent.openclaw_session_id)
        error = await dispatch.try_send_agent_message(
            session_key=agent.openclaw_session_id,
            config=config,
            agent_name=agent.name,
            message=message,
        )
        if error is not None:
            _log.error("_notify_chat_targets: send failed agent=%s error=%s", agent.name, error)
            continue
        _log.info("_notify_chat_targets: sent successfully to agent=%s", agent.name)

        # Poll for the agent's response and store it as board memory.
        import asyncio as _asyncio

        _asyncio.create_task(
            _poll_agent_response(
                board_id=board.id,
                agent_name=agent.name,
                session_key=agent.openclaw_session_id,
                gateway_url=config.url,
                gateway_token=config.token,
                allow_insecure_tls=config.allow_insecure_tls,
                disable_device_pairing=config.disable_device_pairing,
            )
        )


async def _poll_agent_response(
    *,
    board_id: UUID,
    agent_name: str,
    session_key: str,
    gateway_url: str,
    gateway_token: str | None,
    allow_insecure_tls: bool = False,
    disable_device_pairing: bool = False,
    max_attempts: int = 30,
    poll_interval: float = 2.0,
) -> None:
    """Poll OpenClaw chat history for the agent's response and store it as board memory.

    Runs as a background task after sending a chat message to the agent.
    Uses only primitive values (no ORM objects) to avoid detached session errors.
    """
    import asyncio as _asyncio
    import logging as _logging

    from app.services.openclaw.gateway_sdk.client import GatewayClient
    from app.services.openclaw.gateway_sdk.config import GatewayConnectionConfig

    _log = _logging.getLogger("board_memory.poll")

    sdk_config = GatewayConnectionConfig(
        url=gateway_url,
        token=gateway_token,
        allow_insecure_tls=allow_insecure_tls,
        disable_device_pairing=disable_device_pairing,
    )
    sdk_client = GatewayClient(sdk_config)

    # Record the send time so we only store responses newer than our message.
    import time as _time
    send_timestamp = int(_time.time() * 1000)

    # Wait for the agent to start processing.
    await _asyncio.sleep(5)

    for attempt in range(max_attempts):
        try:
            history = await sdk_client.rpc.chat_history(
                session_key=session_key,
                limit=10,
            )
            messages = getattr(history, "messages", [])

            # Find the latest assistant text response newer than our send.
            for msg in reversed(messages):
                role = getattr(msg, "role", None)
                if role != "assistant":
                    continue

                # Skip messages older than our send.
                msg_ts = getattr(msg, "timestamp", None) or 0
                if msg_ts and msg_ts < send_timestamp:
                    continue

                content = getattr(msg, "content", None)
                if not content:
                    continue

                # Extract text from content blocks.
                text = ""
                if isinstance(content, str):
                    text = content
                elif isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            t = block.get("text", "")
                            if t and t.strip():
                                text = t
                                break

                if not text or not text.strip():
                    continue

                # Store as board memory.
                from app.db.session import async_session_maker

                async with async_session_maker() as db_session:
                    reply = BoardMemory(
                        board_id=board_id,
                        content=text.strip(),
                        tags=["chat"],
                        is_chat=True,
                        source=agent_name,
                    )
                    db_session.add(reply)
                    await db_session.commit()
                    _log.info(
                        "poll_agent_response: stored reply board=%s agent=%s len=%d",
                        board_id,
                        agent_name,
                        len(text),
                    )
                return

        except Exception as exc:
            _log.debug("poll_agent_response: attempt %d error: %s", attempt, exc)

        await _asyncio.sleep(poll_interval)

    _log.warning("poll_agent_response: timed out board=%s agent=%s", board_id, agent_name)


@router.get("", response_model=DefaultLimitOffsetPage[BoardMemoryRead])
async def list_board_memory(
    *,
    is_chat: bool | None = IS_CHAT_QUERY,
    board: Board = BOARD_READ_DEP,
    session: AsyncSession = SESSION_DEP,
    _actor: ActorContext = ACTOR_DEP,
) -> LimitOffsetPage[BoardMemoryRead]:
    """List board memory entries, optionally filtering chat entries."""
    statement = (
        BoardMemory.objects.filter_by(board_id=board.id)
        # Old/invalid rows (empty/whitespace-only content) can exist; exclude them to
        # satisfy the NonEmptyStr response schema.
        .filter(func.length(func.trim(col(BoardMemory.content))) > 0)
    )
    if is_chat is not None:
        statement = statement.filter(col(BoardMemory.is_chat) == is_chat)
    statement = statement.order_by(col(BoardMemory.created_at).desc())
    return await paginate(session, statement.statement)


@router.get("/stream")
async def stream_board_memory(
    request: Request,
    *,
    board: Board = BOARD_READ_DEP,
    _actor: ActorContext = ACTOR_DEP,
    since: str | None = SINCE_QUERY,
    is_chat: bool | None = IS_CHAT_QUERY,
) -> EventSourceResponse:
    """Stream board memory events over server-sent events."""
    since_dt = _parse_since(since) or utcnow()
    last_seen = since_dt

    async def event_generator() -> AsyncIterator[dict[str, str]]:
        nonlocal last_seen
        while True:
            if await request.is_disconnected():
                break
            async with async_session_maker() as session:
                memories = await _fetch_memory_events(
                    session,
                    board.id,
                    last_seen,
                    is_chat=is_chat,
                )
            for memory in memories:
                last_seen = max(memory.created_at, last_seen)
                payload = {"memory": _serialize_memory(memory)}
                yield {"event": "memory", "data": json.dumps(payload)}
            await asyncio.sleep(STREAM_POLL_SECONDS)

    return EventSourceResponse(
        event_generator(),
        ping=10,
        headers={
            "X-Accel-Buffering": "no",
            "Cache-Control": "no-cache, no-transform",
        },
    )


@router.post("", response_model=BoardMemoryRead)
async def create_board_memory(
    payload: BoardMemoryCreate,
    board: Board = BOARD_WRITE_DEP,
    session: AsyncSession = SESSION_DEP,
    actor: ActorContext = ACTOR_DEP,
) -> BoardMemory:
    """Create a board memory entry and notify chat targets when needed."""
    is_chat = payload.tags is not None and "chat" in payload.tags
    source = payload.source
    if is_chat and not source:
        if actor.actor_type == "agent" and actor.agent:
            source = actor.agent.name
        elif actor.user:
            source = actor.user.preferred_name or actor.user.name or "User"
    memory = BoardMemory(
        board_id=board.id,
        content=payload.content,
        tags=payload.tags,
        is_chat=is_chat,
        source=source,
    )
    session.add(memory)
    await session.commit()
    await session.refresh(memory)
    if is_chat:
        import asyncio as _asyncio

        # Extract all data needed BEFORE launching background task.
        # ORM objects can't be used after the request session closes.
        _board_id = board.id
        _board_name = board.name
        _gateway_id = board.gateway_id
        _memory_content = memory.content
        _actor_name = _actor_display_name(actor)
        _actor_agent_id = actor.agent.id if actor.actor_type == "agent" and actor.agent else None

        # Collect board agents with their session keys.
        _board_agents = [
            {"id": a.id, "name": a.name, "is_board_lead": a.is_board_lead, "session_key": a.openclaw_session_id}
            for a in await Agent.objects.filter_by(board_id=board.id).all(session)
            if a.openclaw_session_id
        ]

        _asyncio.create_task(_dispatch_chat_to_agents(
            board_id=_board_id,
            board_name=_board_name,
            gateway_id=_gateway_id,
            content=_memory_content,
            actor_name=_actor_name,
            actor_agent_id=_actor_agent_id,
            board_agents=_board_agents,
        ))
    return memory
