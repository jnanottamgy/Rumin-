"""Scenario request and response schemas.

Request schemas validate *shape* (types, lengths, finite numbers). Domain rules that need
the database — does the variable exist, is this kind of change allowed for it — are
checked in ``app.services.scenarios``.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field

from app.domain.enums import ChangeType, EpistemicCategory, ScenarioStatus
from app.domain.scenario_rules import MAX_SHOCKS_PER_SCENARIO
from app.schemas.common import ApiModel, EntityId, InputModel, Page, SafeText

FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]


class ShockInput(InputModel):
    variable_id: EntityId = Field(examples=["var_brent_crude"])
    change_type: ChangeType
    value: FiniteFloat = Field(
        description="Percent for `percent_change` (30 = +30 %); the variable's unit for "
        "`absolute_change` (percentage points for rates).",
        examples=[30],
    )
    note: SafeText = Field(default="", max_length=500)


class ScenarioInput(InputModel):
    """Body for creating a scenario, or replacing one with PUT."""

    name: SafeText = Field(min_length=1, max_length=120, examples=["Oil price shock"])
    description: SafeText = Field(default="", max_length=2000)
    shocks: list[ShockInput] = Field(min_length=1, max_length=MAX_SHOCKS_PER_SCENARIO)


class ShockRead(ApiModel):
    variable_id: str
    change_type: ChangeType
    value: float
    note: str
    epistemic_category: Literal[EpistemicCategory.SCENARIO_INPUT] = EpistemicCategory.SCENARIO_INPUT


class ScenarioRead(ApiModel):
    id: uuid.UUID
    name: str
    description: str
    status: ScenarioStatus
    shocks: list[ShockRead]
    latest_run: None = Field(
        default=None,
        description="Simulation results. Always null in Phase 1: no simulation engine exists "
        "yet, and RUMIN never shows results that were not computed.",
    )
    created_at: datetime
    updated_at: datetime


class ScenarioPage(Page[ScenarioRead]):
    """A page of scenarios."""
