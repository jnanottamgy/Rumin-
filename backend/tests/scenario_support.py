"""Helpers for Scenario Lab tests.

Every company figure here is HYPOTHETICAL: round numbers chosen so that results can be
worked out by hand. The companies are the fictional ones of RUMIN's sample network.

The reference case ("oil, rupee and rates" on Aerisca Airways, 12 months):

* airline: fuel 1,000 kL × 750 USD × 80 INR = 60,000,000 INR a year (5,000,000 a month);
  Brent +20 % reaches jet fuel after 1 month (β = 1); the rupee +5 % from month 1; 40 % of
  the fuel is hedged for 6 months; half of the fuel-cost change reaches fares 2 months later.
  Fuel cost change = 0.25 M (month 1) + 5 × 0.88 M + 6 × 1.3 M = 12.45 M; fare recovery =
  ½ × (0.25 + 4.4 + 4 × 1.3) M = 4.925 M.
* foreign currency: 500,000 USD of revenue and 200,000 USD of costs a year at 80: +5 % for 12
  months → revenue +2,000,000, costs +800,000.
* interest: 100,000,000 of repo-linked debt, +0.5 pp after a 3-month delay: 9 months ×
  41,666.67 = 375,000.

Lines: revenue +6,925,000; operating costs +13,250,000; operating profit −6,325,000;
interest +375,000; profit before tax −6,700,000. Margin 50/300 → 43.675/306.925; coverage
50/12 → 43.675/12.375.
"""

from __future__ import annotations

import copy
from decimal import Decimal
from typing import Any

AERISCA = "company:co_aerisca_airways"
D = Decimal

REFERENCE: dict[str, Any] = {
    "name": "Oil, rupee and rates on Aerisca",
    "shocks": [
        {"variable_id": "var_brent_crude", "change_type": "percent_change", "value": "20"},
        {"variable_id": "var_usd_inr", "change_type": "percent_change", "value": "5"},
        {"variable_id": "var_rbi_repo_rate", "change_type": "absolute_change", "value": "0.5"},
    ],
    "entity": AERISCA,
    "company": {
        "reporting_currency": "INR",
        "annual_revenue": "300000000",
        "annual_operating_costs": "250000000",
    },
    "markets": {"fx_rate": {"value": "80"}},
    "models": {
        "airline_fuel_cost": {
            "inputs": {
                "jet_fuel_price": {"value": "750", "unit": "usd_per_kilolitre"},
                "annual_fuel_consumption": {"value": "1000", "unit": "kilolitre"},
            },
            "assumptions": {
                "hedge_ratio": "40",
                "hedge_months": "6",
                "fare_pass_through": "50",
                "fare_pass_through_lag": "2",
                "crude_pass_through_lag": "1",
            },
        },
        "fx_exposure": {
            "inputs": {
                "annual_usd_revenue": {"value": "500000"},
                "annual_usd_costs": {"value": "200000"},
            }
        },
        "floating_rate_interest": {
            "mode": "include",
            "inputs": {
                "annual_interest_expense": {"value": "12000000"},
                "repo_linked_debt": {"value": "100000000"},
                "us_rate_linked_debt": {"value": "0"},
            },
            "assumptions": {"repo_repricing_lag": "3"},
        },
    },
    "stress_cases": [{"name": "Half", "scale": "0.5"}, {"name": "Double", "scale": "2"}],
}

EXPECTED_LINES = {
    "revenue": (D(300_000_000), D(6_925_000)),
    "operating_costs": (D(250_000_000), D(13_250_000)),
    "operating_profit": (D(50_000_000), D(-6_325_000)),
    "interest_expense": (D(12_000_000), D(375_000)),
    "profit_before_tax": (D(38_000_000), D(-6_700_000)),
}


def reference(**changes: Any) -> dict[str, Any]:
    """The reference scenario body with top-level fields replaced (deep-copied)."""
    body = copy.deepcopy(REFERENCE)
    body.update(copy.deepcopy(changes))
    return body


def brent_only(**changes: Any) -> dict[str, Any]:
    """Brent +20 % on Aerisca with the airline model only (no stress cases)."""
    body = reference(
        name="Brent on Aerisca",
        shocks=[REFERENCE["shocks"][0]],
        models={"airline_fuel_cost": REFERENCE["models"]["airline_fuel_cost"]},
        stress_cases=[],
    )
    body.update(copy.deepcopy(changes))
    return body


def near(actual: str | Decimal, expected: Decimal, quantum: str = "1e-9") -> bool:
    return abs(D(actual) - expected) <= D(quantum)
