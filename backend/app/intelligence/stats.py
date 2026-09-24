"""Exact descriptive statistics for the intelligence layer.

Every calculation runs in the engine's decimal context (34 significant digits, half-even
rounding, traps on invalid operations), so the same stored values always give the same
digits and results can be hashed and reproduced. Nothing here estimates a probability of a
future value: the statistics describe the stored history.

Methods (see ``docs/intelligence/signals.md``):

* **Change** between consecutive values: relative (percent of the earlier value, which must
  be positive) for levels, prices and exchange rates; a difference in percentage points for
  series already expressed in percent.
* **Least-squares trend** over x = 0 … n−1: the slope, its standard error and the *t*
  statistic; a direction is called only when |t| exceeds the two-sided critical value of
  Student's *t* with n − 2 degrees of freedom.
* **Sample standard deviation** (n − 1 in the denominator).
* **Modified z-score** (Iglewicz and Hoaglin, 1993): 0.6745 × (x − median) / MAD, where MAD
  is the median absolute deviation of the reference values. Undefined when MAD is zero.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from app.simulation.decimal_math import HUNDRED, ZERO, arithmetic, to_output

TWO = Decimal(2)
MODIFIED_Z_CONSTANT = Decimal("0.6745")

# Two-sided critical values of Student's t distribution by degrees of freedom (the standard
# published table, three decimals). Degrees of freedom between two rows use the lower row,
# whose value is larger, so a test is never less strict than stated.
_T_TABLE = """
df     0.10    0.05    0.01
1     6.314  12.706  63.657
2     2.920   4.303   9.925
3     2.353   3.182   5.841
4     2.132   2.776   4.604
5     2.015   2.571   4.032
6     1.943   2.447   3.707
7     1.895   2.365   3.499
8     1.860   2.306   3.355
9     1.833   2.262   3.250
10    1.812   2.228   3.169
11    1.796   2.201   3.106
12    1.782   2.179   3.055
13    1.771   2.160   3.012
14    1.761   2.145   2.977
15    1.753   2.131   2.947
16    1.746   2.120   2.921
17    1.740   2.110   2.898
18    1.734   2.101   2.878
19    1.729   2.093   2.861
20    1.725   2.086   2.845
21    1.721   2.080   2.831
22    1.717   2.074   2.819
23    1.714   2.069   2.807
24    1.711   2.064   2.797
25    1.708   2.060   2.787
26    1.706   2.056   2.779
27    1.703   2.052   2.771
28    1.701   2.048   2.763
29    1.699   2.045   2.756
30    1.697   2.042   2.750
40    1.684   2.021   2.704
60    1.671   2.000   2.660
120   1.658   1.980   2.617
"""
SIGNIFICANCE_LEVELS = ("0.10", "0.05", "0.01")


def _parse_table(table: str) -> dict[str, dict[int, Decimal]]:
    rows = [line.split() for line in table.strip().splitlines()[1:]]
    return {
        level: {int(row[0]): Decimal(row[1 + index]) for row in rows}
        for index, level in enumerate(SIGNIFICANCE_LEVELS)
    }


T_CRITICAL: dict[str, dict[int, Decimal]] = _parse_table(_T_TABLE)


def t_critical(degrees_of_freedom: int, significance: str) -> Decimal:
    """The two-sided critical value of Student's t (never smaller than the exact value)."""
    table = T_CRITICAL[significance]
    if degrees_of_freedom < 1:
        raise ValueError("The t test needs at least one degree of freedom.")
    if degrees_of_freedom in table:
        return table[degrees_of_freedom]
    below = [df for df in table if df < degrees_of_freedom]
    if degrees_of_freedom > max(table):
        # Beyond the last row the value is between that row and the normal limit; the row
        # (the larger value) keeps the test conservative.
        return table[max(table)]
    return table[max(below)]


def rounded(value: Decimal | None) -> Decimal | None:
    """A derived value as results carry it: half-even to 10 decimal places, like every
    engine output. Stored values are never rounded."""
    return None if value is None else to_output(value, "A derived value")


def mean(values: Sequence[Decimal]) -> Decimal:
    if not values:
        raise ValueError("The mean of no values is undefined.")
    with arithmetic():
        return sum(values, ZERO) / Decimal(len(values))


def sample_std(values: Sequence[Decimal]) -> Decimal:
    """Sample standard deviation (n − 1). Needs at least two values."""
    if len(values) < 2:
        raise ValueError("A standard deviation needs at least two values.")
    centre = mean(values)
    with arithmetic():
        squares = sum(((value - centre) ** 2 for value in values), ZERO)
        return (squares / Decimal(len(values) - 1)).sqrt()


def median(values: Sequence[Decimal]) -> Decimal:
    if not values:
        raise ValueError("The median of no values is undefined.")
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    with arithmetic():
        return (ordered[middle - 1] + ordered[middle]) / TWO


def mad(values: Sequence[Decimal]) -> Decimal:
    """Median absolute deviation from the median."""
    centre = median(values)
    with arithmetic():
        deviations = [abs(value - centre) for value in values]
    return median(deviations)


def modified_z(value: Decimal, reference: Sequence[Decimal]) -> Decimal | None:
    """0.6745 × (value − median) / MAD of ``reference``; ``None`` when MAD is zero."""
    spread = mad(reference)
    if spread == ZERO:
        return None
    with arithmetic():
        return MODIFIED_Z_CONSTANT * (value - median(reference)) / spread


@dataclass(frozen=True)
class Trend:
    """Least-squares line through (0, y₀) … (n−1, yₙ₋₁)."""

    n: int
    slope: Decimal
    intercept: Decimal
    standard_error: Decimal | None  # of the slope; None with two points (no residual freedom)
    t: Decimal | None  # slope / standard error; None when undefined
    exact_fit: bool  # every point on the line (the standard error is zero)


def least_squares(values: Sequence[Decimal], positions: Sequence[int] | None = None) -> Trend:
    """The ordinary least-squares slope of ``values`` against their ``positions`` (0 … n−1
    by default; periods since the first value when a series has gaps)."""
    n = len(values)
    if n < 2:
        raise ValueError("A trend needs at least two values.")
    if positions is not None and len(positions) != n:
        raise ValueError("Each value needs a position.")
    with arithmetic():
        xs = [Decimal(i) for i in (positions if positions is not None else range(n))]
        x_bar = sum(xs, ZERO) / Decimal(n)
        y_bar = sum(values, ZERO) / Decimal(n)
        sxx = sum(((x - x_bar) ** 2 for x in xs), ZERO)
        sxy = sum(((x - x_bar) * (y - y_bar) for x, y in zip(xs, values, strict=True)), ZERO)
        slope = sxy / sxx
        intercept = y_bar - slope * x_bar
        if n == 2:
            return Trend(n, slope, intercept, None, None, True)
        residuals = [y - (intercept + slope * x) for x, y in zip(xs, values, strict=True)]
        sse = sum((r**2 for r in residuals), ZERO)
        if sse == ZERO:
            return Trend(n, slope, intercept, ZERO, None, True)
        error = ((sse / Decimal(n - 2)) / sxx).sqrt()
        return Trend(n, slope, intercept, error, slope / error, False)


def relative_change(earlier: Decimal, later: Decimal) -> Decimal | None:
    """(later − earlier) / earlier × 100; ``None`` unless ``earlier`` is positive."""
    if earlier <= ZERO:
        return None
    with arithmetic():
        return (later - earlier) / earlier * HUNDRED


def point_change(earlier: Decimal, later: Decimal) -> Decimal:
    """later − earlier (for values already in percent: percentage points)."""
    with arithmetic():
        return later - earlier


def percentile_rank(value: Decimal, population: Sequence[Decimal]) -> Decimal:
    """Share of ``population`` at or below ``value``, in percent."""
    if not population:
        raise ValueError("A percentile rank needs a population.")
    with arithmetic():
        return (
            Decimal(sum(1 for item in population if item <= value))
            / Decimal(len(population))
            * HUNDRED
        )
