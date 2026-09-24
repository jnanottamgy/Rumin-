/**
 * Phase 5 Scenario Lab fixtures, captured from a running backend by
 * `backend/scripts/capture_lab_fixtures.py` (not hand-written): the sample network built into
 * a knowledge graph, and the backend tests' REFERENCE scenario — "oil, rupee and rates" on
 * the fictional Aerisca Airways, with HYPOTHETICAL round figures chosen to be checked by
 * hand (profit before tax −6,700,000 INR over 12 months), not market data or any
 * company's accounts. A second scenario, Brent alone, is the other side of the comparison;
 * `preview-needs-figures` is the airline template as the Lab opens it, before any figure;
 * `models` holds the definitions of the three models the reference scenario includes.
 */
import type {
  ExecutionVerification,
  LabExplanation,
  LabPathway,
  LabSensitivity,
  LabSensitivityList,
  Scenario,
  ScenarioComparison,
  ScenarioExecution,
  ScenarioExecutionPage,
  ScenarioPage,
  ScenarioPlan,
  ScenarioPreview,
  ScenarioResults,
  ScenarioTemplate,
  ScenarioTemplateList,
  SimulationModelDetail,
} from "@/types/api";
import comparison from "./lab/comparison.json";
import execution from "./lab/execution.json";
import executions from "./lab/executions.json";
import explanation from "./lab/explanation.json";
import models from "./lab/models.json";
import pathway from "./lab/pathway.json";
import previewNeedsFigures from "./lab/preview-needs-figures.json";
import results from "./lab/results.json";
import scenario from "./lab/scenario.json";
import scenarios from "./lab/scenarios.json";
import sensitivity from "./lab/sensitivity.json";
import template from "./lab/template.json";
import templates from "./lab/templates.json";
import verification from "./lab/verification.json";

const copy = <T>(value: unknown): T => structuredClone(value) as T;

function planOf(value: ScenarioExecution): ScenarioPlan {
  if (!value.plan) throw new Error("The captured execution has no plan.");
  return value.plan;
}

export const SCENARIO_ID = scenario.id;
export const EXECUTION_ID = execution.id;

export const labFixtures = {
  templates: () => copy<ScenarioTemplateList>(templates),
  template: () => copy<ScenarioTemplate>(template),
  scenario: () => copy<Scenario>(scenario),
  scenarios: () => copy<ScenarioPage>(scenarios),
  execution: () => copy<ScenarioExecution>(execution),
  executions: () => copy<ScenarioExecutionPage>(executions),
  results: () => copy<ScenarioResults>(results),
  pathway: () => copy<LabPathway>(pathway),
  explanation: () => copy<LabExplanation>(explanation),
  sensitivity: () => copy<LabSensitivity>(sensitivity),
  sensitivityList: (): LabSensitivityList => ({ items: [copy<LabSensitivity>(sensitivity)] }),
  verification: () => copy<ExecutionVerification>(verification),
  comparison: () => copy<ScenarioComparison>(comparison),
  previewNeedsFigures: () => copy<ScenarioPreview>(previewNeedsFigures),
  /** The definitions of the models the reference scenario includes, by id. */
  models: () => copy<Record<string, SimulationModelDetail>>(models),
  /**
   * The unstored preview of the reference scenario, assembled from the captured plan,
   * results and pathway (the backend computes all three the same way for a preview);
   * `lib/contract` checks it against the OpenAPI contract.
   */
  preview: (): ScenarioPreview => ({
    plan: planOf(copy<ScenarioExecution>(execution)),
    results: { ...copy<ScenarioResults>(results), execution_id: null },
    pathway: copy<LabPathway>(pathway),
    stored: false,
    note: previewNeedsFigures.note,
  }),
};
