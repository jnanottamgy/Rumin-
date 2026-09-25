"""Seeded draws from explicit, bounded distributions: the random part of a Monte Carlo analysis.

A distribution here is an **assumption the user states**, never an estimate — RUMIN stores no
data to fit one to. Three kinds, each bounded, so that no draw can leave an input's range:

* uniform ``U(a, b)``: every value between *a* and *b* equally likely;
* triangular ``T(a, c, b)``: most likely *c*, falling linearly to nothing at *a* and *b*;
* discrete: listed values with positive weights (the only kind for whole-month inputs).

Random numbers come from ``random.Random(seed).random()`` — the Mersenne Twister's 53-bit
floats, the one part of Python's ``random`` module whose sequence for a given seed Python
guarantees not to change between versions. Each float is converted to a decimal exactly and
turned into a draw by the inverse of the distribution's cumulative distribution function, in
the engine's decimal context; so a seed reproduces every draw to the last digit.
"""

from __future__ import annotations

import random
import secrets
from dataclasses import dataclass
from decimal import Decimal
from typing import ClassVar

from app.simulation.decimal_math import ONE, ZERO, arithmetic

SAMPLER_VERSION = "1.0.0"
GENERATOR = "Python random.Random(seed).random() — Mersenne Twister MT19937, 53-bit"
MAX_SEED = 2**63 - 1
MAX_DISCRETE_VALUES = 12
TWO = Decimal(2)
THREE = Decimal(3)
EIGHTEEN = Decimal(18)
TWELVE = Decimal(12)


class DistributionError(ValueError):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


@dataclass(frozen=True)
class Uniform:
    low: Decimal
    high: Decimal
    kind: ClassVar[str] = "uniform"


@dataclass(frozen=True)
class Triangular:
    low: Decimal
    mode: Decimal
    high: Decimal
    kind: ClassVar[str] = "triangular"


@dataclass(frozen=True)
class Discrete:
    values: tuple[Decimal, ...]
    weights: tuple[Decimal, ...]
    kind: ClassVar[str] = "discrete"


Distribution = Uniform | Triangular | Discrete


def check(distribution: Distribution) -> None:
    """Raise ``DistributionError`` unless the parameters define a proper distribution."""
    if isinstance(distribution, Uniform):
        if not distribution.low < distribution.high:
            raise DistributionError("A uniform distribution needs its low below its high.")
    elif isinstance(distribution, Triangular):
        if not distribution.low < distribution.high:
            raise DistributionError("A triangular distribution needs its low below its high.")
        if not distribution.low <= distribution.mode <= distribution.high:
            raise DistributionError(
                "A triangular distribution's most likely value must lie between its low and high."
            )
    else:
        count = len(distribution.values)
        if count < 2 or count > MAX_DISCRETE_VALUES:
            raise DistributionError(
                f"A discrete distribution needs 2 to {MAX_DISCRETE_VALUES} values."
            )
        if len(set(distribution.values)) != count:
            raise DistributionError("A discrete distribution's values must differ.")
        if len(distribution.weights) != count:
            raise DistributionError("Give one weight per value.")
        if any(weight <= ZERO for weight in distribution.weights):
            raise DistributionError("Every weight must be positive.")


def bounds(distribution: Distribution) -> tuple[Decimal, Decimal]:
    """The smallest and largest value a draw can take."""
    if isinstance(distribution, Discrete):
        return min(distribution.values), max(distribution.values)
    return distribution.low, distribution.high


def mean(distribution: Distribution) -> Decimal:
    """The distribution's own mean (what the draws' average should approach)."""
    with arithmetic():
        if isinstance(distribution, Uniform):
            return (distribution.low + distribution.high) / TWO
        if isinstance(distribution, Triangular):
            return (distribution.low + distribution.mode + distribution.high) / THREE
        total = sum(distribution.weights, ZERO)
        return (
            sum(
                (v * w for v, w in zip(distribution.values, distribution.weights, strict=True)),
                ZERO,
            )
            / total
        )


def variance(distribution: Distribution) -> Decimal:
    with arithmetic():
        if isinstance(distribution, Uniform):
            return (distribution.high - distribution.low) ** 2 / TWELVE
        if isinstance(distribution, Triangular):
            a, c, b = distribution.low, distribution.mode, distribution.high
            return (a * a + b * b + c * c - a * b - a * c - b * c) / EIGHTEEN
        centre = mean(distribution)
        total = sum(distribution.weights, ZERO)
        return (
            sum(
                (
                    w * (v - centre) ** 2
                    for v, w in zip(distribution.values, distribution.weights, strict=True)
                ),
                ZERO,
            )
            / total
        )


def cdf(distribution: Distribution, x: Decimal) -> Decimal:
    """P(X ≤ x)."""
    with arithmetic():
        if isinstance(distribution, Discrete):
            total = sum(distribution.weights, ZERO)
            below = sum(
                (
                    w
                    for v, w in zip(distribution.values, distribution.weights, strict=True)
                    if v <= x
                ),
                ZERO,
            )
            return below / total
        low, high = distribution.low, distribution.high
        if x <= low:
            return ZERO
        if x >= high:
            return ONE
        if isinstance(distribution, Uniform):
            return (x - low) / (high - low)
        mode = distribution.mode
        if x <= mode:
            return (x - low) ** 2 / ((high - low) * (mode - low))
        return ONE - (high - x) ** 2 / ((high - low) * (high - mode))


def quantile(distribution: Distribution, u: Decimal) -> Decimal:
    """The inverse of the cumulative distribution function at ``u`` ∈ [0, 1)."""
    if not ZERO <= u < ONE:
        raise ValueError("u must lie in [0, 1).")
    with arithmetic():
        if isinstance(distribution, Uniform):
            return distribution.low + (distribution.high - distribution.low) * u
        if isinstance(distribution, Triangular):
            a, c, b = distribution.low, distribution.mode, distribution.high
            if u < (c - a) / (b - a):
                return a + (u * (b - a) * (c - a)).sqrt()
            return b - ((ONE - u) * (b - a) * (b - c)).sqrt()
        total = sum(distribution.weights, ZERO)
        target = u * total
        cumulative = ZERO
        for value, weight in zip(distribution.values, distribution.weights, strict=True):
            cumulative += weight
            if target < cumulative:
                return value
        return distribution.values[-1]  # pragma: no cover - u < 1 always stops above


class Stream:
    """Uniform numbers in [0, 1) from one seed, as exact decimals."""

    def __init__(self, seed: int) -> None:
        if not 0 <= seed <= MAX_SEED:
            raise ValueError(f"A seed is a whole number from 0 to {MAX_SEED}.")
        self.seed = seed
        # Reproducibility, not secrecy, is the point: a seeded, documented generator.
        self._random = random.Random(seed)  # noqa: S311

    def next(self) -> Decimal:
        # A double in [0, 1) is k / 2⁵³; Decimal(float) converts it exactly.
        return Decimal(self._random.random())


def new_seed() -> int:
    """A seed for a request that gives none (recorded with the analysis)."""
    return secrets.randbits(63)
