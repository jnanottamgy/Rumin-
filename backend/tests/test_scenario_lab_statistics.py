"""The Monte Carlo analysis's statistics: seeded sampling and the summaries of a sample.

Statistical checks use fixed seeds, so they are deterministic: each asserts that the sampler
behaves like its distribution (moments, Kolmogorov–Smirnov, χ²) at a strict level, and would
fail on a biased or broken sampler. Every figure is SYNTHETIC.
"""

from __future__ import annotations

import math
from decimal import Decimal
from fractions import Fraction

import pytest

from app.scenario_lab.sampling import (
    Discrete,
    Distribution,
    DistributionError,
    Stream,
    Triangular,
    Uniform,
    bounds,
    cdf,
    check,
    mean,
    quantile,
    variance,
)
from app.scenario_lab.summaries import (
    binomial_coverage,
    halves,
    histogram,
    percentile,
    percentile_interval,
    ranks,
    running,
    share_at_or_below,
    share_below,
    spearman,
    standard_error,
)
from app.scenario_lab.summaries import mean as mean_of
from app.simulation.decimal_math import arithmetic

D = Decimal


def draws(distribution: Distribution, n: int, seed: int) -> list[Decimal]:
    stream = Stream(seed)
    return [quantile(distribution, stream.next()) for _ in range(n)]


def ks_statistic(sample: list[Decimal], distribution: Distribution) -> float:
    """sup |Fₙ(x) − F(x)| of a continuous distribution."""
    ordered = sorted(sample)
    n = len(ordered)
    worst = 0.0
    for index, value in enumerate(ordered):
        f = float(cdf(distribution, value))
        worst = max(worst, (index + 1) / n - f, f - index / n)
    return worst


def ks_critical(n: int) -> float:
    # The asymptotic critical value at a 0.1 % significance level.
    return 1.9495 / math.sqrt(n)


# --- The generator -------------------------------------------------------------------------------


def test_the_generator_gives_the_documented_values_for_seed_42() -> None:
    # The Mersenne Twister's first three doubles for seed 42, as documented for CPython: if
    # these ever change, every stored Monte Carlo analysis would stop reproducing.
    stream = Stream(42)
    assert [stream.next() for _ in range(3)] == [
        D(0.6394267984578837),
        D(0.025010755222666936),
        D(0.27502931836911926),
    ]


def test_a_seed_reproduces_every_draw_and_another_does_not() -> None:
    distribution = Triangular(D(-10), D(5), D(40))

    assert draws(distribution, 50, seed=7) == draws(distribution, 50, seed=7)
    assert draws(distribution, 50, seed=7) != draws(distribution, 50, seed=8)


@pytest.mark.parametrize("seed", [-1, 2**63])
def test_a_seed_outside_the_range_is_refused(seed: int) -> None:
    with pytest.raises(ValueError, match="whole number from 0"):
        Stream(seed)


# --- Distributions ------------------------------------------------------------------------------


def test_the_distributions_own_moments() -> None:
    assert (mean(Uniform(D(0), D(12))), variance(Uniform(D(0), D(12)))) == (D(6), D(12))
    # (0 + 36 + 9 − 0 − 0 − 18) / 18 = 1.5
    assert (mean(Triangular(D(0), D(3), D(6))), variance(Triangular(D(0), D(3), D(6)))) == (
        D(3),
        D("1.5"),
    )
    # Values 0, 3, 6 weighted 1, 2, 1: mean 3, variance (9 + 0 + 9) / 4 = 4.5.
    three = Discrete((D(0), D(3), D(6)), (D(1), D(2), D(1)))
    assert (mean(three), variance(three)) == (D(3), D("4.5"))
    assert bounds(three) == (D(0), D(6))


@pytest.mark.parametrize(
    "distribution",
    [
        Uniform(D(0), D(1)),
        Uniform(D(-25), D(40)),
        Triangular(D(-10), D(5), D(40)),
        Triangular(D(0), D(0), D(1)),  # most likely at the low end
        Triangular(D(0), D(1), D(1)),  # most likely at the high end
    ],
    ids=["unit", "wide", "skewed", "mode-at-low", "mode-at-high"],
)
def test_continuous_draws_follow_their_distribution(distribution: Distribution) -> None:
    n = 20_000
    sample = draws(distribution, n, seed=20260925)
    low, high = bounds(distribution)

    assert all(low <= value <= high for value in sample)
    sd = math.sqrt(float(variance(distribution)))
    centre = sum(sample) / n
    assert abs(float(centre) - float(mean(distribution))) < 4 * sd / math.sqrt(n)
    observed = float(sum((value - centre) ** 2 for value in sample) / (n - 1))
    assert abs(observed / float(variance(distribution)) - 1) < 0.03
    assert ks_statistic(sample, distribution) < ks_critical(n)


def test_a_biased_sampler_fails_the_same_check() -> None:
    # The check has teeth: squaring uniform numbers skews them towards the low end.
    n = 20_000
    stream = Stream(20260925)
    skewed = [stream.next() ** 2 for _ in range(n)]

    assert ks_statistic(skewed, Uniform(D(0), D(1))) > ks_critical(n)


def test_discrete_draws_follow_their_weights() -> None:
    n = 12_000
    distribution = Discrete((D(0), D(3), D(6)), (D(1), D(2), D(1)))
    sample = draws(distribution, n, seed=11)
    counts = [sample.count(value) for value in distribution.values]
    expected = [3_000, 6_000, 3_000]
    chi_square = sum((o - e) ** 2 / e for o, e in zip(counts, expected, strict=True))

    assert set(sample) == {D(0), D(3), D(6)}
    assert chi_square < 13.816  # χ² with 2 degrees of freedom at a 0.1 % level


@pytest.mark.parametrize("u", ["0", "0.1", "0.25", "0.5", "0.9", "0.999999"])
def test_the_quantile_inverts_the_cumulative_distribution(u: str) -> None:
    for distribution in (Uniform(D(-5), D(15)), Triangular(D(-10), D(5), D(40))):
        assert abs(cdf(distribution, quantile(distribution, D(u))) - D(u)) < D("1e-30")


@pytest.mark.parametrize(
    ("distribution", "message"),
    [
        (Uniform(D(5), D(5)), "low below its high"),
        (Triangular(D(0), D(7), D(5)), "between its low and high"),
        (Triangular(D(5), D(5), D(5)), "low below its high"),
        (Discrete((D(1),), (D(1),)), "2 to 12 values"),
        (Discrete((D(1), D(1)), (D(1), D(1))), "must differ"),
        (Discrete((D(1), D(2)), (D(1),)), "one weight per value"),
        (Discrete((D(1), D(2)), (D(1), D(0))), "must be positive"),
    ],
)
def test_improper_distributions_are_refused(distribution: Distribution, message: str) -> None:
    with pytest.raises(DistributionError, match=message):
        check(distribution)


# --- Summaries ------------------------------------------------------------------------------------

ONE_TO_TEN = [D(value) for value in range(1, 11)]


@pytest.mark.parametrize(
    ("p", "expected"),
    [(0, "1"), (5, "1.45"), (25, "3.25"), (50, "5.5"), (90, "9.1"), (95, "9.55"), (100, "10")],
)
def test_percentiles_match_excel_percentile_inc(p: int, expected: str) -> None:
    # Excel: =PERCENTILE.INC({1,2,…,10}, p/100).
    assert percentile(ONE_TO_TEN, p) == D(expected)


def test_a_percentile_interval_reports_its_exact_coverage() -> None:
    # n = 20, the median: order statistics 5 and 16; coverage P(5 ≤ B ≤ 15) for B ~ Bin(20, ½)
    # = 1 − 2 × (1 + 20 + 190 + 1,140 + 4,845) / 2²⁰ = 0.98818…
    values = [D(value) for value in range(1, 21)]
    interval = percentile_interval(values, 50)

    assert (interval.lower_rank, interval.upper_rank) == (5, 16)
    assert (interval.lower, interval.upper) == (D(5), D(16))
    assert interval.coverage == D("0.9882")
    assert binomial_coverage(20, Fraction(1, 2), 5, 16) == 1 - Fraction(2 * 6196, 2**20)


def test_percentile_intervals_contain_the_true_percentile_as_often_as_stated() -> None:
    # 400 samples of 200 uniform draws: the interval for the median should contain 0.5 about
    # as often as its stated coverage (checked within four binomial standard errors).
    stream = Stream(5)
    hits = 0
    coverage = None
    trials = 400
    for _ in range(trials):
        sample = sorted(stream.next() for _ in range(200))
        interval = percentile_interval(sample, 50)
        coverage = float(interval.coverage)
        hits += interval.lower <= D("0.5") < interval.upper
    assert coverage is not None
    assert abs(hits / trials - coverage) < 4 * math.sqrt(coverage * (1 - coverage) / trials)


def test_ranks_share_ties_and_spearman_matches_a_hand_calculation() -> None:
    assert ranks([D(10), D(20), D(20), D(30)]) == [D(1), D("2.5"), D("2.5"), D(4)]
    # y ranks 1, 2, 3.5, 5, 3.5: Σdxdy = 8, Σdx² = 10, Σdy² = 9.5, rho = 8 / √95.
    rho = spearman([D(1), D(2), D(3), D(4), D(5)], [D(5), D(6), D(7), D(8), D(7)])
    with arithmetic():
        assert rho == D(8) / D(95).sqrt()
    assert spearman([D(1), D(2), D(3)], [D(1), D(8), D(27)]) == D(1)
    assert spearman([D(1), D(2), D(3)], [D(9), D(4), D(1)]) == D(-1)
    assert spearman([D(1), D(2), D(3)], [D(4), D(4), D(4)]) is None


def test_the_histogram_covers_every_value() -> None:
    sample = draws(Uniform(D(0), D(100)), 1_000, seed=3)
    bins = histogram(sorted(sample))

    assert len(bins) == 20
    assert sum(item.count for item in bins) == 1_000
    assert bins[0].low == min(sample) and bins[-1].high == max(sample)
    assert histogram([D(4), D(4), D(4)])[0].count == 3


def test_the_running_mean_ends_at_the_sample_mean() -> None:
    sample = draws(Uniform(D(0), D(1)), 1_000, seed=9)
    points = running(sample)

    assert [point.draws for point in points][:3] == [50, 100, 150]
    assert points[-1].draws == 1_000
    assert points[-1].mean == mean_of(sample)
    assert points[-1].standard_error is not None
    assert abs(points[-1].standard_error - standard_error(sample)) < D("1e-25")


def test_the_two_halves_are_compared_in_standard_errors() -> None:
    compared = halves([D(1), D(2), D(3), D(4), D(5), D(6)])

    assert (compared.first_mean, compared.second_mean) == (D(2), D(5))
    # (2 − 5) / √(1/3 + 1/3)
    with arithmetic():
        assert compared.z == D(-3) / (D(2) / D(3)).sqrt()
    assert halves([D(1)] * 6).z is None


def test_shares_count_draws_against_a_threshold() -> None:
    assert share_below(ONE_TO_TEN, D(3)) == D("0.2")
    assert share_at_or_below(ONE_TO_TEN, D(3)) == D("0.3")
