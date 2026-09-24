"""The scenario's impact pathway: how each change travelled to each line, as the engine
computed it.

The pathway is assembled from each included model's declared pathway (its definition) and
its run (the transmission paths, outputs and monthly series), then joined by the Lab's own
aggregation equations:

    change ─applies→ variable ─transmission (graph edge, β, lag)→ variable
           ─equation→ line item (a model output) ─aggregation (AG1–AG7)→ line → metric

Only links that carried the scenario's changes are included; every link says what it is
and how it was used (``simulation``): a knowledge-graph relationship the engine propagated
along, a model equation, the Lab's aggregation — or a relationship the graph states and the
Lab only *cites* as context (``context_only``), such as "jet fuel affects the costs of air
transport". The graph's other relationships from the changed variables are listed apart as
**not modelled**: a connection in the graph is not evidence of causation, and nothing is
drawn that the engine did not compute.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.domain.enums import GraphEdgeType
from app.domain.graph_types import EDGE_TYPES
from app.scenario_lab.aggregate import EQUATIONS, LINE_EQUATIONS, METRIC_LABELS, Aggregate
from app.scenario_lab.planner import ModelPlan, Plan
from app.scenario_lab.profiles import ITEMS, LINE_LABELS
from app.simulation.decimal_math import ONE, ZERO, arithmetic, exp, text, to_output
from app.simulation.definitions import InputCategory
from app.simulation.engine import Execution
from app.simulation.runtime import ResolvedValues

# The model outputs that are line items become nodes; a model's own totals (operating profit,
# interest expense, profit before tax) are replaced by the Lab's aggregation.


@dataclass(frozen=True)
class _End:
    node: str | None  # the pathway node, or None when the end is not drawn
    assumption: str | None = None  # an assumption input that modifies a link


def _map_end(ref: str, item: ModelPlan, values: ResolvedValues) -> _End:
    """Where one end of a model's declared pathway link sits in the scenario's pathway: a
    change node (a bound input the scenario changed), a model-scoped variable or line-item
    node, an assumption that modifies a link, or nothing (a model total the Lab replaces)."""
    definition = item.model.definition
    model_id = item.model_id
    kind, _, name = ref.partition(":")
    if kind == "input":
        binding = next((entry for entry in item.profile.shocks if entry.input_id == name), None)
        if binding is not None and values.numbers.get(name, ZERO) != ZERO:
            return _End(f"change:{binding.variable_id}")
        if definition.input(name).category is InputCategory.ASSUMPTION:
            return _End(None, assumption=name)
        return _End(None)
    if kind == "output":
        items = {contribution.output for contribution in item.profile.lines}
        return _End(f"{model_id}:output:{name}" if name in items else None)
    return _End(f"{model_id}:{ref}")


def _relation(edge_type: str) -> str:
    return EDGE_TYPES[GraphEdgeType(edge_type)].label


def _variable_series(
    transmission: Sequence[Mapping[str, Any]], node: str, horizon: int
) -> tuple[list[Decimal], Decimal, int | None, str]:
    """A variable's monthly change, its run-rate change and first month, from the run's
    transmission paths: relative changes for prices, percentage points for rates."""
    paths = [path for path in transmission if path["nodes"][-1] == node]
    kind = paths[0]["kind"] if paths else "log"
    with arithmetic():
        logs = [ZERO] * horizon
        for path in paths:
            last = horizon if path["last_month"] is None else min(path["last_month"], horizon)
            for month in range(max(path["first_month"], 1), last + 1):
                logs[month - 1] += Decimal(path["log_change"])
        total = sum((Decimal(path["log_change"]) for path in paths), ZERO)
        if kind == "level":
            monthly = [to_output(value) for value in logs]
            run_rate = to_output(total)
        else:
            monthly = [to_output(exp(value) - ONE) for value in logs]
            run_rate = to_output(exp(total) - ONE)
    first = min((path["first_month"] for path in paths), default=None)
    return monthly, run_rate, first, kind


def _first_month(values: Sequence[Decimal]) -> int | None:
    return next((month for month, value in enumerate(values, start=1) if value != 0), None)


def _assumption(item: ModelPlan, input_id: str) -> dict[str, Any] | None:
    if item.preparation is None or input_id not in item.preparation.resolved:
        return None
    entry = item.preparation.resolved[input_id]
    return {
        "id": entry.id,
        "label": entry.label,
        "value": entry.value,
        "unit": entry.unit_label,
        "source": entry.source.value,
        "default": entry.default,
    }


@dataclass
class Trace:
    """The pathway while it is being built: the models' part (``trace``), then the Lab's
    lines and metrics (``complete``)."""

    nodes: dict[str, dict[str, Any]]
    links: list[dict[str, Any]]
    used_edges: set[str]

    def add_node(self, node_id: str, **fields: Any) -> None:
        if node_id not in self.nodes:
            self.nodes[node_id] = {
                "id": node_id,
                "group": None,
                "value": None,
                "unit": None,
                "first_month": None,
                "monthly": None,
                "detail": None,
                **fields,
            }

    def add_link(self, source: str, target: str, **fields: Any) -> None:
        self.links.append(
            {
                "id": f"{source}→{target}",
                "source": source,
                "target": target,
                "group": None,
                "equations": [],
                "rule": None,
                "edge": None,
                "coefficient": None,
                "lag_months": None,
                "window": None,
                "assumptions": [],
                "statements": [],
                "sign": None,
                "active": True,
                **fields,
            }
        )


def _aggregation_equation(equation_id: str) -> list[dict[str, str]]:
    equation = EQUATIONS[equation_id]
    return [{"id": equation_id, "name": equation["name"], "formula": equation["formula"]}]


def trace(plan: Plan, executions: Mapping[str, Execution]) -> Trace:
    """Follow each change through every included model's run: the variables it moved (with
    the graph relationships and parameters that carried it) and the line items it changed,
    month by month."""
    spec = plan.spec
    horizon = spec.horizon_months
    state = Trace(nodes={}, links=[], used_edges=set())
    nodes = state.nodes
    add_node = state.add_node
    add_link = state.add_link
    used_edges = state.used_edges
    end_month = spec.end_month
    for change in plan.changes:
        if not change.modelled:
            continue
        add_node(
            f"change:{change.shock.variable_id}",
            kind="change",
            label=change.name,
            knowledge="scenario_input",
            value=text(change.shock.value),
            unit=change.unit,
            first_month=spec.start_month,
            detail=f"Months {spec.start_month}–{min(end_month, horizon)} of {horizon}",
        )

    for item in plan.included:
        execution = executions[item.model_id]
        definition = item.model.definition
        values = item.preparation.values if item.preparation else None
        if values is None:  # pragma: no cover - included models are prepared
            continue
        model_id = item.model_id
        line_outputs = {contribution.output: contribution for contribution in item.profile.lines}
        bound = {binding.input_id: binding.variable_id for binding in item.profile.shocks}
        statements = {statement.id: statement.text for statement in definition.assumptions}
        equations = {equation.id: equation for equation in definition.equations}

        def end(ref: str, item: ModelPlan = item, values: ResolvedValues = values) -> _End:
            return _map_end(ref, item, values)

        mapped: list[tuple[_End, _End, Any]] = [
            (end(link.source), end(link.target), link) for link in definition.pathway
        ]
        modifiers: dict[str, list[str]] = {}
        for source, target, _ in mapped:
            if source.assumption and target.node:
                modifiers.setdefault(target.node, []).append(source.assumption)

        # Only what the scenario's changes reach.
        reached = {
            f"change:{variable}"
            for input_id, variable in bound.items()
            if values.numbers.get(input_id, ZERO) != ZERO
        }
        grew = True
        while grew:
            grew = False
            for source, target, _ in mapped:
                if source.node in reached and target.node and target.node not in reached:
                    reached.add(target.node)
                    grew = True

        for source, target, link in mapped:
            if source.node not in reached or target.node not in reached:
                continue
            for ref, node_id in ((link.source, source.node), (link.target, target.node)):
                kind, _, name = ref.partition(":")
                if kind == "variable":
                    monthly, run_rate, first, shock_kind = _variable_series(
                        execution.transmission, ref, horizon
                    )
                    add_node(
                        node_id,
                        kind="variable",
                        label=plan.names.get(ref) or item.preparation.graph.names.get(ref, ref),  # type: ignore[union-attr]
                        group=model_id,
                        knowledge="simulated",
                        value=text(run_rate),
                        unit="percentage_points" if shock_kind == "level" else "ratio",
                        first_month=first,
                        monthly=[text(value) for value in monthly],
                        detail="Change while the scenario lasts, once every lag has elapsed",
                    )
                elif kind == "output":
                    contribution = line_outputs[name]
                    total = execution.outputs[name]["value"]
                    series = execution.monthly[contribution.monthly]["values"]
                    add_node(
                        node_id,
                        kind="driver",
                        label=contribution.label,
                        group=model_id,
                        knowledge="simulated",
                        value=text(total),
                        unit="currency",
                        first_month=_first_month(series),
                        monthly=[text(value) for value in series],
                        detail=f"{ITEMS[contribution.item]} — {LINE_LABELS[contribution.line]}",
                        line=contribution.line,
                        item=contribution.item,
                    )
            cited = sorted(
                {
                    statement
                    for equation_id in link.equations
                    for statement in equations[equation_id].assumptions
                }
            )
            fields: dict[str, Any] = {
                "group": model_id,
                "label": link.label,
                "equations": [
                    {
                        "id": equation_id,
                        "name": equations[equation_id].name,
                        "formula": equations[equation_id].formula,
                    }
                    for equation_id in link.equations
                ],
                "statements": [{"id": key, "text": statements[key]} for key in cited],
                "assumptions": [
                    entry
                    for name in modifiers.get(target.node or "", [])
                    if (entry := _assumption(item, name)) is not None
                ],
            }
            target_node = nodes.get(target.node or "")
            if target_node is not None and target_node["kind"] == "driver":
                fields["active"] = target_node["first_month"] is not None
            if link.rule:
                rule = next(rule for rule in definition.transmission_rules if rule.id == link.rule)
                edge = item.preparation.graph.transmission.get(rule.id)  # type: ignore[union-attr]
                paths = [path for path in execution.transmission if rule.id in path["rules"]]
                if edge is not None:
                    used_edges.add(edge.edge_key)
                parameters = [
                    entry
                    for name in (rule.coefficient_input, rule.lag_input)
                    if name is not None and (entry := _assumption(item, name)) is not None
                ]
                fields.update(
                    kind="transmission",
                    simulation="propagated",
                    rule=rule.id,
                    edge={
                        "edge_key": edge.edge_key,
                        "edge_type": edge.edge_type,
                        "relationship": _relation(edge.edge_type),
                        "evidence_status": edge.evidence_status,
                        "is_illustrative": edge.is_illustrative,
                    }
                    if edge is not None
                    else None,
                    coefficient=text(values.number(rule.coefficient_input)),
                    lag_months=values.integer(rule.lag_input) if rule.lag_input else 0,
                    window={
                        "first_month": min((path["first_month"] for path in paths), default=None),
                        "last_month": max(
                            (path["last_month"] for path in paths if path["last_month"]),
                            default=None,
                        )
                        if all(path["last_month"] for path in paths)
                        else None,
                    },
                    assumptions=parameters + fields["assumptions"],
                )
            elif source.node and source.node.startswith("change:"):
                fields.update(
                    kind="applies",
                    simulation="applied",
                    window={
                        "first_month": spec.start_month,
                        "last_month": end_month if spec.duration_months else None,
                    },
                )
            else:
                fields.update(kind="equation", simulation="computed")
            if source.node is not None and target.node is not None:
                add_link(source.node, target.node, **fields)

        for contribution in item.profile.lines:
            driver = f"{model_id}:output:{contribution.output}"
            if driver not in nodes:
                continue
            add_link(
                driver,
                f"line:{contribution.line}",
                kind="aggregation",
                simulation="aggregated",
                label="adds to",
                equations=_aggregation_equation(LINE_EQUATIONS[contribution.line]),
                sign=1,
                group=model_id,
                active=nodes[driver]["first_month"] is not None,
            )

        # Context the graph states and the Lab cites: the exposure that made the model apply.
        for chain in item.exposure:
            for edge in chain:
                used_edges.add(edge.key)
                for key in (edge.source, edge.target):
                    kind, _, _ = key.partition(":")
                    node_id = f"{model_id}:{key}" if kind == "variable" else key
                    if node_id in nodes:
                        continue
                    add_node(
                        node_id,
                        kind="variable" if kind == "variable" else "context",
                        label=plan.names.get(key)
                        or item.preparation.graph.names.get(key)  # type: ignore[union-attr]
                        or (plan.entity.name if plan.entity and plan.entity.key == key else key),
                        group=model_id if kind == "variable" else None,
                        knowledge="graph_relationship" if kind != "variable" else "simulated",
                        detail=kind.capitalize(),
                    )
                origin = (
                    f"{model_id}:{edge.source}"
                    if edge.source.startswith("variable:")
                    else edge.source
                )
                add_link(
                    origin,
                    edge.target,
                    kind="cited",
                    simulation="context_only",
                    label=_relation(edge.edge_type),
                    group=model_id,
                    edge={
                        "edge_key": edge.key,
                        "edge_type": edge.edge_type,
                        "relationship": _relation(edge.edge_type),
                        "evidence_status": edge.evidence_status,
                        "is_illustrative": edge.is_illustrative,
                    },
                )

    return state


def complete(state: Trace, plan: Plan, result: Aggregate) -> dict[str, Any]:
    """Add the Lab's lines and metrics, and list what the graph states but no included
    model simulates."""
    nodes = state.nodes
    add_node = state.add_node
    add_link = state.add_link
    for line_id, line in result.lines.items():
        add_node(
            f"line:{line_id}",
            kind="line",
            label=LINE_LABELS[line_id],
            knowledge="simulated",
            value=text(to_output(line.change)),
            unit="currency",
            first_month=_first_month(line.monthly),
            monthly=[text(to_output(value)) for value in line.monthly],
            detail="Change over the horizon",
        )
    for source, target, sign in (
        ("revenue", "operating_profit", 1),
        ("operating_costs", "operating_profit", -1),
        ("operating_profit", "profit_before_tax", 1),
        ("interest_expense", "profit_before_tax", -1),
    ):
        if source in result.lines and target in result.lines:
            add_link(
                f"line:{source}",
                f"line:{target}",
                kind="aggregation",
                simulation="aggregated",
                label="adds to" if sign > 0 else "is deducted from",
                equations=_aggregation_equation(LINE_EQUATIONS[target]),
                sign=sign,
            )
    for metric_id, metric in result.metrics.items():
        add_node(
            f"metric:{metric_id}",
            kind="metric",
            label=METRIC_LABELS[metric_id],
            knowledge="simulated",
            value=text(to_output(metric.change)),
            unit="ratio_points" if metric.unit == "ratio" else metric.unit,
            detail="Change from the baseline",
        )
        sources = (
            ("revenue", "operating_costs")
            if metric_id == "operating_margin"
            else ("operating_profit", "interest_expense")
        )
        for source in sources:
            if source in result.lines:
                add_link(
                    f"line:{source}",
                    f"metric:{metric_id}",
                    kind="aggregation",
                    simulation="aggregated",
                    label="enters",
                    equations=_aggregation_equation(
                        "AG6" if metric_id == "operating_margin" else "AG7"
                    ),
                )

    unmodelled = [
        {
            **edge.to_json(),
            "relationship": _relation(edge.edge_type),
            "source_name": plan.names.get(edge.source, edge.source),
            "target_name": plan.names.get(edge.target, edge.target),
            "reason": "No included model simulates this relationship. The graph states it; "
            "it is not evidence of causation and nothing is computed along it.",
        }
        for edge in plan.ties
        if edge.key not in state.used_edges
    ]
    groups = [
        {
            "id": item.model_id,
            "title": item.profile.title,
            "version": item.model.definition.version,
            "nodes": [node_id for node_id, node in nodes.items() if node["group"] == item.model_id],
        }
        for item in plan.included
    ]
    return {
        "nodes": list(nodes.values()),
        "links": state.links,
        "groups": groups,
        "unmodelled": unmodelled,
        "note": "Links marked context_only are relationships the knowledge graph states; they "
        "decided which models apply and carry no values. Everything else was computed.",
    }
