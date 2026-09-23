from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, enum_column
from app.domain.enums import ChangeType, ScenarioStatus


class Scenario(TimestampMixin, Base):
    """A user-defined "what if" configuration. It holds *inputs only*.

    Simulation results will live in a separate ``simulation_runs`` table (Phase 4), so
    a scenario's inputs can never be mistaken for, or overwritten by, its outputs.
    """

    __tablename__ = "scenarios"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[ScenarioStatus] = mapped_column(
        enum_column(ScenarioStatus, "scenario_status"), default=ScenarioStatus.DRAFT
    )

    shocks: Mapped[list[ScenarioShock]] = relationship(
        back_populates="scenario",
        cascade="all, delete-orphan",
        order_by="ScenarioShock.position",
        lazy="selectin",
    )


class ScenarioShock(Base):
    """One scenario input: a change applied to one economic variable.

    ``value`` is interpreted by ``change_type``: ``percent_change`` → percent (30 means
    +30 %); ``absolute_change`` → the variable's unit, which for rates is percentage
    points. Shock magnitudes are model parameters, not monetary amounts; they are
    stored as fixed-point NUMERIC with 4 decimal places.
    """

    __tablename__ = "scenario_shocks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scenario_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("scenarios.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int]
    variable_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("economic_variables.id", ondelete="RESTRICT")
    )
    change_type: Mapped[ChangeType] = mapped_column(enum_column(ChangeType, "change_type"))
    value: Mapped[float] = mapped_column(Numeric(14, 4, asdecimal=False))
    note: Mapped[str] = mapped_column(Text, default="")

    scenario: Mapped[Scenario] = relationship(back_populates="shocks")

    __table_args__ = (UniqueConstraint("scenario_id", "variable_id"),)
