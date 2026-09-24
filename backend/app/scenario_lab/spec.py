"""A scenario version's content, as a typed document with a canonical form and a hash.

A version is stored as columns (name, description, template), one row per change, and a
JSON ``spec`` for everything else. Its **spec hash** is SHA-256 over the canonical JSON of
the whole document (sorted keys, decimals as plain strings), so two versions with the same
content — however the numbers were typed — have the same hash, and any difference changes
it.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Literal

from app.db.types import canonical_decimal
from app.domain.enums import ChangeType
from app.simulation.definitions import sha256

ModelMode = Literal["auto", "include", "exclude"]
Evidence = Literal["any", "evidence_backed"]
ValueSource = Literal["user", "stored_observation"]

DEFAULT_HORIZON = 12


def decimal_text(value: Decimal) -> str:
    """The canonical plain form: ``30.0000`` → ``30``, ``0.2500`` → ``0.25``."""
    return format(canonical_decimal(value), "f")


@dataclass(frozen=True)
class ShockSpec:
    """One change: a change type and a signed value on one economic variable."""

    variable_id: str
    change_type: ChangeType
    value: Decimal
    note: str = ""


@dataclass(frozen=True)
class ValueSpec:
    """A value for an input: typed (``value``, with ``unit`` for quantities) or the
    latest stored observation of a series (``source="stored_observation"``)."""

    value: str | None = None
    unit: str | None = None
    source: ValueSource | None = None
    series_id: str | None = None


@dataclass(frozen=True)
class ModelSettings:
    """What a scenario says about one model: whether to use it, and its own inputs and
    assumptions (decimal strings)."""

    mode: ModelMode = "auto"
    inputs: Mapping[str, ValueSpec] = field(default_factory=dict)
    assumptions: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class StressCaseSpec:
    """An alternative magnitude of the same changes: every change × ``scale``, or explicit
    values for some variables (the others keep the scenario's values)."""

    name: str
    scale: Decimal | None = None
    changes: Mapping[str, Decimal] = field(default_factory=dict)


@dataclass(frozen=True)
class ScenarioSpec:
    name: str
    description: str = ""
    template_id: str | None = None
    shocks: tuple[ShockSpec, ...] = ()
    entity: str | None = None
    start_month: int = 1
    duration_months: int = 0
    horizon_months: int = DEFAULT_HORIZON
    reporting_currency: str | None = None
    annual_revenue: str | None = None
    annual_operating_costs: str | None = None
    fx_rate: ValueSpec | None = None
    models: Mapping[str, ModelSettings] = field(default_factory=dict)
    evidence: Evidence = "any"
    stored_market_data: bool = False
    stress_cases: tuple[StressCaseSpec, ...] = ()

    def shock(self, variable_id: str) -> ShockSpec | None:
        return next((item for item in self.shocks if item.variable_id == variable_id), None)

    def settings(self, model_id: str) -> ModelSettings:
        return self.models.get(model_id, ModelSettings())

    @property
    def end_month(self) -> int:
        """The last month the changes last (the horizon's end unless a duration is set)."""
        if self.duration_months > 0:
            return self.start_month + self.duration_months - 1
        return self.horizon_months


# --- JSON forms --------------------------------------------------------------------------------


def value_json(value: ValueSpec | None) -> dict[str, Any] | None:
    if value is None:
        return None
    return {
        "value": value.value,
        "unit": value.unit,
        "source": value.source,
        "series_id": value.series_id,
    }


def shock_json(shock: ShockSpec) -> dict[str, Any]:
    return {
        "variable_id": shock.variable_id,
        "change_type": shock.change_type.value,
        "value": decimal_text(shock.value),
        "note": shock.note,
    }


def spec_json(spec: ScenarioSpec) -> dict[str, Any]:
    """The ``spec`` column: everything but the name, description, template and changes."""
    return {
        "entity": spec.entity,
        "timing": {
            "start_month": spec.start_month,
            "duration_months": spec.duration_months,
            "horizon_months": spec.horizon_months,
        },
        "company": {
            "reporting_currency": spec.reporting_currency,
            "annual_revenue": spec.annual_revenue,
            "annual_operating_costs": spec.annual_operating_costs,
        },
        "markets": {"fx_rate": value_json(spec.fx_rate)},
        "models": {
            model_id: {
                "mode": settings.mode,
                "inputs": {
                    name: value_json(item) for name, item in sorted(settings.inputs.items())
                },
                "assumptions": dict(sorted(settings.assumptions.items())),
            }
            for model_id, settings in sorted(spec.models.items())
        },
        "constraints": {
            "evidence": spec.evidence,
            "stored_market_data": spec.stored_market_data,
        },
        "stress_cases": [
            {
                "name": case.name,
                "scale": decimal_text(case.scale) if case.scale is not None else None,
                "changes": {
                    variable: decimal_text(value)
                    for variable, value in sorted(case.changes.items())
                },
            }
            for case in spec.stress_cases
        ],
    }


def document(spec: ScenarioSpec) -> dict[str, Any]:
    """The whole version as canonical, JSON-ready data (what the spec hash is over)."""
    return {
        "name": spec.name,
        "description": spec.description,
        "template_id": spec.template_id,
        "shocks": [shock_json(shock) for shock in spec.shocks],
        **spec_json(spec),
    }


def spec_hash(spec: ScenarioSpec) -> str:
    return sha256(document(spec))


def _value(data: Mapping[str, Any] | None) -> ValueSpec | None:
    if data is None:
        return None
    return ValueSpec(
        value=data.get("value"),
        unit=data.get("unit"),
        source=data.get("source"),
        series_id=data.get("series_id"),
    )


def from_parts(
    *,
    name: str,
    description: str,
    template_id: str | None,
    shocks: Iterable[ShockSpec],
    spec: Mapping[str, Any],
) -> ScenarioSpec:
    """The typed document from its stored parts (a version's columns, rows and JSON)."""
    timing = spec.get("timing", {})
    company = spec.get("company", {})
    constraints = spec.get("constraints", {})
    return ScenarioSpec(
        name=name,
        description=description,
        template_id=template_id,
        shocks=tuple(shocks),
        entity=spec.get("entity"),
        start_month=int(timing.get("start_month", 1)),
        duration_months=int(timing.get("duration_months", 0)),
        horizon_months=int(timing.get("horizon_months", DEFAULT_HORIZON)),
        reporting_currency=company.get("reporting_currency"),
        annual_revenue=company.get("annual_revenue"),
        annual_operating_costs=company.get("annual_operating_costs"),
        fx_rate=_value(spec.get("markets", {}).get("fx_rate")),
        models={
            model_id: ModelSettings(
                mode=item.get("mode", "auto"),
                inputs={
                    name: value
                    for name, raw in item.get("inputs", {}).items()
                    if (value := _value(raw)) is not None
                },
                assumptions=dict(item.get("assumptions", {})),
            )
            for model_id, item in spec.get("models", {}).items()
        },
        evidence=constraints.get("evidence", "any"),
        stored_market_data=bool(constraints.get("stored_market_data", False)),
        stress_cases=tuple(
            StressCaseSpec(
                name=case["name"],
                scale=Decimal(case["scale"]) if case.get("scale") is not None else None,
                changes={
                    variable: Decimal(value) for variable, value in case.get("changes", {}).items()
                },
            )
            for case in spec.get("stress_cases", [])
        ),
    )
