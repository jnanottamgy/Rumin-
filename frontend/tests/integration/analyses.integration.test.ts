/**
 * Integration: the Scenario Lab's advanced analyses and the model verification register,
 * against a running backend.
 *
 * Executes the backend tests' reference scenario — HYPOTHETICAL round figures for the
 * fictional Aerisca Airways, not any company's — and builds every request with the Lab's
 * own form helpers, as the interface does. The distributions are stated for the test; they
 * are assumptions, not estimates. The executed scenario is kept, as every executed
 * scenario is.
 */
import { beforeAll, describe, expect, it } from "vitest";
import {
  jointRequest,
  monteCarloRequest,
  type QuantityDraft,
  sensitivityRequest,
  startingPoint,
} from "@/features/scenarioLab/analysisForm";
import { ApiError } from "@/lib/apiClient";
import { labApi, simulationApi } from "@/services/api";
import type { AnalysisTarget, AnalysisTargets, ScenarioExecution } from "@/types/api";
import { contractViolations } from "./contract";
import { executeReference } from "./reference";

const baseUrl = process.env.RUMIN_API_URL?.replace(/\/+$/, "");
if (!baseUrl)
  throw new Error("Set RUMIN_API_URL to a running RUMIN API (see scripts/smoke_test.sh)");
const options = { baseUrl };

let execution: ScenarioExecution;
let targets: AnalysisTargets;

beforeAll(async () => {
  ({ execution } = await executeReference("Integration: advanced analyses", options));
  targets = await labApi.analyses.targets(execution.id, options);
}, 30_000);

function target(id: string): AnalysisTarget {
  const found = targets.targets.find((item) => item.id === id);
  if (!found) throw new Error(`The execution cannot vary ${id}.`);
  return found;
}

const labels = () => new Map(targets.targets.map((item) => [item.id, item.label]));

describe("what an execution can vary", () => {
  it("lists the scenario's changes, the shared figures and each model's inputs, with limits", () => {
    expect(contractViolations("AnalysisTargetsRead", targets)).toEqual([]);
    expect(new Set(targets.targets.map((item) => item.kind))).toEqual(
      new Set(["change", "shared", "market", "company", "assumption"]),
    );
    expect(target("change:var_brent_crude").base_value).toBe("20");
    expect(targets.metrics.map((metric) => metric.id)).toContain("profit_before_tax");
    expect(targets.limits.monte_carlo).toMatchObject({ min_draws: 100, max_draws: 2000 });
  });
});

describe("Monte Carlo", () => {
  it("draws from the stated distributions, stores the analysis and reproduces it exactly", async () => {
    const crude: QuantityDraft = {
      ...startingPoint(target("change:var_brent_crude")),
      kind: "triangular",
      low: "-10",
      mode: "20",
      high: "60",
    };
    const built = monteCarloRequest(
      {
        metric: "profit_before_tax",
        draws: "300",
        seed: "20260925",
        threshold: "-10000000",
        quantities: [
          crude,
          startingPoint(target("change:var_usd_inr")),
          startingPoint(target("model:floating_rate_interest:repo_repricing_lag")),
        ],
      },
      labels(),
    );
    expect(built.errors).toEqual([]);
    if (!built.request) throw new Error("No request was built.");

    const analysis = await labApi.analyses.create(execution.id, built.request, options);
    expect(contractViolations("ScenarioAnalysisRead", analysis)).toEqual([]);
    const results = analysis.monte_carlo;
    if (!results) throw new Error("A Monte Carlo analysis without its results.");
    expect(results.accepted + results.rejected).toBe(300);
    expect(results.accepted).toBeGreaterThanOrEqual(100);
    // The execution's own value: worked out by hand in backend/tests/scenario_support.py.
    expect(results.base).toBe("-6700000");
    expect(results.histogram.reduce((sum, bin) => sum + bin.count, 0)).toBe(results.accepted);
    const percentiles = results.summary.percentiles.map((item) => Number(item.value));
    expect(percentiles).toEqual([...percentiles].sort((a, b) => a - b));
    expect(analysis.config).toMatchObject({ seed: 20260925, draws: 300 });
    expect(analysis.config.runs.map((run) => run.model_id).sort()).toEqual([
      "airline_fuel_cost",
      "floating_rate_interest",
      "fx_exposure",
    ]);

    const check = await labApi.analyses.verify(execution.id, analysis.id, options);
    expect(contractViolations("AnalysisVerificationRead", check)).toEqual([]);
    expect(check.reproduced).toBe(true);

    const stored = await labApi.analyses.get(execution.id, analysis.id, options);
    expect(stored.result_hash).toBe(analysis.result_hash);
    const listing = await labApi.analyses.list(execution.id, options);
    expect(contractViolations("ScenarioAnalysisList", listing)).toEqual([]);
    expect(listing.items.map((item) => item.id)).toContain(analysis.id);
  });

  it("refuses what the browser cannot read exactly or the draws cannot support", async () => {
    const refused = async (body: unknown) => {
      const error = await labApi.analyses
        .create(execution.id, body as Parameters<typeof labApi.analyses.create>[1], options)
        .then(
          () => {
            throw new Error(`The API accepted ${JSON.stringify(body)}`);
          },
          (caught: unknown) => caught,
        );
      expect(error).toBeInstanceOf(ApiError);
      expect(error).toMatchObject({ kind: "http", status: 422 });
      return (error as ApiError).details.map((detail) => detail.field ?? "");
    };
    const quantities = [
      {
        target: "change:var_brent_crude",
        distribution: { kind: "uniform", low: "10", high: "30" },
      },
    ];
    const base = { kind: "monte_carlo", metric: "profit_before_tax", quantities };
    expect(await refused({ ...base, draws: 500, seed: 2 ** 53 })).toEqual([
      expect.stringMatching(/seed$/),
    ]);
    expect(await refused({ ...base, draws: 99, seed: 1 })).toEqual([
      expect.stringMatching(/draws$/),
    ]);
    // The form refuses a reversed range before sending it; the API refuses it too.
    const reversed = monteCarloRequest(
      {
        metric: "profit_before_tax",
        draws: "500",
        seed: "",
        threshold: "",
        quantities: [{ ...startingPoint(target("change:var_brent_crude")), low: "30", high: "10" }],
      },
      labels(),
    );
    expect(reversed.request).toBeNull();
    expect(
      await refused({
        ...base,
        draws: 500,
        quantities: [
          {
            target: "change:var_brent_crude",
            distribution: { kind: "uniform", low: "30", high: "10" },
          },
        ],
      }),
    ).toEqual(["quantities[0]"]);
  });
});

describe("two quantities together", () => {
  it("evaluates the grid and separates the interaction from the separate effects", async () => {
    const built = jointRequest(
      "operating_profit",
      { target: "change:var_brent_crude", values: "" },
      { target: "change:var_usd_inr", values: "" },
    );
    expect(built.errors).toEqual([]);
    if (!built.request) throw new Error("No request was built.");
    const analysis = await labApi.analyses.create(execution.id, built.request, options);
    expect(contractViolations("ScenarioAnalysisRead", analysis)).toEqual([]);
    const joint = analysis.joint;
    if (!joint) throw new Error("A joint analysis without its grid.");
    const row = joint.rows.values.indexOf(joint.rows.base_value);
    const column = joint.columns.values.indexOf(joint.columns.base_value);
    const executed = joint.cells[row]?.[column];
    // The executed values reproduce the execution: no change, no interaction.
    expect(executed).toMatchObject({ metric: "-6325000", delta: "0", interaction: "0" });
    // Along the executed row and column there is nothing to interact with.
    for (const cell of joint.cells[row] ?? []) expect(cell.interaction).toBe("0");
    for (const cells of joint.cells) expect(cells[column]?.interaction).toBe("0");
    expect(joint.summary.interactions_computed).toBe(
      joint.rows.values.length * joint.columns.values.length,
    );
  });
});

describe("one quantity at a time", () => {
  it("moves the margins with a shared figure (sensitivity method 1.1.0)", async () => {
    const built = sensitivityRequest(
      "operating_margin",
      [
        { target: "change:var_brent_crude", values: "" },
        { target: "shared:annual_revenue", values: "270000000, 330000000" },
      ],
      labels(),
    );
    expect(built.errors).toEqual([]);
    if (!built.request) throw new Error("No request was built.");
    const analysis = await labApi.sensitivity.create(execution.id, built.request, options);
    expect(contractViolations("LabSensitivityRead", analysis)).toEqual([]);
    expect(analysis.method_version).toBe("1.1.0");
    const revenue = analysis.items.find((item) => item.target === "shared:annual_revenue");
    expect(revenue?.points.map((point) => point.value)).toEqual(["270000000", "330000000"]);
    for (const point of revenue?.points ?? []) {
      expect(point.skipped).toBeNull();
      expect(point.delta).not.toBe("0");
    }
  });
});

describe("the verification register", () => {
  it("passes every check for each model version the execution ran, and says what it does not verify", async () => {
    for (const run of execution.runs) {
      const register = await simulationApi.verification(run.model_id, run.model_version, options);
      expect(contractViolations("ModelVerificationRead", register)).toEqual([]);
      expect(register).toMatchObject({
        model_id: run.model_id,
        version: run.model_version,
        failed: 0,
      });
      expect(register.passed).toBe(register.total);
      expect(new Set(register.checks.map((check) => check.kind))).toEqual(
        new Set(["reference", "property", "range", "reproducibility"]),
      );
      expect(register.not_verified.length).toBeGreaterThan(0);
    }
  });
});
