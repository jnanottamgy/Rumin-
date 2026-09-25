import { describe, expect, it } from "vitest";
import {
  clampToRange,
  defaultMetric,
  formatMetric,
  formatMetricChange,
  formatQuantity,
  formatShare,
  jointRequest,
  type MonteCarloDraft,
  monteCarloRequest,
  parseList,
  sensitivityRequest,
  startingPoint,
  variationBounds,
} from "@/features/scenarioLab/analysisForm";
import type { AnalysisTarget } from "@/types/api";
import { labFixtures } from "../fixtures/lab";

const targets = new Map(labFixtures.analysisTargets().targets.map((item) => [item.id, item]));
const target = (id: string): AnalysisTarget => {
  const found = targets.get(id);
  if (!found) throw new Error(`No fixture target ${id}.`);
  return found;
};
const labels = new Map([...targets].map(([id, item]) => [id, item.label]));

describe("starting points for a distribution", () => {
  it("spans the model's default variation, exactly", () => {
    // Crude +20 % ± 10 points; the rate 80 INR per USD ± 5 %; revenue 300,000,000 ± 10 %.
    expect(variationBounds(target("change:var_brent_crude"))).toEqual(["10", "30"]);
    expect(variationBounds(target("shared:fx_rate"))).toEqual(["76", "84"]);
    expect(variationBounds(target("shared:annual_revenue"))).toEqual(["270000000", "330000000"]);
    expect(startingPoint(target("change:var_rbi_repo_rate"))).toMatchObject({
      kind: "uniform",
      low: "0.25",
      high: "0.75",
    });
  });

  it("stays inside the input's range instead of starting from an invalid value", () => {
    // The revenue hedge ratio is 0 % as executed: 0 − 25 is clamped to the minimum.
    expect(startingPoint(target("model:fx_exposure:revenue_hedge_ratio"))).toMatchObject({
      low: "0",
      high: "25",
    });
    // A strict minimum (the exchange rate must be above 0) moves one decimal step inside.
    expect(clampToRange("-5", target("shared:fx_rate"))).toBe("0.000001");
  });

  it("offers whole months as a discrete choice", () => {
    expect(startingPoint(target("model:floating_rate_interest:repo_repricing_lag"))).toMatchObject({
      kind: "discrete",
      values: "1, 3, 5",
      weights: "",
    });
  });

  it("leaves a collapsed range for the user to state", () => {
    // Relative variation around zero debt gives no range at all.
    expect(startingPoint(target("model:floating_rate_interest:us_rate_linked_debt"))).toMatchObject(
      { low: "", high: "" },
    );
  });
});

function draft(overrides: Partial<MonteCarloDraft> = {}): MonteCarloDraft {
  return {
    metric: "profit_before_tax",
    draws: "500",
    seed: "",
    threshold: "",
    quantities: [startingPoint(target("change:var_brent_crude"))],
    ...overrides,
  };
}

describe("the requests the forms send", () => {
  it("builds a Monte Carlo request with exact decimal strings", () => {
    const built = monteCarloRequest(draft({ seed: "42", threshold: "-10000000" }), labels);

    expect(built.errors).toEqual([]);
    expect(built.request).toEqual({
      kind: "monte_carlo",
      metric: "profit_before_tax",
      draws: 500,
      seed: 42,
      threshold: "-10000000",
      quantities: [
        {
          target: "change:var_brent_crude",
          distribution: { kind: "uniform", low: "10", high: "30" },
        },
      ],
    });
  });

  it("names every problem with the quantity it belongs to", () => {
    const crude = startingPoint(target("change:var_brent_crude"));
    const built = monteCarloRequest(
      draft({
        draws: "50",
        seed: "9007199254740992",
        threshold: "ten",
        quantities: [
          { ...crude, kind: "triangular", mode: "35" },
          {
            ...startingPoint(target("model:floating_rate_interest:repo_repricing_lag")),
            weights: "1, 2",
          },
        ],
      }),
      labels,
    );

    expect(built.request).toBeNull();
    expect(built.errors).toEqual([
      "Crude oil price change: the most likely value must lie between the low and high values.",
      "Repo repricing delay (Floating-rate interest): give one weight per value, or none for equal weights.",
      "Choose between 100 and 2,000 draws.",
      "A seed is a whole number from 0 to 9,007,199,254,740,991, or empty.",
      "The threshold must be a plain number.",
    ]);
  });

  it("builds the grid and one-at-a-time requests", () => {
    expect(
      jointRequest(
        "operating_profit",
        { target: "change:var_brent_crude", values: "" },
        { target: "change:var_usd_inr", values: "0, 10" },
      ).request,
    ).toEqual({
      kind: "joint_sensitivity",
      metric: "operating_profit",
      rows: { target: "change:var_brent_crude", mode: "default", values: [] },
      columns: { target: "change:var_usd_inr", mode: "values", values: ["0", "10"] },
    });
    expect(
      jointRequest(
        "",
        { target: "change:var_brent_crude", values: "" },
        { target: "change:var_brent_crude", values: "" },
      ).errors,
    ).toEqual(["Choose two different quantities."]);
    expect(
      sensitivityRequest("", [{ target: "change:var_brent_crude", values: "a, b" }], labels).errors,
    ).toEqual(["Crude oil price change: give up to seven plain numbers, separated by commas."]);
    expect(parseList("0; 3  6")).toEqual(["0", "3", "6"]);
  });
});

describe("writing the analyses' values", () => {
  it("formats lines as money, margins in points and coverage in times", () => {
    expect(formatMetric("-6700000", "profit_before_tax")).toBe("−6.7 M");
    expect(formatMetric("0.1422986072", "operating_margin")).toBe("14.23 %");
    expect(formatMetricChange("-0.0127057784", "operating_margin")).toBe("−1.27 pp");
    expect(formatMetricChange("0.5", "interest_coverage")).toBe("+0.5×");
    expect(formatShare("0.974")).toBe("97.4 %");
    expect(defaultMetric(labFixtures.analysisTargets().metrics)).toBe("profit_before_tax");
  });

  it("writes a quantity in its unit", () => {
    expect(formatQuantity("20", target("change:var_brent_crude"))).toBe("20 %");
    expect(formatQuantity("0.5", target("change:var_rbi_repo_rate"))).toBe("0.5 pp");
    expect(formatQuantity("1", target("model:airline_fuel_cost:crude_pass_through"))).toBe("1");
    expect(formatQuantity("300000000", target("shared:annual_revenue"))).toBe(
      "300,000,000 INR per year",
    );
  });
});
