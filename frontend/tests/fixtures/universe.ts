/**
 * Phase 8 fixtures for the 3D universe, captured from a real backend by
 * `backend/scripts/capture_universe_fixtures.py` (not hand-written): the knowledge graph
 * built from the illustrative sample dataset and the World Bank series catalogue
 * (definitions only), and the backend tests' REFERENCE scenario executed on the fictional
 * Aerisca Airways with HYPOTHETICAL round figures.
 */
import type {
  GraphEdgeDetail,
  GraphEdgePage,
  GraphNeighborhood,
  GraphNodeDetail,
  GraphNodeSearchPage,
  GraphOverview,
  GraphPaths,
  GraphTypes,
  LabPathway,
  ScenarioExecution,
  ScenarioPage,
  ScenarioResults,
} from "@/types/api";
import edgeTransmission from "./universe/edge-transmission.json";
import edges from "./universe/edges.json";
import execution from "./universe/execution.json";
import neighborhoodCompany from "./universe/neighborhood-company.json";
import neighborhoodVariable from "./universe/neighborhood-variable.json";
import nodeCompany from "./universe/node-company.json";
import nodeVariable from "./universe/node-variable.json";
import nodes from "./universe/nodes.json";
import overview from "./universe/overview.json";
import paths from "./universe/paths.json";
import pathways from "./universe/pathways.json";
import results from "./universe/results.json";
import scenarios from "./universe/scenarios.json";
import types from "./universe/types.json";

const copy = <T>(value: unknown): T => structuredClone(value) as T;

export const COMPANY = "company:co_aerisca_airways";
export const VARIABLE = "variable:var_brent_crude";

export const universeFixtures = {
  overview: () => copy<GraphOverview>(overview),
  types: () => copy<GraphTypes>(types),
  nodes: () => copy<GraphNodeSearchPage>(nodes),
  edges: () => copy<GraphEdgePage>(edges),
  nodeCompany: () => copy<GraphNodeDetail>(nodeCompany),
  nodeVariable: () => copy<GraphNodeDetail>(nodeVariable),
  neighborhoodCompany: () => copy<GraphNeighborhood>(neighborhoodCompany),
  neighborhoodVariable: () => copy<GraphNeighborhood>(neighborhoodVariable),
  paths: () => copy<GraphPaths>(paths),
  execution: () => copy<ScenarioExecution>(execution),
  pathways: () => copy<LabPathway>(pathways),
  results: () => copy<ScenarioResults>(results),
  scenarios: () => copy<ScenarioPage>(scenarios),
  edgeTransmission: () => copy<GraphEdgeDetail>(edgeTransmission),
};
