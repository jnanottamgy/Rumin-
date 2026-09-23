"""Helpers for simulation tests.

Every figure here is HYPOTHETICAL: round numbers chosen so that results can be worked out
by hand (a monthly fuel bill of exactly 5,000,000 INR). They describe no real airline and
are not market data.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from app.simulation.data_sources import StoredObservation
from app.simulation.decimal_math import OUTPUT_QUANTUM
from app.simulation.engine import Preparation, channel_issues
from app.simulation.graph_context import GraphContext, GraphEdgeRef
from app.simulation.models.airline_fuel_cost import BRENT, JET_FUEL
from app.simulation.registry import REGISTRY, RegisteredModel
from app.simulation.runtime import Issue
from app.simulation.validation import InputValue, validate_inputs


def _registered(model_id: str) -> RegisteredModel:
    model = REGISTRY.get(model_id)
    if model is None:
        raise RuntimeError(f"Model {model_id} is not registered.")
    return model


MODEL: RegisteredModel = _registered("airline_fuel_cost")

# 1,000 kL a year at 750 USD/kL and 80 INR per USD: 60,000,000 INR a year, 5,000,000 a month.
BASE: dict[str, dict[str, Any]] = {
    "crude_oil_change": {"value": "10"},
    "jet_fuel_price": {"value": "750", "unit": "usd_per_kilolitre"},
    "fx_rate": {"value": "80"},
    "reporting_currency": {"value": "INR"},
    "annual_revenue": {"value": "300000000"},
    "annual_operating_costs": {"value": "250000000"},
    "annual_fuel_consumption": {"value": "1000", "unit": "kilolitre"},
}
MONTHLY_FUEL = Decimal(5_000_000)


def inputs(**changes: Any) -> dict[str, dict[str, Any]]:
    """BASE with some inputs replaced (a plain value, a dict, or None to drop it)."""
    merged = dict(BASE)
    for name, value in changes.items():
        if value is None:
            merged.pop(name, None)
        elif isinstance(value, dict):
            merged[name] = value
        else:
            merged[name] = {"value": value}
    return merged


def raw(values: Mapping[str, Mapping[str, Any]]) -> dict[str, InputValue]:
    return {
        name: InputValue(
            value=item.get("value"),
            unit=item.get("unit"),
            source=item.get("source"),
            series_id=item.get("series_id"),
        )
        for name, item in values.items()
    }


def edge(evidence: str = "model_assumption") -> GraphEdgeRef:
    return GraphEdgeRef(
        rule="T1",
        role="transmission",
        edge_key="e-test-t1",
        edge_type="influences",
        source=BRENT,
        target=JET_FUEL,
        evidence_status=evidence,
        is_illustrative=True,
        description="Test edge.",
    )


def graph(*, confirmed: bool = True, evidence: str = "model_assumption") -> GraphContext:
    """A graph snapshot as ``load_graph_context`` would return it (no database)."""
    return GraphContext(
        build_id=1 if confirmed else None,
        build_finished_at="2026-09-23T12:00:00+00:00" if confirmed else None,
        source_fingerprint="0" * 64 if confirmed else None,
        freshness="current" if confirmed else "not_built",
        transmission={"T1": edge(evidence) if confirmed else None},
        supporting={"S1": None, "S3": None},
        entity=None,
        unused=(),
        unused_total=0,
        names={BRENT: "Brent crude oil price", JET_FUEL: "Jet fuel price"},
    )


def fx_observation(value: str = "80.123456789", unit: str = "INR per USD") -> StoredObservation:
    """A SYNTHETIC stored observation of the World Bank exchange-rate series."""
    return StoredObservation(
        series_id="wb-ind-pa-nus-fcrf",
        series_name="Official exchange rate (synthetic test value)",
        series_unit=unit,
        frequency="annual",
        period_label="2025",
        period_start=date(2025, 1, 1).isoformat(),
        value=Decimal(value),
        raw_value=value,
        quality_status="validated",
        revision=1,
        last_confirmed_at=datetime(2026, 9, 1, tzinfo=UTC).isoformat(),
        capture_id=None,
        job_id="00000000-0000-0000-0000-000000000000",
        dataset_id="worldbank-wdi",
        dataset_version="test",
        license="CC BY 4.0",
        attribution="Synthetic test value",
    )


def prepare_pure(
    values: Mapping[str, Mapping[str, Any]],
    *,
    context: GraphContext | None = None,
    observation: StoredObservation | None = None,
    model: RegisteredModel = MODEL,
) -> Preparation:
    """What ``engine.prepare`` does, with a given graph snapshot instead of a database."""
    context = context or graph()
    resolved, resolved_values, issues = validate_inputs(
        model.definition, raw(values), lookup=lambda _series: observation
    )
    if resolved_values is not None and not any(i.severity == "error" for i in issues):
        issues.extend(model.check(resolved_values))
        issues.extend(channel_issues(model, resolved_values, context))
    failed = any(issue.severity == "error" for issue in issues)
    return Preparation(model, resolved, None if failed else resolved_values, context, issues)


def codes(issues: list[Issue], severity: str | None = None) -> list[str]:
    return [issue.code for issue in issues if severity is None or issue.severity == severity]


def near(actual: Decimal | str, expected: Decimal, quanta: int = 1) -> bool:
    """Equal within ``quanta`` units of the output rounding (1e-10)."""
    return abs(Decimal(actual) - expected) <= OUTPUT_QUANTUM * quanta


def with_model(**changes: Any) -> RegisteredModel:
    """The airline model with a changed definition (for registry and conflict tests)."""
    return RegisteredModel(
        definition=replace(MODEL.definition, **changes), check=MODEL.check, compute=MODEL.compute
    )
