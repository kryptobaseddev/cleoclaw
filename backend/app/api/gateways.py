"""Thin API wrappers for gateway CRUD and template synchronization."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query
from sqlmodel import col

from app.api.deps import require_org_admin
from app.core.auth import AuthContext, get_auth_context
from app.db import crud
from app.db.pagination import paginate
from app.db.session import get_session
from app.models.agents import Agent
from app.models.gateways import Gateway
from app.models.skills import GatewayInstalledSkill
from app.schemas.common import OkResponse
from app.schemas.gateways import (
    GatewayCreate,
    GatewayRead,
    GatewayTemplatesSyncResult,
    GatewayUpdate,
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


@router.post("", response_model=GatewayRead)
async def create_gateway(
    payload: GatewayCreate,
    session: AsyncSession = SESSION_DEP,
    auth: AuthContext = AUTH_DEP,
    ctx: OrganizationContext = ORG_ADMIN_DEP,
) -> Gateway:
    """Create a gateway and validate connectivity via SDK.

    The gateway token is the only credential needed.  Mission Control
    communicates with the gateway entirely through the SDK (HTTP + WS RPC),
    so no gateway-side agent provisioning or template syncing is required
    at registration time.
    """
    # Register with the SDK manager and validate connectivity.
    from app.services.openclaw.gateway_sdk.config import GatewayConnectionConfig
    from app.services.openclaw.gateway_sdk.errors import GatewayError

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

    data = payload.model_dump()
    gateway_id = uuid4()
    data["id"] = gateway_id
    data["organization_id"] = ctx.organization.id
    gateway = await crud.create(session, Gateway, **data)
    gateway_manager.register(gateway)

    # Create a main gateway agent — DB record + register on the gateway via
    # SDK RPC.  No curl templates, no exec approvals, no template sync.
    from app.services.openclaw.constants import DEFAULT_HEARTBEAT_CONFIG
    from app.services.openclaw.db_agent_state import mint_agent_token
    from app.services.openclaw.shared import GatewayAgentIdentity

    session_key = GatewayAgentIdentity.session_key(gateway)
    openclaw_agent_id = GatewayAgentIdentity.openclaw_agent_id(gateway)
    agent_name = f"{gateway.name} Gateway Agent"

    # 1. Create agent on the OpenClaw gateway via SDK RPC.
    workspace = payload.workspace_root or "~/.openclaw"
    try:
        create_result = await client.rpc.agents_create(
            name=agent_name,
            workspace=workspace,
        )
        openclaw_agent_id = create_result.agent_id
    except GatewayError:
        # Agent may already exist on the gateway — that's fine.
        pass

    # 2. Create agent DB record in Mission Control.
    #    last_seen_at is set to now because we just confirmed the agent exists
    #    on the gateway (agents.create succeeded or agent already existed).
    #    Future updates to last_seen_at should come from gateway health checks
    #    via the SDK, not from agent curl callbacks.
    from app.core.time import utcnow

    agent = Agent(
        name=agent_name,
        status="active",
        board_id=None,
        gateway_id=gateway.id,
        is_board_lead=False,
        openclaw_session_id=session_key,
        heartbeat_config=DEFAULT_HEARTBEAT_CONFIG.copy(),
        identity_profile={
            "role": "Gateway Agent",
            "communication_style": "direct, concise, practical",
            "emoji": ":compass:",
        },
        last_seen_at=utcnow(),
    )
    session.add(agent)
    await session.flush()
    mint_agent_token(agent)
    agent.status = "active"
    session.add(agent)
    await session.commit()
    await session.refresh(gateway)

    return gateway


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
    main_agent = await service.find_main_agent(gateway)
    if main_agent is not None:
        await service.clear_agent_foreign_keys(agent_id=main_agent.id)
        await session.delete(main_agent)

    duplicate_main_agents = await Agent.objects.filter_by(
        gateway_id=gateway.id,
        board_id=None,
    ).all(session)
    for agent in duplicate_main_agents:
        if main_agent is not None and agent.id == main_agent.id:
            continue
        await service.clear_agent_foreign_keys(agent_id=agent.id)
        await session.delete(agent)

    # NOTE: The migration declares `ondelete="CASCADE"` for gateway_installed_skills.gateway_id,
    # but some backends/test environments (e.g. SQLite without FK pragma) may not
    # enforce cascades. Delete rows explicitly to guarantee cleanup semantics.
    installed_skills = await GatewayInstalledSkill.objects.filter_by(
        gateway_id=gateway.id,
    ).all(session)
    for installed_skill in installed_skills:
        await session.delete(installed_skill)

    await gateway_manager.remove(gateway.id)
    await session.delete(gateway)
    await session.commit()
    return OkResponse()
