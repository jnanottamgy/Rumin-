"""The types a model's code works with while it runs.

A model is two functions registered with its definition:

* ``check(values) -> list[Issue]`` — cross-field validation once every input has been
  resolved (e.g. "the fuel bill cannot exceed operating costs");
* ``compute(context) -> ModelResult`` — the equations, recording each evaluation as a
  ``Step`` so that every output can be traced to the numbers that produced it.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal

from app.simulation.decimal_math import to_output
from app.simulation.transmission import Propagation

Severity = Literal["error", "warning"]


@dataclass(frozen=True)
class Issue:
    """A validation problem (error: blocks the run) or caveat (warning: recorded with it)."""

    code: str
    message: str
    severity: Severity = "error"
    field: str | None = None  # the input id, when the issue is about one input


@dataclass(frozen=True)
class StepValue:
    symbol: str
    value: Decimal
    unit: str


@dataclass(frozen=True)
class Step:
    equation: str
    label: str
    output: StepValue
    inputs: tuple[StepValue, ...]
    month: int | None = None


class StepRecorder:
    """Collects calculation steps in order. A disabled recorder records nothing (used
    for the extra evaluations behind contribution analysis and sensitivity)."""

    def __init__(self, *, enabled: bool = True) -> None:
        self.enabled = enabled
        self.steps: list[Step] = []

    def record(
        self,
        equation: str,
        label: str,
        output: tuple[str, Decimal, str],
        inputs: Sequence[tuple[str, Decimal, str]] = (),
        *,
        month: int | None = None,
    ) -> Decimal:
        """Record one evaluation and return its (unrounded) output value."""
        symbol, value, unit = output
        if self.enabled:
            self.steps.append(
                Step(
                    equation=equation,
                    label=label,
                    output=StepValue(symbol, to_output(value, label), unit),
                    inputs=tuple(
                        StepValue(name, to_output(number, name), name_unit)
                        for name, number, name_unit in inputs
                    ),
                    month=month,
                )
            )
        return value


@dataclass(frozen=True)
class ResolvedValues:
    """Every input's value after validation: numbers as ``Decimal``, integers as ``int``,
    codes and node keys as ``str``; the unit chosen for each quantity input."""

    numbers: Mapping[str, Decimal]
    integers: Mapping[str, int]
    texts: Mapping[str, str | None]
    units: Mapping[str, str]

    def number(self, input_id: str) -> Decimal:
        return self.numbers[input_id]

    def integer(self, input_id: str) -> int:
        return self.integers[input_id]

    def text(self, input_id: str) -> str | None:
        return self.texts.get(input_id)

    def unit(self, input_id: str) -> str:
        return self.units[input_id]


@dataclass(frozen=True)
class ComputeContext:
    values: ResolvedValues
    horizon: int
    propagation: Propagation
    recorder: StepRecorder


@dataclass
class ModelResult:
    """What ``compute`` returns, before rounding: named scalars and monthly series
    (month 1 first), each with its unit."""

    scalars: dict[str, Decimal] = field(default_factory=dict)
    units: dict[str, str] = field(default_factory=dict)
    monthly: dict[str, list[Decimal]] = field(default_factory=dict)
    monthly_units: dict[str, str] = field(default_factory=dict)


CheckFunction = Callable[[ResolvedValues], list[Issue]]
ComputeFunction = Callable[[ComputeContext], ModelResult]
