"""Structured explanations of a stored run — built from what the run stored, never
re-derived from the current code or data.

An explanation is data, not prose: the equations the run evaluated (with their
assumptions and limitations), every calculation step in order, the input-to-output
pathway (with the knowledge-graph relationships it used and their evidence), the
contribution of each scenario change to each output, the accounting bridge, the
assumptions with the values used, the limitations and the warnings.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.models import SimulationRun, SimulationRunStep
from app.simulation.decimal_math import ONE, arithmetic, exp, text, to_output


def _statements(definition: dict[str, Any], group: str) -> dict[str, str]:
    return {item["id"]: item["text"] for item in definition.get(group, [])}


def _variable_change(run: SimulationRun, node: str) -> str | None:
    """The steady-state relative change of a graph variable (e.g. jet fuel +30 %)."""
    logs = [Decimal(path["log_change"]) for path in run.transmission if path["nodes"][-1] == node]
    if not logs:
        return None
    with arithmetic():
        return text(to_output(exp(sum(logs, Decimal(0))) - ONE))


def pathway(run: SimulationRun, definition: dict[str, Any]) -> dict[str, Any]:
    inputs = {entry["id"]: entry for entry in run.inputs}
    outputs = {item["id"]: item for item in definition["outputs"]}
    names = run.graph_snapshot.get("names", {})
    rules = {rule["id"]: rule for rule in definition["transmission_rules"]}
    edges = run.graph_snapshot.get("transmission", {})
    nodes: dict[str, dict[str, Any]] = {}

    def node(end: str) -> None:
        if end in nodes:
            return
        kind, _, name = end.partition(":")
        if kind == "input":
            entry = inputs[name]
            nodes[end] = {
                "id": end,
                "kind": "input",
                "label": entry["label"],
                "value": entry["value"],
                "unit": entry["unit_label"],
                "knowledge": entry["knowledge"],
            }
        elif kind == "output":
            stored = run.outputs[name]
            nodes[end] = {
                "id": end,
                "kind": "output",
                "label": outputs[name]["label"],
                "value": stored["value"],
                "unit": stored["unit"],
                "knowledge": "simulated_output" if stored["kind"] == "simulated" else "derived",
            }
        else:
            change = _variable_change(run, end)
            nodes[end] = {
                "id": end,
                "kind": "variable",
                "label": names.get(end, end),
                "value": change,
                "unit": "relative change",
                # The variable's level under the scenario: a simulated value.
                "knowledge": "simulated_output" if change is not None else "derived",
            }

    links = []
    for link in definition.get("pathway", []):
        node(link["source"])
        node(link["target"])
        rule = rules.get(link["rule"]) if link.get("rule") else None
        coefficient = inputs[rule["coefficient_input"]]["value"] if rule else None
        lag = inputs[rule["lag_input"]]["value"] if rule and rule.get("lag_input") else None
        links.append(
            {
                "source": link["source"],
                "target": link["target"],
                "label": link["label"],
                "equations": link["equations"],
                "rule": link.get("rule"),
                "edge": edges.get(link["rule"]) if link.get("rule") else None,
                "coefficient": coefficient,
                "lag_months": lag,
            }
        )
    return {"nodes": list(nodes.values()), "links": links}


def explanation(
    run: SimulationRun, definition: dict[str, Any], steps: list[SimulationRunStep]
) -> dict[str, Any]:
    used = {step.equation_id for step in steps}
    assumptions = _statements(definition, "assumptions")
    limitations = _statements(definition, "limitations")
    input_labels = {entry["id"]: entry["label"] for entry in run.inputs}
    output_labels = {item["id"]: item["label"] for item in definition["outputs"]}
    return {
        "equations": [
            {
                **equation,
                "used": equation["id"] in used,
                "assumptions": [
                    {"id": key, "text": assumptions[key]} for key in equation["assumptions"]
                ],
                "limitations": [
                    {"id": key, "text": limitations[key]} for key in equation["limitations"]
                ],
            }
            for equation in definition["equations"]
        ],
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
            for step in steps
        ],
        "pathway": pathway(run, definition),
        "contributions": {
            output: {
                "label": output_labels.get(output, output),
                "items": [
                    {
                        "input": item["input"],
                        "label": input_labels.get(item["input"], item["input"]),
                        "value": item["value"],
                    }
                    for item in items
                ],
            }
            for output, items in run.contributions.items()
        },
        "bridge": run.bridge,
        "parameters": [
            {
                "id": entry["id"],
                "label": entry["label"],
                "value": entry["value"],
                "unit": entry["unit_label"],
                "default": entry["default"],
                "source": entry["source"],
                "changed_from_default": entry["source"] == "user"
                and entry["value"] != entry["default"],
                "rationale": entry["rationale"],
            }
            for entry in run.inputs
            if entry["category"] == "assumption"
        ],
        "assumptions": run.assumptions,
        "limitations": run.limitations,
        "warnings": run.warnings,
        "method": {
            "contributions": "Shapley values over the scenario's non-zero changes: each change "
            "is credited with its average marginal effect over every order of adding the "
            "changes. The credits add up to the total (within rounding to 10 decimal places).",
            "rounding": "Calculations use 34 significant digits; results are rounded half to "
            "even to 10 decimal places.",
        },
    }
