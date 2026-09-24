"""Scenarios (Phase 1, versioned since Phase 5) and their executions (Phase 5).

A scenario is a stable identity (a name) with numbered, **immutable** versions: saving a
change adds a version and never rewrites an old one. An execution runs one version through
the Scenario Lab and stores its plan, the Phase 4 runs of every model it used, and the
aggregated results. Executions refer to versions with ``RESTRICT``, so a version that has
been executed can never disappear or change, and a scenario with executions cannot be
deleted.

A scenario holds *inputs only*; results live in executions and simulation runs, so a
scenario's inputs can never be mistaken for, or overwritten by, its outputs.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, enum_column, utcnow
from app.db.types import UTCDateTime
from app.domain.enums import ChangeType, ScenarioExecutionStatus, ScenarioStatus


class Scenario(TimestampMixin, Base):
    """A user-defined "what if": a name and its numbered versions."""

    __tablename__ = "scenarios"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[ScenarioStatus] = mapped_column(
        enum_column(ScenarioStatus, "scenario_status"), default=ScenarioStatus.DRAFT
    )
    # The newest version's number (versions are numbered 1, 2, 3 … per scenario).
    current_version: Mapped[int] = mapped_column(Integer, default=1)
    template_id: Mapped[str | None] = mapped_column(String(64))

    versions: Mapped[list[ScenarioVersion]] = relationship(
        back_populates="scenario",
        cascade="all, delete-orphan",
        order_by="ScenarioVersion.version",
        lazy="selectin",
    )


class ScenarioVersion(Base):
    """One saved state of a scenario. Never updated after it is inserted."""

    __tablename__ = "scenario_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scenario_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("scenarios.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    template_id: Mapped[str | None] = mapped_column(String(64))
    # Everything but the name, description, template and changes: the company, figures,
    # timing, models, assumptions, constraints and stress cases (validated JSON).
    spec: Mapped[dict[str, Any]] = mapped_column(JSON)
    # SHA-256 of the whole version's canonical form, changes included.
    spec_hash: Mapped[str] = mapped_column(String(64))
    # Where it came from: {"kind": "duplicate" | "restore", "scenario_id", "version"}.
    derived_from: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)

    scenario: Mapped[Scenario] = relationship(back_populates="versions")
    shocks: Mapped[list[ScenarioShock]] = relationship(
        back_populates="version",
        cascade="all, delete-orphan",
        order_by="ScenarioShock.position",
        lazy="selectin",
    )

    __table_args__ = (UniqueConstraint("scenario_id", "version"),)


class ScenarioShock(Base):
    """One scenario change: a change applied to one economic variable, in one version.

    ``value`` is interpreted by ``change_type``: ``percent_change`` → percent (30 means
    +30 %); ``absolute_change`` → the variable's unit, which for rates is percentage
    points. Stored as fixed-point NUMERIC with 4 decimal places and read as an exact
    decimal.
    """

    __tablename__ = "scenario_shocks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scenario_version_id: Mapped[int] = mapped_column(
        ForeignKey("scenario_versions.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int]
    variable_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("economic_variables.id", ondelete="RESTRICT")
    )
    change_type: Mapped[ChangeType] = mapped_column(enum_column(ChangeType, "change_type"))
    value: Mapped[Decimal] = mapped_column(Numeric(14, 4, asdecimal=True))
    note: Mapped[str] = mapped_column(Text, default="")

    version: Mapped[ScenarioVersion] = relationship(back_populates="shocks")

    __table_args__ = (UniqueConstraint("scenario_version_id", "variable_id"),)


class ScenarioExecution(Base):
    """One execution of a scenario version.

    Its state moves forward (queued → validating → simulating → propagating → aggregating
    → completed, failed or cancelled) and each stage is recorded with its times. Once it
    reaches a final state nothing changes it again.
    """

    __tablename__ = "scenario_executions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    scenario_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("scenarios.id", ondelete="RESTRICT"))
    scenario_version_id: Mapped[int] = mapped_column(
        ForeignKey("scenario_versions.id", ondelete="RESTRICT")
    )
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[ScenarioExecutionStatus] = mapped_column(
        enum_column(ScenarioExecutionStatus, "scenario_execution_status")
    )
    # [{"stage", "started_at", "finished_at", "detail"}], in order.
    stages: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    plan: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    results: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    inputs_hash: Mapped[str | None] = mapped_column(String(64))
    result_hash: Mapped[str | None] = mapped_column(String(64))
    lab_version: Mapped[str] = mapped_column(String(16))
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    requested_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    duration_ms: Mapped[int | None] = mapped_column(Integer)

    runs: Mapped[list[ScenarioExecutionRun]] = relationship(
        order_by="ScenarioExecutionRun.position", lazy="selectin"
    )

    __table_args__ = (
        Index("ix_scenario_executions_scenario_requested", "scenario_id", "requested_at"),
        Index("ix_scenario_executions_status", "status"),
    )


class ScenarioExecutionRun(Base):
    """A Phase 4 simulation run produced by a scenario execution (one per model)."""

    __tablename__ = "scenario_execution_runs"

    execution_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("scenario_executions.id", ondelete="RESTRICT"), primary_key=True
    )
    simulation_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("simulation_runs.id", ondelete="RESTRICT"), primary_key=True
    )
    position: Mapped[int] = mapped_column(Integer)
    model_id: Mapped[str] = mapped_column(String(64))
    model_version: Mapped[str] = mapped_column(String(16))


class ScenarioSensitivityAnalysis(Base):
    """A one-at-a-time sensitivity analysis across every model of an execution."""

    __tablename__ = "scenario_sensitivity_analyses"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    execution_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("scenario_executions.id", ondelete="RESTRICT"), index=True
    )
    metric: Mapped[str] = mapped_column(String(64))
    request: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    results: Mapped[dict[str, Any]] = mapped_column(JSON)
    evaluations: Mapped[int] = mapped_column(Integer)
    duration_ms: Mapped[int] = mapped_column(Integer)
    result_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
