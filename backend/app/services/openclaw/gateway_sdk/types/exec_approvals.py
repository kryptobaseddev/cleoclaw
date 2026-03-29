"""Exec approval domain types."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

__all__ = [
    "ExecApprovalsDefaults",
    "ExecApprovalsFile",
    "ExecApprovalsGetResponse",
    "ExecApprovalsSetResponse",
    "ExecApprovalRequestResponse",
    "ExecApprovalResolveResponse",
]


class ExecApprovalsDefaults(BaseModel):
    security: str | None = None
    ask: str | None = None
    allowlist: list[str] | None = None

    model_config = {"extra": "allow"}


class ExecApprovalsFile(BaseModel):
    version: int = 1
    defaults: ExecApprovalsDefaults | None = None
    agents: dict[str, Any] | None = None

    model_config = {"extra": "allow"}


class ExecApprovalsGetResponse(BaseModel):
    path: str
    exists: bool
    hash: str
    file: ExecApprovalsFile


class ExecApprovalsSetResponse(BaseModel):
    path: str
    exists: bool
    hash: str
    file: ExecApprovalsFile


class ExecApprovalRequestResponse(BaseModel):
    id: str
    two_phase: bool | None = Field(default=None, alias="twoPhase")
    expires_at_ms: int = Field(alias="expiresAtMs")

    model_config = {"populate_by_name": True}


class ExecApprovalResolveResponse(BaseModel):
    id: str
    decision: str
    resolved_at: int | None = Field(default=None, alias="resolvedAt")

    model_config = {"populate_by_name": True}
