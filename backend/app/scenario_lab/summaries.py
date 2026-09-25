"""Summaries of a Monte Carlo sample — exact, reproducible, and no more precise than the draws.

Every value is computed in the engine's decimal context from the sample in draw order, so the
same draws always give the same digits (and the same result hash). Methods:

* **Percentiles**: linear interpolation between order statistics (Hyndman & Fan, 1996,
  type 7 — the method of Excel's ``PERCENTILE.INC`` and R's default). With the values sorted
  y₁ ≤ … ≤ yₙ and h = (n − 1)·p + 1, P = y₍⌊h⌋₎ + (h − ⌊h⌋)(y₍⌊h⌋+1₎ − y₍⌊h⌋₎).
* **Interval for a percentile**: two order statistics y₍l₎ and y₍u₎ chosen around n·p. The
  number of draws below the true p-quantile is binomial(n, p), so the interval
  [y₍l₎, y₍u₎) contains it with probability Σₖ₌ₗ^{u−1} C(n, k) pᵏ(1 − p)ⁿ⁻ᵏ — computed exactly
  and reported as the coverage (exact for a continuous result; conservative with ties).
* **Monte Carlo standard error** of the mean: s/√n, s the sample standard deviation.
* **Spearman rank correlation**: Pearson's correlation of the ranks (ties share the average
  rank). It measures monotonic association within the sample — not causation and not a share
  of the variance.
* **Running mean** at checkpoints, and the **two halves** of the draws compared in standard
  errors: diagnostics of whether the draws are enough, not tests of the model.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from fractions import Fraction

from app.intelligence.stats import mean, sample_std
from app.simulation.decimal_math import HUNDRED, ONE, ZERO, arithmetic

PERCENTILES = (5, 10, 25, 50, 75, 90, 95)
INTERVAL_PERCENTILES = (5, 50, 95)
HISTOGRAM_BINS = 20
CHECKPOINTS = 20
# The standard normal's two-sided 95 % point, used only to place the order statistics; the
# coverage reported is the exact binomial one.
Z_95 = Decimal("1.959963984540054")
COVERAGE_PLACES = Decimal("0.0001")


def percentile(ordered: Sequence[Decimal], p: int | Decimal) -> Decimal:
    """The p-th percentile (0–100) of ascending ``ordered`` values, type 7."""
    n = len(ordered)
    if n == 0:
        raise ValueError("A percentile of no values is undefined.")
    with arithmetic():
        h = Decimal(n - 1) * Decimal(p) / HUNDRED
        low = int(h.to_integral_value(rounding=ROUND_FLOOR))
        if low >= n - 1:
            return ordered[-1]
        fraction = h - Decimal(low)
        return ordered[low] + fraction * (ordered[low + 1] - ordered[low])


@dataclass(frozen=True)
class Interval:
    lower_rank: int  # 1-based order statistics
    upper_rank: int
    lower: Decimal
    upper: Decimal
    coverage: Decimal  # the exact probability that [lower, upper) contains the percentile


def binomial_coverage(n: int, p: Fraction, lower_rank: int, upper_rank: int) -> Fraction:
    """P(lower_rank ≤ B ≤ upper_rank − 1) for B ~ binomial(n, p), exactly."""
    q = 1 - p
    return sum(
        (Fraction(math.comb(n, k)) * p**k * q ** (n - k) for k in range(lower_rank, upper_rank)),
        Fraction(0),
    )


def percentile_interval(ordered: Sequence[Decimal], p: int) -> Interval:
    """A distribution-free interval for the p-th percentile, with its exact coverage."""
    n = len(ordered)
    share = Fraction(p, 100)
    with arithmetic():
        expected = Decimal(n) * Decimal(p) / HUNDRED
        spread = Z_95 * (expected * (ONE - Decimal(p) / HUNDRED)).sqrt()
        lower = int((expected - spread).to_integral_value(rounding=ROUND_FLOOR))
        upper = int((expected + spread).to_integral_value(rounding=ROUND_CEILING)) + 1
    lower = max(1, lower)
    upper = min(n, upper)
    coverage = binomial_coverage(n, share, lower, upper)
    with arithmetic():
        exact = Decimal(coverage.numerator) / Decimal(coverage.denominator)
        rounded = exact.quantize(COVERAGE_PLACES)
    return Interval(lower, upper, ordered[lower - 1], ordered[upper - 1], rounded)


def ranks(values: Sequence[Decimal]) -> list[Decimal]:
    """1-based ranks; tied values share the average of their ranks."""
    order = sorted(range(len(values)), key=lambda index: values[index])
    result = [ZERO] * len(values)
    position = 0
    with arithmetic():
        while position < len(order):
            end = position
            while end + 1 < len(order) and values[order[end + 1]] == values[order[position]]:
                end += 1
            average = Decimal(position + end + 2) / Decimal(2)
            for index in order[position : end + 1]:
                result[index] = average
            position = end + 1
    return result


def spearman(x: Sequence[Decimal], y: Sequence[Decimal]) -> Decimal | None:
    """Spearman's rank correlation; None when either sample does not vary."""
    if len(x) != len(y) or len(x) < 3:
        raise ValueError("A rank correlation needs two samples of the same size (3 or more).")
    rx, ry = ranks(x), ranks(y)
    with arithmetic():
        mx, my = mean(rx), mean(ry)
        sxx = sum(((value - mx) ** 2 for value in rx), ZERO)
        syy = sum(((value - my) ** 2 for value in ry), ZERO)
        if sxx == ZERO or syy == ZERO:
            return None
        sxy = sum(((a - mx) * (b - my) for a, b in zip(rx, ry, strict=True)), ZERO)
        return sxy / (sxx * syy).sqrt()


@dataclass(frozen=True)
class Bin:
    low: Decimal
    high: Decimal
    count: int


def histogram(ordered: Sequence[Decimal], bins: int = HISTOGRAM_BINS) -> list[Bin]:
    """Equal-width bins from the smallest to the largest value (the last bin includes it).
    One bin when every value is the same."""
    low, high = ordered[0], ordered[-1]
    if low == high:
        return [Bin(low, high, len(ordered))]
    with arithmetic():
        width = (high - low) / Decimal(bins)
        edges = [low + width * Decimal(index) for index in range(bins)] + [high]
        counts = [0] * bins
        for value in ordered:
            index = int(((value - low) / width).to_integral_value(rounding=ROUND_FLOOR))
            counts[min(index, bins - 1)] += 1
    return [Bin(edges[index], edges[index + 1], counts[index]) for index in range(bins)]


@dataclass(frozen=True)
class Checkpoint:
    draws: int
    mean: Decimal
    standard_error: Decimal | None


def running(values: Sequence[Decimal], checkpoints: int = CHECKPOINTS) -> list[Checkpoint]:
    """The mean of the first k values, and its standard error, at evenly spaced k."""
    n = len(values)
    marks = sorted(
        {max(1, math.ceil(n * index / checkpoints)) for index in range(1, 1 + checkpoints)}
    )
    result: list[Checkpoint] = []
    total = ZERO
    squares = ZERO
    seen = 0
    with arithmetic():
        for mark in marks:
            while seen < mark:
                total += values[seen]
                squares += values[seen] * values[seen]
                seen += 1
            centre = total / Decimal(seen)
            error = None
            if seen > 1:
                variance = (squares - Decimal(seen) * centre * centre) / Decimal(seen - 1)
                error = (max(variance, ZERO) / Decimal(seen)).sqrt()
            result.append(Checkpoint(seen, centre, error))
    return result


@dataclass(frozen=True)
class Halves:
    first_mean: Decimal
    second_mean: Decimal
    z: Decimal | None  # the difference in standard errors; None when neither half varies


def halves(values: Sequence[Decimal]) -> Halves:
    """The first and second halves of the draws (in draw order) compared."""
    middle = len(values) // 2
    first, second = values[:middle], values[middle:]
    first_mean, second_mean = mean(first), mean(second)
    with arithmetic():
        variance = sample_std(first) ** 2 / Decimal(len(first)) + sample_std(second) ** 2 / Decimal(
            len(second)
        )
        if variance == ZERO:
            return Halves(first_mean, second_mean, None)
        return Halves(first_mean, second_mean, (first_mean - second_mean) / variance.sqrt())


def share_at_or_below(values: Sequence[Decimal], threshold: Decimal) -> Decimal:
    with arithmetic():
        return Decimal(sum(1 for value in values if value <= threshold)) / Decimal(len(values))


def share_below(values: Sequence[Decimal], threshold: Decimal) -> Decimal:
    with arithmetic():
        return Decimal(sum(1 for value in values if value < threshold)) / Decimal(len(values))


def standard_error(values: Sequence[Decimal]) -> Decimal:
    with arithmetic():
        return sample_std(values) / Decimal(len(values)).sqrt()


__all__ = [
    "CHECKPOINTS",
    "HISTOGRAM_BINS",
    "INTERVAL_PERCENTILES",
    "PERCENTILES",
    "Bin",
    "Checkpoint",
    "Halves",
    "Interval",
    "binomial_coverage",
    "halves",
    "histogram",
    "mean",
    "percentile",
    "percentile_interval",
    "ranks",
    "running",
    "sample_std",
    "share_at_or_below",
    "share_below",
    "spearman",
    "standard_error",
]
