/**
 * Integration: the frontend's real service layer against a running backend.
 *
 * `scripts/smoke_test.sh` runs this against a fresh, migrated and seeded database.
 * To run it against an API you started yourself:
 *
 *   RUMIN_API_URL=http://127.0.0.1:8000 npm run test:integration
 *
 * Scenarios created here are deleted again; point it only at a disposable database.
 */
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { graphFor } from "@/features/network/useNetworkGraph";
import {
  emptyShock,
  errorsFromApi,
  exampleDraft,
  type ScenarioDraft,
  shockField,
  toPayload,
  validateDraft,
} from "@/features/scenarios/scenarioModel";
import { ApiError } from "@/lib/apiClient";
import { api } from "@/services/api";
import type { EconomicVariable } from "@/types/api";
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

function draftWith(
  shocks: Partial<ScenarioDraft["shocks"][number]>[],
  name = "Integration",
): ScenarioDraft {
  return {
    id: null,
    name,
    description: "",
    shocks: shocks.map((s) => ({ ...emptyShock(), ...s })),
  };
}

async function serverErrors(draft: ScenarioDraft) {
  const error = await api.scenarios.create(toPayload(draft), options).then(
    (scenario) => {
      created.push(scenario.id);
      throw new Error(`The API accepted an invalid scenario: ${JSON.stringify(draft)}`);
    },
    (caught: unknown) => caught,
  );
  expect(error).toBeInstanceOf(ApiError);
  expect(error).toMatchObject({ kind: "http", status: 422, code: "validation_error" });
  return errorsFromApi(error as ApiError, draft);
}

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

describe("scenario drafts", () => {
  it("round-trips a draft the Scenario Lab considers valid", async () => {
    const draft = exampleDraft();
    expect(validateDraft(draft, variables)).toEqual({});

    const saved = await api.scenarios.create(toPayload(draft), options);
    created.push(saved.id);
    expect(contractViolations("ScenarioRead", saved)).toEqual([]);
    expect(saved).toMatchObject({ name: draft.name, status: "draft", latest_run: null });
    expect(saved.shocks).toEqual([
      {
        variable_id: "var_brent_crude",
        change_type: "percent_change",
        value: 30,
        note: "",
        epistemic_category: "scenario_input",
      },
    ]);

    expect(await api.scenarios.get(saved.id, options)).toEqual(saved);
    const listed = await api.scenarios.list(options);
    expect(listed.items.map((item) => item.id)).toContain(saved.id);

    const renamed = await api.scenarios.replace(
      saved.id,
      { ...toPayload(draft), name: "Integration rename" },
      options,
    );
    expect(renamed.name).toBe("Integration rename");

    await api.scenarios.remove(saved.id, options);
    const gone = await api.scenarios.get(saved.id, options).catch((error: unknown) => error);
    expect(gone).toMatchObject({ kind: "http", status: 404, code: "not_found" });
    expect((gone as ApiError).requestId).toBeTruthy();
  });

  // Each case: the Scenario Lab blocks it before sending, AND the API rejects it with a
  // detail that the lab maps back onto the same field. The two can never drift apart.
  const cases: [
    string,
    Partial<ScenarioDraft["shocks"][number]>[],
    (d: ScenarioDraft) => string,
  ][] = [
    [
      "a fall of 100 % or more",
      [{ variableId: "var_brent_crude", changeType: "percent_change", value: "-100" }],
      (d) => shockField(d.shocks[0]?.key ?? "", "value"),
    ],
    [
      "a rise above the published maximum",
      [{ variableId: "var_brent_crude", changeType: "percent_change", value: "1000.5" }],
      (d) => shockField(d.shocks[0]?.key ?? "", "value"),
    ],
    [
      "a change of zero",
      [{ variableId: "var_brent_crude", changeType: "percent_change", value: "0" }],
      (d) => shockField(d.shocks[0]?.key ?? "", "value"),
    ],
    [
      "more than four decimal places",
      [{ variableId: "var_brent_crude", changeType: "percent_change", value: "1.23456" }],
      (d) => shockField(d.shocks[0]?.key ?? "", "value"),
    ],
    [
      "a rate moved by more than 25 percentage points",
      [{ variableId: "var_rbi_repo_rate", changeType: "absolute_change", value: "30" }],
      (d) => shockField(d.shocks[0]?.key ?? "", "value"),
    ],
    [
      "a percent change applied to a rate",
      [{ variableId: "var_rbi_repo_rate", changeType: "percent_change", value: "1" }],
      (d) => shockField(d.shocks[0]?.key ?? "", "changeType"),
    ],
    [
      "an unknown variable",
      [{ variableId: "var_does_not_exist", changeType: "percent_change", value: "1" }],
      (d) => shockField(d.shocks[0]?.key ?? "", "variableId"),
    ],
    [
      "the same variable twice",
      [
        { variableId: "var_brent_crude", changeType: "percent_change", value: "1" },
        { variableId: "var_brent_crude", changeType: "percent_change", value: "2" },
      ],
      (d) => shockField(d.shocks[1]?.key ?? "", "variableId"),
    ],
  ];

  it.each(cases)(
    "rejects %s in the browser and on the server, on the same field",
    async (_, shocks, field) => {
      const draft = draftWith(shocks);
      const expected = field(draft);
      expect(Object.keys(validateDraft(draft, variables))).toEqual([expected]);
      expect(Object.keys(await serverErrors(draft))).toEqual([expected]);
    },
  );

  it("rejects a blank name in both places", async () => {
    const draft = draftWith(
      [{ variableId: "var_brent_crude", changeType: "percent_change", value: "1" }],
      "   ",
    );
    expect(Object.keys(validateDraft(draft, variables))).toEqual(["name"]);
    expect(Object.keys(await serverErrors(draft))).toEqual(["name"]);
  });

  it("rejects fields the contract does not define", async () => {
    const response = await fetch(`${baseUrl}/api/v1/scenarios`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...toPayload(exampleDraft()), simulated_result: 12 }),
    });
    expect(response.status).toBe(422);
    const body = (await response.json()) as unknown;
    expect(contractViolations("ErrorResponse", body)).toEqual([]);
    expect(body).toMatchObject({ error: { details: [{ field: "simulated_result" }] } });
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
