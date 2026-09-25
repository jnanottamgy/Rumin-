/**
 * The backend tests' reference scenario, built the way the Scenario Lab builds it (the
 * draft reducer), with HYPOTHETICAL round figures for the fictional Aerisca Airways — not
 * any company's. `executeReference` saves it, executes it and waits for the stored result.
 */
import { expect } from "vitest";
import { draftFromInput, draftReducer, type LabDraft, toInput } from "@/features/scenarioLab/draft";
import { isFinal } from "@/features/scenarioLab/format";
import { api, labApi } from "@/services/api";
import type { ScenarioExecution } from "@/types/api";

type Options = { baseUrl: string; headers?: Record<string, string> };

export async function referenceDraft(name: string, options: Options): Promise<LabDraft> {
  const template = await labApi.template("oil_rupee_rates", options);
  let draft = { ...draftFromInput(template.scenario), name };
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
  return draft;
}

/** Saves the reference scenario, executes it and waits (up to 20 s) for it to finish. */
export async function executeReference(
  name: string,
  options: Options,
): Promise<{ scenarioId: string; execution: ScenarioExecution }> {
  const saved = await api.scenarios.create(toInput(await referenceDraft(name, options)), options);
  let execution = await labApi.execute(saved.id, null, options);
  const deadline = Date.now() + 20_000;
  while (!isFinal(execution.status) && Date.now() < deadline) {
    await new Promise((resolve) => setTimeout(resolve, execution.poll_after_ms ?? 200));
    execution = await labApi.execution(execution.id, options);
  }
  expect(execution.status).toBe("completed");
  return { scenarioId: saved.id, execution };
}
