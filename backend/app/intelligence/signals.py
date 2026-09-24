"""Signals: defined calculations, each with its method, inputs, period, evidence and limits.

A signal is not a score. Each one answers one question with a documented calculation and
reports the quantities it computed; where it names a level ("rising", "high", "unusual",
"concentrated"), the level comes from a configurable threshold that is recorded with it.
When the data are too short or the calculation is undefined, the signal says so instead of
guessing.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.intelligence.drivers import DriverAnalysis
from app.intelligence.exposure import ExposureMap
from app.intelligence.fmt import listing
from app.intelligence.model import (
    Basis,
    Evidence,
    Fact,
    Period,
    Ref,
    Step,
    evidence_of,
)
from app.intelligence.series import (
    AnomalyResult,
    History,
    TrendResult,
    VolatilityResult,
)
from app.intelligence.thresholds import Thresholds
from app.simulation.decimal_math import HUNDRED, ZERO, arithmetic, to_output


@dataclass(frozen=True)
class SignalSpec:
    id: str
    name: str
    subjects: tuple[str, ...]  # company | industry | series | instrument
    question: str
    definition: str
    method: str
    inputs: str
    levels: tuple[tuple[str, str], ...]
    thresholds: tuple[str, ...]
    limitations: tuple[str, ...]


SPECS: tuple[SignalSpec, ...] = (
    SignalSpec(
        "exposure_breadth",
        "Exposure breadth",
        ("company", "industry"),
        "How many economic variables reach this entity through validated relationships?",
        "The number of distinct economic variables on at least one validated exposure path "
        "to the entity, split by channel (costs, revenue, financing), by directness (direct, "
        "via the industry, upstream) and by evidence status.",
        "Count the variables and paths returned by the exposure analysis (validated edges of "
        "the latest completed build; at most two `influences` hops upstream).",
        "Knowledge-graph edges: affects_costs, affects_revenue, affects_financing, influences, "
        "in_industry.",
        (),
        (),
        (
            "Counts relationships, not money: two exposures with equal counts can differ by "
            "orders of magnitude.",
            "Only what the graph states is counted; an exposure the graph does not record is "
            "invisible.",
        ),
    ),
    SignalSpec(
        "dependency",
        "Dependency",
        ("company", "industry"),
        "Do the entity's stated exposures depend on one variable?",
        "The largest share of the entity's exposure paths that pass through a single "
        "variable, and its supply and credit counterparties by kind.",
        "For each variable, count the exposure paths that contain it; divide the largest "
        "count by the number of paths. Concentrated when the share is at or above the "
        "threshold.",
        "The exposure paths; supplies_to and lends_to edges.",
        (("concentrated", "Concentrated"), ("spread", "Spread")),
        ("dependency_share_percent",),
        (
            "A share of relationships, not of costs or revenue.",
            "Supply and credit relationships say nothing about size or terms.",
        ),
    ),
    SignalSpec(
        "trend",
        "Trend",
        ("series", "instrument"),
        "Has the series been rising or falling over the latest window?",
        "The ordinary least-squares slope of the latest window of values against their "
        "period, with its t statistic.",
        "slope = Σ(x−x̄)(y−ȳ) / Σ(x−x̄)²; t = slope / standard error. A direction is called "
        "only when |t| exceeds the two-sided critical value of Student's t with n−2 degrees "
        "of freedom at the chosen level; otherwise there is no clear direction.",
        "The latest window of current stored values (5 years, 8 quarters, 12 months or 20 "
        "trading days by default).",
        (
            ("rising", "Rising"),
            ("falling", "Falling"),
            ("no_clear_direction", "No clear direction"),
            ("exact_line", "On a straight line"),
        ),
        ("window", "trend_significance"),
        (
            "Describes the window; it is not a forecast.",
            "The test assumes independent, normally distributed residuals, which economic "
            "series often are not; small windows have little power.",
        ),
    ),
    SignalSpec(
        "volatility",
        "Volatility",
        ("series", "instrument"),
        "Is the series moving more than it usually does?",
        "The sample standard deviation of the changes in the latest window, compared with "
        "every earlier window of the same length in the series' own history.",
        "Changes are relative (percent) for levels, exchange rates and prices and in "
        "percentage points for series already in percent. The latest window's standard "
        "deviation is ranked among all windows; high when its percentile is at or above the "
        "threshold.",
        "Changes between consecutive current stored values.",
        (
            ("high", "High"),
            ("not_high", "Not high"),
            ("insufficient_history", "Too little history"),
        ),
        ("window", "volatility_high_percentile", "min_history"),
        (
            "Compares the series with its own past only.",
            "Overlapping windows are not independent; the percentile is descriptive.",
        ),
    ),
    SignalSpec(
        "anomaly",
        "Unusual change",
        ("series", "instrument"),
        "Is the latest change unusual against the series' earlier changes?",
        "The modified z-score of the latest change against all earlier changes.",
        "M = 0.6745 × (x − median) / MAD (Iglewicz and Hoaglin, 1993), where MAD is the "
        "median absolute deviation of the earlier changes. Unusual when |M| is at or above "
        "the threshold; undefined when MAD is zero.",
        "Changes between consecutive current stored values.",
        (
            ("unusual", "Unusual"),
            ("not_unusual", "Not unusual"),
            ("undefined", "Undefined"),
            ("insufficient_history", "Too little history"),
        ),
        ("anomaly_score", "min_history"),
        (
            "Unusual is not wrong: a real event can produce an unusual change, and data "
            "quality is judged separately by the ingestion rules.",
            "Needs enough earlier changes to be meaningful.",
        ),
    ),
    SignalSpec(
        "scenario_sensitivity",
        "Scenario sensitivity",
        ("company",),
        "In the latest stored execution for this company, which change moves the result "
        "most, and by how much per unit?",
        "Each change's contribution to the headline line (profit before tax, else operating "
        "profit), its share of the line's change, and its effect per 1 % (or per percentage "
        "point) of the change; with the stored one-at-a-time ranking when an analysis exists.",
        "Read from the execution's stored results: contributions are the models' Shapley "
        "credits per change. Per unit = contribution ÷ size of the change.",
        "A completed Scenario Lab execution and its stored sensitivity analyses.",
        (),
        (),
        (
            "Per-unit effects are averages over the scenario's change, not slopes: the "
            "models are not linear (hedges, lags, compounding).",
            "Conditional on the scenario's figures and assumptions.",
        ),
    ),
)
SPEC_BY_ID = {spec.id: spec for spec in SPECS}


@dataclass(frozen=True)
class Signal:
    id: str
    name: str
    subject: Ref
    status: str  # computed | insufficient_data | not_applicable
    level: str | None
    level_label: str | None
    summary: str
    values: tuple[Fact, ...]
    period: Period
    inputs: tuple[Ref, ...]
    thresholds: dict[str, Any]
    evidence: Evidence
    limitations: tuple[str, ...]


def _label(spec: SignalSpec, level: str | None) -> str | None:
    return dict(spec.levels).get(level or "", None) if level else None


def _calc(label: str, value: Decimal | int | None, unit: str | None, *refs: Ref) -> Fact:
    return Fact(label, None if value is None else str(value), unit, Basis.CALCULATION, refs)


def _data_evidence(history: History) -> Evidence:
    points = history.points
    steps = [
        Step(
            Basis.OBSERVATION,
            f"{len(points)} stored values of {history.subject.name}",
            (history.subject.ref,),
        ),
        Step(Basis.CALCULATION, "Exact calculation on the stored values"),
    ]
    return evidence_of(steps)


def _series_period(history: History, first: str, last: str) -> Period:
    return Period("observation", f"{first} to {last}", first, last)


def _unavailable(
    spec: SignalSpec,
    subject: Ref,
    summary: str,
    period: Period,
    evidence: Evidence,
    thresholds: dict[str, Any],
    status: str = "insufficient_data",
) -> Signal:
    return Signal(
        spec.id,
        spec.name,
        subject,
        status,
        None,
        None,
        summary,
        (),
        period,
        (),
        thresholds,
        evidence,
        spec.limitations,
    )


# --- Entity signals ------------------------------------------------------------------------


def _edge_steps(exposure: ExposureMap) -> list[Step]:
    """One relationship step per distinct edge on the entity's exposure paths, in words."""
    names = exposure.names
    steps: list[Step] = []
    seen: set[str] = set()
    for path in exposure.paths:
        for e in path.edges:
            if e.key in seen:
                continue
            seen.add(e.key)
            text = f"{names.get(e.source, e.source)} {e.label} {names.get(e.target, e.target)}"
            steps.append(
                Step(Basis.RELATIONSHIP, text, (Ref("graph_edge", e.key, text),), e.evidence_status)
            )
    return steps


def exposure_breadth(exposure: ExposureMap) -> Signal:
    spec = SPEC_BY_ID["exposure_breadth"]
    subject = Ref("graph_node", exposure.entity.key, exposure.entity.name)
    paths = exposure.paths
    variables = exposure.variables
    channels = Counter(p.channel for p in paths)
    directness = Counter(p.directness for p in paths)
    evidence_counts = Counter(p.evidence_status for p in paths)
    build = Ref("graph_build", str(exposure.build_id), f"Build #{exposure.build_id}")
    values = [
        _calc("Variables", len(variables), "count", build),
        _calc("Exposure paths", len(paths), "count", build),
        *(
            _calc(f"Paths to {name}", channels.get(name, 0), "count")
            for name in ("costs", "revenue", "financing")
        ),
        *(
            _calc(f"{label} paths", directness.get(key, 0), "count")
            for key, label in (
                ("direct", "Direct"),
                ("via_industry", "Via industry"),
                ("upstream", "Upstream"),
            )
        ),
        *(
            _calc(f"Paths resting on {status.replace('_', ' ')}", count, "count")
            for status, count in sorted(evidence_counts.items())
        ),
    ]
    steps = [
        Step(Basis.RECORD, f"Knowledge-graph build #{exposure.build_id}", (build,)),
        *_edge_steps(exposure),
    ]
    summary = (
        f"{len(variables)} variable{'s' if len(variables) != 1 else ''} reach "
        f"{exposure.entity.name} through {len(paths)} validated path"
        f"{'s' if len(paths) != 1 else ''}."
        if paths
        else f"The graph states no exposure for {exposure.entity.name}."
    )
    return Signal(
        spec.id,
        spec.name,
        subject,
        "computed",
        None,
        None,
        summary,
        tuple(values),
        Period("graph_build", f"Build #{exposure.build_id}"),
        (build,),
        {},
        evidence_of(steps),
        spec.limitations,
    )


def dependency(exposure: ExposureMap, thresholds: Thresholds) -> Signal:
    spec = SPEC_BY_ID["dependency"]
    subject = Ref("graph_node", exposure.entity.key, exposure.entity.name)
    build = Ref("graph_build", str(exposure.build_id), f"Build #{exposure.build_id}")
    period = Period("graph_build", f"Build #{exposure.build_id}")
    used = thresholds.pick("dependency_share_percent")
    record = evidence_of(
        [Step(Basis.RECORD, f"Knowledge-graph build #{exposure.build_id}", (build,))]
    )
    if not exposure.paths:
        return _unavailable(
            spec,
            subject,
            "No exposure path: dependency does not apply.",
            period,
            record,
            used,
            "not_applicable",
        )
    counts: Counter[str] = Counter()
    names: dict[str, str] = {}
    for path in exposure.paths:
        for node in {n.key: n for n in path.hops}.values():
            counts[node.key] += 1
            names[node.key] = node.name
    top = max(counts.values())
    leaders = sorted(
        (key for key, count in counts.items() if count == top), key=lambda key: names[key]
    )
    leader_names = listing([names[k] for k in leaders])
    with arithmetic():
        share = to_output(Decimal(top) / Decimal(len(exposure.paths)) * HUNDRED, "A share")
    level = "concentrated" if share >= thresholds.dependency_share_percent else "spread"
    roles = Counter(c.role for c in exposure.counterparties)
    values = [
        Fact(
            "Most shared variable" if len(leaders) == 1 else "Most shared variables",
            leader_names,
            None,
            Basis.CALCULATION,
            tuple(Ref("graph_node", k, names[k]) for k in leaders),
        ),
        _calc("Paths through it", top, "count"),
        _calc("Exposure paths", len(exposure.paths), "count"),
        _calc("Share of paths", share, "percent"),
        *(
            _calc(f"{role.capitalize()}s", roles.get(role, 0), "count")
            for role in ("supplier", "customer", "lender", "borrower")
        ),
    ]
    steps = [
        Step(Basis.RECORD, f"Knowledge-graph build #{exposure.build_id}", (build,)),
        *_edge_steps(exposure),
        Step(Basis.CALCULATION, "Share of exposure paths through each variable"),
    ]
    summary = (
        f"{top} of {len(exposure.paths)} exposure paths pass through {leader_names}."
        if len(leaders) == 1
        else f"{leader_names} each lie on {top} of {len(exposure.paths)} exposure paths."
    )
    return Signal(
        spec.id,
        spec.name,
        subject,
        "computed",
        level,
        _label(spec, level),
        summary,
        tuple(values),
        period,
        (build,),
        used,
        evidence_of(steps),
        spec.limitations,
    )


def scenario_sensitivity(drivers: DriverAnalysis | None, subject: Ref) -> Signal:
    spec = SPEC_BY_ID["scenario_sensitivity"]
    if drivers is None or drivers.headline is None:
        return _unavailable(
            spec,
            subject,
            "No completed execution is stored for this company.",
            Period("scenario", "No execution"),
            evidence_of([Step(Basis.RECORD, "No stored execution")]),
            {},
            "not_applicable",
        )
    line = drivers.line(drivers.headline)
    assert line is not None  # noqa: S101 - headline is chosen from the lines
    execution = Ref(
        "execution",
        drivers.execution.id,
        f"{drivers.execution.scenario_name} v{drivers.execution.version}",
    )
    values: list[Fact] = []
    for c in line.contributions:
        values.append(
            Fact(
                f"{c.name}: contribution",
                str(c.value),
                line.currency,
                Basis.SIMULATION,
                (execution,),
            )
        )
        if c.share_of_change is not None:
            values.append(_calc(f"{c.name}: share of the change", c.share_of_change, "percent"))
        if c.per_unit is not None:
            values.append(_calc(f"{c.name}: per {c.per_unit_label}", c.per_unit, line.currency))
    if drivers.sensitivity and drivers.sensitivity.ranking:
        top = drivers.sensitivity.ranking[0]
        values.append(
            Fact(
                "Largest spread in the stored sensitivity analysis",
                top.label,
                None,
                Basis.SIMULATION,
                (
                    Ref(
                        "sensitivity_analysis",
                        drivers.sensitivity.analysis_id,
                        drivers.sensitivity.metric_label,
                    ),
                ),
            )
        )
        values.append(Fact("Its spread", str(top.spread), None, Basis.SIMULATION))
    dominant = line.contributions[0] if line.contributions else None
    summary = (
        f"{dominant.name} contributes most to the change in {line.label.lower()}."
        if dominant
        else f"No change contributes to {line.label.lower()}."
    )
    steps = [
        Step(
            Basis.SIMULATION,
            f"Stored execution {drivers.execution.id}",
            (execution,),
            value=str(line.change),
            unit=line.currency,
        ),
        Step(Basis.CALCULATION, "Contribution ÷ size of each change"),
    ]
    return Signal(
        spec.id,
        spec.name,
        subject,
        "computed",
        None,
        None,
        summary,
        tuple(values),
        Period("scenario", f"{drivers.execution.horizon_months} simulated months"),
        (execution,),
        {},
        evidence_of(steps),
        spec.limitations,
    )


# --- Series signals ------------------------------------------------------------------------


def trend_signal(history: History, result: TrendResult | None, thresholds: Thresholds) -> Signal:
    spec = SPEC_BY_ID["trend"]
    used = thresholds.pick("window", "trend_significance")
    evidence = _data_evidence(history)
    if result is None:
        return _unavailable(
            spec,
            history.subject.ref,
            "Fewer than three values: no trend.",
            Period("observation", "Too few values"),
            evidence,
            used,
        )
    values = [
        _calc("Slope per period", result.slope, history.subject.unit),
        *(
            [
                _calc(
                    "Slope per period, relative to the window's mean",
                    result.relative_slope,
                    "percent",
                )
            ]
            if result.relative_slope is not None
            else []
        ),
        _calc("t statistic", result.t, None),
        _calc("Critical value", result.critical, None),
        _calc("Values in the window", result.n, "count"),
    ]
    summary = {
        "rising": f"Rising over {result.first} to {result.last}.",
        "falling": f"Falling over {result.first} to {result.last}.",
        "exact_line": f"On a straight line over {result.first} to {result.last}.",
    }.get(result.direction, f"No clear direction over {result.first} to {result.last}.")
    return Signal(
        spec.id,
        spec.name,
        history.subject.ref,
        "computed",
        result.direction,
        _label(spec, result.direction),
        summary,
        tuple(values),
        _series_period(history, result.first, result.last),
        (history.subject.ref,),
        used,
        evidence,
        spec.limitations,
    )


def volatility_signal(
    history: History, result: VolatilityResult | None, thresholds: Thresholds
) -> Signal:
    spec = SPEC_BY_ID["volatility"]
    used = thresholds.pick("window", "volatility_high_percentile", "min_history")
    evidence = _data_evidence(history)
    if result is None:
        return _unavailable(
            spec,
            history.subject.ref,
            "Too few changes for a window.",
            Period("observation", "Too few values"),
            evidence,
            used,
        )
    unit = history.subject.change_unit
    values = [
        _calc("Standard deviation of the latest window's changes", result.latest, unit),
        _calc("Earlier windows compared", result.windows, "count"),
        *(
            [_calc("Percentile among all windows", result.percentile, "percentile")]
            if result.percentile is not None
            else []
        ),
        *(
            [_calc("Median of earlier windows", result.median_earlier, unit)]
            if result.median_earlier is not None
            else []
        ),
    ]
    summary = {
        "high": "Moving more than in most earlier windows.",
        "not_high": "Not moving more than usual.",
    }.get(result.level, "Too little history to compare the latest window with.")
    return Signal(
        spec.id,
        spec.name,
        history.subject.ref,
        "computed" if result.level != "insufficient_history" else "insufficient_data",
        result.level,
        _label(spec, result.level),
        summary,
        tuple(values),
        _series_period(history, result.first, result.last),
        (history.subject.ref,),
        used,
        evidence,
        spec.limitations,
    )


def anomaly_signal(
    history: History, result: AnomalyResult | None, thresholds: Thresholds
) -> Signal:
    spec = SPEC_BY_ID["anomaly"]
    used = thresholds.pick("anomaly_score", "min_history")
    evidence = _data_evidence(history)
    if result is None:
        return _unavailable(
            spec,
            history.subject.ref,
            "No change to test.",
            Period("observation", "No change"),
            evidence,
            used,
        )
    change = result.change
    unit = history.subject.change_unit
    values = [
        _calc(
            f"Change {change.earlier.label} to {change.later.label}",
            change.value,
            unit,
            Ref(
                "observation" if history.subject.kind == "series" else "price_bar",
                str(change.later.record_id),
                change.later.label,
            ),
        ),
        _calc("Earlier changes compared", result.reference, "count"),
        *([_calc("Modified z-score", result.score, "score")] if result.score is not None else []),
    ]
    summary = {
        "unusual": "The latest change is unusual against earlier changes.",
        "not_unusual": "The latest change is within the usual range.",
        "undefined": "Earlier changes are all equal: the score is undefined.",
    }.get(result.level, "Too few earlier changes to compare with.")
    return Signal(
        spec.id,
        spec.name,
        history.subject.ref,
        "computed" if result.level in ("unusual", "not_unusual") else "insufficient_data",
        result.level,
        _label(spec, result.level),
        summary,
        tuple(values),
        Period(
            "observation",
            f"{change.earlier.label} to {change.later.label}",
            change.earlier.label,
            change.later.label,
        ),
        (history.subject.ref,),
        used,
        evidence,
        spec.limitations,
    )


def entity_signals(
    exposure: ExposureMap, drivers: DriverAnalysis | None, thresholds: Thresholds
) -> list[Signal]:
    subject = Ref("graph_node", exposure.entity.key, exposure.entity.name)
    found = [exposure_breadth(exposure), dependency(exposure, thresholds)]
    if exposure.entity.node_type == "company":
        found.append(scenario_sensitivity(drivers, subject))
    return found


def series_signals(
    history: History,
    trend_result: TrendResult | None,
    volatility_result: VolatilityResult | None,
    anomaly_result: AnomalyResult | None,
    thresholds: Thresholds,
) -> list[Signal]:
    return [
        trend_signal(history, trend_result, thresholds),
        volatility_signal(history, volatility_result, thresholds),
        anomaly_signal(history, anomaly_result, thresholds),
    ]


def total(values: Sequence[Decimal]) -> Decimal:
    with arithmetic():
        return sum(values, ZERO)
