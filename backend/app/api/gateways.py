"""Thin API wrappers for gateway CRUD and template synchronization."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import col

from app.api.deps import require_org_admin
from app.core.auth import AuthContext, get_auth_context
from app.core.config import settings
from app.db import crud
from app.db.pagination import paginate
from app.db.session import get_session
from app.models.agents import Agent
from app.models.gateways import Gateway
from app.models.skills import GatewayInstalledSkill
from app.schemas.common import OkResponse
from app.schemas.gateways import (
    ConfigureTrustedProxyRequest,
    ConfigureTrustedProxyResponse,
    GatewayCreate,
    GatewayCreateResponse,
    GatewayRead,
    GatewayTemplatesSyncResult,
    GatewayUpdate,
    WorkspaceHealthCheckResult,
)
from app.schemas.pagination import DefaultLimitOffsetPage
from app.services.openclaw.admin_service import GatewayAdminLifecycleService
from app.services.openclaw.gateway_sdk.manager import gateway_manager
from app.services.openclaw.session_service import GatewayTemplateSyncQuery

if TYPE_CHECKING:
    from fastapi_pagination.limit_offset import LimitOffsetPage
    from sqlmodel.ext.asyncio.session import AsyncSession

    from app.services.organizations import OrganizationContext


router = APIRouter(prefix="/gateways", tags=["gateways"])
SESSION_DEP = Depends(get_session)
AUTH_DEP = Depends(get_auth_context)
ORG_ADMIN_DEP = Depends(require_org_admin)
INCLUDE_MAIN_QUERY = Query(default=True)
RESET_SESSIONS_QUERY = Query(default=False)
ROTATE_TOKENS_QUERY = Query(default=False)
FORCE_BOOTSTRAP_QUERY = Query(default=False)
OVERWRITE_QUERY = Query(default=False)
LEAD_ONLY_QUERY = Query(default=False)
BOARD_ID_QUERY = Query(default=None)
_RUNTIME_TYPE_REFERENCES = (UUID,)


def _template_sync_query(
    *,
    include_main: bool = INCLUDE_MAIN_QUERY,
    lead_only: bool = LEAD_ONLY_QUERY,
    reset_sessions: bool = RESET_SESSIONS_QUERY,
    rotate_tokens: bool = ROTATE_TOKENS_QUERY,
    force_bootstrap: bool = FORCE_BOOTSTRAP_QUERY,
    overwrite: bool = OVERWRITE_QUERY,
    board_id: UUID | None = BOARD_ID_QUERY,
) -> GatewayTemplateSyncQuery:
    return GatewayTemplateSyncQuery(
        include_main=include_main,
        lead_only=lead_only,
        reset_sessions=reset_sessions,
        rotate_tokens=rotate_tokens,
        force_bootstrap=force_bootstrap,
        overwrite=overwrite,
        board_id=board_id,
    )


SYNC_QUERY_DEP = Depends(_template_sync_query)


@router.get("", response_model=DefaultLimitOffsetPage[GatewayRead])
async def list_gateways(
    session: AsyncSession = SESSION_DEP,
    ctx: OrganizationContext = ORG_ADMIN_DEP,
) -> LimitOffsetPage[GatewayRead]:
    """List gateways for the caller's organization."""
    statement = (
        Gateway.objects.filter_by(organization_id=ctx.organization.id)
        .order_by(col(Gateway.created_at).desc())
        .statement
    )

    return await paginate(session, statement)


@router.post("/configure-trusted-proxy", response_model=ConfigureTrustedProxyResponse)
async def configure_trusted_proxy(
    payload: ConfigureTrustedProxyRequest,
    auth: AuthContext = AUTH_DEP,
    ctx: OrganizationContext = ORG_ADMIN_DEP,
) -> ConfigureTrustedProxyResponse:
    """Auto-configure trusted-proxy auth on an OpenClaw gateway via RPC.

    Connects to the gateway using token auth, then patches the config to
    enable trusted-proxy mode with the provided NPM IP and FQDN.
    """
    from app.services.openclaw.gateway_sdk.client import GatewayClient
    from app.services.openclaw.gateway_sdk.config import GatewayConnectionConfig
    from app.services.openclaw.gateway_sdk.errors import GatewayError

    try:
        sdk_config = GatewayConnectionConfig(
            url=payload.gateway_url,
            token=payload.gateway_token,
            allow_insecure_tls=False,
            disable_device_pairing=False,
        )
        client = GatewayClient(sdk_config)

        # Verify connectivity first.
        healthy = await client.http.is_healthy(timeout=10)
        if not healthy:
            return ConfigureTrustedProxyResponse(
                ok=False, message="Gateway is not reachable.",
            )

        # Derive port from the gateway URL for allowedOrigins.
        from urllib.parse import urlparse

        parsed = urlparse(payload.gateway_url)
        gw_port = parsed.port or (443 if parsed.scheme == "https" else 18789)

        # Build the config patch as a nested object (JSON merge patch).
        trusted_proxies = [payload.npm_ip, "127.0.0.1", "::1"]
        allowed_origins = [
            f"https://{payload.gateway_fqdn}" if payload.gateway_fqdn else None,
            f"http://localhost:{gw_port}",
            f"http://127.0.0.1:{gw_port}",
        ]
        allowed_origins = [o for o in allowed_origins if o]

        patch: dict[str, object] = {
            "gateway": {
                "trustedProxies": trusted_proxies,
                "auth": {
                    "mode": "trusted-proxy",
                    "trustedProxy": {"userHeader": "x-forwarded-user"},
                },
                "controlUi": {
                    "allowedOrigins": allowed_origins,
                },
            },
        }

        await client.rpc.config_patch(patch)

        return ConfigureTrustedProxyResponse(
            ok=True,
            message="Trusted-proxy auth configured. The gateway will reload automatically.",
            config_applied=patch,
        )

    except GatewayError as exc:
        return ConfigureTrustedProxyResponse(
            ok=False, message=f"Failed to configure: {exc}",
        )
    except Exception as exc:
        return ConfigureTrustedProxyResponse(
            ok=False, message=f"Unexpected error: {exc}",
        )


@router.post("", response_model=GatewayCreateResponse)
async def create_gateway(
    payload: GatewayCreate,
    session: AsyncSession = SESSION_DEP,
    auth: AuthContext = AUTH_DEP,
    ctx: OrganizationContext = ORG_ADMIN_DEP,
) -> GatewayCreateResponse:
    """Create a gateway, default board, and a dedicated CleoClaw agent.

    IMPORTANT: CleoClaw creates its OWN discrete agent on OpenClaw.
    The user's "main" OpenClaw agent is NEVER touched, modified, or routed through.

    Steps:
    1. Validate connectivity via HTTP health check
    2. Create gateway DB record
    3. Attempt WebSocket RPC to verify pairing
       - If pairing required: return gateway with pairing_required=True
       - If connected: provision CleoClaw agent, create board + agent DB records
    4. Return gateway_id, board_id, agent_id, pairing_required
    """
    import logging
    import re

    from app.services.openclaw.gateway_sdk.config import GatewayConnectionConfig
    from app.services.openclaw.gateway_sdk.errors import (
        GatewayError,
        GatewayRPCError,
    )
    from app.services.openclaw.internal.session_keys import agent_session_key

    try:
        sdk_config = GatewayConnectionConfig(
            url=payload.url,
            token=payload.token,
            allow_insecure_tls=payload.allow_insecure_tls,
            disable_device_pairing=payload.disable_device_pairing,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid gateway configuration: {exc}",
        ) from exc

    from app.services.openclaw.gateway_sdk.client import GatewayClient

    client = GatewayClient(sdk_config)
    try:
        healthy = await client.http.is_healthy(timeout=10)
        if not healthy:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Gateway is not reachable. Check the address and token.",
            )
    except GatewayError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Cannot connect to gateway: {exc}",
        ) from exc

    # Create gateway DB record.
    data = payload.model_dump()
    gateway_id = uuid4()
    data["id"] = gateway_id
    data["organization_id"] = ctx.organization.id
    gateway = await crud.create(session, Gateway, **data)
    gateway_manager.register(gateway)

    # Verify RPC connectivity (proves WebSocket + auth works).
    pairing_required = False
    board_id = None
    agent_id = None

    try:
        await client.rpc.agents_list()
    except GatewayRPCError as exc:
        error_msg = str(exc).lower()
        if "pairing" in error_msg or "not paired" in error_msg or "device" in error_msg:
            pairing_required = True
        else:
            logging.getLogger(__name__).warning(
                "gateway.create.rpc_failed gateway=%s: %s", gateway_id, exc,
            )
    except GatewayError:
        pairing_required = True

    # Create board + REAL discrete agent on OpenClaw (never touches "main").
    from app.core.time import utcnow
    from app.models.boards import Board
    from app.services.openclaw.shared import GatewayAgentIdentity

    # Gateway-level CleoClaw agent record (board_id=NULL).
    # This uses mc-gateway-{uuid} as its OpenClaw agent ID — NOT "main".
    # Used by services for gateway-wide operations (admin, skills, heartbeat).
    gw_main_agent = Agent(
        name=f"{payload.name} Gateway Agent",
        status="active",
        last_seen_at=utcnow(),
        is_board_lead=False,
        board_id=None,
        gateway_id=gateway.id,
        openclaw_session_id=GatewayAgentIdentity.session_key(gateway),
    )
    session.add(gw_main_agent)

    # Derive the OpenClaw agent ID for the board lead.
    lead_agent_name = f"{payload.name} Board Lead"
    lead_oc_agent_id = re.sub(r"[^a-z0-9]+", "-", lead_agent_name.lower()).strip("-")
    lead_session_key = agent_session_key(lead_oc_agent_id)

    board = Board(
        name="General",
        slug=f"general-{str(gateway_id)[:8]}",
        description=f"Default workspace for {payload.name}",
        board_type="general",
        gateway_id=gateway.id,
        organization_id=ctx.organization.id,
        require_approval_for_done=False,
        max_agents=5,
    )
    session.add(board)
    await session.flush()
    board_id = board.id

    # Board lead agent — this is the primary CleoClaw agent for this gateway.
    # It maps 1:1 to a discrete OpenClaw agent (NOT the "main" agent).
    agent = Agent(
        name=lead_agent_name,
        status="provisioning",
        last_seen_at=utcnow(),
        is_board_lead=True,
        board_id=board.id,
        gateway_id=gateway.id,
        openclaw_session_id=lead_session_key,
    )
    session.add(agent)
    await session.flush()
    agent_id = agent.id

    await session.commit()

    # Provision the REAL agent on OpenClaw (background task).
    if not pairing_required:
        import asyncio

        async def _provision_lead() -> None:
            try:
                from app.services.openclaw.agent_provisioner import provision_agent

                result = await provision_agent(
                    client=client,
                    agent_name=lead_agent_name,
                    template_context={
                        "agent_name": lead_agent_name,
                        "agent_role": "Board Lead",
                        "board_name": "General",
                        "gateway_name": payload.name,
                        "user_name": auth.user.name if auth.user else "",
                        "org_name": ctx.organization.name if ctx.organization else "",
                        "base_url": str(settings.base_url),
                        "board_id": str(board_id),
                    },
                )
                logging.getLogger(__name__).info(
                    "gateway.create.agent_provisioned gateway=%s result=%s",
                    gateway_id,
                    result,
                )
            except Exception as exc:
                logging.getLogger(__name__).warning(
                    "gateway.create.agent_provision_failed gateway=%s: %s",
                    gateway_id,
                    exc,
                )

        asyncio.create_task(_provision_lead())

    return GatewayCreateResponse(
        gateway_id=gateway.id,
        board_id=board_id,
        agent_id=agent_id,
        pairing_required=pairing_required,
    )


@router.post("/{gateway_id}/complete-setup", response_model=GatewayCreateResponse)
async def complete_gateway_setup(
    gateway_id: UUID,
    session: AsyncSession = SESSION_DEP,
    auth: AuthContext = AUTH_DEP,
    ctx: OrganizationContext = ORG_ADMIN_DEP,
) -> GatewayCreateResponse:
    """Complete gateway setup after device pairing is approved.

    Called by frontend after user approves pairing on the gateway.
    Creates the MC gateway agent on OpenClaw, then the default board + agent in CCMC.
    """
    import logging
    import re

    from app.services.openclaw.gateway_sdk.config import GatewayConnectionConfig
    from app.services.openclaw.gateway_sdk.errors import (
        GatewayError,
        GatewayRPCError,
    )

    service = GatewayAdminLifecycleService(session)
    gateway = await service.require_gateway(
        gateway_id=gateway_id,
        organization_id=ctx.organization.id,
    )

    sdk_config = GatewayConnectionConfig(
        url=gateway.url,
        token=gateway.token,
        allow_insecure_tls=gateway.allow_insecure_tls,
        disable_device_pairing=gateway.disable_device_pairing,
    )

    from app.services.openclaw.gateway_sdk.client import GatewayClient

    client = GatewayClient(sdk_config)

    # Try RPC — if still not paired, return pairing_required
    try:
        await client.rpc.agents_list()
    except (GatewayRPCError, GatewayError) as exc:
        error_msg = str(exc).lower()
        if "pairing" in error_msg or "not paired" in error_msg or "device" in error_msg:
            return GatewayCreateResponse(
                gateway_id=gateway.id,
                pairing_required=True,
            )
        logging.getLogger(__name__).warning(
            "gateway.complete_setup.rpc_failed gateway=%s: %s", gateway_id, exc,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Cannot connect to gateway: {exc}",
        ) from exc

    # Check if board/agent already exist (idempotency).
    # If agents exist but are still "provisioning", trigger provisioning.
    from app.models.boards import Board

    existing_boards = await Board.objects.filter_by(gateway_id=gateway.id).all(session)
    if existing_boards:
        existing_agents = await Agent.objects.filter_by(
            gateway_id=gateway.id, is_board_lead=True,
        ).all(session)

        # Check if provisioning still needs to happen.
        needs_provision = any(a.status == "provisioning" for a in existing_agents)
        if needs_provision and existing_agents:
            lead = existing_agents[0]
            import asyncio

            async def _retry_provision() -> None:
                try:
                    from app.services.openclaw.agent_provisioner import provision_agent

                    result = await provision_agent(
                        client=client,
                        agent_name=lead.name,
                        template_context={
                            "agent_name": lead.name,
                            "agent_role": "Board Lead",
                            "board_name": existing_boards[0].name,
                            "gateway_name": gateway.name,
                            "base_url": str(settings.base_url),
                            "board_id": str(existing_boards[0].id),
                        },
                    )
                    logging.getLogger(__name__).info(
                        "gateway.complete_setup.retry_provision gateway=%s result=%s",
                        gateway_id,
                        result,
                    )
                    # Update agent status to active on success.
                    if result.get("created") in (True, "exists"):
                        from app.db.session import async_session_maker

                        async with async_session_maker() as db:
                            from sqlmodel import select

                            agent = (await db.exec(
                                select(Agent).where(Agent.id == lead.id)
                            )).first()
                            if agent and agent.status == "provisioning":
                                agent.status = "active"
                                db.add(agent)
                                await db.commit()
                except Exception as exc:
                    logging.getLogger(__name__).warning(
                        "gateway.complete_setup.retry_provision_failed gateway=%s: %s",
                        gateway_id,
                        exc,
                    )

            asyncio.create_task(_retry_provision())

        return GatewayCreateResponse(
            gateway_id=gateway.id,
            board_id=existing_boards[0].id if existing_boards else None,
            agent_id=existing_agents[0].id if existing_agents else None,
            pairing_required=False,
        )

    # Create board + REAL discrete agent on OpenClaw (never touches "main").
    from app.core.time import utcnow
    from app.services.openclaw.internal.session_keys import agent_session_key

    lead_agent_name = f"{gateway.name} Board Lead"
    lead_oc_agent_id = re.sub(r"[^a-z0-9]+", "-", lead_agent_name.lower()).strip("-")
    lead_session_key = agent_session_key(lead_oc_agent_id)

    board = Board(
        name="General",
        slug=f"general-{str(gateway_id)[:8]}",
        description=f"Default workspace for {gateway.name}",
        board_type="general",
        gateway_id=gateway.id,
        organization_id=ctx.organization.id,
        require_approval_for_done=False,
        max_agents=5,
    )
    session.add(board)
    await session.flush()

    agent = Agent(
        name=lead_agent_name,
        status="provisioning",
        last_seen_at=utcnow(),
        is_board_lead=True,
        board_id=board.id,
        gateway_id=gateway.id,
        openclaw_session_id=lead_session_key,
    )
    session.add(agent)
    await session.flush()

    await session.commit()

    # Provision the REAL agent on OpenClaw (background task).
    import asyncio

    async def _provision_lead() -> None:
        try:
            from app.services.openclaw.agent_provisioner import provision_agent

            result = await provision_agent(
                client=client,
                agent_name=lead_agent_name,
                template_context={
                    "agent_name": lead_agent_name,
                    "agent_role": "Board Lead",
                    "board_name": "General",
                    "gateway_name": gateway.name,
                    "base_url": str(settings.base_url),
                    "board_id": str(board.id),
                },
            )
            logging.getLogger(__name__).info(
                "gateway.complete_setup.agent_provisioned gateway=%s result=%s",
                gateway_id,
                result,
            )
        except Exception as exc:
            logging.getLogger(__name__).warning(
                "gateway.complete_setup.agent_provision_failed gateway=%s: %s",
                gateway_id,
                exc,
            )

    asyncio.create_task(_provision_lead())

    return GatewayCreateResponse(
        gateway_id=gateway.id,
        board_id=board.id,
        agent_id=agent.id,
        pairing_required=False,
    )


@router.get("/{gateway_id}", response_model=GatewayRead)
async def get_gateway(
    gateway_id: UUID,
    session: AsyncSession = SESSION_DEP,
    ctx: OrganizationContext = ORG_ADMIN_DEP,
) -> Gateway:
    """Return one gateway by id for the caller's organization."""
    service = GatewayAdminLifecycleService(session)
    gateway = await service.require_gateway(
        gateway_id=gateway_id,
        organization_id=ctx.organization.id,
    )
    return gateway


@router.patch("/{gateway_id}", response_model=GatewayRead)
async def update_gateway(
    gateway_id: UUID,
    payload: GatewayUpdate,
    session: AsyncSession = SESSION_DEP,
    auth: AuthContext = AUTH_DEP,
    ctx: OrganizationContext = ORG_ADMIN_DEP,
) -> Gateway:
    """Patch a gateway and re-validate connectivity via SDK."""
    service = GatewayAdminLifecycleService(session)
    gateway = await service.require_gateway(
        gateway_id=gateway_id,
        organization_id=ctx.organization.id,
    )
    updates = payload.model_dump(exclude_unset=True)
    connection_changed = any(
        k in updates for k in ("url", "token", "allow_insecure_tls", "disable_device_pairing")
    )
    await crud.patch(session, gateway, updates)

    if connection_changed:
        from app.services.openclaw.gateway_sdk.client import GatewayClient
        from app.services.openclaw.gateway_sdk.config import GatewayConnectionConfig
        from app.services.openclaw.gateway_sdk.errors import GatewayError

        try:
            sdk_config = GatewayConnectionConfig(
                url=gateway.url,
                token=gateway.token,
                allow_insecure_tls=gateway.allow_insecure_tls,
                disable_device_pairing=gateway.disable_device_pairing,
            )
            client = GatewayClient(sdk_config)
            healthy = await client.http.is_healthy(timeout=10)
            if not healthy:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Gateway is not reachable after update.",
                )
        except GatewayError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Cannot connect to gateway: {exc}",
            ) from exc

    gateway_manager.register(gateway)
    return gateway


@router.post("/{gateway_id}/templates/sync", response_model=GatewayTemplatesSyncResult)
async def sync_gateway_templates(
    gateway_id: UUID,
    sync_query: GatewayTemplateSyncQuery = SYNC_QUERY_DEP,
    session: AsyncSession = SESSION_DEP,
    auth: AuthContext = AUTH_DEP,
    ctx: OrganizationContext = ORG_ADMIN_DEP,
) -> GatewayTemplatesSyncResult:
    """Sync templates for a gateway and optionally rotate runtime settings."""
    service = GatewayAdminLifecycleService(session)
    gateway = await service.require_gateway(
        gateway_id=gateway_id,
        organization_id=ctx.organization.id,
    )
    return await service.sync_templates(gateway, query=sync_query, auth=auth)


REPAIR_QUERY = Query(default=False)


@router.get("/{gateway_id}/workspace/health", response_model=WorkspaceHealthCheckResult)
async def workspace_health_check(
    gateway_id: UUID,
    auto_repair: bool = REPAIR_QUERY,
    session: AsyncSession = SESSION_DEP,
    auth: AuthContext = AUTH_DEP,
    ctx: OrganizationContext = ORG_ADMIN_DEP,
) -> WorkspaceHealthCheckResult:
    """Check integrity of CCMC workspace files on the gateway agent.

    Verifies that CCMC-managed blocks in workspace files haven't been
    modified or removed by the agent.  When ``auto_repair=true``, restores
    CCMC blocks while preserving agent-authored content outside the blocks.
    """
    service = GatewayAdminLifecycleService(session)
    gateway = await service.require_gateway(
        gateway_id=gateway_id,
        organization_id=ctx.organization.id,
    )

    from app.services.openclaw.gateway_sdk.client import GatewayClient
    from app.services.openclaw.gateway_sdk.config import GatewayConnectionConfig
    from app.services.openclaw.workspace_templates import health_check

    sdk_config = GatewayConnectionConfig(
        url=gateway.url,
        token=gateway.token,
        allow_insecure_tls=gateway.allow_insecure_tls,
        disable_device_pairing=gateway.disable_device_pairing,
    )
    client = GatewayClient(sdk_config)

    # Find the board lead agent and derive its OpenClaw agent ID.
    from app.models.boards import Board
    from app.services.openclaw.internal.agent_key import slugify

    boards = await Board.objects.filter_by(gateway_id=gateway.id).all(session)
    board = boards[0] if boards else None

    # Get the board lead agent to determine the correct OpenClaw agent ID.
    lead_agents = await Agent.objects.filter_by(
        gateway_id=gateway.id, is_board_lead=True,
    ).all(session)
    lead_agent = lead_agents[0] if lead_agents else None
    oc_agent_id = slugify(lead_agent.name) if lead_agent else slugify(f"{gateway.name} Board Lead")

    result = await health_check(
        rpc_client=client.rpc,
        agent_id=oc_agent_id,
        agent_name=lead_agent.name if lead_agent else f"{gateway.name} Board Lead",
        auto_repair=auto_repair,
        board_name=board.name if board else "General",
        gateway_name=gateway.name,
        base_url=str(settings.base_url),
        board_id=str(board.id) if board else "",
    )

    repaired_count = sum(1 for info in result.values() if info.get("repaired"))
    healthy = all(
        info.get("status") in ("ok", "skipped") or info.get("repaired")
        for info in result.values()
    )

    return WorkspaceHealthCheckResult(
        gateway_id=gateway.id,
        agent_id=oc_agent_id,
        files=result,
        healthy=healthy,
        repaired=repaired_count,
    )


@router.delete("/{gateway_id}", response_model=OkResponse)
async def delete_gateway(
    gateway_id: UUID,
    session: AsyncSession = SESSION_DEP,
    ctx: OrganizationContext = ORG_ADMIN_DEP,
) -> OkResponse:
    """Delete a gateway in the caller's organization."""
    service = GatewayAdminLifecycleService(session)
    gateway = await service.require_gateway(
        gateway_id=gateway_id,
        organization_id=ctx.organization.id,
    )
    # Delete all agents linked to this gateway from CCMC and OpenClaw.
    import logging

    all_agents = await Agent.objects.filter_by(gateway_id=gateway.id).all(session)
    sdk_client = gateway_manager.get(gateway.id)
    for agent in all_agents:
        # Try to delete from OpenClaw (best effort — don't block CCMC deletion).
        if sdk_client and agent.openclaw_session_id:
            try:
                # Derive the OpenClaw agent ID from the session key.
                from app.services.openclaw.shared import GatewayAgentIdentity

                oc_agent_id = GatewayAgentIdentity.openclaw_agent_id(gateway)
                await sdk_client.rpc.agents_delete(oc_agent_id)
            except Exception as exc:
                logging.getLogger(__name__).warning(
                    "gateway.delete.agent_cleanup_failed agent=%s: %s", agent.id, exc
                )
        await service.clear_agent_foreign_keys(agent_id=agent.id)
        await session.delete(agent)

    # Unlink boards from this gateway (don't delete boards, just unlink).
    from app.models.boards import Board

    boards = await Board.objects.filter_by(gateway_id=gateway.id).all(session)
    for board in boards:
        board.gateway_id = None
        session.add(board)

    # Clean up installed skills.
    installed_skills = await GatewayInstalledSkill.objects.filter_by(
        gateway_id=gateway.id,
    ).all(session)
    for installed_skill in installed_skills:
        await session.delete(installed_skill)

    await gateway_manager.remove(gateway.id)
    await session.delete(gateway)
    await session.commit()
    return OkResponse()
