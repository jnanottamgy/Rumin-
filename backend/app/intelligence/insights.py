"""Insight rules: statements built from findings, each with its evidence chain.

Every rule has an id (``E01`` …) and a documented purpose (``RULES``). A rule fills a sentence
template with computed values and attaches the chain of evidence — observations, calculations,
graph relationships, simulations — that produced them, the facts with their references, the
assumptions and limitations, and rule-based next steps. ``InsightDraft.build`` refuses an
insight without a chain. Rules never add a causal claim, a forecast or a recommendation.

Order (``KIND_ORDER``): new information first (observed changes, unusual moves, revisions),
then what the stored simulations say, then relationships and exposure, then coverage gaps.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from decimal import Decimal

from app.intelligence import fmt
from app.intelligence.drivers import ChangeInput, DriverAnalysis, LineDrivers
from app.intelligence.exposure import (
    INDUSTRY_NOTE,
    NO_CAUSATION,
    NOT_SIZE,
    ExposureMap,
    ExposurePath,
    WorkspaceExposure,
    reach_index,
    variable_exposure,
)
from app.intelligence.graphchanges import RelationshipChanges
from app.intelligence.graphview import EdgeInfo, NodeInfo
from app.intelligence.interpretation import Interpretation
from app.intelligence.model import (
    Basis,
    Fact,
    Insight,
    InsightDraft,
    ModelRef,
    NextStep,
    Period,
    Ref,
    RelationshipRef,
    Step,
)
from app.intelligence.series import Change, History, Revision
from app.intelligence.signals import Signal
from app.scenario_lab.templates import TEMPLATES
from app.simulation.decimal_math import HUNDRED, ZERO

KIND_ORDER = (
    "anomaly",
    "change",
    "exposure_change",
    "revision",
    "trend",
    "volatility",
    "impact",
    "interpretation",
    "contribution",
    "sensitivity",
    "scenario_change",
    "relationship_change",
    "cross_entity",
    "exposure",
    "dependency",
    "counterparty",
    "coverage",
)


@dataclass(frozen=True)
class RuleSpec:
    id: str
    kind: str
    title: str
    purpose: str


RULES: tuple[RuleSpec, ...] = (
    RuleSpec(
        "D01",
        "change",
        "Observed change",
        "The latest change of a series or instrument meets its threshold.",
    ),
    RuleSpec(
        "D02",
        "exposure_change",
        "Observed change on an exposure variable",
        "A detected change in a series recorded as a related measure of a variable that "
        "the graph states reaches companies; names the companies, claims no effect.",
    ),
    RuleSpec(
        "D03",
        "anomaly",
        "Unusual change",
        "The latest change is unusual against earlier changes (modified z-score).",
    ),
    RuleSpec(
        "D04",
        "trend",
        "Trend",
        "The latest window rises or falls with a t statistic beyond the critical value.",
    ),
    RuleSpec(
        "D05",
        "volatility",
        "High volatility",
        "The latest window moves more than most earlier windows.",
    ),
    RuleSpec("D06", "revision", "Data revision", "A stored value was replaced by a revised value."),
    RuleSpec(
        "S01",
        "impact",
        "Simulated impact",
        "The headline result of the latest stored execution for a company.",
    ),
    RuleSpec(
        "S02",
        "contribution",
        "Contributions to a line",
        "A line's change split by the scenario's changes, from stored contributions.",
    ),
    RuleSpec(
        "S03",
        "sensitivity",
        "Effect per unit of a change",
        "Each change's contribution to the headline divided by its size.",
    ),
    RuleSpec(
        "S04",
        "sensitivity",
        "Largest sensitivity",
        "The quantity with the largest spread in a stored sensitivity analysis.",
    ),
    RuleSpec(
        "S05",
        "scenario_change",
        "Change between executions",
        "How the headline moved between two executions of the same scenario.",
    ),
    RuleSpec(
        "S06",
        "interpretation",
        "Observed change through the models",
        "The latest observed change of a related series, applied to a stored "
        "scenario's figures and models: a model interpretation, computed on request and "
        "not stored.",
    ),
    RuleSpec(
        "G01",
        "relationship_change",
        "Relationship change",
        "An exposure-relevant edge the latest graph build added, changed or retired.",
    ),
    RuleSpec(
        "X01",
        "cross_entity",
        "Shared driver",
        "A variable that reaches two or more companies through validated relationships (at "
        "most 12, those reaching the most companies; the exposure matrix shows every one).",
    ),
    RuleSpec(
        "E01",
        "exposure",
        "Stated exposure",
        "A variable that reaches an entity through validated relationships.",
    ),
    RuleSpec(
        "E02",
        "dependency",
        "Concentrated dependency",
        "At least the threshold share of an entity's exposure paths (50 % by default) pass "
        "through one variable.",
    ),
    RuleSpec(
        "E03",
        "counterparty",
        "Supply and credit relationships",
        "The entity's suppliers, customers, lenders and borrowers in the graph.",
    ),
    RuleSpec(
        "C01",
        "coverage",
        "What is and is not covered",
        "Which of an entity's exposures are simulated, simulatable and backed by data.",
    ),
    RuleSpec(
        "C02",
        "coverage",
        "Stored data",
        "How much stored data the analysis can use, and what cannot be computed without it.",
    ),
)
RULE_BY_ID = {rule.id: rule for rule in RULES}

CHANNEL_WORD = {"costs": "costs", "revenue": "revenue", "financing": "financing costs"}
NOT_FORECAST = "Simulated under the scenario's changes, figures and assumptions: not a forecast."


def order(insights: Iterable[Insight]) -> list[Insight]:
    return sorted(insights, key=lambda i: (KIND_ORDER.index(i.kind), i.rule, i.headline))


# --- Shared pieces -------------------------------------------------------------------------


def node_ref(node: NodeInfo) -> Ref:
    return Ref("graph_node", node.key, node.name)


def build_ref(build_id: int | None) -> Ref:
    return Ref("graph_build", str(build_id), f"Build #{build_id}")


def relationship(edge: EdgeInfo, names: dict[str, str]) -> RelationshipRef:
    return RelationshipRef(
        edge_key=edge.key,
        edge_type=edge.edge_type,
        label=edge.label,
        source=edge.source,
        source_name=names.get(edge.source, edge.source),
        target=edge.target,
        target_name=names.get(edge.target, edge.target),
        evidence_status=edge.evidence_status,
        is_illustrative=edge.is_illustrative,
    )


def edge_step(edge: EdgeInfo, names: dict[str, str]) -> Step:
    text = (
        f"{names.get(edge.source, edge.source)} {edge.label} {names.get(edge.target, edge.target)}"
    )
    return Step(
        Basis.RELATIONSHIP, text, (Ref("graph_edge", edge.key, text),), edge.evidence_status
    )


def rationale(edge: EdgeInfo, names: dict[str, str]) -> str | None:
    if not edge.rationale:
        return None
    return (
        f"{names.get(edge.source, edge.source)} {edge.label} "
        f"{names.get(edge.target, edge.target)}: {edge.rationale}"
    )


def execution_ref(drivers: DriverAnalysis) -> Ref:
    e = drivers.execution
    return Ref("execution", e.id, f"{e.scenario_name} · version {e.version}")


def model_ref(drivers: DriverAnalysis) -> ModelRef:
    e = drivers.execution
    return ModelRef(
        "execution",
        e.id,
        f"{e.scenario_name}, version {e.version}",
        tuple(f"{m.model_id} {m.version}" for m in drivers.models),
    )


def templates_for(variable_id: str, model_id: str) -> list[tuple[str, str]]:
    """Templates that change ``variable_id`` with ``model_id`` (most specific first)."""
    found = [
        t
        for t in TEMPLATES
        if model_id in t.models and any(s.variable_id == variable_id for s in t.shocks)
    ]
    return [(t.id, t.title) for t in sorted(found, key=lambda t: (len(t.models), t.id))]


def _names(nodes: Iterable[NodeInfo]) -> dict[str, str]:
    return {node.key: node.name for node in nodes}


# --- Exposure (E01–E03, C01) -----------------------------------------------------------------


def describe_path(path: ExposurePath) -> str:
    channel = CHANNEL_WORD[path.channel]
    base = (
        "directly"
        if path.base == "direct"
        else f"through its industry, {path.industry.name if path.industry else 'its industry'}"
    )
    if path.directness != "upstream":
        return f"{channel} {base}"
    via = " and ".join(node.name for node in path.hops[1:])
    return f"{channel} through {via} (assumed to transmit), which reaches it {base}"


def exposure_insights(
    exposure: ExposureMap,
    drivers_variables: set[str],
    names: dict[str, str],
) -> list[Insight]:
    """E01: one insight per variable that starts a path to the entity."""
    by_origin: dict[str, list[ExposurePath]] = {}
    for path in exposure.paths:
        by_origin.setdefault(path.origin.key, []).append(path)
    found: list[Insight] = []
    entity = exposure.entity
    build = build_ref(exposure.build_id)
    for origin_key, paths in by_origin.items():
        origin = paths[0].origin
        described = [describe_path(p) for p in paths]
        headline = f"{entity.name} is exposed to {origin.name}"
        statement = (
            f"The knowledge graph states that {origin.name} reaches {entity.name}'s "
            f"{fmt.listing(described)}."
        )
        draft = InsightDraft(
            rule="E01",
            kind="exposure",
            headline=headline,
            statement=statement,
            subject=node_ref(entity),
            key={"origin": origin_key, "paths": [[e.key for e in p.edges] for p in paths]},
            period=Period("graph_build", f"Build #{exposure.build_id}"),
        )
        draft.chain.append(
            Step(Basis.RECORD, f"Knowledge-graph build #{exposure.build_id}", (build,))
        )
        seen: set[str] = set()
        for path in paths:
            for edge in path.edges:
                if edge.key in seen:
                    continue
                seen.add(edge.key)
                draft.chain.append(edge_step(edge, names))
                draft.relationships.append(relationship(edge, names))
                note = rationale(edge, names)
                if note:
                    draft.assumptions.append(note)
                if edge.caveat:
                    draft.limitations.append(f"{edge.label}: {edge.caveat}")
        draft.entities.extend([node_ref(entity), node_ref(origin)])
        draft.entities.extend(node_ref(n) for p in paths for n in p.hops[1:])
        draft.facts.append(Fact("Paths", str(len(paths)), "count", Basis.CALCULATION))
        draft.facts.append(
            Fact(
                "Channels", ", ".join(sorted({p.channel for p in paths})), None, Basis.RELATIONSHIP
            )
        )
        models = sorted({m for p in paths for m in p.models})
        draft.facts.append(
            Fact("Models that can simulate it", ", ".join(models) or "None", None, Basis.RECORD)
        )
        draft.limitations.extend([NOT_SIZE, NO_CAUSATION])
        if any(p.directness == "via_industry" or p.base == "via_industry" for p in paths):
            draft.limitations.append(INDUSTRY_NOTE)
        variable_id = origin_key.partition(":")[2]
        if not models:
            draft.next_steps.append(
                NextStep(
                    "model_gap",
                    f"No registered model simulates how {origin.name} reaches {entity.name}; its "
                    "size cannot be simulated yet.",
                    node_ref(origin),
                )
            )
        elif variable_id not in drivers_variables:
            for model_id in models:
                for template_id, title in templates_for(variable_id, model_id)[:1]:
                    draft.next_steps.append(
                        NextStep(
                            "run_template",
                            f"Simulate it: start the “{title}” template for {entity.name}.",
                            Ref("template", template_id, title),
                        )
                    )
        assumed: dict[str, str] = {}
        for path in paths:
            for edge in path.edges:
                if edge.evidence_status == "model_assumption":
                    assumed.setdefault(edge.key, edge_step(edge, names).text)
        if assumed:
            key, first = next(iter(assumed.items()))
            one = len(assumed) == 1
            quoted = fmt.listing([f"“{text}”" for text in assumed.values()])
            draft.next_steps.append(
                NextStep(
                    "find_evidence",
                    f"Recorded as {'a model assumption' if one else 'model assumptions'}: "
                    f"{quoted}. Look for a cited source before relying on "
                    f"{'it' if one else 'them'}.",
                    Ref("graph_edge", key, first),
                )
            )
        for measured in exposure.series:
            if measured.variable == origin_key and (
                measured.info is None or measured.info.observation_count == 0
            ):
                label = measured.info.name if measured.info else measured.series_key
                draft.next_steps.append(
                    NextStep(
                        "ingest_series",
                        f"No values are stored for {label}, recorded as a related measure of "
                        f"{origin.name}: retrieve it to see how it has moved.",
                        Ref(
                            "series",
                            measured.info.series_id if measured.info else measured.series_key,
                            label,
                        ),
                    )
                )
        draft.sources.append(build)
        found.append(draft.build())
    return found


def dependency_insight(
    exposure: ExposureMap, signal: Signal, names: dict[str, str]
) -> Insight | None:
    """E02: when the dependency signal is concentrated."""
    if signal.level != "concentrated":
        return None
    values = {fact.label: fact for fact in signal.values}
    leader = values.get("Most shared variable") or values["Most shared variables"]
    several = len(leader.refs) > 1
    share = Decimal(values["Share of paths"].value or "0")
    through = values["Paths through it"].value
    total = values["Exposure paths"].value
    threshold = signal.thresholds["dependency_share_percent"]
    entity = exposure.entity
    share_text = fmt.percent(share, sign=False)
    draft = InsightDraft(
        rule="E02",
        kind="dependency",
        headline=(
            f"{entity.name}'s stated exposures concentrate on {leader.value}"
            if several
            else f"{entity.name}'s stated exposures depend on {leader.value}"
        ),
        statement=(
            f"{leader.value} each lie on {through} of {entity.name}'s {total} exposure paths "
            f"({share_text} each)."
            if several
            else f"{through} of {entity.name}'s {total} exposure paths ({share_text}) pass "
            f"through {leader.value}."
        )
        + " This counts relationships, not money.",
        subject=node_ref(entity),
        key={"leader": leader.value, "through": through, "total": total},
        period=signal.period,
    )
    draft.chain.append(
        Step(
            Basis.RECORD,
            f"Knowledge-graph build #{exposure.build_id}",
            (build_ref(exposure.build_id),),
        )
    )
    for path in exposure.paths:
        for edge in path.edges:
            draft.chain.append(edge_step(edge, names))
            draft.relationships.append(relationship(edge, names))
            note = rationale(edge, names)
            if note:
                draft.assumptions.append(note)
    draft.chain.append(
        Step(
            Basis.CALCULATION,
            "Share of exposure paths through each variable",
            value=str(share),
            unit="percent",
        )
    )
    draft.chain.append(
        Step(
            Basis.THRESHOLD,
            f"Concentrated at or above {threshold} % of paths",
            (Ref("threshold", "dependency_share_percent"),),
            value=str(threshold),
            unit="percent",
        )
    )
    draft.facts.extend(signal.values)
    draft.entities.append(node_ref(entity))
    draft.entities.extend(leader.refs)
    draft.limitations.extend(signal.limitations)
    draft.sources.append(build_ref(exposure.build_id))
    return draft.build()


def counterparty_insight(exposure: ExposureMap, names: dict[str, str]) -> Insight | None:
    """E03: supply and credit relationships, with their caveats."""
    if not exposure.counterparties:
        return None
    entity = exposure.entity
    groups: dict[str, list[str]] = {}
    for item in exposure.counterparties:
        label = item.counterparty.name + (" (industry)" if item.level == "industry" else "")
        groups.setdefault(item.role, []).append(label)
    phrases = []
    for role, verb in (
        ("supplier", "is supplied by"),
        ("customer", "supplies"),
        ("lender", "borrows from"),
        ("borrower", "lends to"),
    ):
        if role in groups:
            phrases.append(f"{verb} {fmt.listing(groups[role])}")
    draft = InsightDraft(
        rule="E03",
        kind="counterparty",
        headline=f"{entity.name}'s supply and credit relationships",
        statement=f"In the knowledge graph, {entity.name} {fmt.listing(phrases)}.",
        subject=node_ref(entity),
        key=sorted(item.edge.key for item in exposure.counterparties),
        period=Period("graph_build", f"Build #{exposure.build_id}"),
    )
    draft.chain.append(
        Step(
            Basis.RECORD,
            f"Knowledge-graph build #{exposure.build_id}",
            (build_ref(exposure.build_id),),
        )
    )
    for item in exposure.counterparties:
        draft.chain.append(edge_step(item.edge, names))
        draft.relationships.append(relationship(item.edge, names))
        draft.entities.append(node_ref(item.counterparty))
        if item.edge.caveat:
            draft.limitations.append(f"{item.edge.label}: {item.edge.caveat}")
    draft.entities.insert(0, node_ref(entity))
    draft.limitations.append(NO_CAUSATION)
    return draft.build()


def coverage_insight(exposure: ExposureMap, drivers: DriverAnalysis | None) -> Insight | None:
    """C01: which exposures are simulated, simulatable, and backed by stored data."""
    if not exposure.paths:
        return None
    entity = exposure.entity
    origins = {p.origin.key: p.origin for p in exposure.paths}
    simulated = {f"variable:{c.variable_id}" for c in drivers.changes} if drivers else set()
    covered = [o for o in origins if o in simulated]
    simulatable = [o for o in origins if any(p.models for p in exposure.paths if p.origin.key == o)]
    with_data = {
        s.variable for s in exposure.series if s.info is not None and s.info.observation_count > 0
    }
    unstated = sorted(
        {c.name for c in drivers.changes if drivers.unstated_for(c.variable_id)}
        if drivers
        else set()
    )
    statement = (
        f"The knowledge graph states that {len(origins)} "
        f"variable{'s' if len(origins) != 1 else ''} reach {entity.name}: "
        f"{len(covered)} simulated in the latest stored execution, {len(simulatable)} "
        f"simulatable by a registered model, {len(with_data & set(origins))} with stored "
        "observations of a related series."
    )
    if unstated:
        statement += (
            f" The latest execution also simulates {fmt.listing(unstated)}, although the graph "
            f"states no exposure of {entity.name} to "
            f"{'it' if len(unstated) == 1 else 'them'}: that part of the result rests on the "
            "entered figures alone."
        )
    draft = InsightDraft(
        rule="C01",
        kind="coverage",
        headline=f"What RUMIN can say about {entity.name}",
        statement=statement,
        subject=node_ref(entity),
        key={
            "origins": sorted(origins),
            "covered": sorted(covered),
            "simulatable": sorted(simulatable),
            "data": sorted(with_data),
            "unstated": unstated,
        },
        period=Period("graph_build", f"Build #{exposure.build_id}"),
    )
    draft.chain.append(
        Step(
            Basis.RECORD,
            f"Knowledge-graph build #{exposure.build_id}",
            (build_ref(exposure.build_id),),
        )
    )
    if drivers:
        draft.chain.append(
            Step(
                Basis.RECORD,
                "The changes and models of the latest stored execution",
                (execution_ref(drivers),),
            )
        )
        draft.models.append(model_ref(drivers))
    draft.facts.extend(
        [
            Fact("Variables reaching the entity", str(len(origins)), "count", Basis.CALCULATION),
            Fact(
                "Simulated in the latest execution", str(len(covered)), "count", Basis.CALCULATION
            ),
            Fact(
                "Simulatable by a registered model",
                str(len(simulatable)),
                "count",
                Basis.CALCULATION,
            ),
            Fact(
                "With stored observations",
                str(len(with_data & set(origins))),
                "count",
                Basis.CALCULATION,
            ),
            Fact(
                "Simulated without a stated exposure",
                str(len(unstated)),
                "count",
                Basis.CALCULATION,
            ),
        ]
    )
    if drivers:
        draft.limitations.extend(u.message for u in drivers.unstated)
    draft.entities.append(node_ref(entity))
    if drivers is None:
        draft.next_steps.append(
            NextStep(
                "run_scenario",
                f"No execution is stored for {entity.name}: run a scenario to size its exposures.",
                node_ref(entity),
            )
        )
    elif drivers.sensitivity is None:
        draft.next_steps.append(sensitivity_step(drivers))
    draft.limitations.append(NOT_SIZE)
    return draft.build()


@dataclass(frozen=True)
class DataCoverage:
    series: int
    series_with_data: int
    observations: int
    instruments: int
    instruments_with_data: int
    related_series: int  # series recorded as a related measure of a variable
    related_with_data: int


def data_coverage_insight(data: DataCoverage) -> Insight:
    """C02: the stored data the analysis can use (workspace)."""
    if data.series_with_data == 0 and data.instruments_with_data == 0:
        statement = (
            f"No series or instrument has two or more stored values ({data.series} series "
            f"catalogued, {data.observations} values stored). Observed changes, trends, "
            "volatility, unusual moves and revisions cannot be computed; findings rest on "
            "the knowledge graph and stored simulations only."
        )
    else:
        statement = (
            f"{data.series_with_data} of {data.series} catalogued series and "
            f"{data.instruments_with_data} of {data.instruments} instruments have two or more "
            f"stored values; {data.related_with_data} of the {data.related_series} series "
            "recorded as related measures of economic variables do."
        )
    draft = InsightDraft(
        rule="C02",
        kind="coverage",
        headline="What the stored data can support",
        statement=statement,
        subject=Ref("catalogue", "data", "Data catalogue"),
        key={
            "series": data.series,
            "with_data": data.series_with_data,
            "observations": data.observations,
            "instruments": data.instruments,
            "instruments_with_data": data.instruments_with_data,
            "related": data.related_series,
            "related_with_data": data.related_with_data,
        },
        period=Period("analysis", "Stored at the time of analysis"),
    )
    draft.chain.append(
        Step(
            Basis.RECORD,
            f"Data catalogue: {data.series} series, {data.observations} stored values",
            (Ref("catalogue", "data", "Data catalogue"),),
            value=str(data.observations),
            unit="count",
        )
    )
    draft.facts.extend(
        [
            Fact("Series catalogued", str(data.series), "count", Basis.RECORD),
            Fact(
                "Series with two or more values", str(data.series_with_data), "count", Basis.RECORD
            ),
            Fact("Stored values", str(data.observations), "count", Basis.RECORD),
            Fact("Instruments", str(data.instruments), "count", Basis.RECORD),
            Fact(
                "Instruments with two or more bars",
                str(data.instruments_with_data),
                "count",
                Basis.RECORD,
            ),
            Fact(
                "Series related to economic variables",
                str(data.related_series),
                "count",
                Basis.RECORD,
            ),
            Fact(
                "Of which with two or more values",
                str(data.related_with_data),
                "count",
                Basis.RECORD,
            ),
        ]
    )
    draft.limitations.append("Only stored values are analysed: nothing is fetched or filled in.")
    if data.related_with_data < data.related_series:
        draft.next_steps.append(
            NextStep(
                "ingest_series",
                "Retrieve the series recorded as related measures of economic variables, so "
                "observed moves can be set beside the exposures that name them.",
                Ref("catalogue", "data", "Data catalogue"),
            )
        )
    return draft.build()


# --- Simulations (S01–S05) -------------------------------------------------------------------


MAX_ASSUMPTIONS = 12


def _simulation_context(
    draft: InsightDraft, drivers: DriverAnalysis, variable_ids: Iterable[str] | None = None
) -> None:
    """What every simulated finding rests on: the entered figures (a chain step), the runs'
    stated assumptions, and any change the graph does not state an exposure to."""
    figures = _figures_step(drivers)
    if figures:
        draft.chain.append(figures)
    draft.assumptions.extend(drivers.assumptions[:MAX_ASSUMPTIONS])
    if len(drivers.assumptions) > MAX_ASSUMPTIONS:
        draft.assumptions.append(
            f"… and {len(drivers.assumptions) - MAX_ASSUMPTIONS} more stated with the model runs."
        )
    wanted = set(variable_ids) if variable_ids is not None else None
    for item in drivers.unstated:
        if wanted is None or wanted & set(item.variable_ids):
            draft.limitations.append(item.message)
    draft.limitations.append(NOT_FORECAST)


def _figures_step(drivers: DriverAnalysis) -> Step | None:
    if not drivers.figures:
        return None
    text = "; ".join(f"{label} {value} {unit}".strip() for label, value, unit in drivers.figures)
    return Step(Basis.ASSUMPTION, f"Figures entered by the user: {text}", (execution_ref(drivers),))


def _graph_steps(
    paths: Sequence[ExposurePath], variables: Sequence[str], names: dict[str, str]
) -> list[tuple[Step, RelationshipRef]]:
    """Exposure edges that tie the scenario's changed variables to the entity."""
    wanted = {f"variable:{v}" for v in variables}
    found: list[tuple[Step, RelationshipRef]] = []
    seen: set[str] = set()
    for path in paths:
        if path.origin.key not in wanted:
            continue
        for edge in path.edges:
            if edge.key not in seen:
                seen.add(edge.key)
                found.append((edge_step(edge, names), relationship(edge, names)))
    return found


def sensitivity_step(drivers: DriverAnalysis) -> NextStep:
    """One wording for S01 and C01, so the gathered next steps name it once."""
    return NextStep(
        "run_sensitivity",
        "Run a sensitivity analysis on the latest execution to see which inputs and "
        "assumptions move its result most.",
        execution_ref(drivers),
    )


def size_of(change: ChangeInput) -> str:
    """A scenario change in its own terms: percent, or percentage points."""
    if change.change_type == "percent_change":
        return fmt.percent(change.value)
    return fmt.points(change.value)


def impact_insight(
    drivers: DriverAnalysis,
    entity: NodeInfo,
    paths: Sequence[ExposurePath],
    names: dict[str, str],
    not_modelled: Sequence[str],
) -> Insight | None:
    """S01: the headline line of the latest stored execution. ``paths`` are the entity's
    exposure paths: the ones from the changed variables join the chain, so the finding is
    the same in the workspace and in the entity's dossier."""
    if drivers.headline is None:
        return None
    line = drivers.line(drivers.headline)
    if line is None:
        return None
    e = drivers.execution
    pct = f" ({fmt.percent(line.percent_change)})" if line.percent_change is not None else ""
    changes = fmt.listing([f"{c.name} {size_of(c)}" for c in drivers.changes])
    draft = InsightDraft(
        rule="S01",
        kind="impact",
        headline=f"{line.label} {fmt.money(line.change, line.currency, sign=True)}{pct} "
        f"under “{e.scenario_name}”",
        statement=(
            f"In the stored execution of “{e.scenario_name}” (version {e.version}), with "
            f"{changes}, {entity.name}'s {line.label.lower()} changes by "
            f"{fmt.money(line.change, line.currency, sign=True)}{pct} over {e.horizon_months} "
            f"months, from a baseline of {fmt.money(line.baseline, line.currency)}."
        ),
        subject=node_ref(entity),
        key={"execution": e.id, "line": line.id},
        period=Period("scenario", f"{e.horizon_months} simulated months"),
    )
    for step, rel in _graph_steps(paths, [c.variable_id for c in drivers.changes], names):
        draft.chain.append(step)
        draft.relationships.append(rel)
    _simulation_context(draft, drivers)
    draft.chain.append(
        Step(
            Basis.SIMULATION,
            f"Stored execution: {line.label} {fmt.money(line.change, line.currency, sign=True)}",
            (
                execution_ref(drivers),
                *(Ref("run", m.run_id, f"{m.model_id} {m.version}") for m in drivers.models),
            ),
            value=str(line.change),
            unit=line.currency,
        )
    )
    draft.facts.extend(
        [
            Fact(
                f"{line.label}: baseline",
                str(line.baseline),
                line.currency,
                Basis.ASSUMPTION,
                (execution_ref(drivers),),
            ),
            Fact(
                f"{line.label}: change",
                str(line.change),
                line.currency,
                Basis.SIMULATION,
                (execution_ref(drivers),),
            ),
            *(
                [
                    Fact(
                        f"{line.label}: change in percent",
                        str(line.percent_change),
                        "percent",
                        Basis.CALCULATION,
                    )
                ]
                if line.percent_change is not None
                else []
            ),
        ]
    )
    draft.models.append(model_ref(drivers))
    draft.entities.append(node_ref(entity))
    draft.limitations.extend(f"Not modelled: {item}." for item in not_modelled)
    draft.sources.append(execution_ref(drivers))
    if drivers.sensitivity is None:
        draft.next_steps.append(sensitivity_step(drivers))
    return draft.build()


def contribution_insight(
    drivers: DriverAnalysis, line: LineDrivers, entity: NodeInfo
) -> Insight | None:
    """S02: a line's change split by the scenario's changes (points of its baseline)."""
    if not line.contributions or line.change == 0:
        return None
    pct = f" ({fmt.percent(line.percent_change)})" if line.percent_change is not None else ""
    total = fmt.money(line.change, line.currency, sign=True)
    parts = [
        f"{c.name} {fmt.money(c.value, line.currency, sign=True)}"
        + (
            f" ({fmt.percent(c.share_of_change, sign=False)} of the change)"
            if c.share_of_change is not None and ZERO <= c.share_of_change <= HUNDRED
            else ""
        )
        for c in line.contributions
    ]
    residual = (
        ""
        if line.residual == 0
        else (
            f" The contributions leave {fmt.money(line.residual, line.currency, sign=True)} "
            "unattributed."
        )
    )
    top = max(line.contributions, key=lambda c: abs(c.value))
    headline = (
        f"{line.label}: all of the {total} change comes from {top.name}"
        if len(line.contributions) == 1
        else f"{line.label}: {top.name} contributes "
        f"{fmt.money(top.value, line.currency, sign=True)} of the {total} change"
    )
    draft = InsightDraft(
        rule="S02",
        kind="contribution",
        headline=headline,
        statement=(
            f"For {entity.name}, the change in {line.label.lower()}, {total}{pct}, splits by "
            f"the scenario's changes into {fmt.listing(parts)}.{residual}"
        ),
        subject=node_ref(entity),
        key={"execution": drivers.execution.id, "line": line.id},
        period=Period("scenario", f"{drivers.execution.horizon_months} simulated months"),
    )
    draft.chain.append(
        Step(
            Basis.SIMULATION,
            f"Stored contributions to {line.label.lower()}",
            (execution_ref(drivers),),
            value=str(line.change),
            unit=line.currency,
        )
    )
    draft.chain.append(
        Step(Basis.CALCULATION, "Each contribution as a share of the change and of the baseline")
    )
    _simulation_context(draft, drivers, [c.variable_id for c in line.contributions])
    for c in line.contributions:
        draft.facts.append(
            Fact(
                f"{c.name}",
                str(c.value),
                line.currency,
                Basis.SIMULATION,
                (execution_ref(drivers),),
            )
        )
        if c.share_of_change is not None:
            draft.facts.append(
                Fact(
                    f"{c.name}: share of the change",
                    str(c.share_of_change),
                    "percent",
                    Basis.CALCULATION,
                )
            )
        if c.points_of_baseline is not None:
            draft.facts.append(
                Fact(
                    f"{c.name}: points of the baseline",
                    str(c.points_of_baseline),
                    "percent",
                    Basis.CALCULATION,
                )
            )
    draft.facts.append(Fact("Unattributed", str(line.residual), line.currency, Basis.CALCULATION))
    draft.models.append(model_ref(drivers))
    draft.entities.append(node_ref(entity))
    draft.limitations.append(
        "Contributions are Shapley credits: an interaction between two changes is split "
        "evenly between them."
    )
    return draft.build()


def per_unit_insights(drivers: DriverAnalysis, entity: NodeInfo) -> list[Insight]:
    """S03: each change's effect on the headline per 1 % or per percentage point."""
    if drivers.headline is None:
        return []
    line = drivers.line(drivers.headline)
    if line is None:
        return []
    changes = {c.variable_id: c for c in drivers.changes}
    found: list[Insight] = []
    for c in line.contributions:
        change = changes.get(c.variable_id)
        if c.per_unit is None or change is None:
            continue
        applied = (
            fmt.percent(change.value)
            if change.change_type == "percent_change"
            else fmt.points(change.value)
        )
        draft = InsightDraft(
            rule="S03",
            kind="sensitivity",
            headline=f"{line.label} per {c.per_unit_label} of {c.name}",
            statement=(
                f"Per {c.per_unit_label} of {c.name}, {entity.name}'s {line.label.lower()} "
                f"changes by {fmt.money(c.per_unit, line.currency, sign=True)} on average over "
                f"this scenario's {applied}."
            ),
            subject=node_ref(entity),
            key={"execution": drivers.execution.id, "line": line.id, "change": c.variable_id},
            period=Period("scenario", f"{drivers.execution.horizon_months} simulated months"),
        )
        draft.chain.append(
            Step(
                Basis.SIMULATION,
                f"Stored contribution of {c.name}",
                (execution_ref(drivers),),
                value=str(c.value),
                unit=line.currency,
            )
        )
        draft.chain.append(
            Step(
                Basis.CALCULATION,
                f"Contribution ÷ {applied}",
                value=str(c.per_unit),
                unit=line.currency,
            )
        )
        _simulation_context(draft, drivers, [c.variable_id])
        draft.facts.extend(
            [
                Fact(
                    "Contribution",
                    str(c.value),
                    line.currency,
                    Basis.SIMULATION,
                    (execution_ref(drivers),),
                ),
                Fact(
                    "Size of the change",
                    str(change.value),
                    "percent" if change.change_type == "percent_change" else change.unit,
                    Basis.ASSUMPTION,
                ),
                Fact(f"Per {c.per_unit_label}", str(c.per_unit), line.currency, Basis.CALCULATION),
            ]
        )
        draft.models.append(model_ref(drivers))
        draft.entities.append(node_ref(entity))
        draft.limitations.append(
            "An average over the scenario's change, not a slope: hedges, lags and "
            "compounding make the models non-linear."
        )
        found.append(draft.build())
    return found


def ranking_insight(drivers: DriverAnalysis, entity: NodeInfo) -> Insight | None:
    """S04: the largest spread in the latest stored sensitivity analysis."""
    ranking = drivers.sensitivity
    if ranking is None or not ranking.ranking:
        return None
    top = ranking.ranking[0]
    analysis = Ref("sensitivity_analysis", ranking.analysis_id, ranking.metric_label)
    draft = InsightDraft(
        rule="S04",
        kind="sensitivity",
        headline=f"{top.label} moves {ranking.metric_label.lower()} most",
        statement=(
            f"Of the {len(ranking.ranking)} quantities varied one at a time around the stored "
            f"execution, {top.label} moves {ranking.metric_label.lower()} the most (spread "
            f"{fmt.number(top.spread)})."
        ),
        subject=node_ref(entity),
        key={"analysis": ranking.analysis_id, "top": top.target},
        period=Period("scenario", f"{drivers.execution.horizon_months} simulated months"),
    )
    draft.chain.append(
        Step(
            Basis.SIMULATION,
            "Stored one-at-a-time sensitivity analysis",
            (analysis, execution_ref(drivers)),
        )
    )
    draft.facts.extend(
        Fact(item.label, str(item.spread), None, Basis.SIMULATION, (analysis,))
        for item in ranking.ranking
    )
    draft.models.append(model_ref(drivers))
    draft.entities.append(node_ref(entity))
    _simulation_context(draft, drivers)
    draft.limitations.append(
        "One at a time: each quantity moves alone; the spread says how much the result "
        "depends on it, not how likely any value is."
    )
    return draft.build()


def execution_change_insight(
    latest: DriverAnalysis, previous: DriverAnalysis, entity: NodeInfo
) -> Insight | None:
    """S05: the headline between two executions of the same scenario."""
    if latest.headline is None:
        return None
    now, before = latest.line(latest.headline), previous.line(latest.headline)
    if now is None or before is None or now.change == before.change:
        return None
    draft = InsightDraft(
        rule="S05",
        kind="scenario_change",
        headline=f"{now.label} under “{latest.execution.scenario_name}” moved between versions",
        statement=(
            f"The change in {now.label.lower()} moved from "
            f"{fmt.money(before.change, before.currency, sign=True)} (version "
            f"{previous.execution.version}) to {fmt.money(now.change, now.currency, sign=True)} "
            f"(version {latest.execution.version})."
        ),
        subject=node_ref(entity),
        key={"latest": latest.execution.id, "previous": previous.execution.id},
        period=Period(
            "scenario", f"Versions {previous.execution.version} and {latest.execution.version}"
        ),
    )
    draft.chain.extend(
        [
            Step(
                Basis.SIMULATION,
                f"Version {previous.execution.version}",
                (execution_ref(previous),),
                value=str(before.change),
                unit=before.currency,
            ),
            Step(
                Basis.SIMULATION,
                f"Version {latest.execution.version}",
                (execution_ref(latest),),
                value=str(now.change),
                unit=now.currency,
            ),
        ]
    )
    before_changes = {c.variable_id: c.value for c in previous.changes}
    for c in latest.changes:
        if before_changes.get(c.variable_id) != c.value:
            draft.facts.append(
                Fact(f"{c.name}: size of the change", str(c.value), c.unit, Basis.ASSUMPTION)
            )
    draft.models.extend([model_ref(previous), model_ref(latest)])
    draft.entities.append(node_ref(entity))
    _simulation_context(draft, latest)
    return draft.build()


# --- Observed data (D01–D06) -----------------------------------------------------------------


def _obs_ref(history: History, point_id: int, label: str) -> Ref:
    kind = "observation" if history.subject.kind == "series" else "price_bar"
    return Ref(kind, str(point_id), label)


def _data_limitations(history: History) -> list[str]:
    notes = []
    if history.subject.dataset.is_illustrative:
        notes.append(
            f"{history.subject.dataset.name} is sample or synthetic data, not real observations."
        )
    if history.subject.variable_relation:
        notes.append(
            f"Related to a variable, with a stated difference: {history.subject.variable_relation}"
        )
    return notes


def _change_steps(
    history: History, change: Change, threshold_name: str, threshold: Decimal
) -> list[Step]:
    unit = history.subject.unit
    return [
        Step(
            Basis.OBSERVATION,
            f"{history.subject.name}, {change.earlier.label}: "
            f"{fmt.stored(change.earlier.value)} {unit}",
            (
                _obs_ref(history, change.earlier.record_id, change.earlier.label),
                Ref("dataset", history.subject.dataset.id, history.subject.dataset.name),
            ),
            value=str(change.earlier.value),
            unit=unit,
        ),
        Step(
            Basis.OBSERVATION,
            f"{history.subject.name}, {change.later.label}: "
            f"{fmt.stored(change.later.value)} {unit}",
            (
                _obs_ref(history, change.later.record_id, change.later.label),
                Ref("dataset", history.subject.dataset.id, history.subject.dataset.name),
            ),
            value=str(change.later.value),
            unit=unit,
        ),
        Step(
            Basis.CALCULATION,
            f"Change: {fmt.change(change.value, history.subject.change_unit)}",
            value=str(change.value),
            unit=history.subject.change_unit,
        ),
        Step(
            Basis.THRESHOLD,
            f"Meets the {threshold_name.replace('_', ' ')} threshold of {fmt.number(threshold)}",
            (Ref("threshold", threshold_name),),
            value=str(threshold),
        ),
    ]


def change_insight(
    history: History, change: Change, threshold_name: str, threshold: Decimal
) -> Insight:
    """D01: the latest change meets its threshold."""
    verb = "rose" if change.value > 0 else "fell" if change.value < 0 else "did not change"
    magnitude = fmt.change(abs(change.value), history.subject.change_unit).lstrip("+")
    draft = InsightDraft(
        rule="D01",
        kind="change",
        headline=f"{history.subject.name} {verb} {magnitude}",
        statement=(
            f"{history.subject.name} {verb} from {fmt.stored(change.earlier.value)} in "
            f"{change.earlier.label} to {fmt.stored(change.later.value)} in "
            f"{change.later.label} ({fmt.change(change.value, history.subject.change_unit)}), "
            f"as stored."
        ),
        subject=history.subject.ref,
        key={"from": change.earlier.record_id, "to": change.later.record_id},
        period=Period(
            "observation",
            f"{change.earlier.label} to {change.later.label}",
            change.earlier.label,
            change.later.label,
        ),
    )
    draft.chain.extend(_change_steps(history, change, threshold_name, threshold))
    draft.facts.extend(
        [
            Fact(
                change.earlier.label,
                str(change.earlier.value),
                history.subject.unit,
                Basis.OBSERVATION,
                (_obs_ref(history, change.earlier.record_id, change.earlier.label),),
                change.earlier.label,
            ),
            Fact(
                change.later.label,
                str(change.later.value),
                history.subject.unit,
                Basis.OBSERVATION,
                (_obs_ref(history, change.later.record_id, change.later.label),),
                change.later.label,
            ),
            Fact("Change", str(change.value), history.subject.change_unit, Basis.CALCULATION),
            Fact("Threshold", str(threshold), history.subject.change_unit, Basis.THRESHOLD),
        ]
    )
    draft.assumptions.append(
        f"Detected because |change| ≥ {fmt.number(threshold)} "
        f"({history.subject.change_unit.replace('_', ' ')}), a configurable threshold."
    )
    draft.limitations.extend(_data_limitations(history))
    if change.flagged:
        draft.limitations.append(
            "At least one of the two values is flagged for review by the ingestion rules."
        )
    draft.sources.extend(
        [
            history.subject.ref,
            Ref("dataset", history.subject.dataset.id, history.subject.dataset.name),
        ]
    )
    return draft.build()


def exposure_change_insight(
    history: History,
    change: Change,
    threshold_name: str,
    threshold: Decimal,
    workspace: WorkspaceExposure,
    related_edge: EdgeInfo | None,
    names: dict[str, str],
) -> Insight | None:
    """D02: a detected change on a series recorded as a related measure of a variable that
    reaches companies. Names the companies; claims no effect."""
    if not history.subject.variable_id:
        return None
    variable_key = f"variable:{history.subject.variable_id}"
    reached = variable_exposure(workspace, variable_key)
    if not reached:
        return None
    variable_name = names.get(variable_key, history.subject.variable_id)
    companies = [company.name for company, _ in reached]
    draft = InsightDraft(
        rule="D02",
        kind="exposure_change",
        headline=f"{history.subject.name} moved; {len(companies)} companies are exposed to "
        f"{variable_name}",
        statement=(
            f"{history.subject.name} moved {fmt.change(change.value, history.subject.change_unit)} "
            f"from {change.earlier.label} to {change.later.label}. It is recorded as a related "
            f"measure of {variable_name}, which the graph states reaches "
            f"{fmt.listing(companies)}. This names who is exposed; it does not say the "
            "change affected them."
        ),
        subject=history.subject.ref,
        key={
            "from": change.earlier.record_id,
            "to": change.later.record_id,
            "variable": variable_key,
        },
        period=Period(
            "observation",
            f"{change.earlier.label} to {change.later.label}",
            change.earlier.label,
            change.later.label,
        ),
    )
    draft.chain.extend(_change_steps(history, change, threshold_name, threshold))
    if related_edge is not None:
        draft.chain.append(edge_step(related_edge, names))
        draft.relationships.append(relationship(related_edge, names))
    seen: set[str] = set()
    for company, paths in reached:
        draft.entities.append(node_ref(company))
        for path in paths:
            for edge in path.edges:
                if edge.key not in seen:
                    seen.add(edge.key)
                    draft.chain.append(edge_step(edge, names))
                    draft.relationships.append(relationship(edge, names))
    draft.facts.extend(
        [
            Fact("Change", str(change.value), history.subject.change_unit, Basis.CALCULATION),
            Fact("Companies reached", str(len(companies)), "count", Basis.CALCULATION),
        ]
    )
    draft.limitations.extend([*_data_limitations(history), NO_CAUSATION, NOT_SIZE])
    draft.sources.append(history.subject.ref)
    return draft.build()


def anomaly_insight(history: History, signal: Signal) -> Insight | None:
    """D03."""
    if signal.level != "unusual":
        return None
    values = {fact.label: fact for fact in signal.values}
    score = next((f.value for f in signal.values if f.label == "Modified z-score"), None)
    change_fact = signal.values[0]
    draft = InsightDraft(
        rule="D03",
        kind="anomaly",
        headline=f"Unusual change in {history.subject.name}",
        statement=(
            f"The latest change in {history.subject.name} "
            f"({fmt.change(Decimal(change_fact.value or '0'), history.subject.change_unit)}, "
            f"{signal.period.label}) is unusual against its "
            f"{values['Earlier changes compared'].value} earlier changes (modified z-score "
            f"{fmt.number(Decimal(score or '0'))})."
        ),
        subject=history.subject.ref,
        key={"period": signal.period.label, "score": score},
        period=signal.period,
    )
    draft.chain.extend(
        [
            Step(
                Basis.OBSERVATION,
                f"{len(history.points)} stored values of {history.subject.name}",
                (history.subject.ref,),
            ),
            Step(
                Basis.CALCULATION,
                "Modified z-score of the latest change against earlier ones",
                value=score,
                unit="score",
            ),
            Step(
                Basis.THRESHOLD,
                f"At or above {signal.thresholds['anomaly_score']}",
                (Ref("threshold", "anomaly_score"),),
                value=signal.thresholds["anomaly_score"],
            ),
        ]
    )
    draft.facts.extend(signal.values)
    draft.limitations.extend([*signal.limitations, *_data_limitations(history)])
    draft.sources.append(history.subject.ref)
    return draft.build()


def trend_insight(history: History, signal: Signal) -> Insight | None:
    """D04."""
    if signal.level not in ("rising", "falling"):
        return None
    slope = next(f for f in signal.values if f.label == "Slope per period")
    t_value = next((f.value for f in signal.values if f.label == "t statistic"), None)
    critical = next((f.value for f in signal.values if f.label == "Critical value"), None)
    draft = InsightDraft(
        rule="D04",
        kind="trend",
        headline=f"{history.subject.name} has been {signal.level}",
        statement=(
            f"{history.subject.name} has been {signal.level} over {signal.period.label}: "
            f"{fmt.signed_stored(Decimal(slope.value or '0'))} {history.subject.unit} "
            f"{fmt.PER_PERIOD.get(history.subject.frequency, 'per period')} "
            f"(t = {fmt.number(Decimal(t_value or '0'))}, critical value "
            f"{fmt.number(Decimal(critical or '0'), 3)})."
        ),
        subject=history.subject.ref,
        key={"period": signal.period.label, "slope": slope.value},
        period=signal.period,
    )
    draft.chain.extend(
        [
            Step(
                Basis.OBSERVATION,
                f"Stored values of {history.subject.name}, {signal.period.label}",
                (history.subject.ref,),
            ),
            Step(
                Basis.CALCULATION,
                "Least-squares slope and its t statistic",
                value=slope.value,
                unit=history.subject.unit,
            ),
            Step(
                Basis.THRESHOLD,
                f"|t| above the two-sided critical value at "
                f"{signal.thresholds['trend_significance']}",
                (Ref("threshold", "trend_significance"),),
                value=critical,
            ),
        ]
    )
    draft.facts.extend(signal.values)
    draft.limitations.extend([*signal.limitations, *_data_limitations(history)])
    draft.sources.append(history.subject.ref)
    return draft.build()


def volatility_insight(history: History, signal: Signal) -> Insight | None:
    """D05."""
    if signal.level != "high":
        return None
    values = {f.label: f for f in signal.values}
    percentile = values.get("Percentile among all windows")
    rank = percentile.value if percentile and percentile.value else "0"
    draft = InsightDraft(
        rule="D05",
        kind="volatility",
        headline=f"{history.subject.name} is moving more than usual",
        statement=(
            f"The standard deviation of {history.subject.name}'s changes over "
            f"{signal.period.label} is at the "
            f"{fmt.number(Decimal(rank), 0)}"
            f"th percentile of its {values['Earlier windows compared'].value} earlier windows."
        ),
        subject=history.subject.ref,
        key={"period": signal.period.label},
        period=signal.period,
    )
    draft.chain.extend(
        [
            Step(
                Basis.OBSERVATION,
                f"Stored values of {history.subject.name}",
                (history.subject.ref,),
            ),
            Step(Basis.CALCULATION, "Standard deviation of changes, ranked among earlier windows"),
            Step(
                Basis.THRESHOLD,
                f"At or above the {signal.thresholds['volatility_high_percentile']}th percentile",
                (Ref("threshold", "volatility_high_percentile"),),
            ),
        ]
    )
    draft.facts.extend(signal.values)
    draft.limitations.extend([*signal.limitations, *_data_limitations(history)])
    draft.sources.append(history.subject.ref)
    return draft.build()


def revision_insight(history: History, revision: Revision) -> Insight:
    """D06."""
    unit = history.subject.unit
    before = "missing" if revision.previous is None else f"{fmt.stored(revision.previous)} {unit}"
    after = "missing" if revision.revised is None else f"{fmt.stored(revision.revised)} {unit}"
    change = (
        ""
        if revision.change is None
        else (f" ({fmt.change(revision.change, history.subject.change_unit)})")
    )
    draft = InsightDraft(
        rule="D06",
        kind="revision",
        headline=f"{history.subject.name} {revision.label} was revised",
        statement=(
            f"The provider revised {history.subject.name} for {revision.label} from {before} to "
            f"{after}{change}. Both values are kept."
        ),
        subject=history.subject.ref,
        key={"previous": revision.previous_id, "revised": revision.revised_id},
        period=Period("observation", revision.label, revision.label, revision.label),
    )
    draft.chain.extend(
        [
            Step(
                Basis.OBSERVATION,
                f"Revision {revision.previous_revision}: {before}",
                (Ref("observation", str(revision.previous_id), revision.label),),
                value=None if revision.previous is None else str(revision.previous),
                unit=unit,
            ),
            Step(
                Basis.OBSERVATION,
                f"Revision {revision.previous_revision + 1}: {after}",
                (Ref("observation", str(revision.revised_id), revision.label),),
                value=None if revision.revised is None else str(revision.revised),
                unit=unit,
            ),
        ]
    )
    if revision.change is not None:
        draft.chain.append(
            Step(
                Basis.CALCULATION,
                "Size of the revision",
                value=str(revision.change),
                unit=history.subject.change_unit,
            )
        )
        draft.facts.append(
            Fact("Revision", str(revision.change), history.subject.change_unit, Basis.CALCULATION)
        )
    draft.limitations.extend(_data_limitations(history))
    draft.next_steps.append(
        NextStep(
            "review_revision",
            "Check whether analyses that used the earlier value need redoing.",
            history.subject.ref,
        )
    )
    draft.sources.append(history.subject.ref)
    return draft.build()


# --- Graph records (G01, X01) ----------------------------------------------------------------


def relationship_change_insights(changes: RelationshipChanges) -> list[Insight]:
    """G01: exposure-relevant edges the latest build added, changed or retired."""
    if changes.build is None or changes.previous is None:
        return []
    found: list[Insight] = []
    build = build_ref(changes.build.id)
    for item in changes.edges:
        if not item.exposure_relevant:
            continue
        text = f"{item.source_name} {item.label} {item.target_name}"
        draft = InsightDraft(
            rule="G01",
            kind="relationship_change",
            headline=f"Relationship {item.change}: {text}",
            statement=(
                f"Graph build #{changes.build.id} {item.change} the relationship “{text}” "
                f"(recorded as {item.evidence_status.replace('_', ' ')}), compared with build "
                f"#{changes.previous.id}."
            ),
            subject=Ref("graph_edge", item.edge_key, text),
            key={"build": changes.build.id, "edge": item.edge_key, "change": item.change},
            period=Period("graph_build", f"Build #{changes.previous.id} to #{changes.build.id}"),
        )
        draft.chain.append(
            Step(Basis.RECORD, f"Build #{changes.build.id} {item.change} it", (build,))
        )
        draft.chain.append(
            Step(
                Basis.RELATIONSHIP, text, (Ref("graph_edge", item.edge_key),), item.evidence_status
            )
        )
        draft.entities.extend(
            [
                Ref("graph_node", item.source, item.source_name),
                Ref("graph_node", item.target, item.target_name),
            ]
        )
        draft.limitations.append(changes.note)
        draft.sources.append(build)
        found.append(draft.build())
    return found


MAX_SHARED_DRIVERS = 12


def shared_driver_insights(workspace: WorkspaceExposure, names: dict[str, str]) -> list[Insight]:
    """X01: variables that reach two or more companies — at most ``MAX_SHARED_DRIVERS``, those
    reaching the most companies (every variable stays in the exposure matrix)."""
    found: list[Insight] = []
    build = build_ref(workspace.build_id)
    index = reach_index(workspace)
    shared = [
        (variable, reached)
        for variable in workspace.variables
        if len(reached := index.get(variable.key, [])) >= 2
    ]
    shared.sort(key=lambda item: (-len(item[1]), item[0].name))
    for variable, reached in shared[:MAX_SHARED_DRIVERS]:
        by_channel: dict[str, list[str]] = {}
        for company, paths in reached:
            for channel in sorted({p.channel for p in paths}):
                by_channel.setdefault(channel, []).append(company.name)
        phrases = [
            f"the {CHANNEL_WORD[channel]} of {fmt.listing(names_)}"
            for channel, names_ in sorted(by_channel.items())
        ]
        reach = (
            phrases[0] if len(phrases) == 1 else "; ".join(phrases[:-1]) + f"; and {phrases[-1]}"
        )
        draft = InsightDraft(
            rule="X01",
            kind="cross_entity",
            headline=f"{variable.name} reaches {len(reached)} companies",
            statement=f"Through validated relationships, {variable.name} reaches {reach}.",
            subject=Ref("graph_node", variable.key, variable.name),
            key={"variable": variable.key, "companies": [company.key for company, _ in reached]},
            period=Period("graph_build", f"Build #{workspace.build_id}"),
        )
        draft.chain.append(
            Step(Basis.RECORD, f"Knowledge-graph build #{workspace.build_id}", (build,))
        )
        seen: set[str] = set()
        for company, paths in reached:
            draft.entities.append(Ref("graph_node", company.key, company.name))
            for path in paths:
                for edge in path.edges:
                    if edge.key not in seen:
                        seen.add(edge.key)
                        draft.chain.append(edge_step(edge, names))
                        draft.relationships.append(relationship(edge, names))
        draft.facts.append(Fact("Companies reached", str(len(reached)), "count", Basis.CALCULATION))
        draft.limitations.extend(
            [
                NOT_SIZE,
                NO_CAUSATION,
                "Companies can be exposed through opposite channels (costs "
                "for one, revenue for another).",
            ]
        )
        draft.sources.append(build)
        found.append(draft.build())
    return found


def names_of(*groups: Iterable[NodeInfo]) -> dict[str, str]:
    found: dict[str, str] = {}
    for group in groups:
        found.update(_names(group))
    return found


# --- Interpretation (S06) --------------------------------------------------------------------


def interpretation_insight(
    interp: Interpretation,
    history: History,
    entity: NodeInfo,
    related_edge: EdgeInfo | None,
    names: dict[str, str],
    horizon_months: int,
) -> Insight | None:
    """S06: the latest observed change of a related series, applied alone to a stored
    scenario's figures and models — computed on request, not stored."""
    if interp.headline is None:
        return None
    line = interp.line(interp.headline)
    if line is None:
        return None
    observed = interp.observed
    applied = (
        fmt.percent(interp.applied)
        if interp.applied_type == "percent_change"
        else fmt.points(interp.applied)
    )
    pct = f" ({fmt.percent(line.percent_change)})" if line.percent_change is not None else ""
    draft = InsightDraft(
        rule="S06",
        kind="interpretation",
        headline=f"{history.subject.name}'s latest change, through “{interp.scenario_name}”",
        statement=(
            f"Applied alone to the stored scenario “{interp.scenario_name}” (version "
            f"{interp.version}) for {entity.name}, the latest observed change in "
            f"{history.subject.name} ({fmt.change(observed.value, interp.observed_unit)}, "
            f"{observed.earlier.label} to {observed.later.label}; applied as {applied} to "
            f"{interp.variable_name}) gives a change in {line.label.lower()} of "
            f"{fmt.money(line.change, line.currency, sign=True)}{pct} over {horizon_months} "
            "months. This is a model interpretation computed on request, not stored, and not "
            "an observation."
        ),
        subject=node_ref(entity),
        key={
            "execution": interp.execution_id,
            "series": interp.series_id,
            "from": observed.earlier.record_id,
            "to": observed.later.record_id,
        },
        period=Period(
            "observation",
            f"{observed.earlier.label} to {observed.later.label}, applied over "
            f"{horizon_months} simulated months",
            observed.earlier.label,
            observed.later.label,
        ),
    )
    unit = history.subject.unit
    for point in (observed.earlier, observed.later):
        draft.chain.append(
            Step(
                Basis.OBSERVATION,
                f"{history.subject.name}, {point.label}: {fmt.stored(point.value)} {unit}",
                (_obs_ref(history, point.record_id, point.label),),
                value=str(point.value),
                unit=unit,
            )
        )
    draft.chain.append(
        Step(
            Basis.CALCULATION,
            f"Observed change: {fmt.change(observed.value, interp.observed_unit)}",
            value=str(observed.value),
            unit=interp.observed_unit,
        )
    )
    if related_edge is not None:
        draft.chain.append(edge_step(related_edge, names))
        draft.relationships.append(relationship(related_edge, names))
    draft.chain.append(
        Step(
            Basis.ASSUMPTION,
            f"Applied as {applied} to {interp.variable_name} (rounded to the four decimals "
            "the Lab accepts), with the stored scenario's figures, timing, models and "
            "assumptions",
            (Ref("execution", interp.execution_id, interp.scenario_name),),
            value=str(interp.applied),
        )
    )
    draft.chain.append(
        Step(
            Basis.SIMULATION,
            f"Preview through {', '.join(interp.models)}: {line.label} "
            f"{fmt.money(line.change, line.currency, sign=True)} (not stored)",
            (Ref("execution", interp.execution_id, interp.scenario_name),),
            value=str(line.change),
            unit=line.currency,
        )
    )
    draft.facts.extend(
        [
            Fact(
                observed.earlier.label,
                str(observed.earlier.value),
                unit,
                Basis.OBSERVATION,
                (_obs_ref(history, observed.earlier.record_id, observed.earlier.label),),
            ),
            Fact(
                observed.later.label,
                str(observed.later.value),
                unit,
                Basis.OBSERVATION,
                (_obs_ref(history, observed.later.record_id, observed.later.label),),
            ),
            Fact("Observed change", str(observed.value), interp.observed_unit, Basis.CALCULATION),
            Fact(
                "Applied change",
                str(interp.applied),
                "percent" if interp.applied_type == "percent_change" else "percentage_points",
                Basis.ASSUMPTION,
            ),
            *(
                Fact(f"{item.label}: change", str(item.change), item.currency, Basis.SIMULATION)
                for item in interp.lines
            ),
        ]
    )
    draft.models.append(
        ModelRef(
            "execution",
            interp.execution_id,
            f"{interp.scenario_name}, version {interp.version} (interpreted)",
            interp.models,
        )
    )
    draft.entities.extend(
        [
            node_ref(entity),
            Ref("graph_node", f"variable:{interp.variable_id}", interp.variable_name),
        ]
    )
    draft.limitations.extend(
        [
            interp.note,
            "The change is applied as a step for the scenario's timing: it assumes the "
            "observed change holds over the simulated months.",
            *_data_limitations(history),
        ]
    )
    draft.sources.extend([history.subject.ref, Ref("execution", interp.execution_id)])
    return draft.build()
