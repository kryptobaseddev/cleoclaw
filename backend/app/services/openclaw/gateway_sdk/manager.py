"""GatewayClientManager — maintains one GatewayClient per registered gateway.

Usage::

    from app.services.openclaw.gateway_sdk.manager import gateway_manager

    # On gateway create/update — auto-provisions the client
    client = gateway_manager.register(gateway_model)

    # Retrieve by gateway ID
    client = gateway_manager.get(gateway_id)

    # From a Board (via gateway_id FK)
    client = gateway_manager.get(board.gateway_id)

    # Use the client
    agents = await client.rpc.agents_list()
    response = await client.http.chat_completions_text("system", "user")
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from app.core.logging import get_logger
from app.services.openclaw.gateway_sdk.client import GatewayClient
from app.services.openclaw.gateway_sdk.config import GatewayConnectionConfig

if TYPE_CHECKING:
    from app.models.gateways import Gateway

logger = get_logger(__name__)


def _config_from_gateway(gateway: Gateway) -> GatewayConnectionConfig:
    """Build a GatewayConnectionConfig from a Gateway DB model."""
    url = (gateway.url or "").strip()
    if not url:
        msg = f"Gateway {gateway.id} has no URL configured"
        raise ValueError(msg)
    token = (gateway.token or "").strip() or None
    return GatewayConnectionConfig(
        url=url,
        token=token,
        allow_insecure_tls=gateway.allow_insecure_tls,
        disable_device_pairing=gateway.disable_device_pairing,
        workspace_root=(gateway.workspace_root or "").strip() or None,
    )


class GatewayClientManager:
    """Singleton manager maintaining one GatewayClient per gateway ID.

    When a gateway is registered (created or updated), the manager
    provisions a new ``GatewayClient`` with the correct config.  Callers
    retrieve clients by gateway UUID.
    """

    def __init__(self) -> None:
        self._clients: dict[UUID, GatewayClient] = {}

    def register(self, gateway: Gateway) -> GatewayClient:
        """Create or replace the client for a gateway.

        Call this from ``gateways.py`` on create and update.
        """
        existing = self._clients.get(gateway.id)
        if existing is not None:
            # Config may have changed — close old event client
            import asyncio

            try:
                loop = asyncio.get_running_loop()
                loop.create_task(existing.close())
            except RuntimeError:
                pass

        config = _config_from_gateway(gateway)
        client = GatewayClient(config)
        self._clients[gateway.id] = client
        logger.info(
            "gateway_sdk.manager.registered gateway_id=%s url=%s",
            gateway.id,
            config.http_base_url,
        )
        return client

    def get(self, gateway_id: UUID | None) -> GatewayClient | None:
        """Retrieve an existing client by gateway ID."""
        if gateway_id is None:
            return None
        return self._clients.get(gateway_id)

    def require(self, gateway_id: UUID | None) -> GatewayClient:
        """Retrieve a client or raise ValueError if not registered."""
        client = self.get(gateway_id)
        if client is None:
            msg = f"No gateway client registered for {gateway_id}"
            raise ValueError(msg)
        return client

    async def remove(self, gateway_id: UUID) -> None:
        """Remove and close a gateway client."""
        client = self._clients.pop(gateway_id, None)
        if client is not None:
            await client.close()
            logger.info("gateway_sdk.manager.removed gateway_id=%s", gateway_id)

    @property
    def registered_ids(self) -> list[UUID]:
        """List all registered gateway IDs."""
        return list(self._clients.keys())

    async def close_all(self) -> None:
        """Shut down all clients. Call on app shutdown."""
        for gw_id in list(self._clients.keys()):
            await self.remove(gw_id)


# Module-level singleton — import and use directly.
gateway_manager = GatewayClientManager()
