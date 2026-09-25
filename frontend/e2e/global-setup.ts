/**
 * Prepares the run through the API, as a person would through the app: signs in the
 * administrator (RUMIN_TEST_EMAIL / RUMIN_TEST_PASSWORD), creates a viewer, executes the
 * backend tests' HYPOTHETICAL reference scenario for the fictional Aerisca Airways, runs a
 * simulation, stores an intelligence analysis and asks the Analyst one question. Every
 * password is random and made for this run.
 */
import { randomUUID } from "node:crypto";
import { mkdirSync, writeFileSync } from "node:fs";
import { type APIRequestContext, type FullConfig, request } from "@playwright/test";
import {
  ADMIN_STATE,
  credential,
  IDS_FILE,
  type PreparedIds,
  STATE_DIR,
  VIEWER_STATE,
} from "./state";

const API = "/api/v1";

const REFERENCE = {
  name: "E2E: oil, rupee and rates on Aerisca (HYPOTHETICAL)",
  description: "Round, made-up figures for the fictional Aerisca Airways.",
  note: "",
  shocks: [
    { variable_id: "var_brent_crude", change_type: "percent_change", value: "20", note: "" },
    { variable_id: "var_usd_inr", change_type: "percent_change", value: "5", note: "" },
    { variable_id: "var_rbi_repo_rate", change_type: "absolute_change", value: "0.5", note: "" },
  ],
  entity: "company:co_aerisca_airways",
  company: {
    reporting_currency: "INR",
    annual_revenue: "300000000",
    annual_operating_costs: "250000000",
  },
  markets: { fx_rate: { value: "80" } },
  models: {
    airline_fuel_cost: {
      inputs: {
        jet_fuel_price: { value: "750", unit: "usd_per_kilolitre" },
        annual_fuel_consumption: { value: "1000", unit: "kilolitre" },
      },
    },
    fx_exposure: {
      inputs: { annual_usd_revenue: { value: "500000" }, annual_usd_costs: { value: "200000" } },
    },
    floating_rate_interest: {
      mode: "include",
      inputs: {
        annual_interest_expense: { value: "12000000" },
        repo_linked_debt: { value: "100000000" },
        us_rate_linked_debt: { value: "0" },
      },
    },
  },
  stress_cases: [{ name: "Half", scale: "0.5" }],
};

async function ok<T>(response: Awaited<ReturnType<APIRequestContext["get"]>>, what: string) {
  if (!response.ok()) {
    throw new Error(`${what}: HTTP ${response.status()} ${await response.text()}`);
  }
  return (await response.json()) as T;
}

async function signIn(context: APIRequestContext, email: string, password: string) {
  await ok(
    await context.post(`${API}/auth/login`, { data: { email, password } }),
    `sign in ${email}`,
  );
}

export default async function globalSetup(config: FullConfig) {
  const { baseURL, ignoreHTTPSErrors } = config.projects[0]?.use ?? {};
  mkdirSync(STATE_DIR, { recursive: true });
  const admin = await request.newContext({ baseURL, ignoreHTTPSErrors });
  await signIn(admin, credential("RUMIN_TEST_EMAIL"), credential("RUMIN_TEST_PASSWORD"));
  const me = await ok<{ user: { email: string; name: string } }>(
    await admin.get(`${API}/auth/session`),
    "session",
  );
  await admin.storageState({ path: ADMIN_STATE });

  // A viewer who has chosen their own password, and a newcomer who has not.
  const viewer = {
    email: `viewer-${randomUUID().slice(0, 8)}@rumin.test`,
    password: `e2e ${randomUUID()}`,
  };
  const temporary = `temporary ${randomUUID()}`;
  await ok(
    await admin.post(`${API}/users`, {
      data: {
        name: "E2E Viewer",
        email: viewer.email,
        role: "viewer",
        temporary_password: temporary,
      },
    }),
    "create the viewer",
  );
  const viewerContext = await request.newContext({ baseURL, ignoreHTTPSErrors });
  await signIn(viewerContext, viewer.email, temporary);
  await ok(
    await viewerContext.post(`${API}/auth/password`, {
      data: { current_password: temporary, new_password: viewer.password },
    }),
    "the viewer chooses a password",
  );
  await viewerContext.storageState({ path: VIEWER_STATE });
  const newcomer = {
    email: `newcomer-${randomUUID().slice(0, 8)}@rumin.test`,
    password: `temporary ${randomUUID()}`,
  };
  await ok(
    await admin.post(`${API}/users`, {
      data: {
        name: "E2E Newcomer",
        email: newcomer.email,
        role: "analyst",
        temporary_password: newcomer.password,
      },
    }),
    "create the newcomer",
  );

  // Records every page can show.
  const scenario = await ok<{ id: string }>(
    await admin.post(`${API}/scenarios`, { data: REFERENCE }),
    "save the reference scenario",
  );
  let execution = await ok<{ id: string; status: string }>(
    await admin.post(`${API}/scenarios/${scenario.id}/executions`, { data: { version: null } }),
    "execute it",
  );
  for (let i = 0; i < 60 && !["completed", "failed", "cancelled"].includes(execution.status); i++) {
    await new Promise((resolve) => setTimeout(resolve, 500));
    execution = await ok(
      await admin.get(`${API}/scenario-executions/${execution.id}`),
      "follow it",
    );
  }
  if (execution.status !== "completed") throw new Error(`The execution ended ${execution.status}.`);

  const run = await ok<{ id: string }>(
    await admin.post(`${API}/simulations`, {
      data: {
        model_id: "airline_fuel_cost",
        label: "E2E run (HYPOTHETICAL)",
        inputs: {
          crude_oil_change: { value: "10" },
          jet_fuel_price: { value: "750", unit: "usd_per_kilolitre" },
          fx_rate: { value: "80" },
          reporting_currency: { value: "INR" },
          annual_revenue: { value: "300000000" },
          annual_operating_costs: { value: "250000000" },
          annual_fuel_consumption: { value: "1000", unit: "kilolitre" },
        },
      },
    }),
    "run the airline model",
  );
  const analysis = await ok<{ id: string }>(
    await admin.post(`${API}/intelligence/analyses`, {
      data: { scope: "workspace", entity: null, thresholds: null, evidence: "any", label: "E2E" },
    }),
    "store an analysis",
  );
  const session = await ok<{ id: string }>(
    await admin.post(`${API}/analyst/sessions`, { data: { title: "E2E conversation" } }),
    "start a conversation",
  );
  await ok(
    await admin.post(`${API}/analyst/sessions/${session.id}/turns`, {
      data: { question: "Which companies are exposed to Brent crude?" },
    }),
    "ask a question",
  );

  const series = await ok<{ items: { id: string }[] }>(
    await admin.get(`${API}/economic-series?limit=5`),
    "series",
  );
  const instruments = await ok<{ items: { id: string }[] }>(
    await admin.get(`${API}/instruments?limit=5`),
    "instruments",
  );
  const jobs = await ok<{ items: { id: string }[] }>(
    await admin.get(`${API}/ingestion-jobs?limit=5`),
    "jobs",
  );

  const ids: PreparedIds = {
    scenario: scenario.id,
    execution: execution.id,
    run: run.id,
    analysis: analysis.id,
    session: session.id,
    series: series.items[0]?.id ?? null,
    instrument: instruments.items[0]?.id ?? null,
    job: jobs.items[0]?.id ?? null,
    newcomer,
    admin: { email: me.user.email, name: me.user.name },
  };
  writeFileSync(IDS_FILE, JSON.stringify(ids, null, 2));
  await Promise.all([admin.dispose(), viewerContext.dispose()]);
}
