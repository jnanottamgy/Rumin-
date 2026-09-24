""" "What caused this?" — the structured explanation of one line or metric of an execution.

Built only from what the execution and its model runs stored: the Lab's aggregation step,
each model's contribution to the line, and for each model its changes and inputs → the
equations on the path → the intermediate calculation steps → the graph relationships and
transmission paths → its output. With the model version and definition hash, the
assumptions and parameters (and whether each is a default), the data and graph snapshots,
the limitations and warnings. Nothing is generated: there is no text here that the engine
did not compute or a definition does not state.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any

from app.models import ScenarioExecution, SimulationRun, SimulationRunStep
from app.scenario_lab.aggregate import EQUATIONS, LINE_EQUATIONS, METRIC_LABELS
from app.scenario_lab.profiles import LINE_LABELS, PROFILES

METRIC_EQUATIONS = {"operating_margin": "AG6", "interest_coverage": "AG7"}
METRIC_TERMS = {
    "operating_margin": ("revenue", "operating_costs"),
    "interest_coverage": ("operating_profit", "interest_expense"),
}
LINE_TERMS = {
    "operating_profit": ("revenue", "operating_costs"),
    "profit_before_tax": ("operating_profit", "interest_expense"),
}
TARGETS = (*LINE_EQUATIONS, *METRIC_EQUATIONS)


def _equations_on_path(definition: Mapping[str, Any], outputs: set[str]) -> list[str]:
    """The equations a model evaluates between its changes and ``outputs``: those cited by
    every pathway link that leads to them, in the definition's order."""
    links = definition.get("pathway", [])
    targets = {f"output:{name}" for name in outputs}
    cited: set[str] = set()
    grew = True
    while grew:
        grew = False
        for link in links:
            if link["target"] in targets and link["source"] not in targets:
                targets.add(link["source"])
                grew = True
    for link in links:
        if link["target"] in targets:
            cited.update(link["equations"])
    for item in definition["outputs"]:
        if item["id"] in outputs:
            cited.add(item["equation"])
    return [equation["id"] for equation in definition["equations"] if equation["id"] in cited]


def _first_month(values: Sequence[str]) -> int | None:
    return next((month for month, value in enumerate(values, start=1) if Decimal(value) != 0), None)


def _model_part(
    run: SimulationRun,
    definition: Mapping[str, Any],
    steps: Sequence[SimulationRunStep],
    items: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    outputs = {item["output"] for item in items}
    equation_ids = _equations_on_path(definition, outputs)
    equations = {equation["id"]: equation for equation in definition["equations"]}
    statements = {item["id"]: item["text"] for item in definition.get("assumptions", [])}
    limits = {item["id"]: item["text"] for item in definition.get("limitations", [])}
    worked = None
    for item in items:
        series = run.monthly.get(item["monthly_output"], {}).get("values", [])
        month = _first_month(series)
        if month is not None and (worked is None or month < worked):
            worked = month
    chosen = [
        step
        for step in steps
        if step.equation_id in equation_ids and (step.month is None or step.month == worked)
    ]
    return {
        "model_id": run.model_id,
        "version": run.model_version,
        "run_id": str(run.id),
        "inputs_hash": run.inputs_hash,
        "result_hash": run.result_hash,
        "engine_version": run.engine_version,
        "items": [
            {
                "item": item["item"],
                "label": item["label"],
                "output": item["output"],
                "value": item["value"],
                "by_change": item["by_change"],
            }
            for item in items
        ],
        "changes": [entry for entry in run.inputs if entry["category"] == "scenario_input"],
        "inputs": [entry for entry in run.inputs if entry["category"] != "scenario_input"],
        "equations": [
            {
                "id": equation_id,
                "name": equations[equation_id]["name"],
                "formula": equations[equation_id]["formula"],
                "scope": equations[equation_id]["scope"],
                "explanation": equations[equation_id]["explanation"],
                "assumptions": [
                    {"id": key, "text": statements[key]}
                    for key in equations[equation_id]["assumptions"]
                    if key in statements
                ],
                "limitations": [
                    {"id": key, "text": limits[key]}
                    for key in equations[equation_id]["limitations"]
                    if key in limits
                ],
            }
            for equation_id in equation_ids
        ],
        "worked_month": worked,
        "steps": [
            {
                "sequence": step.sequence,
                "equation": step.equation_id,
                "label": step.label,
                "month": step.month,
                "output": {
                    "symbol": step.output_symbol,
                    "value": step.output_value,
                    "unit": step.output_unit,
                },
                "inputs": step.inputs,
            }
            for step in chosen
        ],
        "transmission": run.transmission,
        "graph": {
            "build_id": run.graph_snapshot.get("build_id"),
            "freshness": run.graph_snapshot.get("freshness"),
            "transmission": run.graph_snapshot.get("transmission", {}),
            "supporting": run.graph_snapshot.get("supporting", {}),
            "entity": run.graph_snapshot.get("entity"),
            "names": run.graph_snapshot.get("names", {}),
        },
        "data": run.data_snapshot,
        "assumptions": run.assumptions,
        "limitations": run.limitations,
        "warnings": run.warnings,
    }


def explain(
    execution: ScenarioExecution,
    target: str,
    runs: Mapping[str, SimulationRun],
    definitions: Mapping[str, Mapping[str, Any]],
    steps: Mapping[str, Sequence[SimulationRunStep]],
) -> dict[str, Any] | None:
    """The explanation of ``target`` (a line or a metric), or None if the execution has no
    such result."""
    results = execution.results or {}
    lines = {line["id"]: line for line in results.get("lines", [])}
    metrics = {metric["id"]: metric for metric in results.get("metrics", [])}
    if target in lines:
        result = lines[target]
        equation_id = LINE_EQUATIONS[target]
        label = LINE_LABELS[target]
        terms = [lines[name] for name in LINE_TERMS.get(target, ()) if name in lines]
        own_items = result["items"]
    elif target in metrics:
        result = metrics[target]
        equation_id = METRIC_EQUATIONS[target]
        label = METRIC_LABELS[target]
        terms = [lines[name] for name in METRIC_TERMS[target] if name in lines]
        own_items = []
    else:
        return None

    # The model items behind the target, through the lines it is made of.
    items_by_model: dict[str, list[dict[str, Any]]] = {}
    for line in [result] if own_items else terms:
        for item in line.get("items", []):
            items_by_model.setdefault(item["model_id"], []).append(item)
        for name in LINE_TERMS.get(line["id"], ()):
            for item in lines.get(name, {}).get("items", []):
                items_by_model.setdefault(item["model_id"], []).append(item)

    changes = {
        change["variable_id"]: change for change in (execution.plan or {}).get("changes", [])
    }
    by_change = result.get("by_change") or {}
    lab_steps = [
        step
        for step in results.get("steps", [])
        if step["equation"] == equation_id
        or step["equation"] in {LINE_EQUATIONS[term["id"]] for term in terms}
    ]
    equation = EQUATIONS[equation_id]
    return {
        "execution_id": str(execution.id),
        "target": target,
        "label": label,
        "result": result,
        "equation": {"id": equation_id, **equation},
        "terms": [
            {"id": term["id"], "label": term["label"], "change": term["change"]} for term in terms
        ],
        "by_change": [
            {
                "variable_id": variable,
                "name": changes.get(variable, {}).get("name", variable),
                "change": changes.get(variable, {}).get("value"),
                "unit": changes.get(variable, {}).get("unit"),
                "value": value,
            }
            for variable, value in by_change.items()
        ],
        "lab_steps": lab_steps,
        "models": [
            _model_part(runs[model_id], definitions[model_id], steps.get(model_id, []), items)
            for model_id, items in items_by_model.items()
            if model_id in runs
        ],
        "profiles": {
            model_id: {"title": PROFILES[model_id].title, "covers": PROFILES[model_id].covers}
            for model_id in items_by_model
            if model_id in PROFILES
        },
        "chain": [
            "Scenario changes and inputs",
            "Model equations",
            "Intermediate calculation steps",
            "Knowledge-graph relationships and transmission",
            "Model outputs",
            f"Lab aggregation ({equation_id})",
            label,
        ],
        "method": {
            "contributions": "Within each model, Shapley values over its non-zero changes; the "
            "Lab adds each change's credits across models. They add up to the line within "
            "rounding (10 decimal places).",
            "source": "Built from the stored execution and model runs; nothing is generated.",
        },
    }
