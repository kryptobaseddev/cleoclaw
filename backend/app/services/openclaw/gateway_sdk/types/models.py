"""Models domain types."""

from __future__ import annotations

from pydantic import BaseModel, Field

__all__ = [
    "ModelCatalogEntry",
    "ModelListResponse",
]


class ModelCatalogEntry(BaseModel):
    id: str
    name: str
    provider: str
    context_window: int | None = Field(default=None, alias="contextWindow")
    reasoning: bool | None = None

    model_config = {"populate_by_name": True, "extra": "allow"}


class ModelListResponse(BaseModel):
    models: list[ModelCatalogEntry]
