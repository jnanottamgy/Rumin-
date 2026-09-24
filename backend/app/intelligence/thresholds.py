"""Thresholds: configuration, not claims.

A detected change, a trend direction or a "high" volatility depends on a threshold. Each one
here has a documented default and a reason for it, can be overridden per request within
bounds, and is recorded in every result that used it — so a reader can see exactly which
test a finding passed and repeat it with another value.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields, replace
from decimal import Decimal, InvalidOperation
from typing import Any

from app.domain.enums import Frequency
from app.intelligence.stats import SIGNIFICANCE_LEVELS


@dataclass(frozen=True)
class ThresholdSpec:
    name: str
    label: str
    unit: str
    default: str
    minimum: str | None
    maximum: str | None
    choices: tuple[str, ...] | None
    integer: bool
    rationale: str


SPECS: tuple[ThresholdSpec, ...] = (
    ThresholdSpec(
        "relative_change_percent",
        "Change in a level or exchange rate",
        "percent",
        "5",
        "0.1",
        "100",
        None,
        False,
        "A round, deliberately high default for annual averages, so that only large "
        "movements are reported. It is a filter for attention, not a statement that smaller "
        "changes do not matter; lower it to see more.",
    ),
    ThresholdSpec(
        "point_change",
        "Change in a rate or a percentage",
        "percentage_points",
        "1",
        "0.01",
        "50",
        None,
        False,
        "Series already expressed in percent (inflation, growth, interest rates, shares of "
        "GDP) are compared in percentage points, never in percent of themselves. One point "
        "is a round default for annual data.",
    ),
    ThresholdSpec(
        "price_move_percent",
        "Move in a daily close",
        "percent",
        "5",
        "0.1",
        "100",
        None,
        False,
        "Day-to-day moves of 5 % or more in a close. Ingestion already flags moves above "
        "40 % as possible data errors; this threshold is for attention, not for quality.",
    ),
    ThresholdSpec(
        "anomaly_score",
        "Unusual change (modified z-score)",
        "score",
        "3.5",
        "1",
        "10",
        None,
        False,
        "Iglewicz and Hoaglin (1993) recommend treating modified z-scores above 3.5 as "
        "potential outliers. The score uses the median and the median absolute deviation, "
        "so one earlier extreme change does not hide the next.",
    ),
    ThresholdSpec(
        "trend_significance",
        "Trend test level",
        "probability",
        "0.05",
        None,
        None,
        SIGNIFICANCE_LEVELS,
        False,
        "A direction is called only when the slope's t statistic exceeds the two-sided "
        "critical value of Student's t at this level. The test assumes independent, normally "
        "distributed residuals; economic series often violate this, so a called trend "
        "describes the window, not a law.",
    ),
    ThresholdSpec(
        "volatility_high_percentile",
        "High volatility",
        "percentile",
        "80",
        "50",
        "100",
        None,
        False,
        "Volatility is compared with the series' own history: the latest window is called "
        "high when its standard deviation is at or above this percentile of every earlier "
        "window of the same length.",
    ),
    ThresholdSpec(
        "dependency_share_percent",
        "Concentrated dependency",
        "percent",
        "50",
        "10",
        "100",
        None,
        False,
        "An entity's stated exposures are called concentrated when at least this share of "
        "its exposure paths pass through one variable. It counts relationships, not money.",
    ),
    ThresholdSpec(
        "min_history",
        "Changes needed for a baseline",
        "count",
        "8",
        "4",
        "200",
        None,
        True,
        "Anomaly and volatility compare the latest change with earlier ones; with fewer than "
        "this many earlier changes the comparison is not made, and the result says so.",
    ),
    ThresholdSpec(
        "window",
        "Window (periods)",
        "periods",
        "",
        "3",
        "250",
        None,
        True,
        "Periods used for the trend and the latest volatility window. Left empty, it "
        "follows the frequency: 5 years, 8 quarters, 12 months or 20 trading days.",
    ),
)
SPEC_BY_NAME = {spec.name: spec for spec in SPECS}
WINDOW_BY_FREQUENCY: dict[str, int] = {
    Frequency.ANNUAL.value: 5,
    Frequency.QUARTERLY.value: 8,
    Frequency.MONTHLY.value: 12,
    Frequency.DAILY.value: 20,
}


@dataclass(frozen=True)
class Thresholds:
    relative_change_percent: Decimal = Decimal(5)
    point_change: Decimal = Decimal(1)
    price_move_percent: Decimal = Decimal(5)
    anomaly_score: Decimal = Decimal("3.5")
    trend_significance: str = "0.05"
    volatility_high_percentile: Decimal = Decimal(80)
    dependency_share_percent: Decimal = Decimal(50)
    min_history: int = 8
    window: int | None = None

    def window_for(self, frequency: str) -> int:
        return self.window or WINDOW_BY_FREQUENCY.get(frequency, 5)

    def to_json(self) -> dict[str, Any]:
        data: dict[str, Any] = {}
        for item in fields(self):
            value = getattr(self, item.name)
            data[item.name] = format(value, "f") if isinstance(value, Decimal) else value
        return data

    def pick(self, *names: str) -> dict[str, Any]:
        """The named thresholds, as recorded with a finding that used them."""
        data = self.to_json()
        return {name: data[name] for name in names}


DEFAULTS = Thresholds()


@dataclass(frozen=True)
class ThresholdProblem:
    field: str
    message: str


class ThresholdError(ValueError):
    def __init__(self, problems: list[ThresholdProblem]) -> None:
        super().__init__("; ".join(problem.message for problem in problems))
        self.problems = problems


def resolve(overrides: Mapping[str, Any] | None) -> Thresholds:
    """The defaults with ``overrides`` applied; every invalid value is reported at once."""
    if not overrides:
        return DEFAULTS
    problems: list[ThresholdProblem] = []
    changes: dict[str, Any] = {}
    for name, raw in overrides.items():
        spec = SPEC_BY_NAME.get(name)
        if spec is None:
            problems.append(ThresholdProblem(name, f"'{name}' is not a threshold."))
            continue
        if raw is None or raw == "":
            continue
        if spec.choices is not None:
            if str(raw) not in spec.choices:
                allowed = ", ".join(spec.choices)
                problems.append(ThresholdProblem(name, f"{spec.label} must be one of {allowed}."))
                continue
            changes[name] = str(raw)
            continue
        if isinstance(raw, bool):
            problems.append(ThresholdProblem(name, f"{spec.label} must be a number."))
            continue
        try:
            value = Decimal(str(raw))
        except InvalidOperation:
            problems.append(ThresholdProblem(name, f"{spec.label} must be a number."))
            continue
        if not value.is_finite():
            problems.append(ThresholdProblem(name, f"{spec.label} must be a finite number."))
            continue
        low = Decimal(spec.minimum) if spec.minimum is not None else None
        high = Decimal(spec.maximum) if spec.maximum is not None else None
        if (low is not None and value < low) or (high is not None and value > high):
            problems.append(
                ThresholdProblem(
                    name,
                    f"{spec.label} must be between {spec.minimum} and {spec.maximum} "
                    f"({spec.unit}).",
                )
            )
            continue
        if spec.integer:
            if value != value.to_integral_value():
                problems.append(ThresholdProblem(name, f"{spec.label} must be a whole number."))
                continue
            changes[name] = int(value)
        else:
            changes[name] = value
    if problems:
        raise ThresholdError(problems)
    return replace(DEFAULTS, **changes)
