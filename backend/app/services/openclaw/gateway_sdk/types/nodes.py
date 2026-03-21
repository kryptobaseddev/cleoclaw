"""Node domain types."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

__all__ = [
    "NodeEntry",
    "NodeListResponse",
    "NodeDescribeResponse",
    "NodeRenameResponse",
    "NodeInvokeResponse",
    "NodePairingRequest",
    "PairedNode",
    "NodePairListResponse",
    "NodePairApproveResponse",
    "NodePairRejectResponse",
]


class NodeEntry(BaseModel):
    node_id: str = Field(alias="nodeId")
    display_name: str | None = Field(default=None, alias="displayName")
    role: str | None = None
    platform: str | None = None
    version: str | None = None
    connected: bool | None = None
    last_seen_at_ms: int | None = Field(default=None, alias="lastSeenAtMs")

    model_config = {"populate_by_name": True, "extra": "allow"}


class NodeListResponse(BaseModel):
    ts: int
    nodes: list[NodeEntry]


class NodeDescribeResponse(BaseModel):
    ok: bool
    node_id: str = Field(alias="nodeId")

    model_config = {"populate_by_name": True, "extra": "allow"}


class NodeRenameResponse(BaseModel):
    node_id: str = Field(alias="nodeId")
    display_name: str = Field(alias="displayName")

    model_config = {"populate_by_name": True}


class NodeInvokeResponse(BaseModel):
    id: str
    node_id: str = Field(alias="nodeId")
    pending: bool

    model_config = {"populate_by_name": True}


class NodePairingRequest(BaseModel):
    request_id: str = Field(alias="requestId")
    device_id: str = Field(alias="deviceId")

    model_config = {"populate_by_name": True, "extra": "allow"}


class PairedNode(BaseModel):
    device_id: str = Field(alias="deviceId")
    display_name: str | None = Field(default=None, alias="displayName")

    model_config = {"populate_by_name": True, "extra": "allow"}


class NodePairListResponse(BaseModel):
    pending: list[NodePairingRequest]
    paired: list[PairedNode]


class NodePairApproveResponse(BaseModel):
    request_id: str = Field(alias="requestId")
    device: PairedNode

    model_config = {"populate_by_name": True}


class NodePairRejectResponse(BaseModel):
    request_id: str = Field(alias="requestId")
    device_id: str = Field(alias="deviceId")

    model_config = {"populate_by_name": True}
