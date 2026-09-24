"""How a scenario's content becomes each model's inputs — and how a model's input maps back
to the place in the scenario it came from.

A scenario states each shared figure once (the company, its reporting currency, revenue,
operating costs, the exchange rate, the timing); every model that takes the same input
receives the same value, with the same meaning and unit. A change on a graph variable goes
to the input a model's profile binds it to, and only if the kinds match (a percent change
to a percent input, percentage points to a rate input). Everything else a model needs is
that model's own input or assumption, stated in the scenario per model.

Nothing is filled in: a figure the scenario does not state is simply not passed, and the
model's validation reports it as missing (or uses the definition's stated default for an
assumption, recorded as a default).
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal

from app.scenario_lab.profiles import ScenarioProfile
from app.scenario_lab.spec import ScenarioSpec, ValueSpec, decimal_text
from app.simulation.definitions import InputCategory
from app.simulation.registry import RegisteredModel
from app.simulation.validation import InputValue

# Model inputs the scenario states once for every model, and where.
SHARED_PATHS: dict[str, str] = {
    "entity": "entity",
    "reporting_currency": "company.reporting_currency",
    "annual_revenue": "company.annual_revenue",
    "annual_operating_costs": "company.annual_operating_costs",
    "fx_rate": "markets.fx_rate",
}
TIMING_PATHS = ("timing.horizon_months", "timing.start_month", "timing.duration_months")


def _value(item: ValueSpec) -> InputValue:
    return InputValue(
        value=item.value, unit=item.unit, source=item.source, series_id=item.series_id
    )


def model_inputs(
    spec: ScenarioSpec,
    profile: ScenarioProfile,
    model: RegisteredModel,
    *,
    changes: Mapping[str, Decimal] | None = None,
) -> dict[str, InputValue]:
    """The raw inputs of one model for a scenario. ``changes`` replaces the values of some
    of the scenario's changes (a stress case), by variable id."""
    definition = model.definition
    ids = {item.id for item in definition.inputs}
    raw: dict[str, InputValue] = {}

    if spec.entity and "entity" in ids:
        raw["entity"] = InputValue(spec.entity)
    shared: dict[str, str | None] = {
        "reporting_currency": spec.reporting_currency,
        "annual_revenue": spec.annual_revenue,
        "annual_operating_costs": spec.annual_operating_costs,
    }
    for name, figure in shared.items():
        if name in ids and figure is not None:
            raw[name] = InputValue(figure)
    if "fx_rate" in ids and spec.fx_rate is not None:
        raw["fx_rate"] = _value(spec.fx_rate)

    raw[definition.horizon_input] = InputValue(spec.horizon_months)
    if definition.shock_start_input:
        raw[definition.shock_start_input] = InputValue(spec.start_month)
    if definition.shock_duration_input:
        raw[definition.shock_duration_input] = InputValue(spec.duration_months)

    for binding in profile.shocks:
        shock = spec.shock(binding.variable_id)
        if shock is None or shock.change_type is not binding.change_type:
            continue
        value = (changes or {}).get(binding.variable_id, shock.value)
        raw[binding.input_id] = InputValue(decimal_text(value))

    settings = spec.settings(profile.model_id)
    for name, item in settings.inputs.items():
        raw[name] = _value(item)
    for name, text in settings.assumptions.items():
        raw[name] = InputValue(text)
    return raw


def spec_path(
    spec: ScenarioSpec, profile: ScenarioProfile, model: RegisteredModel, input_id: str
) -> str:
    """Where a model input's value comes from in the scenario (for error fields)."""
    definition = model.definition
    if input_id in SHARED_PATHS:
        return SHARED_PATHS[input_id]
    if input_id == definition.horizon_input:
        return TIMING_PATHS[0]
    if input_id == definition.shock_start_input:
        return TIMING_PATHS[1]
    if input_id == definition.shock_duration_input:
        return TIMING_PATHS[2]
    for binding in profile.shocks:
        if binding.input_id == input_id:
            index = next(
                (
                    i
                    for i, shock in enumerate(spec.shocks)
                    if shock.variable_id == binding.variable_id
                ),
                None,
            )
            return f"shocks[{index}].value" if index is not None else "shocks"
    try:
        category = definition.input(input_id).category
    except KeyError:
        return f"models.{profile.model_id}.inputs.{input_id}"
    group = "assumptions" if category is InputCategory.ASSUMPTION else "inputs"
    return f"models.{profile.model_id}.{group}.{input_id}"


def own_inputs(model: RegisteredModel) -> list[str]:
    """The model's own figures (company inputs and market baselines it alone takes)."""
    return [
        item.id
        for item in model.definition.inputs
        if item.category in (InputCategory.COMPANY_INPUT, InputCategory.MARKET_BASELINE)
        and item.id not in SHARED_PATHS
    ]


def assumptions(model: RegisteredModel) -> list[str]:
    return [
        item.id for item in model.definition.inputs if item.category is InputCategory.ASSUMPTION
    ]
