"""Agent domain types."""

from __future__ import annotations

from pydantic import BaseModel, Field

__all__ = [
    "AgentIdentity",
    "AgentSummary",
    "AgentListResponse",
    "AgentCreateResponse",
    "AgentUpdateResponse",
    "AgentDeleteResponse",
    "AgentFileEntry",
    "AgentFilesListResponse",
    "AgentFileGetResponse",
    "AgentFileSetResponse",
]


class AgentIdentity(BaseModel):
    name: str | None = None
    theme: str | None = None
    emoji: str | None = None
    avatar: str | None = None
    avatar_url: str | None = Field(default=None, alias="avatarUrl")


class AgentSummary(BaseModel):
    id: str
    name: str | None = None
    identity: AgentIdentity | None = None

    model_config = {"populate_by_name": True}


class AgentListResponse(BaseModel):
    default_id: str = Field(alias="defaultId")
    main_key: str = Field(alias="mainKey")
    scope: str
    agents: list[AgentSummary]

    model_config = {"populate_by_name": True}


class AgentCreateResponse(BaseModel):
    ok: bool
    agent_id: str = Field(alias="agentId")
    name: str
    workspace: str

    model_config = {"populate_by_name": True}


class AgentUpdateResponse(BaseModel):
    ok: bool
    agent_id: str = Field(alias="agentId")

    model_config = {"populate_by_name": True}


class AgentDeleteResponse(BaseModel):
    ok: bool
    agent_id: str = Field(alias="agentId")
    removed_bindings: int = Field(default=0, alias="removedBindings")

    model_config = {"populate_by_name": True}


class AgentFileEntry(BaseModel):
    name: str
    path: str
    missing: bool
    size: int | None = None
    updated_at_ms: int | None = Field(default=None, alias="updatedAtMs")
    content: str | None = None

    model_config = {"populate_by_name": True}


class AgentFilesListResponse(BaseModel):
    agent_id: str = Field(alias="agentId")
    workspace: str
    files: list[AgentFileEntry]

    model_config = {"populate_by_name": True}


class AgentFileGetResponse(BaseModel):
    agent_id: str = Field(alias="agentId")
    workspace: str
    file: AgentFileEntry

    model_config = {"populate_by_name": True}


class AgentFileSetResponse(BaseModel):
    ok: bool
    agent_id: str = Field(alias="agentId")
    name: str
    workspace: str

    model_config = {"populate_by_name": True}
