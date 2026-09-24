/**
 * Integration: the frontend's real service layer against a running backend.
 *
 * `scripts/smoke_test.sh` runs this against a fresh, migrated and seeded database.
 * To run it against an API you started yourself:
 *
 *   RUMIN_API_URL=http://127.0.0.1:8000 npm run test:integration
 *
 * Scenarios created here are deleted again where they can be — an executed scenario is
 * kept, because its executions must stay reproducible — so point it only at a disposable
 * database. The company figures used are HYPOTHETICAL round numbers, not any company's.
 */
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { graphFor } from "@/features/network/useNetworkGraph";
import {
  draftFromInput,
  draftFromScenario,
  draftReducer,
  toInput,
  toUpdate,
} from "@/features/scenarioLab/draft";
import { isFinal } from "@/features/scenarioLab/format";
import { ApiError } from "@/lib/apiClient";
import { api, intelligenceApi, labApi, simulationApi } from "@/services/api";
import type { EconomicVariable, ScenarioExecution, ScenarioInput } from "@/types/api";
import { contractViolations } from "./contract";

const baseUrl = process.env.RUMIN_API_URL?.replace(/\/+$/, "");
if (!baseUrl) {
  throw new Error(
    "Set RUMIN_API_URL to a running RUMIN API (see scripts/smoke_test.sh), e.g. http://127.0.0.1:8765",
  );
}
const options = { baseUrl };

let variables: Map<string, EconomicVariable>;
const created: string[] = [];

beforeAll(async () => {
  const page = await api.variables(options);
  variables = new Map(page.items.map((variable) => [variable.id, variable]));
});

afterAll(async () => {
  for (const id of created) await api.scenarios.remove(id, options).catch(() => undefined);
});

/** A scenario body the API should refuse; returns the fields it names. */
async function refusedFields(input: ScenarioInput): Promise<string[]> {
  const error = await api.scenarios.create(input, options).then(
    (scenario) => {
      created.push(scenario.id);
      throw new Error(`The API accepted an invalid scenario: ${JSON.stringify(input)}`);
    },
    (caught: unknown) => caught,
  );
  expect(error).toBeInstanceOf(ApiError);
  expect(error).toMatchObject({ kind: "http", status: 422, code: "validation_error" });
  return (error as ApiError).details.map((detail) => detail.field ?? "");
}

const unique = (name: string) =>
  `${name} ${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;

describe("health", () => {
  it("is up and ready", async () => {
    const health = await api.health(options);
    expect(health).toMatchObject({ status: "ok", service: "rumin-api" });
    expect(contractViolations("HealthResponse", health)).toEqual([]);

    const ready = await api.readiness(options);
    expect(ready.status).toBe("ready");
    expect(contractViolations("ReadinessResponse", ready)).toEqual([]);
  });
});

describe("responses match the committed OpenAPI contract", () => {
  it("network", async () => {
    // api.network() also runs the frontend's own integrity checks (validateNetwork).
    const network = await api.network(options);
    expect(contractViolations("NetworkResponse", network)).toEqual([]);
  });

  it("variables", async () => {
    expect(contractViolations("EconomicVariablePage", await api.variables(options))).toEqual([]);
  });

  it("system status", async () => {
    const system = await api.system(options);
    expect(contractViolations("SystemStatus", system)).toEqual([]);
    expect(system.dataset.loaded).toBe(true);
    const simulation = system.capabilities.find((c) => c.id === "simulation_engine");
    expect(simulation?.available).toBe(true);
    const probabilistic = system.capabilities.find((c) => c.id === "probabilistic_simulation");
    expect(probabilistic?.available).toBe(false);
  });

  it("scenario list", async () => {
    expect(contractViolations("ScenarioPage", await api.scenarios.list(options))).toEqual([]);
  });
});

describe("the network the frontend draws", () => {
  it("builds a complete graph with a finite layout from the live data", async () => {
    const network = await api.network(options);
    const { model, layout, portraitLayout } = graphFor(network);

    expect(model.nodes.length).toBe(network.nodes.length);
    expect(model.edges.length).toBe(network.edges.length);
    expect(model.dataset?.is_illustrative).toBe(true);
    for (const node of model.nodes) {
      for (const positions of [layout.positions, portraitLayout.positions]) {
        const point = positions.get(node.id);
        expect(point && Number.isFinite(point.x) && Number.isFinite(point.y), node.id).toBe(true);
      }
    }
    // Every economic relationship is labelled as an assumption, never as a fact.
    for (const edge of network.edges) {
      if (edge.category === "economic") expect(edge.epistemic_category).toBe("assumption");
    }
  });
});

describe("scenarios through the Lab's draft model", () => {
  it("saves a template's starting point and versions an edit without rewriting the first", async () => {
    const template = await labApi.template("policy_rate_rise", options);
    expect(contractViolations("TemplateRead", template)).toEqual([]);
    const draft = { ...draftFromInput(template.scenario), name: unique("Integration rates") };

    const saved = await api.scenarios.create(toInput(draft), options);
    created.push(saved.id);
    expect(contractViolations("ScenarioRead", saved)).toEqual([]);
    expect(saved).toMatchObject({ name: draft.name, current_version: 1, latest_execution: null });
    expect(saved.shocks).toEqual([
      {
        variable_id: "var_rbi_repo_rate",
        change_type: "absolute_change",
        value: "1.5",
        note: "",
        epistemic_category: "scenario_input",
      },
    ]);
    expect(await api.scenarios.get(saved.id, options)).toEqual(saved);
    const listed = await api.scenarios.list(options);
    expect(listed.items.map((item) => item.id)).toContain(saved.id);

    const edited = draftReducer(draftFromScenario(saved), {
      type: "set",
      field: "name",
      value: `${draft.name} (edited)`,
    });
    const second = await api.scenarios.replace(saved.id, toUpdate(edited, 1), options);
    expect(second.current_version).toBe(2);
    expect((await labApi.version(saved.id, 1, options)).name).toBe(draft.name);
    // An edit made from a version that is no longer the latest is refused, not merged.
    const stale = await api.scenarios
      .replace(saved.id, toUpdate(edited, 1), options)
      .catch((error: unknown) => error);
    expect(stale).toMatchObject({ kind: "http", status: 409 });

    await api.scenarios.remove(saved.id, options);
    const gone = await api.scenarios.get(saved.id, options).catch((error: unknown) => error);
    expect(gone).toMatchObject({ kind: "http", status: 404, code: "not_found" });
    expect((gone as ApiError).requestId).toBeTruthy();
  });

  // Each case: what the builder sends, refused by the API on the field the builder shows
  // the message on (the builder applies no domain rule of its own).
  const changeOf = (
    variable_id: string,
    change_type: "percent_change" | "absolute_change",
    value: string,
  ) => ({
    variable_id,
    change_type,
    value,
    note: "",
  });
  const cases: [string, ScenarioInput["shocks"], string][] = [
    [
      "a fall of 100 % or more",
      [changeOf("var_brent_crude", "percent_change", "-100")],
      "shocks[0].value",
    ],
    [
      "a rise above the published maximum",
      [changeOf("var_brent_crude", "percent_change", "1000.5")],
      "shocks[0].value",
    ],
    ["a change of zero", [changeOf("var_brent_crude", "percent_change", "0")], "shocks[0].value"],
    [
      "more than four decimal places",
      [changeOf("var_brent_crude", "percent_change", "1.23456")],
      "shocks[0].value",
    ],
    [
      "a rate moved by more than 25 percentage points",
      [changeOf("var_rbi_repo_rate", "absolute_change", "30")],
      "shocks[0].value",
    ],
    [
      "a percent change applied to a rate",
      [changeOf("var_rbi_repo_rate", "percent_change", "1")],
      "shocks[0].change_type",
    ],
    [
      "an unknown variable",
      [changeOf("var_does_not_exist", "percent_change", "1")],
      "shocks[0].variable_id",
    ],
    [
      "the same variable twice",
      [
        changeOf("var_brent_crude", "percent_change", "1"),
        changeOf("var_brent_crude", "percent_change", "2"),
      ],
      "shocks[1].variable_id",
    ],
  ];

  it.each(cases)("refuses %s on the field the builder shows it", async (_, shocks, field) => {
    expect(variables.size).toBeGreaterThan(0);
    const input = toInput(
      draftFromInput({ name: unique("Integration refused"), description: "", note: "", shocks }),
    );
    expect(await refusedFields(input)).toEqual([field]);
  });

  it("rejects fields the contract does not define", async () => {
    const body = toInput(
      draftFromInput({
        name: unique("Integration extra"),
        description: "",
        note: "",
        shocks: [changeOf("var_brent_crude", "percent_change", "1")],
      }),
    );
    const response = await fetch(`${baseUrl}/api/v1/scenarios`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...body, simulated_result: 12 }),
    });
    expect(response.status).toBe(422);
    const error = (await response.json()) as unknown;
    expect(contractViolations("ErrorResponse", error)).toEqual([]);
    expect(error).toMatchObject({ error: { details: [{ field: "simulated_result" }] } });
  });

  it("answers malformed JSON with the standard error envelope", async () => {
    const response = await fetch(`${baseUrl}/api/v1/scenarios`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: '{"name": ',
    });
    expect(response.status).toBe(422);
    const body = (await response.json()) as { error: { request_id: string } };
    expect(contractViolations("ErrorResponse", body)).toEqual([]);
    expect(body.error.request_id).toBe(response.headers.get("X-Request-ID"));
  });
});

describe("the Scenario Lab against the live API", () => {
  it("lists templates built only on registered models, and the ones it does not offer", async () => {
    const templates = await labApi.templates(options);
    expect(contractViolations("TemplateList", templates)).toEqual([]);
    const models = new Set((await simulationApi.models(options)).map((model) => model.id));
    for (const template of templates.items) {
      for (const model of template.models) expect(models.has(model.model_id)).toBe(true);
    }
    // Demand and supply-chain shocks need volumes, which no registered model simulates.
    expect(templates.unsupported.map((item) => item.id)).toEqual(["demand", "supply_chain"]);
  });

  it("plans a template before its figures exist, without computing anything", async () => {
    const template = await labApi.template("crude_oil_airline", options);
    const preview = await labApi.preview(toInput(draftFromInput(template.scenario)), options);
    expect(contractViolations("PreviewRead", preview)).toEqual([]);
    expect(preview.stored).toBe(false);
    expect(preview.results).toBeNull();
    expect(preview.plan.executable).toBe(false);
    expect(preview.plan.issues.some((issue) => issue.code === "required")).toBe(true);
  });

  it("executes a scenario in the background, reports its stages and reproduces it", async () => {
    // The backend tests' reference case, with HYPOTHETICAL round figures.
    const template = await labApi.template("oil_rupee_rates", options);
    let draft = { ...draftFromInput(template.scenario), name: unique("Integration execution") };
    draft = {
      ...draft,
      entity: "company:co_aerisca_airways",
      reportingCurrency: "INR",
      annualRevenue: "300000000",
      annualOperatingCosts: "250000000",
      fxRate: { value: "80", unit: "", source: "user", seriesId: "" },
    };
    const inputs: [string, string, string, string][] = [
      ["airline_fuel_cost", "jet_fuel_price", "750", "usd_per_kilolitre"],
      ["airline_fuel_cost", "annual_fuel_consumption", "1000", "kilolitre"],
      ["fx_exposure", "annual_usd_revenue", "500000", ""],
      ["fx_exposure", "annual_usd_costs", "200000", ""],
      ["floating_rate_interest", "annual_interest_expense", "12000000", ""],
      ["floating_rate_interest", "repo_linked_debt", "100000000", ""],
      ["floating_rate_interest", "us_rate_linked_debt", "0", ""],
    ];
    for (const [model, input, value, unit] of inputs) {
      draft = draftReducer(draft, { type: "modelInput", model, input, patch: { value, unit } });
    }
    draft = draftReducer(draft, {
      type: "modelMode",
      model: "floating_rate_interest",
      mode: "include",
    });
    const assumptions: [string, string, string][] = [
      ["airline_fuel_cost", "hedge_ratio", "40"],
      ["airline_fuel_cost", "hedge_months", "6"],
      ["airline_fuel_cost", "fare_pass_through", "50"],
      ["airline_fuel_cost", "fare_pass_through_lag", "2"],
      ["airline_fuel_cost", "crude_pass_through_lag", "1"],
      ["floating_rate_interest", "repo_repricing_lag", "3"],
    ];
    for (const [model, input, value] of assumptions) {
      draft = draftReducer(draft, { type: "modelAssumption", model, input, value });
    }

    const plan = await labApi.plan(toInput(draft), options);
    expect(contractViolations("PlanRead", plan)).toEqual([]);
    expect(plan.issues.filter((issue) => issue.severity === "error")).toEqual([]);
    expect(plan.executable).toBe(true);

    const saved = await api.scenarios.create(toInput(draft), options);
    created.push(saved.id);
    const started = await labApi.execute(saved.id, null, options);
    expect(contractViolations("ExecutionRead", started)).toEqual([]);

    let execution: ScenarioExecution = started;
    const deadline = Date.now() + 20_000;
    while (!isFinal(execution.status) && Date.now() < deadline) {
      await new Promise((resolve) => setTimeout(resolve, execution.poll_after_ms ?? 200));
      execution = await labApi.execution(started.id, options);
    }
    expect(execution.status).toBe("completed");
    expect(execution.stages.map((stage) => stage.stage)).toEqual([
      "validating",
      "simulating",
      "propagating",
      "aggregating",
    ]);
    expect(execution.runs.map((run) => run.model_id).sort()).toEqual([
      "airline_fuel_cost",
      "floating_rate_interest",
      "fx_exposure",
    ]);

    const results = await labApi.results(execution.id, options);
    expect(contractViolations("ResultsRead", results)).toEqual([]);
    const change = Object.fromEntries(results.lines.map((line) => [line.id, line.change]));
    // Worked out by hand in backend/tests/scenario_support.py.
    expect(change).toMatchObject({
      revenue: "6925000",
      operating_costs: "13250000",
      operating_profit: "-6325000",
      interest_expense: "375000",
      profit_before_tax: "-6700000",
    });
    const pathway = await labApi.pathways(execution.id, options);
    expect(contractViolations("LabPathwayRead", pathway)).toEqual([]);
    expect(
      pathway.links
        .filter((link) => link.kind === "cited")
        .every((link) => link.simulation === "context_only"),
    ).toBe(true);
    const explanation = await labApi.explanation(execution.id, "profit_before_tax", options);
    expect(contractViolations("LabExplanationRead", explanation)).toEqual([]);

    const verification = await labApi.verify(execution.id, options);
    expect(verification.reproduced).toBe(true);

    // An executed scenario keeps its history: it cannot be deleted.
    const kept = await api.scenarios.remove(saved.id, options).catch((error: unknown) => error);
    expect(kept).toMatchObject({ kind: "http", status: 409 });
  });
});

describe("Financial intelligence against the live API", () => {
  const aerisca = "company:co_aerisca_airways";

  it("analyses the workspace with every finding tied to its evidence", async () => {
    const overview = await intelligenceApi.overview({}, options);
    expect(contractViolations("OverviewRead", overview)).toEqual([]);
    expect(overview.build.freshness).not.toBe("not_built");
    expect(overview.insights.length).toBeGreaterThan(0);
    for (const insight of overview.insights) {
      expect(insight.chain.length).toBeGreaterThan(0);
      expect(insight.evidence.weakest_step).not.toBeNull();
    }
    // The SYNTHETIC smoke-test prices are an instrument with stored values.
    expect(overview.instruments.map((item) => item.subject.id)).toContain("smoke-synthetic");
    const methods = await intelligenceApi.methods(options);
    expect(contractViolations("MethodsRead", methods)).toEqual([]);
    const changes = await intelligenceApi.changes({ price_move_percent: "1" }, options);
    expect(contractViolations("ChangesRead", changes)).toEqual([]);
    // 102.00 → 100.40 is −1.57 %: reported at a 1 % threshold, not at the default 5 %.
    expect(changes.observed.map((item) => item.change.value)).toContain("-1.568627451");
  });

  it("builds a dossier and a brief from validated relationships", async () => {
    const entities = await intelligenceApi.entities(undefined, options);
    expect(contractViolations("EntityListRead", entities)).toEqual([]);
    expect(entities.items.map((item) => item.entity.key)).toContain(aerisca);

    const dossier = await intelligenceApi.entity(aerisca, {}, "any", options);
    expect(contractViolations("EntityAnalysisRead", dossier)).toEqual([]);
    expect(dossier.exposure.paths.length).toBeGreaterThan(0);
    for (const path of dossier.exposure.paths) {
      for (const edge of path.edges) expect(edge.quality_status).toBe("validated");
    }
    const brief = await intelligenceApi.brief(aerisca, {}, options);
    expect(contractViolations("BriefRead", brief)).toEqual([]);
    expect(brief.evidence.map((item) => item.insight_id)).toEqual(
      dossier.insights.map((item) => item.id),
    );
  });

  it("refuses an invalid threshold with its field", async () => {
    const error = await intelligenceApi
      .overview({ relative_change_percent: "0" }, options)
      .catch((caught: unknown) => caught);
    expect(error).toMatchObject({ kind: "http", status: 422, code: "validation_error" });
    expect((error as ApiError).details.map((detail) => detail.field)).toEqual([
      "relative_change_percent",
    ]);
  });

  it("stores an analysis and reads it back unchanged and current", async () => {
    const stored = await intelligenceApi.analyses.create(
      { scope: "entity", entity: aerisca, thresholds: null, evidence: "any", label: null },
      options,
    );
    expect(contractViolations("AnalysisRead", stored)).toEqual([]);
    const again = await intelligenceApi.analyses.get(stored.id, options);
    expect(again.result_hash).toBe(stored.result_hash);
    expect(again.freshness.status).toBe("current");
    const listed = await intelligenceApi.analyses.list({ entity: aerisca }, options);
    expect(listed.items.map((item) => item.id)).toContain(stored.id);
  });
});

describe("browser access", () => {
  it("allows the Vite dev server's origin and no other", async () => {
    const preflight = (origin: string) =>
      fetch(`${baseUrl}/api/v1/scenarios`, {
        method: "OPTIONS",
        headers: {
          Origin: origin,
          "Access-Control-Request-Method": "POST",
          "Access-Control-Request-Headers": "content-type",
        },
      });
    const allowed = await preflight("http://localhost:5173");
    expect(allowed.headers.get("access-control-allow-origin")).toBe("http://localhost:5173");
    const other = await preflight("https://evil.example");
    expect(other.headers.get("access-control-allow-origin")).toBeNull();
  });
});
