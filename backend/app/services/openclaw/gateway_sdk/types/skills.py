"""Skills domain types."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

__all__ = [
    "SkillStatusResponse",
    "SkillBinsResponse",
    "SkillInstallResponse",
    "SkillUpdateResponse",
]


class SkillStatusResponse(BaseModel):
    agent_id: str = Field(alias="agentId")
    workspace_dir: str = Field(alias="workspaceDir")
    report: dict[str, Any]

    model_config = {"populate_by_name": True}


class SkillBinsResponse(BaseModel):
    bins: list[str]


class SkillInstallResponse(BaseModel):
    ok: bool
    message: str | None = None
    install_id: str | None = Field(default=None, alias="installId")

    model_config = {"populate_by_name": True, "extra": "allow"}


class SkillUpdateResponse(BaseModel):
    ok: bool
    skill_key: str = Field(alias="skillKey")
    config: dict[str, Any] | None = None

    model_config = {"populate_by_name": True}
