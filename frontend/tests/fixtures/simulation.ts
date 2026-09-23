/**
 * Phase 4 simulation fixtures, captured from a running backend (not hand-written): the
 * sample network built into a knowledge graph (build #4), and one run of the airline
 * model with the page's HYPOTHETICAL example inputs — round numbers chosen to be checked
 * by hand (a fuel bill of 5,000,000 INR a month), not market data or any airline's
 * figures. `validate-invalid` and `run-refused` use the same inputs with the hedge ratio
 * at 150 % and the annual revenue left out.
 */
import type {
  GraphNodeSearchPage,
  SensitivityAnalysis,
  SimulationExplanation,
  SimulationModelDetail,
  SimulationModelSummary,
  SimulationProvenance,
  SimulationRun,
  SimulationRunPage,
  SimulationValidation,
  SimulationVerification,
} from "@/types/api";
import airlines from "./simulation/airlines.json";
import explanation from "./simulation/explanation.json";
import model from "./simulation/model.json";
import models from "./simulation/models.json";
import provenance from "./simulation/provenance.json";
import run from "./simulation/run.json";
import runRefused from "./simulation/run-refused.json";
import runs from "./simulation/runs.json";
import sensitivity from "./simulation/sensitivity.json";
import validateInvalid from "./simulation/validate-invalid.json";
import validateValid from "./simulation/validate-valid.json";
import verify from "./simulation/verify.json";

const copy = <T>(value: unknown): T => structuredClone(value) as T;

export const RUN_ID = run.id;

export const simulationFixtures = {
  models: () => copy<SimulationModelSummary[]>(models),
  model: () => copy<SimulationModelDetail>(model),
  validateValid: () => copy<SimulationValidation>(validateValid),
  validateInvalid: () => copy<SimulationValidation>(validateInvalid),
  runRefused: () => copy<{ error: { details: unknown[] } }>(runRefused),
  run: () => copy<SimulationRun>(run),
  explanation: () => copy<SimulationExplanation>(explanation),
  provenance: () => copy<SimulationProvenance>(provenance),
  verify: () => copy<SimulationVerification>(verify),
  sensitivity: () => copy<SensitivityAnalysis>(sensitivity),
  runs: () => copy<SimulationRunPage>(runs),
  airlines: () => copy<GraphNodeSearchPage>(airlines),
};

export const simulationPath = {
  models: "/api/v1/simulation-models",
  model: "/api/v1/simulation-models/airline_fuel_cost",
  validate: "/api/v1/simulations/validate",
  runs: "/api/v1/simulations",
  run: (id: string) => `/api/v1/simulations/${id}`,
  explanation: (id: string) => `/api/v1/simulations/${id}/explanation`,
  provenance: (id: string) => `/api/v1/simulations/${id}/provenance`,
  verify: (id: string) => `/api/v1/simulations/${id}/verify`,
  sensitivity: (id: string) => `/api/v1/simulations/${id}/sensitivity`,
  airlines: "/api/v1/graph/nodes",
};
