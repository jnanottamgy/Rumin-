"""Typed, versioned model definitions.

A definition says everything a model *is*, without executing anything:

* its identity (id, version, status);
* the inputs it accepts, with category, unit, range, decimals, default and rationale;
* the equations it evaluates, each with its terms, units, assumptions and limitations;
* the knowledge-graph relationships it may propagate shocks along (transmission rules)
  and the ones it only cites (supporting relationships);
* its outputs, assumptions, limitations and validation rules.

Definitions are plain frozen data. Their canonical JSON form is hashed (SHA-256): a run
records the hash of the definition it used, and a stored model version may never change
its definition without a new version number. Optional fields added after the first
release (the shock timing inputs) are left out of the canonical form while unset, so the
hash of every definition released before them stays exactly as it was.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, fields, is_dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal

from app.db.types import canonical_decimal
from app.domain.enums import SimulationModelStatus

VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")
MODEL_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]{2,63}$")

# Units a scenario input (a shock on a graph variable) may have: a percentage change of a
# level (a price, an exchange rate) or a change in percentage points of a rate.
PERCENT_CHANGE = "percent_change"
PERCENTAGE_POINTS = "percentage_points"
SHOCK_UNITS = frozenset({PERCENT_CHANGE, PERCENTAGE_POINTS})

# ModelDefinition fields added after the first release; omitted from the canonical JSON
# while None, so earlier definitions keep their hashes.
OPTIONAL_DEFINITION_FIELDS = ("shock_start_input", "shock_duration_input")


ModelStatus = SimulationModelStatus


class InputCategory(StrEnum):
    """Where an input comes from, as a model defines it."""

    SCENARIO_INPUT = "scenario_input"  # a change the user chooses to explore
    MARKET_BASELINE = "market_baseline"  # a market level: stored data or entered by the user
    COMPANY_INPUT = "company_input"  # figures about the company, entered by the user
    ASSUMPTION = "assumption"  # a modelling assumption with a stated default
    SETTING = "setting"  # how the run is carried out (e.g. its horizon)


class InputKind(StrEnum):
    DECIMAL = "decimal"  # a number in a fixed unit
    INTEGER = "integer"
    QUANTITY = "quantity"  # a number with a unit chosen from a list
    CURRENCY = "currency"  # an ISO 4217 code
    GRAPH_NODE = "graph_node"  # a node key in the knowledge graph


class Knowledge(StrEnum):
    """What a resolved value *is*. Kept apart everywhere a run is shown."""

    SCENARIO_INPUT = "scenario_input"
    HISTORICAL_DATA = "historical_data"
    USER_INPUT = "user_input"
    ASSUMPTION = "assumption"
    SETTING = "setting"


class ValueSource(StrEnum):
    USER = "user"
    DEFAULT = "default"
    STORED_OBSERVATION = "stored_observation"


@dataclass(frozen=True)
class ObservationSource:
    """A stored Phase 2 series that may supply an input's value."""

    series_id: str
    label: str
    # The series' unit, as the catalogue states it; the stored series must still match.
    unit: str
    # (quote, base): the value is quote-currency units per base-currency unit. The source is
    # only valid when the run's reporting currency is the quote currency.
    currency_pair: tuple[str, str]
    caveat: str


@dataclass(frozen=True)
class SensitivitySpec:
    """Default low/high values for one-at-a-time sensitivity analysis.

    ``absolute``: base − step and base + step, in the input's own unit.
    ``relative``: base × (1 − step %) and base × (1 + step %).
    Points outside the input's valid range are skipped and reported, never clipped.
    """

    mode: Literal["absolute", "relative"]
    step: Decimal


@dataclass(frozen=True)
class InputDefinition:
    id: str
    label: str
    category: InputCategory
    kind: InputKind
    description: str
    unit: str | None = None
    units: tuple[str, ...] = ()
    minimum: Decimal | None = None
    maximum: Decimal | None = None
    minimum_exclusive: bool = False
    maximum_exclusive: bool = False
    max_decimals: int = 6
    required: bool = True
    default: Decimal | str | None = None
    rationale: str | None = None
    # The knowledge-graph node this input shocks or measures, e.g. "variable:var_brent_crude".
    variable: str | None = None
    sources: tuple[ObservationSource, ...] = ()
    sensitivity: SensitivitySpec | None = None


@dataclass(frozen=True)
class Term:
    symbol: str
    meaning: str
    unit: str


@dataclass(frozen=True)
class EquationDefinition:
    id: str
    name: str
    formula: str
    output: Term
    terms: tuple[Term, ...]
    explanation: str
    scope: Literal["annual", "monthly", "horizon", "steady_state"]
    assumptions: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()


@dataclass(frozen=True)
class TransmissionRule:
    """A knowledge-graph relationship a model may propagate shocks along.

    ``log_linear``: the target's log-change gains ``coefficient × the source's log-change``,
    ``lag`` months later. The coefficient and lag are model inputs (assumptions), never
    read from the graph; the graph must state the relationship for it to be used.
    """

    id: str
    edge_type: str
    source: str
    target: str
    coefficient_input: str
    lag_input: str | None
    form: Literal["log_linear"]
    description: str


@dataclass(frozen=True)
class SupportingRelationship:
    """A knowledge-graph relationship a model cites but never propagates along.

    ``{entity}`` stands for the company the run is about, if one is chosen.
    """

    id: str
    edge_type: str
    source: str
    target: str
    role: str
    required_with_entity: bool = False


@dataclass(frozen=True)
class OutputDefinition:
    id: str
    label: str
    unit: str
    kind: Literal["derived", "simulated"]
    description: str
    equation: str
    # Whether the output is attributed to the scenario's shocks (Shapley values).
    attributable: bool = False


@dataclass(frozen=True)
class Statement:
    id: str
    text: str


@dataclass(frozen=True)
class ValidationRuleDefinition:
    id: str
    description: str
    severity: Literal["error", "warning"]


@dataclass(frozen=True)
class PathwayLink:
    """One link of the input-to-output pathway a run is explained with.

    Ends are ``input:<id>``, ``output:<id>`` or a knowledge-graph node key; ``rule`` names
    the transmission rule when the link is a propagated graph relationship.
    """

    source: str
    target: str
    label: str
    equations: tuple[str, ...] = ()
    rule: str | None = None


@dataclass(frozen=True)
class BridgeItem:
    """One step of an accounting bridge: ``sign × output`` (the steps sum to the total)."""

    output: str
    sign: Literal[1, -1]
    label: str


@dataclass(frozen=True)
class ModelDefinition:
    id: str
    version: str
    name: str
    summary: str
    description: str
    domain: str
    status: ModelStatus
    inputs: tuple[InputDefinition, ...]
    equations: tuple[EquationDefinition, ...]
    outputs: tuple[OutputDefinition, ...]
    transmission_rules: tuple[TransmissionRule, ...]
    supporting_relationships: tuple[SupportingRelationship, ...]
    assumptions: tuple[Statement, ...]
    limitations: tuple[Statement, ...]
    validation_rules: tuple[ValidationRuleDefinition, ...]
    references: tuple[Statement, ...]
    # The month-by-month series a run returns (same fields as outputs).
    monthly_outputs: tuple[OutputDefinition, ...] = ()
    pathway: tuple[PathwayLink, ...] = ()
    # An exact identity between outputs (e.g. gross change, hedging, fares → profit).
    bridge: tuple[BridgeItem, ...] = ()
    bridge_total: str | None = None
    horizon_input: str = "horizon_months"
    # The outputs a summary of a run shows first.
    headline_outputs: tuple[str, ...] = ()
    # Inputs varied by a sensitivity analysis when the request names none, and its metric.
    sensitivity_defaults: tuple[str, ...] = ()
    sensitivity_metric: str | None = None
    time_step: Literal["month"] = "month"
    max_horizon_months: int = 36
    max_propagation_depth: int = 4
    # Integer settings that time every shock of a run: the month the changes take effect
    # and how many months they last (0: until the end of the horizon). Without them,
    # changes are permanent from month 1.
    shock_start_input: str | None = None
    shock_duration_input: str | None = None

    def __post_init__(self) -> None:
        if not MODEL_ID_PATTERN.match(self.id):
            raise ValueError(f"Invalid model id '{self.id}'.")
        if not VERSION_PATTERN.match(self.version):
            raise ValueError(f"Model version '{self.version}' is not MAJOR.MINOR.PATCH.")
        for group in ("inputs", "equations", "outputs", "transmission_rules", "assumptions"):
            ids = [item.id for item in getattr(self, group)]
            if len(ids) != len(set(ids)):
                raise ValueError(f"Duplicate ids in {self.id} {group}: {ids}.")
        known = {item.id for item in self.inputs}
        outputs = {item.id for item in self.outputs}
        for rule in self.transmission_rules:
            for name in (rule.coefficient_input, rule.lag_input):
                if name is not None and name not in known:
                    raise ValueError(f"Rule {rule.id} refers to unknown input '{name}'.")
        for name in self.headline_outputs:
            if name not in outputs:
                raise ValueError(f"Headline output '{name}' is not an output.")
        for name in self.sensitivity_defaults:
            if name not in known:
                raise ValueError(f"Sensitivity default '{name}' is not an input.")
        if self.sensitivity_metric is not None and self.sensitivity_metric not in outputs:
            raise ValueError("The sensitivity metric must be an output.")
        if self.horizon_input not in known:
            raise ValueError(f"{self.id} has no horizon input '{self.horizon_input}'.")
        for name in (self.shock_start_input, self.shock_duration_input):
            if name is not None and (
                name not in known or self.input(name).kind is not InputKind.INTEGER
            ):
                raise ValueError(f"Shock timing input '{name}' is not an integer input.")
        level_nodes = set()
        for item in self.inputs:
            if item.category is InputCategory.SCENARIO_INPUT and item.variable:
                if item.unit not in SHOCK_UNITS:
                    raise ValueError(
                        f"Scenario input {item.id} shocks a graph variable, so its unit must be "
                        f"one of {sorted(SHOCK_UNITS)}."
                    )
                if item.unit == PERCENTAGE_POINTS:
                    level_nodes.add(item.variable)
        for rule in self.transmission_rules:
            if {rule.source, rule.target} & level_nodes:
                raise ValueError(
                    f"Rule {rule.id} touches a node shocked in percentage points; log-linear "
                    "rules carry percentage changes only."
                )
        for step in self.bridge:
            if step.output not in outputs:
                raise ValueError(f"Bridge step refers to unknown output '{step.output}'.")
        if self.bridge and self.bridge_total not in outputs:
            raise ValueError("The bridge total must be an output.")
        equations = {item.id for item in self.equations}
        rules = {item.id for item in self.transmission_rules}
        for link in self.pathway:
            for end in (link.source, link.target):
                kind, _, name = end.partition(":")
                if (kind == "input" and name not in known) or (
                    kind == "output" and name not in outputs
                ):
                    raise ValueError(f"Pathway end '{end}' is unknown.")
            if link.rule is not None and link.rule not in rules:
                raise ValueError(f"Pathway link cites unknown rule {link.rule}.")
            if set(link.equations) - equations:
                raise ValueError(f"Pathway link cites unknown equations {link.equations}.")
        for output in (*self.outputs, *self.monthly_outputs):
            if output.equation not in equations:
                raise ValueError(f"Output {output.id} refers to unknown equation.")
        statements = {item.id for item in self.assumptions}
        limitations = {item.id for item in self.limitations}
        for equation in self.equations:
            unknown = (set(equation.assumptions) - statements) | (
                set(equation.limitations) - limitations
            )
            if unknown:
                raise ValueError(f"Equation {equation.id} cites unknown statements {unknown}.")

    def input(self, input_id: str) -> InputDefinition:
        for item in self.inputs:
            if item.id == input_id:
                return item
        raise KeyError(input_id)

    def output(self, output_id: str) -> OutputDefinition:
        for item in self.outputs:
            if item.id == output_id:
                return item
        raise KeyError(output_id)

    @property
    def key(self) -> str:
        return f"{self.id}@{self.version}"


def plain(value: Any) -> Any:
    """A JSON-ready copy: dataclasses as dicts, tuples as lists, decimals as exact strings."""
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: plain(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, Decimal):
        return format(canonical_decimal(value), "f")
    if isinstance(value, tuple | list):
        return [plain(item) for item in value]
    if isinstance(value, dict):
        return {str(key): plain(item) for key, item in value.items()}
    return value


def to_json(definition: ModelDefinition) -> dict[str, Any]:
    """The definition as JSON-ready data (the form stored with each model version)."""
    data: dict[str, Any] = plain(definition)
    for name in OPTIONAL_DEFINITION_FIELDS:
        if data.get(name) is None:
            data.pop(name, None)
    return data


def canonical_json(data: Any) -> str:
    """Deterministic JSON: sorted keys, no whitespace, decimals as exact strings."""
    return json.dumps(plain(data), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256(data: Any) -> str:
    return hashlib.sha256(canonical_json(data).encode("utf-8")).hexdigest()


def definition_hash(definition: ModelDefinition) -> str:
    return sha256(to_json(definition))
