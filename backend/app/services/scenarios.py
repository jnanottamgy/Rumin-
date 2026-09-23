"""Scenario workspace: create, read, update and delete *draft* scenarios.

There is deliberately no "run" operation on a scenario. Simulation runs are a separate,
append-only resource (``/api/v1/simulations``, Phase 4); connecting drafts to runs is the
Scenario Lab (Phase 5).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import DomainValidationError, NotFoundError
from app.db.base import utcnow
from app.domain.enums import ScenarioStatus
from app.domain.scenario_rules import validate_change
from app.models import EconomicVariable, Scenario, ScenarioShock
from app.schemas.common import ErrorDetail
from app.schemas.scenario import ScenarioInput, ScenarioPage, ScenarioRead, ShockInput


def _validate_shocks(session: Session, shocks: Sequence[ShockInput]) -> None:
    """Apply the domain rules that need the database. Collects every problem at once."""
    requested = {shock.variable_id for shock in shocks}
    variables = {
        variable.id: variable
        for variable in session.scalars(
            select(EconomicVariable).where(EconomicVariable.id.in_(requested))
        )
    }

    details: list[ErrorDetail] = []
    first_index: dict[str, int] = {}
    for index, shock in enumerate(shocks):
        prefix = f"shocks[{index}]"
        if shock.variable_id in first_index:
            details.append(
                ErrorDetail(
                    location="body",
                    field=f"{prefix}.variable_id",
                    message=f"This variable is already changed by input "
                    f"{first_index[shock.variable_id] + 1}; combine them into one change.",
                    type="duplicate_variable",
                )
            )
            continue
        first_index[shock.variable_id] = index

        variable = variables.get(shock.variable_id)
        if variable is None:
            details.append(
                ErrorDetail(
                    location="body",
                    field=f"{prefix}.variable_id",
                    message=f"Unknown economic variable '{shock.variable_id}'.",
                    type="unknown_variable",
                )
            )
            continue

        violation = validate_change(
            variable.value_kind, variable.unit, shock.change_type, shock.value
        )
        if violation is not None:
            details.append(
                ErrorDetail(
                    location="body",
                    field=f"{prefix}.{violation.field}",
                    message=violation.message,
                    type="invalid_change",
                )
            )

    if details:
        raise DomainValidationError("The scenario inputs are invalid.", details=details)


def _build_shocks(shocks: Sequence[ShockInput]) -> list[ScenarioShock]:
    return [
        ScenarioShock(
            position=position,
            variable_id=shock.variable_id,
            change_type=shock.change_type,
            value=shock.value,
            note=shock.note,
        )
        for position, shock in enumerate(shocks)
    ]


def _get(session: Session, scenario_id: uuid.UUID) -> Scenario:
    scenario = session.get(Scenario, scenario_id)
    if scenario is None:
        raise NotFoundError(f"No scenario with ID '{scenario_id}'.")
    return scenario


def list_scenarios(session: Session, *, limit: int, offset: int) -> ScenarioPage:
    total = session.scalar(select(func.count()).select_from(Scenario)) or 0
    rows = session.scalars(
        select(Scenario)
        .order_by(Scenario.updated_at.desc(), Scenario.id)
        .limit(limit)
        .offset(offset)
    ).all()
    items = [ScenarioRead.model_validate(row) for row in rows]
    return ScenarioPage(items=items, total=total, limit=limit, offset=offset)


def get_scenario(session: Session, scenario_id: uuid.UUID) -> ScenarioRead:
    return ScenarioRead.model_validate(_get(session, scenario_id))


def create_scenario(session: Session, payload: ScenarioInput) -> ScenarioRead:
    _validate_shocks(session, payload.shocks)
    scenario = Scenario(
        name=payload.name,
        description=payload.description,
        status=ScenarioStatus.DRAFT,
        shocks=_build_shocks(payload.shocks),
    )
    session.add(scenario)
    session.commit()
    return ScenarioRead.model_validate(scenario)


def replace_scenario(
    session: Session, scenario_id: uuid.UUID, payload: ScenarioInput
) -> ScenarioRead:
    scenario = _get(session, scenario_id)
    _validate_shocks(session, payload.shocks)
    scenario.name = payload.name
    scenario.description = payload.description
    # Remove the old inputs first: inserting replacements for the same variables before
    # the old rows are deleted would violate UNIQUE(scenario_id, variable_id).
    scenario.shocks.clear()
    session.flush()
    scenario.shocks.extend(_build_shocks(payload.shocks))
    scenario.updated_at = utcnow()
    session.commit()
    return ScenarioRead.model_validate(scenario)


def delete_scenario(session: Session, scenario_id: uuid.UUID) -> None:
    session.delete(_get(session, scenario_id))
    session.commit()
