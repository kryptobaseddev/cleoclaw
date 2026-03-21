"""CCMC Gateway Client SDK — typed, transport-aware interface to OpenClaw gateways."""

from app.services.openclaw.gateway_sdk.client import GatewayClient
from app.services.openclaw.gateway_sdk.config import GatewayConnectionConfig, Transport
from app.services.openclaw.gateway_sdk.errors import (
    GatewayAuthError,
    GatewayConnectionError,
    GatewayError,
    GatewayHTTPError,
    GatewayRPCError,
    GatewayTimeoutError,
)
from app.services.openclaw.gateway_sdk.manager import GatewayClientManager, gateway_manager

__all__ = [
    "GatewayClient",
    "GatewayClientManager",
    "GatewayConnectionConfig",
    "GatewayError",
    "GatewayAuthError",
    "GatewayConnectionError",
    "GatewayHTTPError",
    "GatewayRPCError",
    "GatewayTimeoutError",
    "Transport",
    "gateway_manager",
]
