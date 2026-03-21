"""HTTP REST client for OpenClaw gateway endpoints.

Covers:
- POST /v1/chat/completions  (OpenAI-compatible)
- POST /tools/invoke          (direct tool invocation)
- GET  /health, /ready        (gateway probes)
- POST /hooks                 (webhook dispatch)

All methods return typed Pydantic models and raise GatewayError subclasses.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.core.logging import get_logger
from app.services.openclaw.gateway_sdk.config import GatewayConnectionConfig
from app.services.openclaw.gateway_sdk.errors import (
    GatewayAuthError,
    GatewayConnectionError,
    GatewayHTTPError,
    GatewayTimeoutError,
)
from app.services.openclaw.gateway_sdk.types.chat import (
    ChatCompletionMessage,
    ChatCompletionRequest,
    ChatCompletionResponse,
)
from app.services.openclaw.gateway_sdk.types.health import HealthResponse
from app.services.openclaw.gateway_sdk.types.tools import ToolInvokeRequest, ToolInvokeResponse

logger = get_logger(__name__)

DEFAULT_TIMEOUT_S = 30.0
CHAT_COMPLETION_TIMEOUT_S = 120.0


class GatewayHTTPClient:
    """Typed HTTP client for OpenClaw gateway REST endpoints."""

    def __init__(self, config: GatewayConnectionConfig) -> None:
        self._config = config
        self._base_url = config.http_base_url

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        headers.update(self._config.auth_headers())
        return headers

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        timeout: float = DEFAULT_TIMEOUT_S,
    ) -> httpx.Response:
        """Execute an HTTP request and handle transport/auth errors."""
        url = f"{self._base_url}{path}"
        verify = not self._config.allow_insecure_tls

        try:
            async with httpx.AsyncClient(verify=verify) as client:
                response = await client.request(
                    method,
                    url,
                    headers=self._headers(),
                    json=json_body,
                    timeout=timeout,
                )
        except httpx.TimeoutException as exc:
            raise GatewayTimeoutError(
                f"Request timed out: {method} {path}",
                method=path,
                transport="http",
            ) from exc
        except httpx.ConnectError as exc:
            raise GatewayConnectionError(
                f"Cannot connect to gateway: {exc}",
                transport="http",
            ) from exc
        except httpx.HTTPError as exc:
            raise GatewayConnectionError(
                f"HTTP transport error: {exc}",
                transport="http",
            ) from exc

        if response.status_code == 401:
            raise GatewayAuthError(
                "Gateway authentication failed",
                method=path,
                transport="http",
            )
        if response.status_code == 403:
            raise GatewayAuthError(
                "Gateway authorization denied",
                method=path,
                transport="http",
            )

        if response.status_code >= 400:
            body = response.text
            raise GatewayHTTPError(
                f"Gateway returned {response.status_code}: {body[:200]}",
                method=path,
                status_code=response.status_code,
                response_body=body,
            )

        return response

    # ── Chat Completions ───────────────────────────────────────────────

    async def chat_completions(
        self,
        messages: list[ChatCompletionMessage],
        *,
        model: str = "openclaw:main",
        agent_id: str | None = None,
        session_key: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        timeout: float = CHAT_COMPLETION_TIMEOUT_S,
    ) -> ChatCompletionResponse:
        """Send a chat completion request to the gateway.

        This is a deterministic HTTP transport — the gateway handles all LLM
        routing, provider auth, and model selection.
        """
        request = ChatCompletionRequest(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        body = request.model_dump(exclude_none=True)

        headers = self._headers()
        if agent_id:
            headers["x-openclaw-agent-id"] = agent_id
        if session_key:
            headers["x-openclaw-session-key"] = session_key

        url = f"{self._base_url}/v1/chat/completions"
        verify = not self._config.allow_insecure_tls

        try:
            async with httpx.AsyncClient(verify=verify) as client:
                response = await client.post(
                    url,
                    headers=headers,
                    json=body,
                    timeout=timeout,
                )
        except httpx.TimeoutException as exc:
            raise GatewayTimeoutError(
                "Chat completion timed out",
                method="/v1/chat/completions",
                transport="http",
            ) from exc
        except httpx.ConnectError as exc:
            raise GatewayConnectionError(
                f"Cannot connect to gateway: {exc}",
                transport="http",
            ) from exc
        except httpx.HTTPError as exc:
            raise GatewayConnectionError(
                f"HTTP transport error: {exc}",
                transport="http",
            ) from exc

        if response.status_code == 401:
            raise GatewayAuthError(
                "Gateway authentication failed",
                method="/v1/chat/completions",
                transport="http",
            )

        if response.status_code >= 400:
            raise GatewayHTTPError(
                f"Chat completion failed ({response.status_code})",
                method="/v1/chat/completions",
                status_code=response.status_code,
                response_body=response.text,
            )

        data = response.json()
        logger.debug(
            "gateway.http.chat_completions.success model=%s choices=%d",
            data.get("model"),
            len(data.get("choices", [])),
        )
        return ChatCompletionResponse.model_validate(data)

    async def chat_completions_text(
        self,
        system_prompt: str,
        user_message: str,
        *,
        model: str = "openclaw:main",
        agent_id: str | None = None,
        timeout: float = CHAT_COMPLETION_TIMEOUT_S,
    ) -> str:
        """Convenience: send system + user messages and return the text response."""
        messages = [
            ChatCompletionMessage(role="system", content=system_prompt),
            ChatCompletionMessage(role="user", content=user_message),
        ]
        response = await self.chat_completions(
            messages, model=model, agent_id=agent_id, timeout=timeout
        )
        if not response.choices:
            return ""
        content = response.choices[0].message.content
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "\n".join(
                str(block.get("text", ""))
                for block in content
                if isinstance(block, dict) and block.get("type") == "text"
            )
        return ""

    # ── Tools Invoke ───────────────────────────────────────────────────

    async def tools_invoke(
        self,
        tool: str,
        *,
        action: str | None = None,
        args: dict[str, Any] | None = None,
        session_key: str = "main",
        timeout: float = DEFAULT_TIMEOUT_S,
    ) -> ToolInvokeResponse:
        """Invoke a gateway tool directly via HTTP."""
        request = ToolInvokeRequest(
            tool=tool,
            action=action,
            args=args,
            sessionKey=session_key,
        )
        response = await self._request(
            "POST",
            "/tools/invoke",
            json_body=request.model_dump(by_alias=True, exclude_none=True),
            timeout=timeout,
        )
        data = response.json()
        logger.debug("gateway.http.tools_invoke.success tool=%s ok=%s", tool, data.get("ok"))
        return ToolInvokeResponse.model_validate(data)

    # ── Health Probes ──────────────────────────────────────────────────

    async def health(self, *, timeout: float = 5.0) -> HealthResponse:
        """Check gateway liveness."""
        response = await self._request("GET", "/health", timeout=timeout)
        return HealthResponse.model_validate(response.json())

    async def ready(self, *, timeout: float = 5.0) -> HealthResponse:
        """Check gateway readiness."""
        response = await self._request("GET", "/ready", timeout=timeout)
        return HealthResponse.model_validate(response.json())

    async def is_healthy(self, *, timeout: float = 5.0) -> bool:
        """Quick check: returns True if gateway responds to /health, False otherwise."""
        try:
            await self.health(timeout=timeout)
            return True
        except Exception:
            return False

    # ── Hooks ──────────────────────────────────────────────────────────

    async def hooks_dispatch(
        self,
        payload: dict[str, Any],
        *,
        hook_path: str = "/hooks",
        idempotency_key: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_S,
    ) -> dict[str, Any]:
        """Dispatch a webhook payload to the gateway."""
        headers = self._headers()
        if idempotency_key:
            headers["X-Idempotency-Key"] = idempotency_key

        url = f"{self._base_url}{hook_path}"
        verify = not self._config.allow_insecure_tls

        try:
            async with httpx.AsyncClient(verify=verify) as client:
                response = await client.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=timeout,
                )
        except httpx.TimeoutException as exc:
            raise GatewayTimeoutError(
                "Hook dispatch timed out",
                method=hook_path,
                transport="http",
            ) from exc
        except httpx.HTTPError as exc:
            raise GatewayConnectionError(
                f"Hook dispatch transport error: {exc}",
                transport="http",
            ) from exc

        if response.status_code >= 400:
            raise GatewayHTTPError(
                f"Hook dispatch failed ({response.status_code})",
                method=hook_path,
                status_code=response.status_code,
                response_body=response.text,
            )

        return response.json()
