/**
 * API fixtures captured from the running backend with the illustrative sample dataset
 * (`GET /api/v1/network`, `/api/v1/variables`, `/api/v1/system`). They are the real
 * contract, not hand-written approximations; the integration suite checks the live API
 * against the same code paths.
 */
import { validateNetwork } from "@/features/network/model";
import type {
  EconomicVariable,
  EconomicVariablePage,
  NetworkResponse,
  Scenario,
  ScenarioPage,
  SystemStatus,
} from "@/types/api";
import networkJson from "./network.json";
import systemJson from "./system.json";
import variablesJson from "./variables.json";

/** Fresh copies, so a test can never leak mutations into another. */
export const networkFixture = (): NetworkResponse => validateNetwork(structuredClone(networkJson));

export const variablesFixture = (): EconomicVariablePage =>
  structuredClone(variablesJson) as EconomicVariablePage;

export const systemFixture = (): SystemStatus => structuredClone(systemJson) as SystemStatus;

export function variableFixture(id: string): EconomicVariable {
  const variable = variablesFixture().items.find((item) => item.id === id);
  if (!variable) throw new Error(`No variable "${id}" in the fixture.`);
  return variable;
}

export function scenarioFixture(overrides: Partial<Scenario> = {}): Scenario {
  return {
    id: "7632ecaf-b2bb-4839-84b3-400268a18c22",
    name: "Oil price shock",
    description: "Brent crude rises 30 %.",
    status: "draft",
    shocks: [
      {
        variable_id: "var_brent_crude",
        change_type: "percent_change",
        value: 30,
        note: "",
        epistemic_category: "scenario_input",
      },
    ],
    latest_run: null,
    created_at: "2026-09-23T10:00:00Z",
    updated_at: "2026-09-23T10:00:00Z",
    ...overrides,
  };
}

export function scenarioPageFixture(items: Scenario[] = []): ScenarioPage {
  return { items, total: items.length, limit: 100, offset: 0 };
}
