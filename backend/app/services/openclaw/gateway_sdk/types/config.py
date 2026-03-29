"""Config domain types."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

__all__ = [
    "ConfigGetResponse",
    "ConfigSetResponse",
    "ConfigPatchResponse",
    "ConfigApplyResponse",
]


class ConfigGetResponse(BaseModel):
    path: str | None = None
    raw: str | None = None
    snapshot: dict[str, Any] | None = None
    schema_: dict[str, Any] | None = Field(default=None, alias="schema")
    ui_hints: dict[str, Any] | None = Field(default=None, alias="uiHints")

    model_config = {"populate_by_name": True, "extra": "allow"}


class ConfigSetResponse(BaseModel):
    ok: bool
    path: str
    error: str | None = None


class ConfigPatchResponse(BaseModel):
    applied: bool

    model_config = {"extra": "allow"}


class ConfigApplyResponse(BaseModel):
    ok: bool
    path: str
    error: str | None = None
