"""WebSocket RPC client for the CCMC Gateway Client SDK.

Wraps the connect-per-call WebSocket RPC protocol used by the OpenClaw gateway
and exposes typed, domain-organized methods that return Pydantic models rather
than raw dicts.  The connection/auth flow (protocol v3, device auth, control-UI
auth, connect-challenge handling) is preserved exactly from ``gateway_rpc.py``.
"""

from __future__ import annotations

import asyncio
import json
from time import perf_counter, time
from typing import Any
from urllib.parse import urlencode, urlparse, urlunparse
from uuid import uuid4

import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException

from app.core.logging import TRACE_LEVEL, get_logger
from app.services.openclaw.device_identity import (
    build_device_auth_payload,
    load_or_create_device_identity,
    public_key_raw_base64url_from_pem,
    sign_device_payload,
)
from app.services.openclaw.gateway_sdk.config import (
    CONTROL_UI_CLIENT_ID,
    CONTROL_UI_CLIENT_MODE,
    DEFAULT_CLIENT_ID,
    DEFAULT_CLIENT_MODE,
    GATEWAY_OPERATOR_SCOPES,
    PROTOCOL_VERSION,
    GatewayConnectionConfig,
)
from app.services.openclaw.gateway_sdk.errors import (
    GatewayConnectionError,
    GatewayRPCError,
    GatewayServiceRestartError,
    GatewayTimeoutError,
)
from app.services.openclaw.gateway_sdk.types import (
    AgentCreateResponse,
    AgentDeleteResponse,
    AgentFileGetResponse,
    AgentFilesListResponse,
    AgentFileSetResponse,
    AgentListResponse,
    AgentUpdateResponse,
    ChatHistoryResponse,
    ChatSendResponse,
    ConfigGetResponse,
    ConfigPatchResponse,
    ConfigSetResponse,
    CronJob,
    CronJobListResponse,
    CronRemoveResponse,
    CronRunsResponse,
    CronRunTriggerResponse,
    CronStatusResponse,
    DevicePairApproveResponse,
    DevicePairListResponse,
    DevicePairRejectResponse,
    DevicePairRemoveResponse,
    ExecApprovalResolveResponse,
    ExecApprovalsGetResponse,
    ExecApprovalsSetResponse,
    HealthResponse,
    ModelListResponse,
    NodeDescribeResponse,
    NodeListResponse,
    NodePairApproveResponse,
    NodePairListResponse,
    SessionDeleteResponse,
    SessionListResponse,
    SessionPatchResponse,
    SkillInstallResponse,
    SkillStatusResponse,
    SkillUpdateResponse,
    StatusResponse,
    UsageCostResponse,
    UsageStatusResponse,
)

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Internal protocol helpers (mirrored from gateway_rpc.py)
# ---------------------------------------------------------------------------


def _build_gateway_ws_url(config: GatewayConnectionConfig) -> str:
    """Return the WebSocket URL with optional token query param."""
    base_url = (config.ws_url or "").strip()
    if not base_url:
        msg = "Gateway WebSocket URL is not configured."
        raise GatewayConnectionError(msg, transport="rpc")
    token = config.token
    if not token:
        return base_url
    parsed = urlparse(base_url)
    query = urlencode({"token": token})
    return str(urlunparse(parsed._replace(query=query)))


def _redacted_url_for_log(raw_url: str) -> str:
    parsed = urlparse(raw_url)
    return str(urlunparse(parsed._replace(query="", fragment="")))


def _build_device_connect_payload(
    *,
    client_id: str,
    client_mode: str,
    role: str,
    scopes: list[str],
    auth_token: str | None,
    connect_nonce: str | None,
) -> dict[str, Any]:
    identity = load_or_create_device_identity()
    signed_at_ms = int(time() * 1000)
    payload = build_device_auth_payload(
        device_id=identity.device_id,
        client_id=client_id,
        client_mode=client_mode,
        role=role,
        scopes=scopes,
        signed_at_ms=signed_at_ms,
        token=auth_token,
        nonce=connect_nonce,
    )
    device_payload: dict[str, Any] = {
        "id": identity.device_id,
        "publicKey": public_key_raw_base64url_from_pem(identity.public_key_pem),
        "signature": sign_device_payload(identity.private_key_pem, payload),
        "signedAt": signed_at_ms,
    }
    if connect_nonce:
        device_payload["nonce"] = connect_nonce
    return device_payload


def _build_connect_params(
    config: GatewayConnectionConfig,
    *,
    connect_nonce: str | None = None,
) -> dict[str, Any]:
    role = "operator"
    scopes = list(GATEWAY_OPERATOR_SCOPES)
    use_control_ui = config.connect_mode == "control_ui"
    params: dict[str, Any] = {
        "minProtocol": PROTOCOL_VERSION,
        "maxProtocol": PROTOCOL_VERSION,
        "role": role,
        "scopes": scopes,
        "client": {
            "id": CONTROL_UI_CLIENT_ID if use_control_ui else DEFAULT_CLIENT_ID,
            "version": "1.0.0",
            "platform": "python",
            "mode": CONTROL_UI_CLIENT_MODE if use_control_ui else DEFAULT_CLIENT_MODE,
        },
    }
    if not use_control_ui:
        params["device"] = _build_device_connect_payload(
            client_id=DEFAULT_CLIENT_ID,
            client_mode=DEFAULT_CLIENT_MODE,
            role=role,
            scopes=scopes,
            auth_token=config.token,
            connect_nonce=connect_nonce,
        )
    auth: dict[str, Any] = {}
    if config.token:
        auth["token"] = config.token
    if not use_control_ui:
        identity = load_or_create_device_identity()
        if identity.device_token:
            auth["deviceToken"] = identity.device_token
    if auth:
        params["auth"] = auth
    return params


async def _recv_first_message_or_none(
    ws: websockets.ClientConnection,
) -> str | bytes | None:
    try:
        return await asyncio.wait_for(ws.recv(), timeout=2)
    except TimeoutError:
        return None


async def _await_response(
    ws: websockets.ClientConnection,
    request_id: str,
) -> object:
    while True:
        raw = await ws.recv()
        data = json.loads(raw)
        logger.log(
            TRACE_LEVEL,
            "gateway.sdk.rpc.recv request_id=%s type=%s",
            request_id,
            data.get("type"),
        )

        if data.get("type") == "res" and data.get("id") == request_id:
            ok = data.get("ok")
            if ok is not None and not ok:
                error_obj = data.get("error", {})
                error_msg = error_obj.get("message", "Gateway RPC error") if isinstance(error_obj, dict) else "Gateway RPC error"
                error_code = error_obj.get("code") if isinstance(error_obj, dict) else None
                raise GatewayRPCError(error_msg, error_code=error_code)
            return data.get("payload")

        if data.get("id") == request_id:
            if data.get("error"):
                error_obj = data["error"]
                error_msg = error_obj.get("message", "Gateway RPC error") if isinstance(error_obj, dict) else str(error_obj)
                error_code = error_obj.get("code") if isinstance(error_obj, dict) else None
                raise GatewayRPCError(error_msg, error_code=error_code)
            return data.get("result")


async def _send_request(
    ws: websockets.ClientConnection,
    method: str,
    params: dict[str, Any] | None,
) -> object:
    request_id = str(uuid4())
    message = {
        "type": "req",
        "id": request_id,
        "method": method,
        "params": params or {},
    }
    logger.log(
        TRACE_LEVEL,
        "gateway.sdk.rpc.send method=%s request_id=%s params_keys=%s",
        method,
        request_id,
        sorted((params or {}).keys()),
    )
    await ws.send(json.dumps(message))
    return await _await_response(ws, request_id)


async def _ensure_connected(
    ws: websockets.ClientConnection,
    first_message: str | bytes | None,
    config: GatewayConnectionConfig,
) -> object:
    connect_nonce: str | None = None
    if first_message:
        if isinstance(first_message, bytes):
            first_message = first_message.decode("utf-8")
        data = json.loads(first_message)
        if data.get("type") == "event" and data.get("event") == "connect.challenge":
            payload = data.get("payload")
            if isinstance(payload, dict):
                nonce = payload.get("nonce")
                if isinstance(nonce, str) and nonce.strip():
                    connect_nonce = nonce.strip()
        else:
            logger.warning(
                "gateway.sdk.rpc.connect.unexpected_first_message type=%s event=%s",
                data.get("type"),
                data.get("event"),
            )
    connect_id = str(uuid4())
    response = {
        "type": "req",
        "id": connect_id,
        "method": "connect",
        "params": _build_connect_params(config, connect_nonce=connect_nonce),
    }
    await ws.send(json.dumps(response))
    result = await _await_response(ws, connect_id)
    # Save device token returned by gateway after pairing approval.
    if isinstance(result, dict):
        auth_data = result.get("auth")
        if isinstance(auth_data, dict):
            device_token = auth_data.get("deviceToken")
            if isinstance(device_token, str) and device_token.strip():
                from app.services.openclaw.device_identity import save_device_token

                save_device_token(device_token.strip())
    return result


async def _call_once(
    method: str,
    params: dict[str, Any] | None,
    *,
    config: GatewayConnectionConfig,
    gateway_url: str,
) -> object:
    origin = config.build_control_ui_origin() if config.disable_device_pairing else None
    ssl_context = config.build_ssl_context()
    connect_kwargs: dict[str, Any] = {"ping_interval": None}
    if origin is not None:
        connect_kwargs["origin"] = origin
    if ssl_context is not None:
        connect_kwargs["ssl"] = ssl_context
    async with websockets.connect(gateway_url, **connect_kwargs) as ws:
        first_message = await _recv_first_message_or_none(ws)
        await _ensure_connected(ws, first_message, config)
        return await _send_request(ws, method, params)


# ---------------------------------------------------------------------------
# Public client class
# ---------------------------------------------------------------------------


class GatewayRPCClient:
    """Typed WebSocket RPC client for the OpenClaw gateway.

    Opens a new WebSocket connection per call (connect-per-call, not persistent),
    authenticates via the gateway connect protocol (v3), sends the request, and
    returns a typed Pydantic response model.

    Usage::

        config = GatewayConnectionConfig(url="ws://localhost:4000", token="...")
        client = GatewayRPCClient(config)
        agents = await client.agents_list()
    """

    def __init__(self, config: GatewayConnectionConfig) -> None:
        self._config = config

    # ------------------------------------------------------------------
    # Core transport
    # ------------------------------------------------------------------

    async def _call(self, method: str, params: dict[str, Any] | None = None) -> object:
        """Open a connection, authenticate, call *method*, return raw payload.

        Maps transport and protocol errors to the typed GatewayError hierarchy.
        """
        config = self._config
        gateway_url = _build_gateway_ws_url(config)
        started_at = perf_counter()
        logger.debug(
            (
                "gateway.sdk.rpc.call.start method=%s gateway_url=%s "
                "allow_insecure_tls=%s disable_device_pairing=%s"
            ),
            method,
            _redacted_url_for_log(gateway_url),
            config.allow_insecure_tls,
            config.disable_device_pairing,
        )
        try:
            payload = await _call_once(method, params, config=config, gateway_url=gateway_url)
            logger.debug(
                "gateway.sdk.rpc.call.success method=%s duration_ms=%s",
                method,
                int((perf_counter() - started_at) * 1000),
            )
            return payload
        except GatewayRPCError:
            logger.warning(
                "gateway.sdk.rpc.call.rpc_error method=%s duration_ms=%s",
                method,
                int((perf_counter() - started_at) * 1000),
            )
            raise
        except asyncio.TimeoutError as exc:
            logger.error(
                "gateway.sdk.rpc.call.timeout method=%s duration_ms=%s",
                method,
                int((perf_counter() - started_at) * 1000),
            )
            raise GatewayTimeoutError(
                f"Timed out waiting for gateway response to {method!r}",
                method=method,
            ) from exc
        except ConnectionClosed as exc:
            if exc.rcvd and exc.rcvd.code == 1012:
                logger.info(
                    "gateway.sdk.rpc.call.service_restart method=%s duration_ms=%s",
                    method,
                    int((perf_counter() - started_at) * 1000),
                )
                raise GatewayServiceRestartError(
                    "Gateway restarting after config change",
                    method=method,
                ) from exc
            logger.error(
                "gateway.sdk.rpc.call.transport_error method=%s duration_ms=%s error_type=%s",
                method,
                int((perf_counter() - started_at) * 1000),
                exc.__class__.__name__,
            )
            raise GatewayConnectionError(
                str(exc),
                method=method,
                transport="rpc",
            ) from exc
        except (ConnectionError, OSError, ValueError, WebSocketException) as exc:
            logger.error(
                "gateway.sdk.rpc.call.transport_error method=%s duration_ms=%s error_type=%s",
                method,
                int((perf_counter() - started_at) * 1000),
                exc.__class__.__name__,
            )
            raise GatewayConnectionError(
                str(exc),
                method=method,
                transport="rpc",
            ) from exc

    # ------------------------------------------------------------------
    # Agents
    # ------------------------------------------------------------------

    async def agents_list(self) -> AgentListResponse:
        """List all agents on the gateway."""
        raw = await self._call("agents.list")
        return AgentListResponse.model_validate(raw)

    async def agents_create(
        self,
        name: str,
        workspace: str,
        *,
        emoji: str | None = None,
        avatar: str | None = None,
    ) -> AgentCreateResponse:
        """Create a new agent on the gateway.

        Args:
            name: Agent display name (agent ID is derived from this).
            workspace: Workspace path on the gateway (e.g. ~/.openclaw).
            emoji: Optional emoji for the agent.
            avatar: Optional avatar URL.
        """
        params: dict[str, Any] = {"name": name, "workspace": workspace}
        if emoji is not None:
            params["emoji"] = emoji
        if avatar is not None:
            params["avatar"] = avatar
        try:
            raw = await self._call("agents.create", params)
            return AgentCreateResponse.model_validate(raw)
        except GatewayServiceRestartError:
            # Agent was likely created before the restart. Wait and verify.
            logger.info("gateway.sdk.rpc.agents_create.restart_recovery name=%s", name)
            await asyncio.sleep(5)
            agents = await self.agents_list()
            for agent in agents.agents:
                if agent.name == name:
                    return AgentCreateResponse(
                        ok=True, agentId=agent.id, name=agent.name or name, workspace=workspace,
                    )
            raise  # Agent not found after restart — re-raise

    async def agents_update(self, agent_id: str, config: dict[str, Any]) -> AgentUpdateResponse:
        """Update an existing agent's configuration."""
        raw = await self._call("agents.update", {"agentId": agent_id, "config": config})
        return AgentUpdateResponse.model_validate(raw)

    async def agents_delete(self, agent_id: str) -> AgentDeleteResponse:
        """Delete an agent by ID."""
        try:
            raw = await self._call("agents.delete", {"agentId": agent_id})
            return AgentDeleteResponse.model_validate(raw)
        except GatewayServiceRestartError:
            logger.info("gateway.sdk.rpc.agents_delete.restart_recovery agent_id=%s", agent_id)
            await asyncio.sleep(5)
            agents = await self.agents_list()
            for agent in agents.agents:
                if agent.id == agent_id:
                    raise  # Agent still exists — deletion failed
            return AgentDeleteResponse(ok=True, agentId=agent_id, removedBindings=0)

    async def agents_files_list(self, agent_id: str) -> AgentFilesListResponse:
        """List files for an agent workspace."""
        raw = await self._call("agents.files.list", {"agentId": agent_id})
        return AgentFilesListResponse.model_validate(raw)

    async def agents_files_get(self, agent_id: str, name: str) -> AgentFileGetResponse:
        """Get a specific file from an agent workspace."""
        raw = await self._call("agents.files.get", {"agentId": agent_id, "name": name})
        return AgentFileGetResponse.model_validate(raw)

    async def agents_files_set(
        self, agent_id: str, name: str, content: str
    ) -> AgentFileSetResponse:
        """Write or update a file in an agent workspace."""
        raw = await self._call(
            "agents.files.set", {"agentId": agent_id, "name": name, "content": content}
        )
        return AgentFileSetResponse.model_validate(raw)

    # ------------------------------------------------------------------
    # Config
    # ------------------------------------------------------------------

    async def config_get(self) -> ConfigGetResponse:
        """Fetch the current gateway configuration."""
        raw = await self._call("config.get")
        return ConfigGetResponse.model_validate(raw)

    async def config_set(self, path: str, value: Any) -> ConfigSetResponse:
        """Set a single configuration value by dot-path."""
        raw = await self._call("config.set", {"path": path, "value": value})
        return ConfigSetResponse.model_validate(raw)

    async def config_patch(self, patch: dict[str, Any]) -> ConfigPatchResponse:
        """Apply a partial patch to the gateway configuration.

        Performs a read-modify-write: fetches the current config hash via
        ``config.get``, then sends ``config.patch`` with ``baseHash`` and
        the patch as a JSON string in ``raw``.  Config changes that affect
        the gateway (auth, bind, port) trigger an automatic restart, so a
        1012 close or timeout is treated as success.
        """
        import json as _json

        # Get current config hash for optimistic concurrency.
        current = await self._call("config.get")
        base_hash = current.get("hash") if isinstance(current, dict) else None

        params: dict[str, Any] = {"raw": _json.dumps(patch)}
        if base_hash:
            params["baseHash"] = base_hash

        try:
            raw = await self._call("config.patch", params)
            return ConfigPatchResponse.model_validate(raw)
        except (GatewayServiceRestartError, GatewayTimeoutError):
            # Config was applied — gateway restarted before responding.
            logger.info("gateway.sdk.rpc.config_patch.restart_after_apply")
            return ConfigPatchResponse.model_validate({"applied": True})

    # ------------------------------------------------------------------
    # Cron
    # ------------------------------------------------------------------

    async def cron_list(self) -> CronJobListResponse:
        """List all cron jobs."""
        raw = await self._call("cron.list")
        return CronJobListResponse.model_validate(raw)

    async def cron_add(self, job: dict[str, Any]) -> CronJob:
        """Add a new cron job."""
        raw = await self._call("cron.add", {"job": job})
        return CronJob.model_validate(raw)

    async def cron_update(self, job_id: str, updates: dict[str, Any]) -> CronJob:
        """Update an existing cron job."""
        raw = await self._call("cron.update", {"id": job_id, "updates": updates})
        return CronJob.model_validate(raw)

    async def cron_remove(self, job_id: str) -> CronRemoveResponse:
        """Remove a cron job by ID."""
        raw = await self._call("cron.remove", {"id": job_id})
        return CronRemoveResponse.model_validate(raw)

    async def cron_run(self, job_id: str) -> CronRunTriggerResponse:
        """Trigger an immediate run of a cron job."""
        raw = await self._call("cron.run", {"id": job_id})
        return CronRunTriggerResponse.model_validate(raw)

    async def cron_runs(self, job_id: str | None = None) -> CronRunsResponse:
        """Fetch cron run history, optionally filtered by job ID."""
        params: dict[str, Any] = {}
        if job_id is not None:
            params["id"] = job_id
        raw = await self._call("cron.runs", params or None)
        return CronRunsResponse.model_validate(raw)

    async def cron_status(self) -> CronStatusResponse:
        """Get overall cron scheduler status."""
        raw = await self._call("cron.status")
        return CronStatusResponse.model_validate(raw)

    # ------------------------------------------------------------------
    # Exec approvals
    # ------------------------------------------------------------------

    async def exec_approvals_get(self) -> ExecApprovalsGetResponse:
        """Fetch the current exec approvals file."""
        raw = await self._call("exec.approvals.get")
        return ExecApprovalsGetResponse.model_validate(raw)

    async def exec_approvals_set(self, file: dict[str, Any]) -> ExecApprovalsSetResponse:
        """Write the exec approvals file."""
        raw = await self._call("exec.approvals.set", {"file": file})
        return ExecApprovalsSetResponse.model_validate(raw)

    async def exec_approval_resolve(
        self, id: str, decision: str
    ) -> ExecApprovalResolveResponse:
        """Resolve a pending exec approval request."""
        raw = await self._call("exec.approval.resolve", {"id": id, "decision": decision})
        return ExecApprovalResolveResponse.model_validate(raw)

    # ------------------------------------------------------------------
    # Skills
    # ------------------------------------------------------------------

    async def skills_status(self) -> SkillStatusResponse:
        """Get skill installation status for the active agent."""
        raw = await self._call("skills.status")
        return SkillStatusResponse.model_validate(raw)

    async def skills_install(self, skill_id: str) -> SkillInstallResponse:
        """Install a skill by ID."""
        raw = await self._call("skills.install", {"skillId": skill_id})
        return SkillInstallResponse.model_validate(raw)

    async def skills_update(self, skill_key: str, config: dict[str, Any]) -> SkillUpdateResponse:
        """Update a skill's configuration."""
        raw = await self._call("skills.update", {"skillKey": skill_key, "config": config})
        return SkillUpdateResponse.model_validate(raw)

    # ------------------------------------------------------------------
    # Models
    # ------------------------------------------------------------------

    async def models_list(self) -> ModelListResponse:
        """List available AI models."""
        raw = await self._call("models.list")
        return ModelListResponse.model_validate(raw)

    # ------------------------------------------------------------------
    # Usage
    # ------------------------------------------------------------------

    async def usage_status(self) -> UsageStatusResponse:
        """Get provider usage status."""
        raw = await self._call("usage.status")
        return UsageStatusResponse.model_validate(raw)

    async def usage_cost(self) -> UsageCostResponse:
        """Get cost breakdown."""
        raw = await self._call("usage.cost")
        return UsageCostResponse.model_validate(raw)

    # ------------------------------------------------------------------
    # Nodes
    # ------------------------------------------------------------------

    async def node_list(self) -> NodeListResponse:
        """List all connected nodes."""
        raw = await self._call("node.list")
        return NodeListResponse.model_validate(raw)

    async def node_describe(self, node_id: str) -> NodeDescribeResponse:
        """Describe a specific node."""
        raw = await self._call("node.describe", {"nodeId": node_id})
        return NodeDescribeResponse.model_validate(raw)

    async def node_pair_list(self) -> NodePairListResponse:
        """List pending and paired nodes."""
        raw = await self._call("node.pair.list")
        return NodePairListResponse.model_validate(raw)

    async def node_pair_approve(self, request_id: str) -> NodePairApproveResponse:
        """Approve a node pairing request."""
        raw = await self._call("node.pair.approve", {"requestId": request_id})
        return NodePairApproveResponse.model_validate(raw)

    # ------------------------------------------------------------------
    # Device pairing
    # ------------------------------------------------------------------

    async def device_pair_list(self) -> DevicePairListResponse:
        """List pending and paired devices."""
        raw = await self._call("device.pair.list")
        return DevicePairListResponse.model_validate(raw)

    async def device_pair_approve(self, request_id: str) -> DevicePairApproveResponse:
        """Approve a device pairing request."""
        raw = await self._call("device.pair.approve", {"requestId": request_id})
        return DevicePairApproveResponse.model_validate(raw)

    async def device_pair_reject(self, request_id: str) -> DevicePairRejectResponse:
        """Reject a device pairing request."""
        raw = await self._call("device.pair.reject", {"requestId": request_id})
        return DevicePairRejectResponse.model_validate(raw)

    async def device_pair_remove(self, device_id: str) -> DevicePairRemoveResponse:
        """Remove a paired device."""
        raw = await self._call("device.pair.remove", {"deviceId": device_id})
        return DevicePairRemoveResponse.model_validate(raw)

    # ------------------------------------------------------------------
    # Sessions
    # ------------------------------------------------------------------

    async def sessions_list(self) -> SessionListResponse:
        """List all sessions."""
        raw = await self._call("sessions.list")
        return SessionListResponse.model_validate(raw)

    async def session_patch(self, key: str, label: str | None = None) -> SessionPatchResponse:
        """Ensure a session exists and optionally update its label."""
        params: dict[str, Any] = {"key": key}
        if label is not None:
            params["label"] = label
        raw = await self._call("sessions.patch", params)
        return SessionPatchResponse.model_validate(raw)

    async def session_delete(self, key: str) -> SessionDeleteResponse:
        """Delete a session by key."""
        raw = await self._call("sessions.delete", {"key": key})
        return SessionDeleteResponse.model_validate(raw)

    # ------------------------------------------------------------------
    # Chat
    # ------------------------------------------------------------------

    async def chat_send(
        self,
        session_key: str,
        message: str,
        deliver: bool = False,
    ) -> ChatSendResponse:
        """Send a chat message to a session."""
        params: dict[str, Any] = {
            "sessionKey": session_key,
            "message": message,
            "deliver": deliver,
            "idempotencyKey": str(uuid4()),
        }
        raw = await self._call("chat.send", params)
        return ChatSendResponse.model_validate(raw)

    async def chat_history(
        self,
        session_key: str,
        limit: int | None = None,
    ) -> ChatHistoryResponse:
        """Fetch chat history for a session."""
        params: dict[str, Any] = {"sessionKey": session_key}
        if limit is not None:
            params["limit"] = limit
        raw = await self._call("chat.history", params)
        return ChatHistoryResponse.model_validate(raw)

    # ------------------------------------------------------------------
    # Health / Status
    # ------------------------------------------------------------------

    async def health(self) -> HealthResponse:
        """Check gateway health."""
        raw = await self._call("health")
        return HealthResponse.model_validate(raw)

    async def status(self) -> StatusResponse:
        """Get gateway status summary."""
        raw = await self._call("status")
        return StatusResponse.model_validate(raw)
