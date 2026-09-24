"""Input validation against a model definition.

Every input is checked before anything is computed:

* **numbers** are plain decimals (``"30"``, ``"2.35"``; JSON numbers are read through their
  shortest form). Exponents, thousands separators, symbols, NaN and infinities are
  refused, and so are more decimal places than the input allows;
* **ranges** follow the definition (e.g. a percent change must be above −100 % and at most
  +1,000 %: the Phase 1 scenario rules);
* **percentages** are given in percent (30 means 30 %) and converted to fractions by the
  model's equations, never guessed;
* **units** must be the input's unit, or one of the listed units for a quantity; nothing
  else is converted;
* **currencies** are ISO 4217 codes; a stored observation may only supply a value whose
  currency pair and unit match;
* **integers** (months) must be whole numbers;
* **required** inputs must be present; an omitted optional input takes the definition's
  default, recorded as such.

Validation never fills in a missing value with data it does not have.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from app.graph.drafts import NODE_KEY_PATTERN
from app.simulation.data_sources import StoredObservation
from app.simulation.decimal_math import text
from app.simulation.definitions import (
    InputCategory,
    InputDefinition,
    InputKind,
    Knowledge,
    ModelDefinition,
    ObservationSource,
    ValueSource,
)
from app.simulation.runtime import Issue, ResolvedValues
from app.simulation.units import PRICE_UNITS, VOLUME_UNITS, currency_is_valid, unit_label

PLAIN_DECIMAL = re.compile(r"^[+-]?\d{1,30}(\.\d{1,30})?$")
NODE_KEY = re.compile(NODE_KEY_PATTERN)


@dataclass(frozen=True)
class InputValue:
    """One input as a request gives it."""

    value: str | int | float | None = None
    unit: str | None = None
    source: Literal["user", "stored_observation"] | None = None
    series_id: str | None = None


@dataclass(frozen=True)
class ResolvedInput:
    """One input after validation: its value, where it came from and what it is."""

    id: str
    label: str
    category: InputCategory
    knowledge: Knowledge
    source: ValueSource
    value: str | None
    unit: str | None
    unit_label: str
    default: str | None
    rationale: str | None
    variable: str | None
    observation: StoredObservation | None = None

    def snapshot(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "category": self.category.value,
            "knowledge": self.knowledge.value,
            "source": self.source.value,
            "value": self.value,
            "unit": self.unit,
            "unit_label": self.unit_label,
            "default": self.default,
            "rationale": self.rationale,
            "variable": self.variable,
            "observation": self.observation.snapshot() if self.observation else None,
        }


ObservationLookup = Callable[[str], StoredObservation | None]


def _display(value: Decimal | str | None) -> str | None:
    if value is None:
        return None
    return text(value) if isinstance(value, Decimal) else value


def parse_number(raw: str | int | float) -> Decimal | None:
    """An exact decimal from a request value, or None if it is not a plain number."""
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return Decimal(raw)
    if isinstance(raw, float):
        if not math.isfinite(raw):
            return None
        raw = repr(raw)  # the shortest string that round-trips: 0.1 → "0.1"
        if "e" in raw or "E" in raw:
            return None
    if not isinstance(raw, str) or not PLAIN_DECIMAL.match(raw.strip()):
        return None
    try:
        return Decimal(raw.strip())
    except InvalidOperation:  # pragma: no cover - the pattern already guarantees a number
        return None


def decimal_places(value: Decimal) -> int:
    """Significant decimal places: trailing zeros after the point do not count."""
    exponent = value.normalize().as_tuple().exponent
    return max(0, -exponent) if isinstance(exponent, int) else 0


def _bound_text(definition: InputDefinition, bound: Decimal) -> str:
    unit = definition.unit or ""
    if unit in ("percent", "percent_change"):
        return f"{text(bound)} %"
    if unit == "percentage_points":
        return f"{text(bound)} percentage points"
    return text(bound)


def check_range(definition: InputDefinition, value: Decimal) -> str | None:
    minimum, maximum = definition.minimum, definition.maximum
    if minimum is not None:
        if definition.minimum_exclusive and value <= minimum:
            return f"must be greater than {_bound_text(definition, minimum)}"
        if not definition.minimum_exclusive and value < minimum:
            return f"must be at least {_bound_text(definition, minimum)}"
    if maximum is not None:
        if definition.maximum_exclusive and value >= maximum:
            return f"must be less than {_bound_text(definition, maximum)}"
        if not definition.maximum_exclusive and value > maximum:
            return f"must be at most {_bound_text(definition, maximum)}"
    return None


def _knowledge(category: InputCategory, source: ValueSource) -> Knowledge:
    if category is InputCategory.SCENARIO_INPUT:
        return Knowledge.SCENARIO_INPUT
    if category is InputCategory.ASSUMPTION:
        return Knowledge.ASSUMPTION
    if category is InputCategory.SETTING:
        return Knowledge.SETTING
    if source is ValueSource.STORED_OBSERVATION:
        return Knowledge.HISTORICAL_DATA
    return Knowledge.USER_INPUT


def _source_for(definition: InputDefinition, series_id: str | None) -> ObservationSource | None:
    if series_id is None and len(definition.sources) == 1:
        return definition.sources[0]
    return next((item for item in definition.sources if item.series_id == series_id), None)


def validate_inputs(
    definition: ModelDefinition,
    raw_inputs: Mapping[str, InputValue],
    *,
    lookup: ObservationLookup,
) -> tuple[dict[str, ResolvedInput], ResolvedValues | None, list[Issue]]:
    """Check and resolve every input. ``values`` is None when any input has an error."""
    issues: list[Issue] = []
    known = {item.id for item in definition.inputs}
    for name in sorted(set(raw_inputs) - known):
        issues.append(
            Issue("unknown_input", f"'{name}' is not an input of this model.", field=name)
        )

    numbers: dict[str, Decimal] = {}
    integers: dict[str, int] = {}
    texts: dict[str, str | None] = {}
    units: dict[str, str] = {}
    resolved: dict[str, ResolvedInput] = {}
    observations: dict[str, tuple[ObservationSource, StoredObservation]] = {}

    for item in definition.inputs:
        raw = raw_inputs.get(item.id)
        source = ValueSource.USER
        observation: StoredObservation | None = None
        chosen_unit = item.unit
        value: Decimal | str | None

        wants_observation = raw is not None and raw.source == "stored_observation"
        if raw is None or (raw.value is None and not wants_observation):
            if item.required:
                issues.append(Issue("required", f"{item.label} is required.", field=item.id))
                continue
            value = item.default
            source = ValueSource.DEFAULT
            if item.kind is InputKind.QUANTITY and value is not None:
                chosen_unit = item.units[0]
        elif raw is not None and wants_observation:
            spec = _source_for(item, raw.series_id)
            if spec is None:
                issues.append(
                    Issue(
                        "observation_matches",
                        f"{item.label} cannot come from stored series "
                        f"'{raw.series_id or '(none given)'}'.",
                        field=item.id,
                    )
                )
                continue
            observation = lookup(spec.series_id)
            if observation is None:
                issues.append(
                    Issue(
                        "no_stored_observation",
                        f"No value of '{spec.label}' is stored yet (run the World Bank "
                        "retrieval), so enter the value instead.",
                        field=item.id,
                    )
                )
                continue
            if observation.series_unit != spec.unit:
                issues.append(
                    Issue(
                        "observation_matches",
                        f"The stored series is in '{observation.series_unit}', not "
                        f"'{spec.unit}', so it cannot supply {item.label.lower()}.",
                        field=item.id,
                    )
                )
                continue
            value = observation.value
            source = ValueSource.STORED_OBSERVATION
            observations[item.id] = (spec, observation)
        else:
            parsed = _parse(item, raw, issues)
            if parsed is None:
                continue
            value, chosen_unit = parsed

        if isinstance(value, Decimal) and source is not ValueSource.DEFAULT:
            problem = None
            if item.kind is InputKind.INTEGER and value != value.to_integral_value():
                problem = "must be a whole number"
            elif (
                # A stored observation keeps the precision it was published with.
                source is ValueSource.USER
                and item.kind is not InputKind.INTEGER
                and decimal_places(value) > item.max_decimals
            ):
                problem = (
                    f"can have at most {item.max_decimals} decimal places"
                    if item.max_decimals
                    else "must be a whole number"
                )
            else:
                problem = check_range(item, value)
            if problem:
                issues.append(Issue("input_range", f"{item.label} {problem}.", field=item.id))
                continue

        if item.kind is InputKind.INTEGER:
            integers[item.id] = int(value) if isinstance(value, Decimal) else 0
        elif item.kind in (InputKind.DECIMAL, InputKind.QUANTITY):
            numbers[item.id] = value if isinstance(value, Decimal) else Decimal(0)
            if item.kind is InputKind.QUANTITY and chosen_unit:
                units[item.id] = chosen_unit
        else:
            texts[item.id] = value if isinstance(value, str) else None

        resolved[item.id] = ResolvedInput(
            id=item.id,
            label=item.label,
            category=item.category,
            knowledge=_knowledge(item.category, source),
            source=source,
            value=_display(value),
            unit=chosen_unit,
            unit_label="",
            default=_display(item.default),
            rationale=item.rationale,
            variable=item.variable,
            observation=observation,
        )

    # Cross-input checks that validation itself owns: currencies of stored observations.
    currency = texts.get("reporting_currency")
    for input_id, (spec, _observation) in observations.items():
        quote = spec.currency_pair[0]
        if currency is not None and currency != quote:
            issues.append(
                Issue(
                    "observation_matches",
                    f"The stored series gives {quote} per {spec.currency_pair[1]}, but the "
                    f"reporting currency is {currency}. Enter the rate instead: RUMIN does "
                    "not convert between currencies without a rate you provide.",
                    field=input_id,
                )
            )

    # Unit labels, now that the reporting currency is known.
    labelled: dict[str, ResolvedInput] = {}
    for input_id, entry in resolved.items():
        labelled[input_id] = _with_label(entry, definition.input(input_id), currency)

    if any(issue.severity == "error" for issue in issues):
        return labelled, None, issues
    return labelled, ResolvedValues(numbers, integers, texts, units), issues


def _with_label(entry: ResolvedInput, item: InputDefinition, currency: str | None) -> ResolvedInput:
    unit = entry.unit or ""
    if unit in PRICE_UNITS:
        label = PRICE_UNITS[unit].label
    elif unit in VOLUME_UNITS:
        label = f"{VOLUME_UNITS[unit].label} per year"
    else:
        label = unit_label(unit, currency=currency) if unit else ""
    return ResolvedInput(**{**entry.__dict__, "unit_label": label})


def _parse(
    item: InputDefinition, raw: InputValue, issues: list[Issue]
) -> tuple[Decimal | str, str | None] | None:
    """One raw value, parsed for its kind; None (with an issue) if it cannot be."""
    value = raw.value
    if item.kind in (InputKind.CURRENCY, InputKind.GRAPH_NODE):
        if raw.unit is not None:
            issues.append(Issue("unit_choice", f"{item.label} takes no unit.", field=item.id))
            return None
        if not isinstance(value, str):
            issues.append(Issue("input_range", f"{item.label} must be text.", field=item.id))
            return None
        if item.kind is InputKind.CURRENCY and not currency_is_valid(value):
            issues.append(
                Issue(
                    "input_range",
                    f"{item.label} must be an ISO 4217 code of three capital letters, e.g. INR.",
                    field=item.id,
                )
            )
            return None
        if item.kind is InputKind.GRAPH_NODE and not NODE_KEY.match(value):
            issues.append(
                Issue(
                    "input_range",
                    f"{item.label} must be a knowledge-graph node key such as "
                    "company:co_aerisca_airways.",
                    field=item.id,
                )
            )
            return None
        return value, item.unit

    if value is None:
        issues.append(Issue("required", f"{item.label} needs a value.", field=item.id))
        return None
    number = parse_number(value)
    if number is None:
        issues.append(
            Issue(
                "input_range",
                f"{item.label} must be a plain number such as 30 or 2.35 (no separators, "
                "symbols or exponents).",
                field=item.id,
            )
        )
        return None
    if item.kind is InputKind.QUANTITY:
        if raw.unit not in item.units:
            choices = ", ".join(item.units)
            issues.append(
                Issue(
                    "unit_choice",
                    f"{item.label} needs a unit: one of {choices}.",
                    field=item.id,
                )
            )
            return None
        return number, raw.unit
    if raw.unit is not None and raw.unit != item.unit:
        issues.append(
            Issue(
                "unit_choice",
                f"{item.label} is given in '{item.unit}'; '{raw.unit}' is not converted.",
                field=item.id,
            )
        )
        return None
    return number, item.unit
