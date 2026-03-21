"""Usage and cost domain types."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

__all__ = [
    "UsageStatusResponse",
    "UsageCostResponse",
]


class UsageStatusResponse(BaseModel):
    """Provider usage summary. Shape varies by gateway version."""

    model_config = {"extra": "allow"}


class UsageCostResponse(BaseModel):
    """Cost breakdown summary. Shape varies by gateway version."""

    model_config = {"extra": "allow"}
