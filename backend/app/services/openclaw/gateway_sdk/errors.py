"""Typed error hierarchy for all gateway SDK transports.

Replaces the flat ``OpenClawGatewayError`` with transport-aware exceptions
so callers can catch specific failure modes without string inspection.
"""

from __future__ import annotations

from typing import Any


class GatewayError(Exception):
    """Base exception for all gateway SDK errors."""

    def __init__(
        self,
        message: str,
        *,
        method: str | None = None,
        transport: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.method = method
        self.transport = transport
        self.details = details or {}


class GatewayConnectionError(GatewayError):
    """Failed to establish or maintain a gateway connection."""


class GatewayAuthError(GatewayError):
    """Authentication or authorization failure."""


class GatewayTimeoutError(GatewayError):
    """Operation timed out waiting for a gateway response."""


class GatewayRPCError(GatewayError):
    """Error returned by a WebSocket RPC method call.

    Attributes:
        error_code: Gateway error code from the response, if available.
    """

    def __init__(
        self,
        message: str,
        *,
        method: str | None = None,
        error_code: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, method=method, transport="rpc", details=details)
        self.error_code = error_code


class GatewayHTTPError(GatewayError):
    """Error from an HTTP REST call to the gateway.

    Attributes:
        status_code: HTTP status code from the response.
        response_body: Raw response body, if available.
    """

    def __init__(
        self,
        message: str,
        *,
        method: str | None = None,
        status_code: int | None = None,
        response_body: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, method=method, transport="http", details=details)
        self.status_code = status_code
        self.response_body = response_body


class GatewayEventError(GatewayError):
    """Error in the WebSocket event subscription channel."""

    def __init__(
        self,
        message: str,
        *,
        event: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, transport="event", details=details)
        self.event = event
