/**
 * Phase 3 knowledge-graph fixtures, captured from running backends (not hand-written):
 *
 * - most files: the graph built from the illustrative sample dataset and the World Bank
 *   series catalogue (definitions only — no values were retrieved in the build
 *   environment);
 * - `overview-not-built`: a seeded database whose graph was never built;
 * - `overview-stale`: a database whose source records changed after the build.
 *
 * Every company in them is fictional; see the `nature` of each node.
 */
import type {
  GraphEdgeDetail,
  GraphNeighborhood,
  GraphNodeDetail,
  GraphNodeSearchPage,
  GraphOverview,
  GraphPaths,
  GraphTypes,
} from "@/types/api";
import edgeUsdInrDeltrin from "./graph/edge-usdinr-deltrin.json";
import industries from "./graph/industries.json";
import mostConnected from "./graph/most-connected.json";
import neighborhoodAerisca from "./graph/neighborhood-aerisca.json";
import neighborhoodDeltrin from "./graph/neighborhood-deltrin.json";
import neighborhoodDeltrinRecorded from "./graph/neighborhood-deltrin-recorded.json";
import nodeAerisca from "./graph/node-aerisca.json";
import nodeDeltrin from "./graph/node-deltrin.json";
import overview from "./graph/overview.json";
import overviewNotBuilt from "./graph/overview-not-built.json";
import overviewStale from "./graph/overview-stale.json";
import pathsAeriscaBrent from "./graph/paths-aerisca-brent.json";
import pathsNone from "./graph/paths-none.json";
import searchAeri from "./graph/search-aeri.json";
import types from "./graph/types.json";

const copy = <T>(value: unknown): T => structuredClone(value) as T;

export const graphFixtures = {
  overview: () => copy<GraphOverview>(overview),
  overviewNotBuilt: () => copy<GraphOverview>(overviewNotBuilt),
  overviewStale: () => copy<GraphOverview>(overviewStale),
  types: () => copy<GraphTypes>(types),
  searchAeri: () => copy<GraphNodeSearchPage>(searchAeri),
  mostConnected: () => copy<GraphNodeSearchPage>(mostConnected),
  industries: () => copy<GraphNodeSearchPage>(industries),
  /** Deltrin Refining, depth 1 (9 nodes, 18 edges). */
  neighborhoodDeltrin: () => copy<GraphNeighborhood>(neighborhoodDeltrin),
  /** Deltrin Refining, depth 1, evidence-backed and analyst-created edges only. */
  neighborhoodDeltrinRecorded: () => copy<GraphNeighborhood>(neighborhoodDeltrinRecorded),
  /** Aerisca Airways, depth 1: adds Air transport to Deltrin's neighbourhood. */
  neighborhoodAerisca: () => copy<GraphNeighborhood>(neighborhoodAerisca),
  nodeDeltrin: () => copy<GraphNodeDetail>(nodeDeltrin),
  nodeAerisca: () => copy<GraphNodeDetail>(nodeAerisca),
  /** USD/INR exchange rate — affects costs of → Deltrin Refining (a model assumption). */
  edgeUsdInrDeltrin: () => copy<GraphEdgeDetail>(edgeUsdInrDeltrin),
  pathsAeriscaBrent: () => copy<GraphPaths>(pathsAeriscaBrent),
  /** The same pair with at most 1 hop: no path. */
  pathsNone: () => copy<GraphPaths>(pathsNone),
};

export const DELTRIN = "company:co_deltrin_refining";
export const AERISCA = "company:co_aerisca_airways";
export const AIR_TRANSPORT = "industry:ind_air_transport";
export const BRENT = "variable:var_brent_crude";
export const USD_INR_EDGE = "e-dff724fccf21ee64";

/** API paths as the client requests them (node keys are URL-encoded). */
export const graphPath = {
  overview: "/api/v1/graph/overview",
  types: "/api/v1/graph/types",
  nodes: "/api/v1/graph/nodes",
  node: (key: string) => `/api/v1/graph/nodes/${encodeURIComponent(key)}`,
  neighborhood: (key: string) => `/api/v1/graph/nodes/${encodeURIComponent(key)}/neighborhood`,
  edge: (id: string) => `/api/v1/graph/edges/${id}`,
  paths: "/api/v1/graph/paths",
};
