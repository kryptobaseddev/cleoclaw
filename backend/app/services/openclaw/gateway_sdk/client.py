"""Unified GatewayClient facade composing all three transports.

Usage::

    from app.services.openclaw.gateway_sdk import GatewayConnectionConfig
    from app.services.openclaw.gateway_sdk.client import GatewayClient

    config = GatewayConnectionConfig(url="http://10.0.10.21:18789", token="...")
    client = GatewayClient(config)

    # HTTP transport
    response = await client.http.chat_completions_text("system prompt", "user msg")
    health = await client.http.health()

    # WebSocket RPC transport
    agents = await client.rpc.agents_list()
    config_val = await client.rpc.config_get()
    cron_jobs = await client.rpc.cron_list()

    # WebSocket event transport
    client.events.on("exec.approval.requested", my_handler)
    await client.events.start()
"""

from __future__ import annotations

from app.services.openclaw.gateway_sdk.config import GatewayConnectionConfig
from app.services.openclaw.gateway_sdk.event_client import GatewayEventClient
from app.services.openclaw.gateway_sdk.http_client import GatewayHTTPClient
from app.services.openclaw.gateway_sdk.rpc_client import GatewayRPCClient


class GatewayClient:
    """Single entry point for all gateway communication.

    Composes the three transport clients and shares a single
    ``GatewayConnectionConfig`` across them.  Callers access transports
    via ``client.http``, ``client.rpc``, and ``client.events``.
    """

    def __init__(self, config: GatewayConnectionConfig) -> None:
        self._config = config
        self.http = GatewayHTTPClient(config)
        self.rpc = GatewayRPCClient(config)
        self.events = GatewayEventClient(config)

    @property
    def config(self) -> GatewayConnectionConfig:
        return self._config

    async def health_check(self) -> bool:
        """Quick liveness check via HTTP /health."""
        return await self.http.is_healthy()

    async def close(self) -> None:
        """Shut down the event subscriber if running."""
        await self.events.stop()
