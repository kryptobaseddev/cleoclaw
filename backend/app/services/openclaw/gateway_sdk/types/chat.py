"""Chat completions types for HTTP /v1/chat/completions endpoint."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

__all__ = [
    "ChatCompletionMessage",
    "ChatCompletionRequest",
    "ChatCompletionChoice",
    "ChatCompletionUsage",
    "ChatCompletionResponse",
]


class ChatCompletionMessage(BaseModel):
    role: str
    content: str | list[dict[str, Any]] | None = None


class ChatCompletionRequest(BaseModel):
    model: str = "openclaw:main"
    messages: list[ChatCompletionMessage]
    stream: bool = False
    temperature: float | None = None
    max_tokens: int | None = None

    model_config = {"extra": "allow"}


class ChatCompletionChoice(BaseModel):
    index: int = 0
    message: ChatCompletionMessage
    finish_reason: str | None = Field(default=None, alias="finish_reason")

    model_config = {"populate_by_name": True}


class ChatCompletionUsage(BaseModel):
    prompt_tokens: int = Field(default=0, alias="prompt_tokens")
    completion_tokens: int = Field(default=0, alias="completion_tokens")
    total_tokens: int = Field(default=0, alias="total_tokens")

    model_config = {"populate_by_name": True}


class ChatCompletionResponse(BaseModel):
    id: str | None = None
    object: str | None = None
    created: int | None = None
    model: str | None = None
    choices: list[ChatCompletionChoice]
    usage: ChatCompletionUsage | None = None
