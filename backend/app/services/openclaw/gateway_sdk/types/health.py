"""Health and status domain types."""

from __future__ import annotations

from pydantic import BaseModel

__all__ = [
    "HealthResponse",
    "StatusResponse",
]


class HealthResponse(BaseModel):
    ts: int | None = None
    cached: bool | None = None

    model_config = {"extra": "allow"}


class StatusResponse(BaseModel):
    """Gateway status summary. Shape varies by scope and version."""

    model_config = {"extra": "allow"}
