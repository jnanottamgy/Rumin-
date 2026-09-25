/**
 * Phase 5 Scenario Lab fixtures, captured from a running backend by
 * `backend/scripts/capture_lab_fixtures.py` (not hand-written): the sample network built into
 * a knowledge graph, and the backend tests' REFERENCE scenario — "oil, rupee and rates" on
 * the fictional Aerisca Airways, with HYPOTHETICAL round figures chosen to be checked by
 * hand (profit before tax −6,700,000 INR over 12 months), not market data or any
 * company's accounts. A second scenario, Brent alone, is the other side of the comparison;
 * `preview-needs-figures` is the airline template as the Lab opens it, before any figure;
 * `models` holds the definitions of the three models the reference scenario includes.
 *
 * Phase 9: `analysis-targets` (what the execution can vary), a Monte Carlo analysis with
 * seed 20260925 and distributions chosen for the fixture (assumptions, not estimates), a
 * joint grid of crude oil and the rupee, the list of both, a re-run of the Monte Carlo
 * analysis, and each included model's verification register.
 */
import type {
  AnalysisTargets,
  AnalysisVerification,
  ExecutionVerification,
  LabExplanation,
  LabPathway,
  LabSensitivity,
  LabSensitivityList,
  ModelVerification,
  Scenario,
  ScenarioAnalysis,
  ScenarioAnalysisList,
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
import analyses from "./lab/analyses.json";
import analysisJoint from "./lab/analysis-joint.json";
import analysisMonteCarlo from "./lab/analysis-monte-carlo.json";
import analysisTargets from "./lab/analysis-targets.json";
import analysisVerification from "./lab/analysis-verification.json";
import comparison from "./lab/comparison.json";
import execution from "./lab/execution.json";
import executions from "./lab/executions.json";
import explanation from "./lab/explanation.json";
import modelVerification from "./lab/model-verification.json";
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
  analysisTargets: () => copy<AnalysisTargets>(analysisTargets),
  monteCarlo: () => copy<ScenarioAnalysis>(analysisMonteCarlo),
  joint: () => copy<ScenarioAnalysis>(analysisJoint),
  analyses: () => copy<ScenarioAnalysisList>(analyses),
  analysisVerification: () => copy<AnalysisVerification>(analysisVerification),
  /** Each included model's verification register, by model id. */
  modelVerification: () => copy<Record<string, ModelVerification>>(modelVerification),
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
