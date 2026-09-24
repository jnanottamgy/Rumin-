"""What each model declares about the scenarios it applies to (its *scenario profile*).

A model definition says what a model computes; its profile says how the Scenario Lab may
use it:

* **changes it responds to** — the economic variable, the kind of change (percent or
  percentage points) and the model input the change goes to. Nothing is converted: a
  change of the wrong kind is refused, never translated;
* **its graph exposure** — the relationship the knowledge graph must state between the
  changed variable and a chosen company (directly or through the company's industry) for
  the model to apply to that company by default;
* **the lines it contributes to** — each of its outputs mapped to revenue, operating costs
  or interest expense, with an *item* from a closed list (jet fuel, dollar costs,
  crude-linked inputs, …) and the variables that drive it. Two models in one scenario may
  never claim the same item on the same line; that is how double counting is prevented.

Profiles live beside the definitions, not inside them, so released definition hashes do
not change; each profile has its own hash, recorded with every execution.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from app.domain.enums import ChangeType
from app.simulation.definitions import InputCategory, plain, sha256
from app.simulation.registry import REGISTRY, RegisteredModel
from app.simulation.runtime import ResolvedValues

Line = Literal["revenue", "operating_costs", "interest_expense"]

LINE_LABELS: dict[str, str] = {
    "revenue": "Revenue",
    "operating_costs": "Operating costs",
    "operating_profit": "Operating profit",
    "interest_expense": "Interest expense",
    "profit_before_tax": "Profit before tax",
}

# The closed list of items a line can be made of. Each is covered by at most one model in a
# scenario.
ITEMS: dict[str, str] = {
    "jet_fuel": "Jet fuel",
    "fuel_cost_recovery": "Fare recovery of fuel costs",
    "usd_revenue": "Revenue invoiced in US dollars",
    "usd_costs": "Costs paid in US dollars (other than those another model covers)",
    "repo_linked_interest": "Interest on debt linked to the repo rate",
    "us_rate_linked_interest": "Interest on debt linked to US short-term rates",
    "crude_linked_inputs": "Inputs priced off crude oil (other than jet fuel)",
    "crude_cost_recovery": "Price recovery of crude-linked costs",
    "gas_linked_inputs": "Inputs priced off natural gas",
    "gas_cost_recovery": "Price recovery of gas-linked costs",
}


@dataclass(frozen=True)
class ShockBinding:
    """A change to ``variable_id`` of kind ``change_type`` goes to ``input_id``."""

    variable_id: str
    input_id: str
    change_type: ChangeType


@dataclass(frozen=True)
class LineContribution:
    line: Line
    item: str
    label: str
    output: str  # the horizon total
    monthly: str  # the monthly series
    drivers: tuple[str, ...]  # economic variable ids


@dataclass(frozen=True)
class Exposure:
    """The graph states ``variable —relationship→ company`` (or → the company's industry)."""

    relationships: tuple[str, ...]
    variable_id: str
    via_industry: bool = True


@dataclass(frozen=True)
class Event:
    """A moment on the timeline, derived from the run's own inputs."""

    month: int
    label: str
    model_id: str


@dataclass(frozen=True)
class ScenarioProfile:
    model_id: str
    title: str
    covers: str
    shocks: tuple[ShockBinding, ...]
    lines: tuple[LineContribution, ...]
    exposures: tuple[Exposure, ...]
    # True: a company whose exposure the graph does not state is outside the model's scope
    # (the model itself refuses it). False: the model can still be added by hand, and the
    # exposure then rests on the user's figures.
    exposure_required: bool
    operating_profit_output: str | None
    # The model's own outputs worth showing next to the lines.
    key_outputs: tuple[str, ...]

    @property
    def variables(self) -> set[str]:
        return {binding.variable_id for binding in self.shocks}

    def binding(self, variable_id: str) -> ShockBinding | None:
        return next((item for item in self.shocks if item.variable_id == variable_id), None)


P = ChangeType.PERCENT_CHANGE
A = ChangeType.ABSOLUTE_CHANGE

AIRLINE = ScenarioProfile(
    model_id="airline_fuel_cost",
    title="Airline fuel cost",
    covers="An airline's jet fuel bill (priced in US dollars, partly hedged) and the part of "
    "its change passed on to fares.",
    shocks=(
        ShockBinding("var_brent_crude", "crude_oil_change", P),
        ShockBinding("var_jet_fuel", "jet_fuel_margin_change", P),
        ShockBinding("var_usd_inr", "usd_change", P),
    ),
    lines=(
        LineContribution(
            "operating_costs",
            "jet_fuel",
            "Jet fuel",
            "fuel_cost_change",
            "fuel_cost_change",
            ("var_brent_crude", "var_jet_fuel", "var_usd_inr"),
        ),
        LineContribution(
            "revenue",
            "fuel_cost_recovery",
            "Fare recovery",
            "fare_recovery",
            "fare_recovery",
            ("var_brent_crude", "var_jet_fuel", "var_usd_inr"),
        ),
    ),
    exposures=(Exposure(("affects_costs",), "var_jet_fuel"),),
    exposure_required=True,
    operating_profit_output="operating_profit_change",
    key_outputs=(
        "fuel_cost_change",
        "hedging_effect",
        "fare_recovery",
        "jet_fuel_price_change",
        "steady_state_operating_profit_change",
    ),
)

FX = ScenarioProfile(
    model_id="fx_exposure",
    title="Foreign-currency revenue and costs",
    covers="Revenue invoiced and costs paid in US dollars, converted at the month's exchange "
    "rate, with hedges.",
    shocks=(ShockBinding("var_usd_inr", "fx_change", P),),
    lines=(
        LineContribution(
            "revenue",
            "usd_revenue",
            "US-dollar revenue",
            "revenue_change",
            "revenue_change",
            ("var_usd_inr",),
        ),
        LineContribution(
            "operating_costs",
            "usd_costs",
            "US-dollar costs",
            "cost_change",
            "cost_change",
            ("var_usd_inr",),
        ),
    ),
    exposures=(Exposure(("affects_costs", "affects_revenue"), "var_usd_inr"),),
    exposure_required=False,
    operating_profit_output="operating_profit_change",
    key_outputs=(
        "revenue_change",
        "cost_change",
        "net_usd_exposure",
        "run_rate_operating_profit_change",
    ),
)

INTEREST = ScenarioProfile(
    model_id="floating_rate_interest",
    title="Floating-rate interest",
    covers="Interest on floating-rate debt linked to the RBI repo rate or US short-term "
    "rates, after pass-through and repricing delays.",
    shocks=(
        ShockBinding("var_rbi_repo_rate", "repo_rate_change", A),
        ShockBinding("var_us_fed_funds", "us_rate_change", A),
    ),
    lines=(
        LineContribution(
            "interest_expense",
            "repo_linked_interest",
            "Repo-linked debt",
            "repo_interest_change",
            "repo_interest_change",
            ("var_rbi_repo_rate",),
        ),
        LineContribution(
            "interest_expense",
            "us_rate_linked_interest",
            "US-rate-linked debt",
            "us_interest_change",
            "us_interest_change",
            ("var_us_fed_funds",),
        ),
    ),
    exposures=(
        Exposure(("affects_financing",), "var_rbi_repo_rate"),
        Exposure(("affects_financing",), "var_us_fed_funds"),
    ),
    exposure_required=False,
    operating_profit_output=None,
    key_outputs=(
        "interest_expense_change",
        "interest_coverage_change",
        "run_rate_interest_change",
    ),
)

CRUDE_LINKED = ScenarioProfile(
    model_id="crude_linked_costs",
    title="Crude-oil-linked costs",
    covers="Operating costs priced off crude oil (feedstock, diesel), with hedges and price "
    "recovery. Not jet fuel: the airline model covers it.",
    shocks=(ShockBinding("var_brent_crude", "crude_oil_change", P),),
    lines=(
        LineContribution(
            "operating_costs",
            "crude_linked_inputs",
            "Crude-linked inputs",
            "linked_cost_change",
            "linked_cost_change",
            ("var_brent_crude",),
        ),
        LineContribution(
            "revenue",
            "crude_cost_recovery",
            "Price recovery",
            "price_recovery",
            "price_recovery",
            ("var_brent_crude",),
        ),
    ),
    exposures=(Exposure(("affects_costs",), "var_brent_crude"),),
    exposure_required=False,
    operating_profit_output="operating_profit_change",
    key_outputs=(
        "linked_cost_change",
        "hedging_effect",
        "price_recovery",
        "run_rate_operating_profit_change",
    ),
)

GAS_LINKED = ScenarioProfile(
    model_id="gas_linked_costs",
    title="Natural-gas-linked costs",
    covers="Operating costs priced off natural gas (fuel, feedstock), with hedges and price "
    "recovery.",
    shocks=(ShockBinding("var_henry_hub_gas", "gas_price_change", P),),
    lines=(
        LineContribution(
            "operating_costs",
            "gas_linked_inputs",
            "Gas-linked inputs",
            "linked_cost_change",
            "linked_cost_change",
            ("var_henry_hub_gas",),
        ),
        LineContribution(
            "revenue",
            "gas_cost_recovery",
            "Price recovery",
            "price_recovery",
            "price_recovery",
            ("var_henry_hub_gas",),
        ),
    ),
    exposures=(Exposure(("affects_costs",), "var_henry_hub_gas"),),
    exposure_required=False,
    operating_profit_output="operating_profit_change",
    key_outputs=(
        "linked_cost_change",
        "hedging_effect",
        "price_recovery",
        "run_rate_operating_profit_change",
    ),
)

PROFILES: dict[str, ScenarioProfile] = {
    profile.model_id: profile for profile in (AIRLINE, FX, INTEREST, CRUDE_LINKED, GAS_LINKED)
}

# Notes shown when both models of a pair are used in one scenario. They do not block: each
# model's figures are defined to leave the other's out, but the user must make them so.
CAUTIONS: dict[frozenset[str], str] = {
    frozenset({"airline_fuel_cost", "fx_exposure"}): (
        "Leave jet fuel out of the US-dollar costs: the airline fuel model already converts "
        "the fuel bill at the new exchange rate."
    ),
    frozenset({"airline_fuel_cost", "crude_linked_costs"}): (
        "Both respond to crude oil. Leave jet fuel out of the crude-linked costs: the "
        "airline fuel model covers it."
    ),
    frozenset({"fx_exposure", "crude_linked_costs"}): (
        "If some crude-linked inputs are paid in US dollars, the combined result leaves out "
        "the small cross effect of the two changes (crude change × currency change)."
    ),
    frozenset({"fx_exposure", "gas_linked_costs"}): (
        "If some gas-linked inputs are paid in US dollars, the combined result leaves out "
        "the small cross effect of the two changes (gas change × currency change)."
    ),
}


def lab_model(model_id: str) -> RegisteredModel | None:
    """The version of a model the Lab runs: the latest runnable one."""
    return REGISTRY.get(model_id)


def profile_hash(profile: ScenarioProfile) -> str:
    return sha256(plain(profile))


def check_profiles(profiles: Mapping[str, ScenarioProfile]) -> None:
    """Every profile must match its model's definition; raised at import."""
    items: dict[tuple[str, str], str] = {}
    for profile in profiles.values():
        model = lab_model(profile.model_id)
        if model is None:
            raise ValueError(f"Profile {profile.model_id} has no registered model.")
        definition = model.definition
        inputs = {item.id: item for item in definition.inputs}
        outputs = {item.id for item in definition.outputs}
        monthly = {item.id for item in definition.monthly_outputs}
        for binding in profile.shocks:
            item = inputs.get(binding.input_id)
            if item is None or item.category is not InputCategory.SCENARIO_INPUT:
                raise ValueError(f"{profile.model_id}: {binding.input_id} is not a change.")
            expected = "percentage_points" if binding.change_type is A else "percent_change"
            if item.unit != expected:
                raise ValueError(f"{profile.model_id}: {binding.input_id} is not in {expected}.")
            if item.variable != f"variable:{binding.variable_id}":
                raise ValueError(
                    f"{profile.model_id}: {binding.input_id} changes another variable."
                )
        for contribution in profile.lines:
            if contribution.item not in ITEMS:
                raise ValueError(f"{profile.model_id}: unknown item {contribution.item}.")
            if contribution.output not in outputs or contribution.monthly not in monthly:
                raise ValueError(f"{profile.model_id}: {contribution.output} is not an output.")
            key = (contribution.line, contribution.item)
            if key in items:
                raise ValueError(f"{profile.model_id} and {items[key]} both cover {key}.")
            items[key] = profile.model_id
        for name in (*profile.key_outputs, profile.operating_profit_output):
            if name is not None and name not in outputs:
                raise ValueError(f"{profile.model_id}: {name} is not an output.")


check_profiles(PROFILES)


# --- Timeline events ---------------------------------------------------------------------------


def _first_change(series: Sequence[Decimal] | None) -> int | None:
    """The first month (1-based) in which a monthly change is not zero."""
    for month, value in enumerate(series or (), start=1):
        if value != 0:
            return month
    return None


def events(
    profile: ScenarioProfile,
    values: ResolvedValues,
    monthly: Mapping[str, Sequence[Decimal]],
    start: int,
    horizon: int,
) -> list[Event]:
    """Moments on the timeline that follow from a model run: a lag elapsing, hedges
    expiring while the change lasts, fares or selling prices and loans starting to move.
    Read from the run's own inputs and monthly results; only months within the horizon."""
    model_id = profile.model_id
    found: list[Event] = []

    def add(month: int | None, label: str) -> None:
        if month is not None and 1 <= month <= horizon:
            found.append(Event(month, label, model_id))

    def number(name: str) -> Decimal:
        return values.numbers.get(name, Decimal(0))

    def integer(name: str) -> int:
        return values.integers.get(name, 0)

    def hedges_expire(label: str, hedged: bool) -> None:
        # Hedges cover months 1…M; their expiry matters only if they covered a changed month.
        months = integer("hedge_months")
        if hedged and months >= start:
            add(months + 1, label)

    if model_id == "airline_fuel_cost":
        lag = integer("crude_pass_through_lag")
        if number("crude_oil_change") != 0 and lag > 0:
            add(start + lag, f"The crude oil change reaches jet fuel ({lag}-month lag)")
        hedges_expire("Fuel hedges expire", number("hedge_ratio") > 0)
        add(_first_change(monthly.get("fare_recovery")), "Fares start to recover fuel costs")
    elif model_id == "fx_exposure":
        hedges_expire(
            "Currency hedges expire",
            number("revenue_hedge_ratio") > 0 or number("cost_hedge_ratio") > 0,
        )
    elif model_id == "floating_rate_interest":
        add(_first_change(monthly.get("repo_interest_change")), "Repo-linked loans reprice")
        add(_first_change(monthly.get("us_interest_change")), "US-rate-linked loans reprice")
    elif model_id in ("crude_linked_costs", "gas_linked_costs"):
        lag = integer("cost_pass_through_lag")
        if lag > 0:
            add(start + lag, f"Input prices follow the benchmark ({lag}-month lag)")
        hedges_expire("Input hedges expire", number("hedge_ratio") > 0)
        add(_first_change(monthly.get("price_recovery")), "Selling prices start to recover costs")
    return found


def scenario_events(start: int, end: int, horizon: int) -> list[Event]:
    """The changes taking effect and, if they end within the horizon, ending."""
    found = [Event(start, "The changes take effect", "scenario")] if start <= horizon else []
    if end < horizon:
        found.append(
            Event(end + 1, "The changes end; the variables return to their baselines", "scenario")
        )
    return found


def ordered(found: Iterable[Event]) -> list[Event]:
    return sorted(
        found, key=lambda item: (item.month, item.model_id != "scenario", item.model_id, item.label)
    )
