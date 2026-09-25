"""Monte Carlo analysis of a stored execution — **stochastic analysis** under stated assumptions.

The user gives one or more of the execution's quantities an explicit distribution (uniform,
triangular or discrete, see ``sampling``). Each draw sets every such quantity to a value drawn
from its distribution, independently of the others, and the execution's models and lines are
re-evaluated (``evaluation.Evaluator``); everything else keeps the execution's value. The
spread of the resulting line or metric shows how much it would vary **if the quantities
varied as stated** — conditional on those distributions, which are assumptions, not
estimates. It is not a forecast and not a probability of any future value.

* Each distribution must lie inside its input's valid range, with no more decimals than the
  input accepts, so a draw is never clipped; draws are rounded half to even to the input's
  decimals.
* A draw that breaks a model's own rule, or needs a graph relationship the execution's stored
  snapshot does not state, is rejected — counted with its reason, never adjusted. The
  summaries then describe the accepted draws only, and say so.
* Bounded: 100–2,000 draws, at most eight quantities, a deadline; fewer than 100 accepted
  draws give no summary.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.scenario_lab import summaries
from app.scenario_lab.aggregate import LINE_EQUATIONS, METRIC_LABELS
from app.scenario_lab.evaluation import (
    DeadlineExceeded,
    Evaluator,
    Skipped,
    Target,
    conform,
    targets,
    value_problem,
)
from app.scenario_lab.executor import Member
from app.scenario_lab.profiles import LINE_LABELS
from app.scenario_lab.sampling import (
    Discrete,
    Distribution,
    DistributionError,
    Stream,
    Triangular,
    Uniform,
    check,
    mean,
    quantile,
    variance,
)
from app.scenario_lab.spec import ScenarioSpec
from app.simulation.decimal_math import ZERO, arithmetic, text, to_output
from app.simulation.validation import decimal_places

MIN_DRAWS = 100
MAX_DRAWS = 2_000
DEFAULT_DRAWS = 500
MAX_QUANTITIES = 8
MIN_ACCEPTED = 100
DEADLINE_SECONDS = 20.0
# Two halves whose means differ by more than this many standard errors are flagged.
HALVES_FLAG = Decimal(3)
METRICS = (*LINE_EQUATIONS, *METRIC_LABELS)

INDEPENDENCE_NOTE = (
    "The quantities are drawn independently of each other: a relationship between them (a "
    "weaker rupee when crude oil rises, say) is not modelled."
)
CONDITIONAL_NOTE = (
    "The spread describes the result if the quantities varied as you stated — the "
    "distributions are your assumptions, not estimates from data. It is not a forecast and "
    "not the probability of any outcome."
)


class MonteCarloError(ValueError):
    def __init__(self, message: str, *, field: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.field = field


@dataclass(frozen=True)
class Assumption:
    """One quantity's stated distribution."""

    target: str
    distribution: Distribution


def distribution_json(distribution: Distribution) -> dict[str, Any]:
    if isinstance(distribution, Uniform):
        return {"kind": "uniform", "low": text(distribution.low), "high": text(distribution.high)}
    if isinstance(distribution, Triangular):
        return {
            "kind": "triangular",
            "low": text(distribution.low),
            "mode": text(distribution.mode),
            "high": text(distribution.high),
        }
    return {
        "kind": "discrete",
        "values": [text(value) for value in distribution.values],
        "weights": [text(weight) for weight in distribution.weights],
    }


def _points(distribution: Distribution) -> list[Decimal]:
    """Every value the distribution is defined by (its ends, its mode, its listed values)."""
    if isinstance(distribution, Uniform):
        return [distribution.low, distribution.high]
    if isinstance(distribution, Triangular):
        return [distribution.low, distribution.mode, distribution.high]
    return list(distribution.values)


def plan(
    available: dict[str, Target], assumptions: Sequence[Assumption]
) -> list[tuple[Target, Distribution]]:
    """Check every stated distribution against its quantity; the pairs to draw from."""
    if not assumptions:
        raise MonteCarloError("Give at least one quantity a distribution.", field="quantities")
    if len(assumptions) > MAX_QUANTITIES:
        raise MonteCarloError(
            f"At most {MAX_QUANTITIES} quantities per analysis.", field="quantities"
        )
    names = [item.target for item in assumptions]
    if len(names) != len(set(names)):
        raise MonteCarloError("Each quantity can have only one distribution.", field="quantities")
    planned: list[tuple[Target, Distribution]] = []
    for index, item in enumerate(assumptions):
        field = f"quantities[{index}]"
        target = available.get(item.target)
        if target is None:
            raise MonteCarloError(
                f"'{item.target}' is not a quantity of this execution.", field=field
            )
        try:
            check(item.distribution)
        except DistributionError as error:
            raise MonteCarloError(f"{target.label}: {error.message}", field=field) from error
        if target.integer and not isinstance(item.distribution, Discrete):
            raise MonteCarloError(
                f"{target.label} counts whole months: give it a discrete distribution.",
                field=field,
            )
        definition = target.definition
        places = 0 if target.integer else definition.max_decimals
        for value in _points(item.distribution):
            if decimal_places(value) > places:
                raise MonteCarloError(
                    f"{target.label} accepts at most {places} decimal places; "
                    f"{text(value)} has more.",
                    field=field,
                )
            problem = value_problem(target, value)
            if problem:
                raise MonteCarloError(
                    f"Every value of {target.label}'s distribution must be valid: "
                    f"{text(value)} {problem}.",
                    field=field,
                )
        planned.append((target, item.distribution))
    return planned


def _metric_label(metric: str) -> str:
    return LINE_LABELS.get(metric) or METRIC_LABELS.get(metric, metric)


def _kind(metric: str) -> str:
    return "line_change" if metric in LINE_EQUATIONS else "metric_value"


def run(
    spec: ScenarioSpec,
    members: Sequence[Member],
    assumptions: Sequence[Assumption],
    *,
    metric: str,
    draws: int,
    seed: int,
    threshold: Decimal | None = None,
    deadline_seconds: float = DEADLINE_SECONDS,
) -> dict[str, Any]:
    """Draw, re-evaluate and summarise. Pure given its arguments: the same seed and inputs
    always give the same result, digit for digit."""
    if metric not in METRICS:
        raise MonteCarloError(f"'{metric}' is not a line or metric of the Lab.", field="metric")
    if not MIN_DRAWS <= draws <= MAX_DRAWS:
        raise MonteCarloError(f"Choose between {MIN_DRAWS} and {MAX_DRAWS:,} draws.", field="draws")
    planned = plan(targets(spec, members), assumptions)
    evaluator = Evaluator(spec, members, deadline_seconds=deadline_seconds)
    base = evaluator.base_totals.get(metric)
    if base is None:
        raise MonteCarloError(
            f"This execution has no {metric.replace('_', ' ')}: no included model produces it.",
            field="metric",
        )

    stream = Stream(seed)
    values: list[Decimal] = []
    inputs: list[list[Decimal]] = [[] for _ in planned]
    outputs: dict[str, list[Decimal]] = {name: [] for name in evaluator.base_totals}
    rejected: Counter[str] = Counter()
    examples: dict[str, str] = {}
    for _ in range(draws):
        # Every draw takes one number per quantity, rejected or not, so a rejection never
        # shifts the draws after it.
        drawn = [
            (target, conform(target.definition, quantile(distribution, stream.next())))
            for target, distribution in planned
        ]
        try:
            result = evaluator.evaluate(drawn)
        except Skipped as skipped:
            rejected[skipped.code] += 1
            examples.setdefault(skipped.code, skipped.message)
            continue
        except DeadlineExceeded as stopped:
            raise MonteCarloError(
                f"The analysis stopped after {stopped.evaluations:,} draws: it exceeded "
                f"{stopped.seconds:g} seconds. Use fewer draws."
            ) from None
        values.append(result[metric])
        for index, (_, value) in enumerate(drawn):
            inputs[index].append(value)
        for name in outputs:
            outputs[name].append(result[name])

    accepted = len(values)
    if accepted < MIN_ACCEPTED:
        reasons = "; ".join(examples[code] for code, _ in rejected.most_common(2))
        raise MonteCarloError(
            f"Only {accepted} of {draws:,} draws were valid for the models; at least "
            f"{MIN_ACCEPTED} are needed for a summary. Narrow the distributions. ({reasons})",
            field="quantities",
        )
    return _summarise(
        planned,
        metric=metric,
        base=base,
        base_totals=evaluator.base_totals,
        values=values,
        inputs=inputs,
        outputs=outputs,
        draws=draws,
        rejected=rejected,
        examples=examples,
        threshold=threshold,
        evaluations=evaluator.evaluations + 1,
        duration_ms=evaluator.elapsed_ms,
    )


def _out(value: Decimal) -> str:
    return text(to_output(value))


def _summarise(
    planned: Sequence[tuple[Target, Distribution]],
    *,
    metric: str,
    base: Decimal,
    base_totals: dict[str, Decimal],
    values: list[Decimal],
    inputs: list[list[Decimal]],
    outputs: dict[str, list[Decimal]],
    draws: int,
    rejected: Counter[str],
    examples: dict[str, str],
    threshold: Decimal | None,
    evaluations: int,
    duration_ms: int,
) -> dict[str, Any]:
    ordered = sorted(values)
    n = len(values)
    centre = summaries.mean(values)
    deviation = summaries.sample_std(values)
    error = summaries.standard_error(values)
    with arithmetic():
        relative = abs(error / centre) if centre != ZERO else None
    percentiles = []
    for p in summaries.PERCENTILES:
        entry: dict[str, Any] = {"p": p, "value": _out(summaries.percentile(ordered, p))}
        if p in summaries.INTERVAL_PERCENTILES:
            interval = summaries.percentile_interval(ordered, p)
            entry["interval"] = {
                "lower": _out(interval.lower),
                "upper": _out(interval.upper),
                "lower_rank": interval.lower_rank,
                "upper_rank": interval.upper_rank,
                "coverage": text(interval.coverage),
            }
        else:
            entry["interval"] = None
        percentiles.append(entry)
    kind = _kind(metric)
    halves = summaries.halves(values)
    quantities = []
    for index, (target, distribution) in enumerate(planned):
        drawn = inputs[index]
        with arithmetic():
            sd = variance(distribution).sqrt()
        rho = summaries.spearman(drawn, values)
        quantities.append(
            {
                "target": target.id,
                "label": target.label,
                "kind": target.kind,
                "models": target.models,
                "unit": target.unit,
                "base_value": text(target.base),
                "distribution": distribution_json(distribution),
                "distribution_mean": _out(mean(distribution)),
                "distribution_sd": _out(sd),
                "accepted_mean": _out(summaries.mean(drawn)),
                "rank_correlation": _out(rho) if rho is not None else None,
            }
        )
    notes = [CONDITIONAL_NOTE]
    if len(planned) > 1:
        notes.append(INDEPENDENCE_NOTE)
    if rejected:
        notes.append(
            f"{sum(rejected.values()):,} of {draws:,} draws broke a model's rule and were "
            "rejected: the summaries describe the accepted draws, so the stated distributions "
            "are cut where the models do not apply."
        )
    flagged = halves.z is not None and abs(halves.z) > HALVES_FLAG
    if flagged:
        notes.append(
            "The first and second halves of the draws disagree by more than three standard "
            "errors: use more draws before relying on the summary."
        )
    return {
        "metric": metric,
        "metric_label": _metric_label(metric),
        "metric_kind": kind,
        "base": text(base),
        "draws": draws,
        "accepted": n,
        "rejected": sum(rejected.values()),
        "rejections": [
            {"code": code, "count": count, "example": examples[code]}
            for code, count in sorted(rejected.items(), key=lambda item: (-item[1], item[0]))
        ],
        "quantities": quantities,
        "summary": {
            "mean": _out(centre),
            "standard_deviation": _out(deviation),
            "standard_error": _out(error),
            "relative_standard_error": _out(relative) if relative is not None else None,
            "minimum": _out(ordered[0]),
            "maximum": _out(ordered[-1]),
            "percentiles": percentiles,
            "share_below_zero": _out(summaries.share_below(values, ZERO))
            if kind == "line_change"
            else None,
            "threshold": text(threshold) if threshold is not None else None,
            "share_at_or_below_threshold": _out(summaries.share_at_or_below(values, threshold))
            if threshold is not None
            else None,
        },
        "histogram": [
            {"low": _out(item.low), "high": _out(item.high), "count": item.count}
            for item in summaries.histogram(ordered)
        ],
        "convergence": {
            "checkpoints": [
                {
                    "draws": point.draws,
                    "mean": _out(point.mean),
                    "standard_error": _out(point.standard_error)
                    if point.standard_error is not None
                    else None,
                }
                for point in summaries.running(values)
            ],
            "first_half_mean": _out(halves.first_mean),
            "second_half_mean": _out(halves.second_mean),
            "halves_z": _out(halves.z) if halves.z is not None else None,
            "halves_flagged": flagged,
        },
        "outputs": [_output_summary(name, base_totals[name], outputs[name]) for name in outputs],
        "notes": notes,
        "evaluations": evaluations,
        "duration_ms": duration_ms,
    }


def _output_summary(name: str, base: Decimal, values: list[Decimal]) -> dict[str, Any]:
    ordered = sorted(values)
    return {
        "id": name,
        "label": _metric_label(name),
        "kind": _kind(name),
        "base": text(base),
        "mean": _out(summaries.mean(values)),
        "p5": _out(summaries.percentile(ordered, 5)),
        "p50": _out(summaries.percentile(ordered, 50)),
        "p95": _out(summaries.percentile(ordered, 95)),
    }
