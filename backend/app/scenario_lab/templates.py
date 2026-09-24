"""Scenario templates: ready-made starting points, each built on implemented models.

A template is a set of changes, the models that simulate them and suggested stress cases.
Everything else it shows — the inputs it requires and the ones that are optional, the
validation rules, the outputs to expect — is *derived* from the models' definitions and
scenario profiles, so a template can only offer what its models implement. A template
carries no company figures: RUMIN never fills those in.

Demand and supply-chain templates are listed as unavailable, with the reason: no
registered model simulates them.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal

from app.domain.enums import ChangeType
from app.scenario_lab.inputs import SHARED_PATHS, spec_path
from app.scenario_lab.profiles import ITEMS, LINE_LABELS, PROFILES, lab_model
from app.scenario_lab.spec import (
    ModelSettings,
    ScenarioSpec,
    ShockSpec,
    StressCaseSpec,
    decimal_text,
)
from app.simulation.definitions import InputCategory, plain
from app.simulation.units import unit_label

TemplateCategory = Literal["commodity", "currency", "interest_rate", "energy_cost", "combined"]

P = ChangeType.PERCENT_CHANGE
A = ChangeType.ABSOLUTE_CHANGE


@dataclass(frozen=True)
class Template:
    id: str
    title: str
    category: TemplateCategory
    question: str
    summary: str
    shocks: tuple[ShockSpec, ...]
    models: tuple[str, ...]
    stress_cases: tuple[StressCaseSpec, ...] = ()
    horizon_months: int = 12


def _cases(variable: str, *values: tuple[str, str]) -> tuple[StressCaseSpec, ...]:
    return tuple(
        StressCaseSpec(name=name, changes={variable: Decimal(value)}) for name, value in values
    )


TEMPLATES: tuple[Template, ...] = (
    Template(
        id="crude_oil_airline",
        title="Crude oil shock on an airline",
        category="commodity",
        question="What happens to an airline's fuel bill and operating profit if Brent crude "
        "rises 20\u00a0%?",
        summary="Brent crude rises; the change reaches jet fuel through the pass-through the "
        "airline model assumes, then the fuel bill, hedges and fares.",
        shocks=(ShockSpec("var_brent_crude", P, Decimal(20)),),
        models=("airline_fuel_cost",),
        stress_cases=_cases("var_brent_crude", ("Base", "10"), ("Stress", "25"), ("Extreme", "40")),
    ),
    Template(
        id="jet_fuel_airline",
        title="Jet fuel price shock",
        category="energy_cost",
        question="What happens to an airline if the jet fuel price rises 15\u00a0% with crude oil "
        "unchanged (a wider refining margin)?",
        summary="Jet fuel rises on its own; the airline model carries it to the fuel bill, "
        "hedges and fares.",
        shocks=(ShockSpec("var_jet_fuel", P, Decimal(15)),),
        models=("airline_fuel_cost",),
        stress_cases=_cases("var_jet_fuel", ("Mild", "7.5"), ("Severe", "30")),
    ),
    Template(
        id="rupee_depreciation",
        title="Rupee depreciation",
        category="currency",
        question="What happens to a company's revenue and costs invoiced in US dollars if the "
        "rupee weakens 10\u00a0% against the dollar?",
        summary="USD/INR rises; revenue and costs in US dollars are converted at the new rate, "
        "net of hedges.",
        shocks=(ShockSpec("var_usd_inr", P, Decimal(10)),),
        models=("fx_exposure",),
        stress_cases=_cases("var_usd_inr", ("Mild", "5"), ("Severe", "20")),
    ),
    Template(
        id="policy_rate_rise",
        title="Policy-rate rise",
        category="interest_rate",
        question="What happens to a company's interest costs and profit before tax if the RBI "
        "repo rate rises 1.5 percentage points?",
        summary="The repo rate rises; floating-rate loans linked to it reprice after the stated "
        "delay, with the stated pass-through.",
        shocks=(ShockSpec("var_rbi_repo_rate", A, Decimal("1.5")),),
        models=("floating_rate_interest",),
        stress_cases=_cases("var_rbi_repo_rate", ("Mild", "0.5"), ("Severe", "2.5")),
    ),
    Template(
        id="crude_linked_costs",
        title="Crude oil shock on crude-linked costs",
        category="commodity",
        question="What happens to a refiner's or a road haulier's costs if Brent crude "
        "rises 25\u00a0%?",
        summary="Brent rises; costs priced off crude (feedstock, diesel) follow with the stated "
        "pass-through and lag, net of hedges and price recovery.",
        shocks=(ShockSpec("var_brent_crude", P, Decimal(25)),),
        models=("crude_linked_costs",),
        stress_cases=_cases("var_brent_crude", ("Base", "10"), ("Stress", "25"), ("Extreme", "40")),
    ),
    Template(
        id="natural_gas",
        title="Natural gas price shock",
        category="energy_cost",
        question="What happens to a company whose costs follow natural gas if Henry Hub rises "
        "30\u00a0%?",
        summary="Henry Hub rises; gas-linked costs follow with the stated pass-through and lag, "
        "net of hedges and price recovery.",
        shocks=(ShockSpec("var_henry_hub_gas", P, Decimal(30)),),
        models=("gas_linked_costs",),
        stress_cases=_cases("var_henry_hub_gas", ("Mild", "15"), ("Severe", "60")),
    ),
    Template(
        id="oil_rupee_rates",
        title="Oil, rupee and rates together",
        category="combined",
        question="What happens to an airline if Brent rises 20\u00a0%, the rupee weakens "
        "5\u00a0% and the repo rate rises 0.5 percentage points at the same time?",
        summary="Three changes, three models: the fuel bill (crude and the exchange rate), "
        "other US-dollar revenue and costs, and floating-rate interest.",
        shocks=(
            ShockSpec("var_brent_crude", P, Decimal(20)),
            ShockSpec("var_usd_inr", P, Decimal(5)),
            ShockSpec("var_rbi_repo_rate", A, Decimal("0.5")),
        ),
        models=("airline_fuel_cost", "fx_exposure", "floating_rate_interest"),
        stress_cases=(
            StressCaseSpec(name="Half", scale=Decimal("0.5")),
            StressCaseSpec(name="Double", scale=Decimal(2)),
        ),
    ),
)

UNSUPPORTED: tuple[dict[str, str], ...] = (
    {
        "id": "demand",
        "title": "Demand shock",
        "reason": "No registered model simulates volumes. Every model holds volumes fixed "
        "(fuel consumed, US dollars invoiced), so a demand change would contradict them.",
    },
    {
        "id": "supply_chain",
        "title": "Supply-chain disruption",
        "reason": "No registered model simulates supply disruptions: the knowledge graph's "
        "supplier relationships carry no quantities to simulate with.",
    },
)

BY_ID = {item.id: item for item in TEMPLATES}


def check_templates() -> None:
    """Every template must use registered models that respond to its changes; raised at
    import."""
    for item in TEMPLATES:
        for model_id in item.models:
            if model_id not in PROFILES or lab_model(model_id) is None:
                raise ValueError(f"Template {item.id} uses an unregistered model {model_id}.")
        for shock in item.shocks:
            if not any(
                (binding := PROFILES[model_id].binding(shock.variable_id)) is not None
                and binding.change_type is shock.change_type
                for model_id in item.models
            ):
                raise ValueError(f"Template {item.id}: no model takes {shock.variable_id}.")


check_templates()


def get(template_id: str) -> Template | None:
    return BY_ID.get(template_id)


def spec_for(item: Template) -> ScenarioSpec:
    """The template as a scenario to start from: its changes, models and stress cases, no
    company and no figures."""
    return ScenarioSpec(
        name=item.title,
        description=item.summary,
        template_id=item.id,
        shocks=item.shocks,
        horizon_months=item.horizon_months,
        models={model_id: ModelSettings(mode="include") for model_id in item.models},
        stress_cases=item.stress_cases,
    )


def _kind(category: InputCategory, input_id: str) -> str:
    if input_id == "entity":
        return "entity"
    return {
        InputCategory.SCENARIO_INPUT: "change",
        InputCategory.MARKET_BASELINE: "market",
        InputCategory.COMPANY_INPUT: "company",
        InputCategory.ASSUMPTION: "assumption",
        InputCategory.SETTING: "setting",
    }[category]


def requirements(item: Template) -> dict[str, Any]:
    """What the template's models need, validate and produce, from their definitions."""
    spec = spec_for(item)
    required: dict[str, dict[str, Any]] = {}
    optional: dict[str, dict[str, Any]] = {}
    rules: list[dict[str, Any]] = []
    outputs: list[dict[str, Any]] = []
    lines: dict[str, list[dict[str, str]]] = {}
    for model_id in item.models:
        profile = PROFILES[model_id]
        model = lab_model(model_id)
        if model is None:  # pragma: no cover - check_templates guarantees it
            continue
        definition = model.definition
        bound = {binding.input_id for binding in profile.shocks}
        for entry in definition.inputs:
            if entry.category is InputCategory.SCENARIO_INPUT and entry.id in bound:
                continue  # the template's changes are listed separately
            path = spec_path(spec, profile, model, entry.id)
            target = required if entry.required else optional
            if path in target:
                target[path]["models"].append(model_id)
                continue
            target[path] = {
                "path": path,
                "input": entry.id,
                "label": entry.label,
                "kind": _kind(entry.category, entry.id),
                "unit": entry.unit,
                "unit_label": unit_label(entry.unit) if entry.unit else None,
                "units": list(entry.units),
                "default": plain(entry.default),
                "description": entry.description,
                "shared": entry.id in SHARED_PATHS,
                "models": [model_id],
            }
        rules.extend({"model_id": model_id, **plain(rule)} for rule in definition.validation_rules)
        for contribution in profile.lines:
            lines.setdefault(contribution.line, []).append(
                {
                    "model_id": model_id,
                    "item": contribution.item,
                    "label": ITEMS[contribution.item],
                }
            )
        for name in profile.key_outputs:
            output = definition.output(name)
            outputs.append(
                {"model_id": model_id, "id": name, "label": output.label, "unit": output.unit}
            )
    derived = []
    if "revenue" in lines or "operating_costs" in lines:
        derived += ["operating_profit", "operating_margin"]
    if "interest_expense" in lines:
        derived += ["profit_before_tax", "interest_coverage"]
    return {
        "changes": [
            {
                "variable_id": shock.variable_id,
                "change_type": shock.change_type.value,
                "value": decimal_text(shock.value),
            }
            for shock in item.shocks
        ],
        "required_inputs": list(required.values()),
        "optional_inputs": list(optional.values()),
        "validation_rules": rules,
        "expected_outputs": {
            "lines": [
                {"line": line, "label": LINE_LABELS[line], "items": items}
                for line, items in lines.items()
            ],
            "derived": [
                {"id": name, "label": LINE_LABELS.get(name, name.replace("_", " ").capitalize())}
                for name in derived
            ],
            "model_outputs": outputs,
        },
    }
