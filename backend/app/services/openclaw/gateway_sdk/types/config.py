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
    raw: str
    snapshot: dict[str, Any]
    schema_: dict[str, Any] | None = Field(default=None, alias="schema")
    ui_hints: dict[str, Any] | None = Field(default=None, alias="uiHints")

    model_config = {"populate_by_name": True}


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
