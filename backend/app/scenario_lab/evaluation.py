"""Re-evaluating a stored execution with some of its quantities set to other values.

Every analysis of an execution — one quantity at a time, two together, or many drawn at
random — asks the same question for each point: *what are the lines and metrics if these
quantities take these values and everything else keeps the execution's?* This module answers
it once, for all of them:

1. each value must pass the input's own rules (a whole number for months, the range);
2. every model that uses a varied quantity gets the new values together, and its own
   cross-field rules (``check``) and the execution's graph channels must still hold;
3. those models are re-evaluated by the Phase 4 engine; the others keep their outcomes;
4. the Lab's aggregation recombines the lines and metrics **from the varied values** — a
   shared figure such as revenue is also the base of the margins and of interest coverage.

A value that breaks a rule is never clipped or adjusted: the point is skipped with the
reason. The graph used is the snapshot stored with each run; nothing is read from the
current graph.
"""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from decimal import ROUND_HALF_EVEN, Decimal

from app.scenario_lab.aggregate import (
    Aggregate,
    Outcome,
    Part,
    aggregate,
    outcome_of_result,
    totals,
)
from app.scenario_lab.executor import Member
from app.scenario_lab.inputs import SHARED_PATHS
from app.scenario_lab.spec import ScenarioSpec
from app.simulation.decimal_math import NumericalError
from app.simulation.definitions import InputCategory, InputDefinition, InputKind
from app.simulation.engine import channel_issues, evaluate_result, links_for
from app.simulation.runtime import ResolvedValues
from app.simulation.validation import check_range, decimal_places

# How each kind of model input is described when it is varied.
KINDS = {
    InputCategory.ASSUMPTION: "assumption",
    InputCategory.COMPANY_INPUT: "company",
    InputCategory.MARKET_BASELINE: "market",
}


class Skipped(Exception):
    """A point that cannot be evaluated: the reason, in a sentence, and the rule's code (the
    model's validation rule, ``out_of_range``, a numerical limit…) to group reasons by."""

    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.message = message
        self.code = code


class DeadlineExceeded(Exception):
    def __init__(self, evaluations: int, seconds: float) -> None:
        super().__init__(f"exceeded {seconds:g} seconds after {evaluations} evaluations")
        self.evaluations = evaluations
        self.seconds = seconds


@dataclass(frozen=True)
class Target:
    """What an analysis can vary: a change, a shared figure or one model's input."""

    id: str  # "change:var_brent_crude", "shared:annual_revenue", "model:<model>:<input>"
    label: str
    kind: str  # change | shared | company | market | assumption
    uses: tuple[tuple[Member, str], ...]  # (model, its input id)

    @property
    def definition(self) -> InputDefinition:
        member, input_id = self.uses[0]
        return member.model.definition.input(input_id)

    @property
    def integer(self) -> bool:
        return self.definition.kind is InputKind.INTEGER

    @property
    def unit(self) -> str | None:
        definition = self.definition
        if definition.unit:
            return definition.unit
        member, input_id = self.uses[0]
        return member.values.unit(input_id) if definition.kind is InputKind.QUANTITY else None

    @property
    def base(self) -> Decimal:
        member, input_id = self.uses[0]
        return base_value(member, input_id)

    @property
    def models(self) -> list[str]:
        return [member.model_id for member, _ in self.uses]


def targets(spec: ScenarioSpec, members: Sequence[Member]) -> dict[str, Target]:
    """Everything an analysis of this execution can vary."""
    found: dict[str, Target] = {}
    for shock in spec.shocks:
        uses = tuple(
            (member, binding.input_id)
            for member in members
            if (binding := member.profile.binding(shock.variable_id)) is not None
            and binding.change_type is shock.change_type
        )
        if uses:
            found[f"change:{shock.variable_id}"] = Target(
                f"change:{shock.variable_id}",
                uses[0][0].model.definition.input(uses[0][1]).label,
                "change",
                uses,
            )
    for name in SHARED_PATHS:
        uses = tuple(
            (member, name)
            for member in members
            if any(item.id == name for item in member.model.definition.inputs)
        )
        if uses and uses[0][0].model.definition.input(name).kind in (
            InputKind.DECIMAL,
            InputKind.QUANTITY,
        ):
            found[f"shared:{name}"] = Target(
                f"shared:{name}", uses[0][0].model.definition.input(name).label, "shared", uses
            )
    for member in members:
        for item in member.model.definition.inputs:
            if item.id in SHARED_PATHS or item.category in (
                InputCategory.SCENARIO_INPUT,
                InputCategory.SETTING,
            ):
                continue
            if item.kind not in (InputKind.DECIMAL, InputKind.QUANTITY, InputKind.INTEGER):
                continue
            key = f"model:{member.model_id}:{item.id}"
            found[key] = Target(
                key,
                f"{item.label} ({member.profile.title})",
                KINDS[item.category],
                ((member, item.id),),
            )
    return found


def base_value(member: Member, input_id: str) -> Decimal:
    """The execution's value of one model input."""
    values = member.values
    if member.model.definition.input(input_id).kind is InputKind.INTEGER:
        return Decimal(values.integer(input_id))
    return values.number(input_id)


def conform(definition: InputDefinition, value: Decimal) -> Decimal:
    """``value`` with no more decimals than the input accepts (rounded half to even)."""
    places = 0 if definition.kind is InputKind.INTEGER else definition.max_decimals
    if decimal_places(value) <= places:
        return value
    return value.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_EVEN)


def value_problem(target: Target, value: Decimal) -> str | None:
    """Why ``value`` is not a valid value of ``target`` (for every model using it), or None."""
    if target.integer and value != value.to_integral_value():
        return "must be a whole number"
    for member, input_id in target.uses:
        problem = check_range(member.model.definition.input(input_id), value)
        if problem:
            return problem
    return None


class Evaluator:
    """Evaluates an execution's lines and metrics with some quantities set to other values."""

    def __init__(
        self, spec: ScenarioSpec, members: Sequence[Member], *, deadline_seconds: float
    ) -> None:
        self.members = list(members)
        self.horizon = spec.horizon_months
        self.deadline_seconds = deadline_seconds
        self.started = time.monotonic()
        self.evaluations = 0
        self.base_outcomes = {
            member.model_id: self._outcome(member, member.values) for member in self.members
        }
        self.base = self._combine(self.base_outcomes, {})
        self.base_totals = totals(self.base)

    @property
    def elapsed_ms(self) -> int:
        return round((time.monotonic() - self.started) * 1000)

    def _outcome(self, member: Member, values: ResolvedValues) -> Outcome:
        links = links_for(member.model, values, member.preparation.graph)
        return outcome_of_result(
            member.model_id, evaluate_result(member.model, values, links, self.horizon)
        )

    def _combine(
        self, outcomes: Mapping[str, Outcome], varied: Mapping[str, ResolvedValues]
    ) -> Aggregate:
        return aggregate(
            [
                Part(
                    member.profile,
                    varied.get(member.model_id, member.values),
                    outcomes[member.model_id],
                )
                for member in self.members
            ],
            horizon=self.horizon,
        )

    def evaluate(self, settings: Sequence[tuple[Target, Decimal]]) -> dict[str, Decimal]:
        """Every line's change and every metric's value with each target set to its value.

        Raises ``Skipped`` with the reason when a value or the combination breaks a rule, and
        ``DeadlineExceeded`` once the analysis has run longer than its deadline.
        """
        for target, value in settings:
            problem = value_problem(target, value)
            if problem:
                raise Skipped(f"{target.label} {problem}.", code="out_of_range")
        changes: dict[str, dict[str, Decimal]] = {}
        order: list[Member] = []
        for target, value in settings:
            for member, input_id in target.uses:
                if member.model_id not in changes:
                    changes[member.model_id] = {}
                    order.append(member)
                changes[member.model_id][input_id] = value
        varied: dict[str, ResolvedValues] = {}
        for member in order:
            values = member.values
            numbers = dict(values.numbers)
            integers = dict(values.integers)
            for input_id, value in changes[member.model_id].items():
                if member.model.definition.input(input_id).kind is InputKind.INTEGER:
                    integers[input_id] = int(value)
                else:
                    numbers[input_id] = value
            candidate = replace(values, numbers=numbers, integers=integers)
            try:
                blocking = [
                    issue for issue in member.model.check(candidate) if issue.severity == "error"
                ]
            except NumericalError as error:
                raise Skipped(error.message, code=error.code) from error
            blocking += [
                issue
                for issue in channel_issues(member.model, candidate, member.preparation.graph)
                if issue.severity == "error"
            ]
            if blocking:
                raise Skipped(blocking[0].message, code=blocking[0].code)
            varied[member.model_id] = candidate
        outcomes = dict(self.base_outcomes)
        try:
            for member in order:
                if time.monotonic() - self.started > self.deadline_seconds:
                    raise DeadlineExceeded(self.evaluations, self.deadline_seconds)
                outcomes[member.model_id] = self._outcome(member, varied[member.model_id])
            result = totals(self._combine(outcomes, varied))
        except NumericalError as error:
            raise Skipped(error.message, code=error.code) from error
        self.evaluations += 1
        return result
