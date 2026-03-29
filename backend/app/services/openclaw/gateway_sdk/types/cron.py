"""Cron domain types."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

__all__ = [
    "CronJob",
    "CronJobListResponse",
    "CronStatusResponse",
    "CronRunEntry",
    "CronRunsResponse",
    "CronRunTriggerResponse",
    "CronRemoveResponse",
]


class CronJob(BaseModel):
    id: str | None = None
    name: str | None = None
    enabled: bool | None = None
    schedule: str | None = None
    next_run_at_ms: int | None = Field(default=None, alias="nextRunAtMs")
    last_run_at_ms: int | None = Field(default=None, alias="lastRunAtMs")
    last_status: str | None = Field(default=None, alias="lastStatus")

    model_config = {"populate_by_name": True, "extra": "allow"}


class CronJobListResponse(BaseModel):
    total: int
    items: list[CronJob]
    limit: int | None = None
    offset: int | None = None


class CronStatusResponse(BaseModel):
    enabled: bool
    jobs_count: int | None = Field(default=None, alias="jobsCount")
    next_run_at_ms: int | None = Field(default=None, alias="nextRunAtMs")

    model_config = {"populate_by_name": True, "extra": "allow"}


class CronRunEntry(BaseModel):
    id: str | None = None
    job_id: str | None = Field(default=None, alias="jobId")
    status: str | None = None
    started_at_ms: int | None = Field(default=None, alias="startedAtMs")
    ended_at_ms: int | None = Field(default=None, alias="endedAtMs")

    model_config = {"populate_by_name": True, "extra": "allow"}


class CronRunsResponse(BaseModel):
    total: int
    items: list[CronRunEntry]
    job_id: str | None = Field(default=None, alias="jobId")
    limit: int | None = None
    offset: int | None = None

    model_config = {"populate_by_name": True}


class CronRunTriggerResponse(BaseModel):
    id: str
    job_id: str = Field(alias="jobId")
    enqueued: bool

    model_config = {"populate_by_name": True}


class CronRemoveResponse(BaseModel):
    removed: bool
    id: str | None = None
