"""Simulation engine tables (Phase 4): model versions, runs, their steps and sensitivity
analyses.

Runs and analyses are **append-only**: nothing updates or deletes them, and a new run
never overwrites an old one. Each run keeps everything needed to explain and reproduce
it — the model version and its definition hash, the input snapshot (with where every
value came from), the knowledge-graph snapshot, every calculation step, the outputs and
the hashes of inputs and results.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, ForeignKey, Index, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, enum_column, utcnow
from app.db.types import ExactDecimal, UTCDateTime
from app.domain.enums import SimulationModelStatus, SimulationRunStatus


class SimulationModelVersion(Base):
    """One registered (model, version): its definition as it was when first used.

    The definition is code; this row is the durable copy that keeps old runs explainable
    after the code moves on. A version's definition hash may never change.
    """

    __tablename__ = "simulation_model_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    model_id: Mapped[str] = mapped_column(String(64))
    version: Mapped[str] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(200))
    status: Mapped[SimulationModelStatus] = mapped_column(
        enum_column(SimulationModelStatus, "simulation_model_status")
    )
    definition: Mapped[dict[str, Any]] = mapped_column(JSON)
    definition_hash: Mapped[str] = mapped_column(String(64))
    registered_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)

    __table_args__ = (UniqueConstraint("model_id", "version"),)


class SimulationRun(Base):
    """One completed run of a model version on a set of inputs."""

    __tablename__ = "simulation_runs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    model_version_id: Mapped[int] = mapped_column(
        ForeignKey("simulation_model_versions.id", ondelete="RESTRICT")
    )
    model_id: Mapped[str] = mapped_column(String(64))
    model_version: Mapped[str] = mapped_column(String(16))
    status: Mapped[SimulationRunStatus] = mapped_column(
        enum_column(SimulationRunStatus, "simulation_run_status")
    )
    label: Mapped[str | None] = mapped_column(String(120))
    entity_id: Mapped[str | None] = mapped_column(String(128))
    horizon_months: Mapped[int] = mapped_column(Integer)
    # Every input: value, unit, category, what it is (knowledge), where it came from.
    inputs: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    inputs_hash: Mapped[str] = mapped_column(String(64))
    assumptions: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    limitations: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    graph_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    data_snapshot: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    outputs: Mapped[dict[str, Any]] = mapped_column(JSON)
    monthly: Mapped[dict[str, Any]] = mapped_column(JSON)
    contributions: Mapped[dict[str, Any]] = mapped_column(JSON)
    bridge: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    transmission: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    warnings: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    result_hash: Mapped[str] = mapped_column(String(64))
    engine_version: Mapped[str] = mapped_column(String(16))
    # Deterministic models have no seed; a future Monte Carlo run would record one here.
    random_seed: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime())
    finished_at: Mapped[datetime] = mapped_column(UTCDateTime())
    duration_ms: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    # Who owns it (Phase 10): the person who ran it, or the owner of the scenario whose
    # execution stored it; null for runs made before accounts existed.
    owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    __table_args__ = (
        Index("ix_simulation_runs_model_created", "model_id", "created_at"),
        Index("ix_simulation_runs_inputs_hash", "inputs_hash"),
        Index("ix_simulation_runs_entity_id", "entity_id"),
    )


class SimulationRunStep(Base):
    """One evaluated equation of a run: its inputs and output, with units."""

    __tablename__ = "simulation_run_steps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("simulation_runs.id", ondelete="CASCADE"), index=True
    )
    sequence: Mapped[int] = mapped_column(Integer)
    equation_id: Mapped[str] = mapped_column(String(16))
    label: Mapped[str] = mapped_column(String(200))
    month: Mapped[int | None] = mapped_column(Integer)
    output_symbol: Mapped[str] = mapped_column(String(32))
    output_value: Mapped[Decimal] = mapped_column(ExactDecimal())
    output_unit: Mapped[str] = mapped_column(String(100))
    inputs: Mapped[list[dict[str, Any]]] = mapped_column(JSON)

    __table_args__ = (UniqueConstraint("run_id", "sequence"),)


class SimulationSensitivityAnalysis(Base):
    """A one-at-a-time sensitivity analysis of a run."""

    __tablename__ = "simulation_sensitivity_analyses"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("simulation_runs.id", ondelete="RESTRICT"), index=True
    )
    metric: Mapped[str] = mapped_column(String(64))
    request: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    results: Mapped[dict[str, Any]] = mapped_column(JSON)
    evaluations: Mapped[int] = mapped_column(Integer)
    duration_ms: Mapped[int] = mapped_column(Integer)
    result_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    # Who asked for it (Phase 10; null before accounts existed).
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
