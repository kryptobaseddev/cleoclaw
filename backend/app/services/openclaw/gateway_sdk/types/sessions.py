"""Session domain types."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

__all__ = [
    "SessionEntry",
    "SessionListResponse",
    "SessionCreateResponse",
    "SessionPatchResponse",
    "SessionDeleteResponse",
    "SessionResetResponse",
    "SessionCompactResponse",
    "SessionMessage",
    "ChatHistoryResponse",
    "ChatSendResponse",
    "SessionSubscribeResponse",
    "SessionPreviewEntry",
    "SessionPreviewResponse",
]


class SessionEntry(BaseModel):
    session_id: str | None = Field(default=None, alias="sessionId")
    key: str
    label: str | None = None
    status: str | None = None
    started_at: int | None = Field(default=None, alias="startedAt")
    ended_at: int | None = Field(default=None, alias="endedAt")
    total_tokens: int | None = Field(default=None, alias="totalTokens")
    model: str | None = None

    model_config = {"populate_by_name": True, "extra": "allow"}


class SessionListResponse(BaseModel):
    total: int
    ts: int
    items: list[SessionEntry]
    limit: int | None = None

    model_config = {"populate_by_name": True}


class SessionCreateResponse(BaseModel):
    ok: bool
    key: str
    session_id: str = Field(alias="sessionId")
    status: str

    model_config = {"populate_by_name": True}


class SessionPatchResponse(BaseModel):
    ok: bool
    key: str
    patched: bool


class SessionDeleteResponse(BaseModel):
    ok: bool
    key: str


class SessionResetResponse(BaseModel):
    ok: bool
    key: str


class SessionCompactResponse(BaseModel):
    ok: bool
    key: str
    compacted: bool
    archived: str | None = None
    kept: int | None = None


class SessionMessage(BaseModel):
    role: str
    content: str | list[dict[str, Any]] | None = None
    text: str | None = None
    timestamp: int | None = None
    usage: dict[str, Any] | None = None
    cost: dict[str, Any] | None = None

    model_config = {"extra": "allow"}


class ChatHistoryResponse(BaseModel):
    session_key: str = Field(alias="sessionKey")
    session_id: str | None = Field(default=None, alias="sessionId")
    messages: list[SessionMessage]
    thinking_level: str | None = Field(default=None, alias="thinkingLevel")
    fast_mode: bool | None = Field(default=None, alias="fastMode")
    verbose_level: str | None = Field(default=None, alias="verboseLevel")

    model_config = {"populate_by_name": True}


class ChatSendResponse(BaseModel):
    run_id: str = Field(alias="runId")
    status: str

    model_config = {"populate_by_name": True}


class SessionSubscribeResponse(BaseModel):
    subscribed: bool
    key: str | None = None


class SessionPreviewEntry(BaseModel):
    key: str
    message: str | None = None

    model_config = {"extra": "allow"}


class SessionPreviewResponse(BaseModel):
    ts: int
    previews: list[SessionPreviewEntry]
