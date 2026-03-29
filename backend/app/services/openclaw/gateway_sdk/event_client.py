"""WebSocket event subscriber for the CCMC Gateway Client SDK.

Provides ``GatewayEventClient``, a persistent WebSocket connection that dispatches
gateway events to registered handlers and automatically reconnects on disconnect.
"""

from __future__ import annotations

import asyncio
import json
from time import time
from typing import Any, Awaitable, Callable
from urllib.parse import urlencode, urlparse, urlunparse
from uuid import uuid4

import websockets
from websockets.exceptions import WebSocketException

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
    GatewayAuthError,
    GatewayConnectionError,
    GatewayEventError,
)

logger = get_logger(__name__)

# Type alias for event handler callables.
# Handlers receive (event_name, payload) and may be sync or async.
EventHandler = Callable[[str, dict[str, Any]], Awaitable[None] | None]


def _build_ws_url_with_token(config: GatewayConnectionConfig) -> str:
    """Append the auth token as a query parameter to the WebSocket URL, if present."""
    if not config.token:
        return config.ws_url
    parsed = urlparse(config.ws_url)
    query = urlencode({"token": config.token})
    return str(urlunparse(parsed._replace(query=query)))


def _build_device_connect_payload(
    *,
    client_id: str,
    client_mode: str,
    role: str,
    scopes: list[str],
    auth_token: str | None,
    connect_nonce: str | None,
) -> dict[str, Any]:
    """Build the device identity + signature block for a connect request."""
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
    """Build the ``connect`` RPC params matching the gateway_rpc.py convention."""
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
    if config.token:
        params["auth"] = {"token": config.token}
    return params


class GatewayEventClient:
    """Persistent WebSocket event subscriber for the CCMC Gateway.

    Connects to the gateway, authenticates using the same flow as
    ``gateway_rpc.py``, and dispatches inbound events to registered handlers.
    Reconnects automatically with exponential back-off when the connection drops.

    Usage::

        client = GatewayEventClient(config)
        client.on("chat", my_chat_handler)
        await client.start()          # blocks / runs until stopped
        await client.stop()

    Handlers are callables with the signature::

        async def handler(event: str, payload: dict[str, Any]) -> None: ...
        # or synchronous
        def handler(event: str, payload: dict[str, Any]) -> None: ...
    """

    def __init__(self, config: GatewayConnectionConfig) -> None:
        self._config = config
        self._handlers: dict[str, list[EventHandler]] = {}
        self._ws: websockets.ClientConnection | None = None
        self._running = False
        self._reconnect_delay = 1.0
        self._max_reconnect_delay = 30.0
        # Background task reference kept so it can be cancelled on stop().
        self._listen_task: asyncio.Task[None] | None = None

    # ------------------------------------------------------------------
    # Handler registration
    # ------------------------------------------------------------------

    def on(self, event: str, handler: EventHandler) -> None:
        """Register *handler* to be called when *event* is received."""
        self._handlers.setdefault(event, [])
        if handler not in self._handlers[event]:
            self._handlers[event].append(handler)

    def off(self, event: str, handler: EventHandler) -> None:
        """Unregister *handler* from *event*.  No-op if not registered."""
        handlers = self._handlers.get(event)
        if handlers and handler in handlers:
            handlers.remove(handler)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Connect to the gateway and start the event-listen loop.

        This method starts the background listen loop and returns immediately.
        The loop auto-reconnects on disconnect until ``stop()`` is called.
        """
        if self._running:
            return
        self._running = True
        self._listen_task = asyncio.create_task(self._run_loop(), name="gateway-event-listen")
        logger.debug("gateway.event_client.started ws_url=%s", self._config.ws_url)

    async def stop(self) -> None:
        """Gracefully disconnect and stop the event-listen loop."""
        self._running = False
        if self._listen_task is not None and not self._listen_task.done():
            self._listen_task.cancel()
            try:
                await self._listen_task
            except asyncio.CancelledError:
                pass
            self._listen_task = None
        await self._close_ws()
        logger.debug("gateway.event_client.stopped")

    # ------------------------------------------------------------------
    # Session subscriptions
    # ------------------------------------------------------------------

    async def subscribe_session(self, session_key: str) -> None:
        """Subscribe to session events via ``sessions.subscribe`` RPC.

        Must be called after ``start()`` has established a connection.
        """
        await self._send_rpc("sessions.subscribe", {"key": session_key})
        logger.debug("gateway.event_client.session.subscribed session_key=%s", session_key)

    async def unsubscribe_session(self, session_key: str) -> None:
        """Unsubscribe from session events via ``sessions.unsubscribe`` RPC."""
        await self._send_rpc("sessions.unsubscribe", {"key": session_key})
        logger.debug("gateway.event_client.session.unsubscribed session_key=%s", session_key)

    # ------------------------------------------------------------------
    # Internal — connection
    # ------------------------------------------------------------------

    async def _run_loop(self) -> None:
        """Outer reconnect loop — keeps trying as long as ``_running`` is True."""
        while self._running:
            try:
                await self._connect()
                self._reconnect_delay = 1.0  # Reset back-off on successful connect
                await self._listen_loop()
            except asyncio.CancelledError:
                break
            except (GatewayConnectionError, GatewayAuthError) as exc:
                logger.warning(
                    "gateway.event_client.connect_error error=%s reconnect_in=%.1fs",
                    exc,
                    self._reconnect_delay,
                )
            except (WebSocketException, OSError, ConnectionError) as exc:
                logger.warning(
                    "gateway.event_client.transport_error error_type=%s error=%s reconnect_in=%.1fs",
                    exc.__class__.__name__,
                    exc,
                    self._reconnect_delay,
                )
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "gateway.event_client.unexpected_error error_type=%s error=%s reconnect_in=%.1fs",
                    exc.__class__.__name__,
                    exc,
                    self._reconnect_delay,
                )
            finally:
                await self._close_ws()

            if self._running:
                await self._reconnect()

    async def _connect(self) -> None:
        """Establish a WebSocket connection and authenticate.

        Replicates the connect flow from ``gateway_rpc.py``:
        1. Open WebSocket.
        2. Wait up to 2 s for an optional ``connect.challenge`` event.
        3. Send ``connect`` RPC with auth params (device or control-UI mode).
        4. Await the ``connect`` response.
        """
        ws_url = _build_ws_url_with_token(self._config)
        connect_kwargs: dict[str, Any] = {"ping_interval": None}

        ssl_context = self._config.build_ssl_context()
        if ssl_context is not None:
            connect_kwargs["ssl"] = ssl_context

        if self._config.connect_mode == "control_ui":
            origin = self._config.build_control_ui_origin()
            if origin is not None:
                connect_kwargs["origin"] = origin

        logger.debug(
            "gateway.event_client.connecting ws_url=%s connect_mode=%s",
            self._config.ws_url,  # log without token
            self._config.connect_mode,
        )

        try:
            ws = await websockets.connect(ws_url, **connect_kwargs)
        except (OSError, ConnectionError, WebSocketException) as exc:
            raise GatewayConnectionError(
                f"Failed to open WebSocket: {exc}",
                transport="event",
            ) from exc

        self._ws = ws

        # Step 1: Wait for optional connect.challenge (2 s timeout)
        connect_nonce: str | None = None
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=2)
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            data: dict[str, Any] = json.loads(raw)
            logger.log(
                TRACE_LEVEL,
                "gateway.event_client.first_message type=%s event=%s",
                data.get("type"),
                data.get("event"),
            )
            if data.get("type") == "event" and data.get("event") == "connect.challenge":
                payload = data.get("payload")
                if isinstance(payload, dict):
                    nonce = payload.get("nonce")
                    if isinstance(nonce, str) and nonce.strip():
                        connect_nonce = nonce.strip()
            else:
                logger.warning(
                    "gateway.event_client.unexpected_first_message type=%s event=%s",
                    data.get("type"),
                    data.get("event"),
                )
        except TimeoutError:
            # No challenge message — proceed without nonce.
            pass

        # Step 2: Send connect request
        connect_id = str(uuid4())
        connect_msg = {
            "type": "req",
            "id": connect_id,
            "method": "connect",
            "params": _build_connect_params(self._config, connect_nonce=connect_nonce),
        }
        try:
            await ws.send(json.dumps(connect_msg))
        except WebSocketException as exc:
            raise GatewayConnectionError(
                f"Failed to send connect request: {exc}",
                transport="event",
            ) from exc

        # Step 3: Await connect response
        try:
            response = await self._await_response(ws, connect_id)
        except GatewayAuthError:
            raise
        except GatewayConnectionError:
            raise
        except Exception as exc:
            raise GatewayConnectionError(
                f"Connect handshake failed: {exc}",
                transport="event",
            ) from exc

        logger.debug(
            "gateway.event_client.connected connect_mode=%s response_keys=%s",
            self._config.connect_mode,
            sorted(response.keys()) if isinstance(response, dict) else None,
        )

    async def _await_response(
        self,
        ws: websockets.ClientConnection,
        request_id: str,
    ) -> dict[str, Any]:
        """Wait for the RPC response matching *request_id*.

        Enqueues any events received while waiting so they are not lost.
        """
        while True:
            raw = await ws.recv()
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            data: dict[str, Any] = json.loads(raw)
            logger.log(
                TRACE_LEVEL,
                "gateway.event_client.recv_during_rpc request_id=%s type=%s",
                request_id,
                data.get("type"),
            )

            if data.get("type") == "res" and data.get("id") == request_id:
                ok = data.get("ok")
                if ok is not None and not ok:
                    error = data.get("error", {}).get("message", "Gateway error")
                    error_code = data.get("error", {}).get("code")
                    if error_code in {"auth_failed", "unauthorized", "forbidden"}:
                        raise GatewayAuthError(error, transport="event")
                    raise GatewayConnectionError(error, transport="event")
                return data.get("payload") or {}

            # Legacy response format (id match without type=res)
            if data.get("id") == request_id:
                if data.get("error"):
                    message = data["error"].get("message", "Gateway error")
                    raise GatewayConnectionError(message, transport="event")
                return data.get("result") or {}

            # Not our response — dispatch as event if it looks like one
            if data.get("type") == "event":
                event_name = data.get("event", "")
                event_payload = data.get("payload") or {}
                if event_name:
                    asyncio.create_task(
                        self._dispatch_event(event_name, event_payload),
                        name=f"gateway-event-{event_name}",
                    )

    # ------------------------------------------------------------------
    # Internal — listen loop
    # ------------------------------------------------------------------

    async def _listen_loop(self) -> None:
        """Receive messages from the gateway and dispatch events to handlers."""
        ws = self._ws
        if ws is None:
            return

        logger.debug("gateway.event_client.listen_loop.start")
        try:
            async for raw in ws:
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8")
                try:
                    data: dict[str, Any] = json.loads(raw)
                except json.JSONDecodeError:
                    logger.warning(
                        "gateway.event_client.invalid_json raw_len=%d",
                        len(raw),
                    )
                    continue

                logger.log(
                    TRACE_LEVEL,
                    "gateway.event_client.recv type=%s event=%s",
                    data.get("type"),
                    data.get("event"),
                )

                if data.get("type") == "event":
                    event_name = data.get("event", "")
                    event_payload = data.get("payload") or {}
                    if event_name:
                        await self._dispatch_event(event_name, event_payload)
        except asyncio.CancelledError:
            raise
        except WebSocketException as exc:
            logger.info(
                "gateway.event_client.listen_loop.ws_closed error_type=%s error=%s",
                exc.__class__.__name__,
                exc,
            )
        except (OSError, ConnectionError) as exc:
            logger.warning(
                "gateway.event_client.listen_loop.transport_error error_type=%s error=%s",
                exc.__class__.__name__,
                exc,
            )
        finally:
            logger.debug("gateway.event_client.listen_loop.end")

    # ------------------------------------------------------------------
    # Internal — reconnect
    # ------------------------------------------------------------------

    async def _reconnect(self) -> None:
        """Wait for the current back-off delay, then double it (capped)."""
        delay = self._reconnect_delay
        logger.info(
            "gateway.event_client.reconnecting delay=%.1fs",
            delay,
        )
        await asyncio.sleep(delay)
        self._reconnect_delay = min(delay * 2, self._max_reconnect_delay)

    # ------------------------------------------------------------------
    # Internal — event dispatch
    # ------------------------------------------------------------------

    async def _dispatch_event(self, event: str, payload: dict[str, Any]) -> None:
        """Invoke all handlers registered for *event*.

        Handlers are called in registration order.  Exceptions are caught and
        logged so a failing handler does not prevent others from running.
        """
        handlers = list(self._handlers.get(event, []))
        if not handlers:
            logger.log(TRACE_LEVEL, "gateway.event_client.unhandled_event event=%s", event)
            return

        for handler in handlers:
            try:
                result = handler(event, payload)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "gateway.event_client.handler_error event=%s handler=%s error_type=%s error=%s",
                    event,
                    getattr(handler, "__name__", repr(handler)),
                    exc.__class__.__name__,
                    exc,
                )

    # ------------------------------------------------------------------
    # Internal — RPC send (post-connect)
    # ------------------------------------------------------------------

    async def _send_rpc(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Send an RPC request over the established WebSocket and await the response.

        Raises ``GatewayConnectionError`` if the client is not connected.
        """
        ws = self._ws
        if ws is None:
            raise GatewayConnectionError(
                f"Cannot send RPC '{method}': not connected",
                method=method,
                transport="event",
            )
        request_id = str(uuid4())
        message = {
            "type": "req",
            "id": request_id,
            "method": method,
            "params": params,
        }
        logger.log(
            TRACE_LEVEL,
            "gateway.event_client.rpc.send method=%s request_id=%s",
            method,
            request_id,
        )
        try:
            await ws.send(json.dumps(message))
        except WebSocketException as exc:
            raise GatewayConnectionError(
                f"Failed to send RPC '{method}': {exc}",
                method=method,
                transport="event",
            ) from exc
        return await self._await_response(ws, request_id)

    # ------------------------------------------------------------------
    # Internal — teardown
    # ------------------------------------------------------------------

    async def _close_ws(self) -> None:
        """Close the WebSocket connection if open, swallowing errors."""
        ws = self._ws
        self._ws = None
        if ws is not None:
            try:
                await ws.close()
            except Exception:  # noqa: BLE001
                pass
