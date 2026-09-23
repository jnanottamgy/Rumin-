"""Health, readiness and system-status schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from app.schemas.common import ApiModel
from app.schemas.network import DatasetSummary


class HealthResponse(ApiModel):
    status: Literal["ok"]
    service: str
    version: str


class ReadinessChecks(ApiModel):
    database: Literal["ok", "unavailable"]
    migrations: Literal["up_to_date", "outdated", "missing", "unknown"]
    dataset: Literal["loaded", "missing", "unknown"]


class ReadinessResponse(ApiModel):
    status: Literal["ready", "not_ready"]
    checks: ReadinessChecks


class DatabaseStatus(ApiModel):
    backend: str = Field(examples=["sqlite", "postgresql"])
    reachable: bool
    migration_revision: str | None
    migration_head: str | None
    schema_up_to_date: bool


class DatasetStatus(ApiModel):
    loaded: bool
    summary: DatasetSummary | None
    entity_counts: dict[str, int]
    relationship_count: int


class Capability(ApiModel):
    id: str
    label: str
    available: bool
    planned_phase: int | None = Field(description="Roadmap phase that delivers it, if planned.")
    note: str


class SystemStatus(ApiModel):
    service: str
    version: str
    api_version: str
    environment: str
    server_time: datetime
    database: DatabaseStatus
    dataset: DatasetStatus
    capabilities: list[Capability]
