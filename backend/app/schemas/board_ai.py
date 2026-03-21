"""Schemas for AI-assisted board creation request/response payloads."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class BoardCreationDraft(BaseModel):
    """Structured draft generated from natural language by the gateway AI."""

    name: str | None = None
    description: str | None = None
    board_type: str = "goal"  # goal | general
    objective: str | None = None
    success_metrics: dict[str, Any] | None = None
    target_date: str | None = None
    suggested_tags: list[str] | None = None
    lead_agent_name: str | None = None
    lead_agent_identity: dict[str, str] | None = None


class BoardAIGenerateRequest(BaseModel):
    """Request payload for generating an AI board draft from natural language."""

    description: str
    gateway_id: str


class BoardAIRefineRequest(BaseModel):
    """Request payload for refining an existing AI board draft."""

    draft: BoardCreationDraft
    feedback: str
    gateway_id: str
