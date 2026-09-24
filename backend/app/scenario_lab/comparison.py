"""Comparing executions side by side.

2–6 completed executions: their changes, the models they used, every line and metric, the
differences against a chosen reference execution, the inputs and assumptions that differ,
the pathway links that differ and, where analysed, their sensitivity rankings.

Differences are computed only between executions with the same reporting currency and
horizon (nothing is converted); otherwise the values are shown side by side, not
differenced. Nothing is ranked and nothing is recommended: which result is preferable
depends on an objective the user has not stated.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any

from app.models import ScenarioExecution, ScenarioSensitivityAnalysis, SimulationRun
from app.scenario_lab.aggregate import LINE_EQUATIONS, METRIC_LABELS
from app.scenario_lab.inputs import SHARED_PATHS
from app.scenario_lab.profiles import LINE_LABELS
from app.simulation.decimal_math import HUNDRED, arithmetic, text, to_output

MIN_EXECUTIONS = 2
MAX_EXECUTIONS = 6
NOTE = (
    "Executions are shown side by side and differenced against the reference only when "
    "their currency and horizon match. Nothing is ranked or recommended: which result is "
    "preferable depends on an objective you have not stated."
)


def _difference(value: str | None, reference: str | None) -> dict[str, str | None] | None:
    if value is None or reference is None:
        return None
    with arithmetic():
        absolute = Decimal(value) - Decimal(reference)
        percent = (
            to_output(absolute / abs(Decimal(reference)) * HUNDRED)
            if Decimal(reference) != 0
            else None
        )
    return {
        "absolute": text(to_output(absolute)),
        "percent": text(percent) if percent is not None else None,
    }


def _summary(execution: ScenarioExecution, name: str) -> dict[str, Any]:
    results = execution.results or {}
    plan = execution.plan or {}
    return {
        "execution_id": str(execution.id),
        "scenario_id": str(execution.scenario_id),
        "scenario_name": name,
        "version": execution.version,
        "requested_at": execution.requested_at.isoformat(),
        "currency": results.get("currency"),
        "horizon_months": results.get("horizon_months"),
        "timing": results.get("timing"),
        "entity": results.get("entity"),
        "changes": plan.get("changes", []),
        "models": [
            {"model_id": model["model_id"], "version": model["version"], "title": model["title"]}
            for model in results.get("models", [])
        ],
        "result_hash": execution.result_hash,
    }


def compare(
    executions: Sequence[ScenarioExecution],
    names: Mapping[str, str],
    runs: Mapping[str, Sequence[SimulationRun]],
    analyses: Mapping[str, ScenarioSensitivityAnalysis | None],
    reference_id: str,
) -> dict[str, Any]:
    """``executions`` in the order to show them; ``names`` and ``runs`` by execution id."""
    summaries = [_summary(item, names[str(item.id)]) for item in executions]
    reference = next(item for item in summaries if item["execution_id"] == reference_id)
    comparable = {
        item["execution_id"]: item["currency"] == reference["currency"]
        and item["horizon_months"] == reference["horizon_months"]
        for item in summaries
    }

    def values_of(kind: str) -> dict[str, dict[str, dict[str, Any]]]:
        table: dict[str, dict[str, dict[str, Any]]] = {}
        for item in executions:
            for entry in (item.results or {}).get(kind, []):
                table.setdefault(entry["id"], {})[str(item.id)] = entry
        return table

    lines = values_of("lines")
    metrics = values_of("metrics")
    order = [key for key in LINE_EQUATIONS if key in lines]
    ref_key = reference_id

    def row(entries: dict[str, dict[str, Any]], field: str) -> list[dict[str, Any]]:
        reference_entry = entries.get(ref_key)
        cells = []
        for item in summaries:
            key = item["execution_id"]
            entry = entries.get(key)
            cells.append(
                {
                    "execution_id": key,
                    "baseline": entry.get("baseline") if entry else None,
                    "change": entry.get("change") if entry else None,
                    "scenario": entry.get("scenario") if entry else None,
                    "percent_change": entry.get("percent_change") if entry else None,
                    "modelled": entry is not None,
                    "difference": _difference(
                        entry.get(field) if entry else None,
                        reference_entry.get(field) if reference_entry else None,
                    )
                    if comparable[key] and key != ref_key
                    else None,
                }
            )
        return cells

    # Inputs that differ between executions using the same model. A figure shared by every
    # model (revenue, the exchange rate …) is compared once, as the scenario's; a model only
    # some executions used is shown by their model lists, not input by input.
    inputs: dict[tuple[str, str], dict[str, Any]] = {}
    for item in executions:
        for run in runs.get(str(item.id), []):
            for entry in run.inputs:
                if entry["category"] == "setting" or entry["id"] == "entity":
                    continue
                owner = "scenario" if entry["id"] in SHARED_PATHS else run.model_id
                record = inputs.setdefault(
                    (owner, entry["id"]),
                    {
                        "model_id": owner,
                        "input": entry["id"],
                        "label": entry["label"],
                        "category": entry["category"],
                        "values": {},
                    },
                )
                record["values"].setdefault(
                    str(item.id),
                    {
                        "value": entry["value"],
                        "unit": entry["unit_label"],
                        "source": entry["source"],
                    },
                )
    differing = [
        {**record, "values": [record["values"].get(item["execution_id"]) for item in summaries]}
        for record in inputs.values()
        if len(record["values"]) > 1
        and len({value["value"] for value in record["values"].values()}) > 1
    ]

    link_sets = {
        str(item.id): {
            link["id"]
            for link in (item.results or {}).get("pathway", {}).get("links", [])
            if link["simulation"] != "context_only"
        }
        for item in executions
    }
    all_links = sorted(set().union(*link_sets.values())) if link_sets else []
    pathway_differences = [
        {"link": link, "present": [link in link_sets[item["execution_id"]] for item in summaries]}
        for link in all_links
        if not all(link in link_sets[item["execution_id"]] for item in summaries)
    ]

    sensitivity = []
    for summary in summaries:
        analysis = analyses.get(summary["execution_id"])
        sensitivity.append(
            {
                "execution_id": summary["execution_id"],
                "metric": analysis.metric if analysis else None,
                "ranking": analysis.results.get("ranking", []) if analysis else [],
            }
        )

    return {
        "reference": reference_id,
        "executions": summaries,
        "comparable": comparable,
        "lines": [
            {"id": key, "label": LINE_LABELS[key], "values": row(lines[key], "change")}
            for key in order
        ],
        "metrics": [
            {"id": key, "label": METRIC_LABELS[key], "values": row(metrics[key], "scenario")}
            for key in METRIC_LABELS
            if key in metrics
        ],
        "inputs": sorted(differing, key=lambda record: (record["model_id"], record["input"])),
        "pathways": pathway_differences,
        "sensitivity": sensitivity,
        "note": NOTE,
    }
