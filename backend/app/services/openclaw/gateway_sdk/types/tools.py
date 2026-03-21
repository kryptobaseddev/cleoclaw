"""Tools invoke types for HTTP /tools/invoke endpoint."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

__all__ = [
    "ToolInvokeRequest",
    "ToolInvokeResponse",
]


class ToolInvokeRequest(BaseModel):
    tool: str
    action: str | None = None
    args: dict[str, Any] | None = None
    session_key: str = Field(default="main", alias="sessionKey")
    dry_run: bool = Field(default=False, alias="dryRun")

    model_config = {"populate_by_name": True}


class ToolInvokeResponse(BaseModel):
    ok: bool
    result: Any = None
