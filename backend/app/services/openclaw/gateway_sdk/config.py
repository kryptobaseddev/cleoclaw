"""Gateway connection configuration shared by all SDK transports.

Replaces the legacy ``GatewayConfig`` dataclass in ``gateway_rpc.py`` with a
Pydantic model that derives HTTP and WebSocket URLs from a single base URL and
centralizes auth, TLS, and device-pairing settings.
"""

from __future__ import annotations

import ssl
from enum import Enum
from urllib.parse import urlparse, urlunparse

from pydantic import BaseModel, Field, model_validator


class Transport(str, Enum):
    """Available gateway transport methods."""

    HTTP = "http"
    RPC = "rpc"
    EVENT = "event"


PROTOCOL_VERSION = 3

GATEWAY_OPERATOR_SCOPES: tuple[str, ...] = (
    "operator.read",
    "operator.admin",
    "operator.approvals",
    "operator.pairing",
)

DEFAULT_CLIENT_ID = "gateway-client"
DEFAULT_CLIENT_MODE = "backend"
CONTROL_UI_CLIENT_ID = "openclaw-control-ui"
CONTROL_UI_CLIENT_MODE = "ui"


class GatewayConnectionConfig(BaseModel):
    """Unified connection config for all gateway transports.

    Construct from a Gateway DB model or manually.  Derives ``http_base_url``
    and ``ws_url`` from the canonical ``url`` field so callers never need to
    build transport-specific URLs themselves.
    """

    url: str = Field(description="Gateway base URL (http(s) or ws(s) scheme)")
    token: str | None = Field(default=None, description="Bearer auth token")
    allow_insecure_tls: bool = Field(default=False)
    disable_device_pairing: bool = Field(default=False)
    workspace_root: str | None = Field(default=None)

    # Derived — populated by model_validator
    http_base_url: str = Field(default="", description="HTTP(S) base URL for REST calls")
    ws_url: str = Field(default="", description="WS(S) URL for RPC/event connections")

    model_config = {"frozen": True}

    @model_validator(mode="after")
    def _derive_transport_urls(self) -> GatewayConnectionConfig:
        parsed = urlparse(self.url)
        scheme = (parsed.scheme or "").lower()

        # Derive HTTP URL
        if scheme in ("http", "https"):
            http_url = urlunparse(parsed._replace(query="", fragment=""))
        elif scheme == "ws":
            http_url = urlunparse(parsed._replace(scheme="http", query="", fragment=""))
        elif scheme == "wss":
            http_url = urlunparse(parsed._replace(scheme="https", query="", fragment=""))
        else:
            http_url = self.url

        # Derive WS URL
        if scheme in ("ws", "wss"):
            ws = urlunparse(parsed._replace(query="", fragment=""))
        elif scheme == "http":
            ws = urlunparse(parsed._replace(scheme="ws", query="", fragment=""))
        elif scheme == "https":
            ws = urlunparse(parsed._replace(scheme="wss", query="", fragment=""))
        else:
            ws = self.url

        # Pydantic frozen model — use __dict__ to set derived fields
        object.__setattr__(self, "http_base_url", http_url.rstrip("/"))
        object.__setattr__(self, "ws_url", ws.rstrip("/"))
        return self

    @property
    def connect_mode(self) -> str:
        return "control_ui" if self.disable_device_pairing else "device"

    def build_ssl_context(self) -> ssl.SSLContext | None:
        """Create an insecure SSL context when explicitly opted in for wss://."""
        parsed = urlparse(self.ws_url)
        if parsed.scheme != "wss":
            return None
        if not self.allow_insecure_tls:
            return None
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx

    def build_control_ui_origin(self) -> str | None:
        """Build the Origin header value for control-UI connections."""
        parsed = urlparse(self.url)
        if not parsed.hostname:
            return None
        if parsed.scheme in ("ws", "http"):
            origin_scheme = "http"
        elif parsed.scheme in ("wss", "https"):
            origin_scheme = "https"
        else:
            return None
        host = parsed.hostname
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        if parsed.port is not None:
            host = f"{host}:{parsed.port}"
        return f"{origin_scheme}://{host}"

    def auth_headers(self) -> dict[str, str]:
        """Return HTTP auth headers for REST calls."""
        if self.token:
            return {"Authorization": f"Bearer {self.token}"}
        return {}
