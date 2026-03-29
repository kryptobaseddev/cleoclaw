"""Device domain types."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

__all__ = [
    "DevicePairingRequest",
    "PairedDevice",
    "DevicePairListResponse",
    "DevicePairApproveResponse",
    "DevicePairRejectResponse",
    "DevicePairRemoveResponse",
    "DeviceTokenRotateResponse",
    "DeviceTokenRevokeResponse",
]


class DevicePairingRequest(BaseModel):
    request_id: str = Field(alias="requestId")
    device_id: str = Field(alias="deviceId")

    model_config = {"populate_by_name": True, "extra": "allow"}


class PairedDevice(BaseModel):
    device_id: str = Field(alias="deviceId")
    display_name: str | None = Field(default=None, alias="displayName")
    platform: str | None = None
    role: str | None = None
    roles: list[str] | None = None
    scopes: list[str] | None = None
    created_at_ms: int | None = Field(default=None, alias="createdAtMs")

    model_config = {"populate_by_name": True, "extra": "allow"}


class DevicePairListResponse(BaseModel):
    pending: list[DevicePairingRequest]
    paired: list[PairedDevice]


class DevicePairApproveResponse(BaseModel):
    request_id: str = Field(alias="requestId")
    device: PairedDevice

    model_config = {"populate_by_name": True}


class DevicePairRejectResponse(BaseModel):
    request_id: str = Field(alias="requestId")
    device_id: str = Field(alias="deviceId")

    model_config = {"populate_by_name": True}


class DevicePairRemoveResponse(BaseModel):
    device_id: str = Field(alias="deviceId")

    model_config = {"populate_by_name": True, "extra": "allow"}


class DeviceTokenRotateResponse(BaseModel):
    device_id: str = Field(alias="deviceId")
    role: str
    token: str
    scopes: list[str]
    rotated_at_ms: int = Field(alias="rotatedAtMs")

    model_config = {"populate_by_name": True}


class DeviceTokenRevokeResponse(BaseModel):
    device_id: str = Field(alias="deviceId")
    role: str
    revoked_at_ms: int = Field(alias="revokedAtMs")

    model_config = {"populate_by_name": True}
