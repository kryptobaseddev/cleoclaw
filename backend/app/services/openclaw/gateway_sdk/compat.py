"""Backward-compatibility bridge between legacy gateway_rpc.py and the new SDK.

This module provides aliases and wrapper functions so existing code that imports
from ``gateway_rpc`` continues to work unchanged.  New code should import
directly from ``gateway_sdk`` instead.

Migration path:
1. Old: ``from app.services.openclaw.gateway_rpc import GatewayConfig, OpenClawGatewayError``
2. New: ``from app.services.openclaw.gateway_sdk import GatewayConnectionConfig, GatewayError``
"""

from __future__ import annotations

from typing import Any

from app.services.openclaw.gateway_sdk.config import GatewayConnectionConfig
from app.services.openclaw.gateway_sdk.errors import (
    GatewayConnectionError,
    GatewayError,
    GatewayRPCError,
    GatewayTimeoutError,
)


def config_from_legacy(
    url: str,
    token: str | None = None,
    allow_insecure_tls: bool = False,
    disable_device_pairing: bool = False,
) -> GatewayConnectionConfig:
    """Convert legacy GatewayConfig constructor args to SDK config."""
    return GatewayConnectionConfig(
        url=url,
        token=token,
        allow_insecure_tls=allow_insecure_tls,
        disable_device_pairing=disable_device_pairing,
    )


def legacy_error_from_sdk(exc: GatewayError) -> Exception:
    """Convert SDK error to a legacy-compatible OpenClawGatewayError shape."""
    # Import lazily to avoid circular dependency
    from app.services.openclaw.gateway_rpc import OpenClawGatewayError

    return OpenClawGatewayError(str(exc))


def is_gateway_error(exc: Exception) -> bool:
    """Check if an exception is any kind of gateway error (old or new)."""
    from app.services.openclaw.gateway_rpc import OpenClawGatewayError

    return isinstance(exc, (GatewayError, OpenClawGatewayError))
