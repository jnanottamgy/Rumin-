"""Analyses as JSON: the shape the API serves and a stored analysis keeps.

Decimals travel as exact strings in plain notation, dates as ISO 8601, and every reference
keeps its kind and id so a reader can follow a value back to its record. The same function
produces the live response and the stored snapshot, so a stored analysis reads exactly like
the analysis it records.

The **brief** is the structured object a future AI Analyst would receive about one entity:
observations, drivers, relationships, simulation results, assumptions, evidence and
limitations, each carrying its evidence grade, plus rules for narrating it. It holds no free
text written by a model: every sentence in it comes from a documented rule, and every number
from a stored record or an exact calculation.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import fields, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from app.db.types import canonical_decimal
from app.intelligence import INTELLIGENCE_VERSION
from app.intelligence.drivers import DriverAnalysis
from app.intelligence.engine import (
    BuildInfo,
    EntityAnalysis,
    SeriesAnalysis,
    WorkspaceAnalysis,
)
from app.intelligence.exposure import ExposureMap, ExposurePath, WorkspaceExposure, summary
from app.intelligence.insights import KIND_ORDER, RULE_BY_ID
from app.intelligence.model import EDGE_GRADE, GRADE_STRENGTH, Grade, Insight
from app.intelligence.series import Change, Subject
from app.intelligence.thresholds import Thresholds

MAX_POINTS = 400  # values of a history served with an analysis (the latest ones)
MAX_CHANGES = 60
BRIEF_FORMAT = "rumin.intelligence.brief/1"
NARRATION_RULES = (
    "Quote numbers only from the facts, steps and values given here; never compute, "
    "extrapolate or round them into new figures.",
    "Keep each statement's evidence grade beside it, and say 'simulated' for every value "
    "that comes from a model run: such values hold only under the scenario's inputs and "
    "assumptions and are not forecasts.",
    "A relationship in the knowledge graph says that an entity is exposed, never how much; "
    "do not describe it as a cause or give it a size.",
    "Do not add entities, relationships, data or assumptions that are not listed here; say "
    "what is not known instead.",
    "Recommendations are out of scope: next steps are the analytical checks listed here.",
)

_EXTRA: dict[type, tuple[str, ...]] = {Subject: ("change_unit",), Change: ("direction", "flagged")}


def data(value: Any) -> Any:
    """A JSON-ready copy of an engine value (see the module docstring)."""
    if is_dataclass(value) and not isinstance(value, type):
        found = {item.name: data(getattr(value, item.name)) for item in fields(value)}
        for name in _EXTRA.get(type(value), ()):
            found[name] = data(getattr(value, name))
        return found
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, Decimal):
        return format(canonical_decimal(value), "f")
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, tuple | list):
        return [data(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): data(item) for key, item in value.items()}
    return value


def build(info: BuildInfo) -> dict[str, Any]:
    return data(info)  # type: ignore[no-any-return]


def thresholds(used: Thresholds) -> dict[str, Any]:
    return used.to_json()


def insight(item: Insight) -> dict[str, Any]:
    found: dict[str, Any] = data(item)
    rule = RULE_BY_ID.get(item.rule)
    found["rule_title"] = rule.title if rule else item.rule
    return found


def insights(items: Iterable[Insight]) -> list[dict[str, Any]]:
    return [insight(item) for item in items]


def grade_counts(items: Sequence[Insight]) -> dict[str, int]:
    counts = Counter(item.evidence.grade.value for item in items)
    return {grade.value: counts.get(grade.value, 0) for grade in Grade}


def kind_counts(items: Sequence[Insight]) -> dict[str, int]:
    counts = Counter(item.kind for item in items)
    return {kind: counts[kind] for kind in KIND_ORDER if counts.get(kind)}


# --- Exposure ------------------------------------------------------------------------------


def exposure_map(found: ExposureMap) -> dict[str, Any]:
    result: dict[str, Any] = data(found)
    result["summary"] = summary(found.paths)
    result["variables"] = data(found.variables)
    return result


def _cell(company: str, variable: str, paths: Sequence[ExposurePath]) -> dict[str, Any]:
    weakest = min(
        (p.evidence_status for p in paths),
        key=lambda status: GRADE_STRENGTH[EDGE_GRADE.get(status, Grade.UNVERIFIED)],
    )
    return {
        "company": company,
        "variable": variable,
        "paths": len(paths),
        "channels": sorted({p.channel for p in paths}),
        "directness": sorted({p.directness for p in paths}),
        "evidence_status": weakest,
        "models": sorted({m for p in paths for m in p.models}),
    }


def exposure_matrix(workspace: WorkspaceExposure) -> dict[str, Any]:
    """Companies × variables: each cell lists the channels and path kinds through which the
    graph states the variable reaches the company (any variable on a path, origin or hop)."""
    cells: list[dict[str, Any]] = []
    for company in workspace.companies:
        by_variable: dict[str, list[ExposurePath]] = {}
        for path in workspace.paths.get(company.key, ()):
            for key in path.variable_keys:
                by_variable.setdefault(key, []).append(path)
        cells.extend(_cell(company.key, key, paths) for key, paths in sorted(by_variable.items()))
    return {
        "build_id": workspace.build_id,
        "companies": data(workspace.companies),
        "variables": data(workspace.variables),
        "cells": cells,
        "truncated": workspace.truncated,
    }


# --- Observed data -------------------------------------------------------------------------


def series_analysis(found: SeriesAnalysis, *, max_points: int = MAX_POINTS) -> dict[str, Any]:
    points = found.history.points
    changes = found.changes
    return {
        "subject": data(found.history.subject),
        "points": data(points[-max_points:]),
        "points_total": len(points),
        "changes": data(changes[-MAX_CHANGES:]),
        "changes_total": len(changes),
        "threshold_name": found.threshold_name,
        "threshold": data(found.threshold),
        "detected": data(found.detected),
        "latest": data(found.latest),
        "trend": data(found.trend),
        "volatility": data(found.volatility),
        "anomaly": data(found.anomaly),
        "revisions": data(found.revisions),
        "signals": data(found.signals),
    }


def series_summary(found: SeriesAnalysis) -> dict[str, Any]:
    """One line per series or instrument in the overview (no history)."""
    points = found.history.points
    levels = {signal.id: signal.level for signal in found.signals}
    return {
        "subject": data(found.history.subject),
        "points_total": len(points),
        "first": points[0].label if points else None,
        "last": points[-1].label if points else None,
        "latest_value": data(points[-1].value) if points else None,
        "latest": data(found.latest),
        "threshold_name": found.threshold_name,
        "threshold": data(found.threshold),
        "detected": len(found.detected),
        "latest_detected": found.latest is not None and found.latest in found.detected,
        "trend": levels.get("trend"),
        "volatility": levels.get("volatility"),
        "anomaly": levels.get("anomaly"),
        "revisions": len(found.revisions),
    }


# --- Simulations ---------------------------------------------------------------------------


def drivers(found: DriverAnalysis | None) -> dict[str, Any] | None:
    if found is None:
        return None
    result: dict[str, Any] = data(found)
    result["figures"] = [
        {"label": label, "value": value, "unit": unit} for label, value, unit in found.figures
    ]
    for line, source in zip(result["lines"], found.lines, strict=True):
        for item, item_source in zip(line["items"], source.items, strict=True):
            item["by_change"] = {key: data(value) for key, value in item_source.by_change}
    return result


def impact(found: DriverAnalysis) -> dict[str, Any] | None:
    """The headline line of an execution (for lists)."""
    line = found.line(found.headline) if found.headline else None
    if line is None:
        return None
    return {
        "entity_key": found.entity_key,
        "execution": data(found.execution),
        "line": line.id,
        "label": line.label,
        "currency": line.currency,
        "baseline": data(line.baseline),
        "change": data(line.change),
        "percent_change": data(line.percent_change),
        "changes": data(found.changes),
    }


# --- Analyses ------------------------------------------------------------------------------


def entity_analysis(found: EntityAnalysis) -> dict[str, Any]:
    return {
        "engine_version": INTELLIGENCE_VERSION,
        "entity": data(found.entity),
        "build": build(found.build),
        "thresholds": thresholds(found.thresholds),
        "exposure": exposure_map(found.exposure),
        "executions": data(found.executions),
        "drivers": drivers(found.drivers),
        "previous": drivers(found.previous),
        "series": [series_analysis(item) for item in found.series],
        "interpretations": data(found.interpretations),
        "not_interpreted": data(found.not_interpreted),
        "signals": data(found.signals),
        "insights": insights(found.insights),
        "grades": grade_counts(found.insights),
        "kinds": kind_counts(found.insights),
        "next_steps": data(found.next_steps),
    }


def workspace_analysis(found: WorkspaceAnalysis) -> dict[str, Any]:
    return {
        "engine_version": INTELLIGENCE_VERSION,
        "build": build(found.build),
        "thresholds": thresholds(found.thresholds),
        "coverage": data(found.coverage),
        "insights": insights(found.insights),
        "grades": grade_counts(found.insights),
        "kinds": kind_counts(found.insights),
        "next_steps": data(found.next_steps),
        "exposure": exposure_matrix(found.exposure),
        "series": [series_summary(item) for item in found.series],
        "instruments": [series_summary(item) for item in found.instruments],
        "relationships": data(found.relationships),
        "impacts": [
            item
            for item in (impact(found.drivers[key]) for key in sorted(found.drivers))
            if item is not None
        ],
    }


# --- The brief ------------------------------------------------------------------------------


def _unique(items: Iterable[str]) -> list[str]:
    seen: list[str] = []
    for item in items:
        if item not in seen:
            seen.append(item)
    return seen


def brief(found: EntityAnalysis, generated_at: datetime) -> dict[str, Any]:
    """The structured object a future AI Analyst would receive about one entity."""
    exposure = found.exposure
    relationships: dict[str, dict[str, Any]] = {}
    for edge in [
        *(e for p in exposure.paths for e in p.edges),
        *(c.edge for c in exposure.counterparties),
        *(e for link in exposure.context for e in link.edges),
    ]:
        relationships.setdefault(edge.key, data(edge))
    observations = [
        {
            "subject": data(item.history.subject),
            "latest_change": data(item.latest),
            "meets_threshold": item.latest is not None and item.latest in item.detected,
            "threshold": {"name": item.threshold_name, "value": data(item.threshold)},
            "signals": [
                {
                    "id": signal.id,
                    "status": signal.status,
                    "level": signal.level,
                    "summary": signal.summary,
                    "values": data(signal.values),
                    "evidence_grade": signal.evidence.grade.value,
                }
                for signal in item.signals
            ],
            "revisions": data(item.revisions),
            "evidence_grade": Grade.OBSERVED.value,
        }
        for item in found.series
    ]
    simulation = None
    if found.drivers is not None:
        d = found.drivers
        simulation = {
            "execution": data(d.execution),
            "changes": data(d.changes),
            "lines": [
                {
                    "id": line.id,
                    "label": line.label,
                    "currency": line.currency,
                    "baseline": data(line.baseline),
                    "change": data(line.change),
                    "scenario": data(line.scenario),
                    "percent_change": data(line.percent_change),
                }
                for line in d.lines
            ],
            "metrics": data(d.metrics),
            "not_modelled": list(d.not_modelled),
            "unstated_exposures": data(d.unstated),
            "interpretations": data(found.interpretations),
            "evidence_grade": Grade.SIMULATED.value,
        }
    driver_block = None
    if found.drivers is not None:
        d = found.drivers
        driver_block = {
            "headline": d.headline,
            "lines": [
                {
                    "id": line.id,
                    "label": line.label,
                    "change": data(line.change),
                    "currency": line.currency,
                    "contributions": data(line.contributions),
                    "unattributed": data(line.residual),
                }
                for line in d.lines
            ],
            "sensitivity": data(d.sensitivity),
            "method": "Shapley credits of the stored model runs, per scenario change.",
            "evidence_grade": Grade.SIMULATED.value,
        }
    assumptions = _unique(
        [
            *(a for item in found.insights for a in item.assumptions),
            *(found.drivers.assumptions if found.drivers else ()),
        ]
    )
    limitations = _unique(note for item in found.insights for note in item.limitations)
    return {
        "format": BRIEF_FORMAT,
        "engine_version": INTELLIGENCE_VERSION,
        "generated_at": generated_at.isoformat(),
        "entity": data(found.entity),
        "build": build(found.build),
        "thresholds": thresholds(found.thresholds),
        "observations": observations,
        "exposures": data(exposure.paths),
        "counterparties": data(exposure.counterparties),
        "context": data(exposure.context),
        "relationships": list(relationships.values()),
        "drivers": driver_block,
        "simulation_results": simulation,
        "figures_entered": (
            [
                {"label": label, "value": value, "unit": unit}
                for label, value, unit in found.drivers.figures
            ]
            if found.drivers
            else []
        ),
        "assumptions": assumptions,
        "evidence": [
            {
                "insight_id": item.id,
                "rule": item.rule,
                "kind": item.kind,
                "statement": item.statement,
                "grade": item.evidence.grade.value,
                "conditional_on_simulation": item.evidence.conditional_on_simulation,
                "facts": data(item.facts),
                "chain": data(item.chain),
            }
            for item in found.insights
        ],
        "limitations": limitations,
        "next_steps": data(found.next_steps),
        "narration_rules": list(NARRATION_RULES),
    }
