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
  ScenarioSummary,
  SystemStatus,
} from "@/types/api";
import { labFixtures } from "./lab";
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

/** A saved scenario, as captured with the Scenario Lab fixtures (see `./lab`). */
export function scenarioFixture(overrides: Partial<Scenario> = {}): Scenario {
  return { ...labFixtures.scenario(), ...overrides };
}

/** The scenario library: the captured scenarios by default, or the given summaries. */
export function scenarioPageFixture(items?: ScenarioSummary[]): ScenarioPage {
  if (!items) return labFixtures.scenarios();
  return { items, total: items.length, limit: 100, offset: 0 };
}
