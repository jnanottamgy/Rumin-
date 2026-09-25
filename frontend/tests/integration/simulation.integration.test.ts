/**
 * Integration: the simulation engine through the frontend's real service layer and form
 * code, against a running backend whose knowledge graph has been built
 * (scripts/smoke_test.sh). The inputs are the page's HYPOTHETICAL example — round numbers
 * whose results are checked here against a hand calculation.
 */
import { beforeAll, describe, expect, it } from "vitest";
import { withExample } from "@/features/simulation/examples";
import { emptyForm, issuesFromDetails, toRequestInputs } from "@/features/simulation/form";
import { ApiError } from "@/lib/apiClient";
import { simulationApi } from "@/services/api";
import type { SimulationModelDetail, SimulationRequest, SimulationRun } from "@/types/api";
import { contractViolations } from "./contract";
import { baseUrl, options, signedIn } from "./session";

let model: SimulationModelDetail;
let request: SimulationRequest;
let run: SimulationRun;

beforeAll(async () => {
  model = await simulationApi.model("airline_fuel_cost", options);
  const example = withExample(model.id, emptyForm(model));
  if (!example) throw new Error("The model has no example inputs.");
  request = { model_id: model.id, inputs: toRequestInputs(model, example) };
  run = await simulationApi.run({ ...request, label: "Integration: example" }, options);
});

const output = (name: string) => run.outputs.find((item) => item.id === name)?.value;

describe("simulation models", () => {
  it("lists the registered models and describes one fully", async () => {
    const models = await simulationApi.models(options);
    for (const item of models) {
      expect(contractViolations("SimulationModelSummary", item)).toEqual([]);
    }
    expect(contractViolations("SimulationModelDetail", model)).toEqual([]);
    expect(model.graph_freshness).toBe("current");
    // The one relationship a shock travels along is confirmed by the built graph.
    expect(model.transmission_rules[0]?.graph_edge?.edge_type).toBe("influences");
  });
});

describe("a run of the example", () => {
  it("validates what the form sends", async () => {
    const report = await simulationApi.validate(request, options);
    expect(contractViolations("ValidationReport", report)).toEqual([]);
    expect(report.valid).toBe(true);
    expect(report.inputs_hash).toBe(run.inputs_hash);
  });

  it("matches the hand calculation", () => {
    expect(contractViolations("SimulationRunRead", run)).toEqual([]);
    // 5,000,000 a month; crude +10 %; half hedged for 3 months; 40 % passed on after 2.
    expect(output("fuel_cost_change")).toBe("5250000");
    expect(output("gross_fuel_cost_change")).toBe("6000000");
    expect(output("hedging_effect")).toBe("-750000");
    expect(output("fare_recovery")).toBe("1700000");
    expect(output("operating_profit_change")).toBe("-3550000");
    expect(output("steady_state_operating_profit_change")).toBe("-3600000");
    expect(run.bridge?.total.value).toBe("-3550000");
    expect(run.monthly.every((series) => series.values.length === 12)).toBe(true);
  });

  it("is explained step by step and traced to the graph", async () => {
    const explanation = await simulationApi.explanation(run.id, options);
    expect(contractViolations("ExplanationRead", explanation)).toEqual([]);
    expect(explanation.steps.map((step) => step.sequence)).toEqual(
      explanation.steps.map((_, index) => index + 1),
    );
    const graphLink = explanation.pathway.links.find((link) => link.rule === "T1");
    expect(graphLink?.edge?.evidence_status).toBe("model_assumption");

    const provenance = await simulationApi.provenance(run.id, options);
    expect(contractViolations("ProvenanceRead", provenance)).toEqual([]);
    expect(provenance.random_seed).toBeNull();
  });

  it("reproduces exactly, and identical inputs give the identical result", async () => {
    const check = await simulationApi.verify(run.id, options);
    expect(check.reproduced).toBe(true);
    const again = await simulationApi.run(request, options);
    expect(again.id).not.toBe(run.id);
    expect(again.result_hash).toBe(run.result_hash);
  });

  it("ranks inputs by their effect in a stored sensitivity analysis", async () => {
    const analysis = await simulationApi.sensitivity.create(run.id, { inputs: [] }, options);
    expect(contractViolations("SensitivityAnalysisRead", analysis)).toEqual([]);
    expect(analysis.ranking[0]?.input).toBe("crude_oil_change");
    const listed = await simulationApi.sensitivity.list(run.id, options);
    expect(listed.items.map((item) => item.id)).toContain(analysis.id);
  });
});

describe("refusals", () => {
  it("names every invalid input, and stores nothing", async () => {
    const { annual_revenue: _leftOut, ...rest } = request.inputs ?? {};
    const inputs = { ...rest, hedge_ratio: { value: "150" } };
    const error = await simulationApi.run({ model_id: model.id, inputs }, options).then(
      () => null,
      (reason: unknown) => reason,
    );
    expect(error).toBeInstanceOf(ApiError);
    const issues = issuesFromDetails((error as ApiError).details);
    expect(issues.map((issue) => issue.field).sort()).toEqual(["annual_revenue", "hedge_ratio"]);
  });

  it("never replaces or deletes a run", async () => {
    for (const method of ["PUT", "PATCH", "DELETE"]) {
      const response = await fetch(`${baseUrl}/api/v1/simulations/${run.id}`, {
        method,
        headers: signedIn,
      });
      expect(response.status, method).toBe(405);
    }
  });
});
