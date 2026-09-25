/**
 * Integration: the Phase 3 knowledge-graph API against a running backend.
 *
 * `scripts/smoke_test.sh` builds the graph with `python -m app.graph build` after loading
 * the sample dataset, the series catalogue (definitions only) and a three-row SYNTHETIC
 * price file, so the graph holds real reference records, the fictional sample network
 * and one sample instrument.
 */
import { describe, expect, it } from "vitest";
import { ApiError } from "@/lib/apiClient";
import { graphApi } from "@/services/api";
import { contractViolations } from "./contract";
import { baseUrl, options, signedIn } from "./session";

const DELTRIN = "company:co_deltrin_refining";
const AERISCA = "company:co_aerisca_airways";
const BRENT = "variable:var_brent_crude";

describe("graph overview and vocabulary", () => {
  it("reports a current build whose counts come from the build itself", async () => {
    const overview = await graphApi.overview(options);
    expect(contractViolations("GraphOverview", overview)).toEqual([]);
    expect(overview.freshness.status).toBe("current");
    const build = overview.build;
    expect(build?.status).toMatch(/^completed/);
    expect(build?.nodes.processed).toBe(
      (build?.nodes.valid ?? 0) + (build?.nodes.flagged ?? 0) + (build?.nodes.rejected ?? 0),
    );
    expect(build?.node_count).toBe(overview.metrics.node_count);
    const sum = overview.type_map.reduce((total, item) => total + item.count, 0);
    expect(sum).toBe(build?.node_count);
    // Every edge has at least one evidence record; an edge without one is rejected.
    const provenance = overview.metrics.provenance as { edges_with_evidence: number };
    expect(provenance.edges_with_evidence).toBe(build?.edge_count);
    expect(overview.notes.join(" ")).toMatch(/not a map of the complete economy/);
  });

  it("describes every node type, edge type and evidence status", async () => {
    const types = await graphApi.types(options);
    expect(contractViolations("GraphTypesResponse", types)).toEqual([]);
    expect(types.evidence_statuses.map((item) => item.status).sort()).toEqual([
      "analyst_created",
      "evidence_backed",
      "model_assumption",
      "unverified",
    ]);
    for (const edgeType of types.edge_types) expect(edgeType.caveat.length).toBeGreaterThan(20);
  });
});

describe("search", () => {
  it("puts an exact identifier match first", async () => {
    const page = await graphApi.search({ q: "IN" }, options);
    expect(contractViolations("Page_NodeSearchResult_", page)).toEqual([]);
    expect(page.items[0]).toMatchObject({ id: "country:cty_in", match: "identifier" });
  });

  it("finds the sample instrument and market imported from the price file", async () => {
    const instrument = await graphApi.search({ q: "SMOKETEST", types: ["instrument"] }, options);
    expect(instrument.items[0]).toMatchObject({
      type: "instrument",
      nature: "sample",
      data_status: "values_stored",
    });
    const market = await graphApi.search({ q: "XNSE", types: ["market"] }, options);
    expect(market.items[0]?.type).toBe("market");
  });
});

describe("nodes, neighbourhoods and edges", () => {
  it("returns a node with identifiers, sources and assumed exposures", async () => {
    const node = await graphApi.node(DELTRIN, options);
    expect(contractViolations("GraphNodeDetail", node)).toEqual([]);
    expect(node).toMatchObject({ type: "company", nature: "fictional" });
    expect(node.sources[0]).toMatchObject({ table: "companies", record_id: "co_deltrin_refining" });
    expect(node.exposures?.map((item) => item.kind).sort()).toContain("via_industry");

    const india = await graphApi.node("country:cty_in", options);
    const alpha2 = india.identifiers.find((item) => item.scheme === "iso3166_alpha2");
    expect(alpha2?.value).toBe("IN");
  });

  it("returns a closed neighbourhood: every edge joins two returned nodes", async () => {
    const hood = await graphApi.neighborhood(DELTRIN, 2, 60, {}, options);
    expect(contractViolations("NeighborhoodResponse", hood)).toEqual([]);
    const ids = new Set(hood.nodes.map((node) => node.id));
    expect(ids.has(DELTRIN)).toBe(true);
    expect(hood.nodes.length).toBeLessThanOrEqual(60);
    for (const edge of hood.edges) {
      expect(ids.has(edge.source) && ids.has(edge.target), edge.id).toBe(true);
    }
    expect(hood.queries).toBeLessThanOrEqual(3);
  });

  it("applies filters on the server", async () => {
    const hood = await graphApi.neighborhood(
      DELTRIN,
      1,
      60,
      { evidenceStatuses: ["evidence_backed", "analyst_created"], includeIllustrative: true },
      options,
    );
    for (const edge of hood.edges) {
      expect(["evidence_backed", "analyst_created"]).toContain(edge.evidence_status);
    }
    const real = await graphApi.neighborhood(
      DELTRIN,
      1,
      60,
      { includeIllustrative: false },
      options,
    );
    expect(real.edges.every((edge) => !edge.is_illustrative)).toBe(true);
  });

  it("explains every edge with at least one evidence record", async () => {
    const hood = await graphApi.neighborhood(DELTRIN, 1, 60, {}, options);
    for (const summary of hood.edges.slice(0, 6)) {
      const edge = await graphApi.edge(summary.id, options);
      expect(contractViolations("GraphEdgeDetail", edge)).toEqual([]);
      expect(edge.evidence.length).toBeGreaterThan(0);
      for (const item of edge.evidence) {
        expect(item.statement.length).toBeGreaterThan(0);
        expect(item.rule).toMatch(/^[NR]\d{2} /);
      }
      expect(edge.caveat.length).toBeGreaterThan(0);
    }
  });

  it("rejects traversal beyond its limits instead of walking the whole graph", async () => {
    const tooDeep = graphApi.neighborhood(DELTRIN, 4, 60, {}, options);
    await expect(tooDeep).rejects.toBeInstanceOf(ApiError);
    await expect(tooDeep).rejects.toMatchObject({ status: 422 });
    await expect(graphApi.neighborhood(DELTRIN, 1, 500, {}, options)).rejects.toMatchObject({
      status: 422,
    });
  });
});

describe("paths and components", () => {
  it("finds shortest paths made of real, consecutive edges", async () => {
    const answer = await graphApi.paths(AERISCA, BRENT, 4, 3, {}, options);
    expect(contractViolations("PathsResponse", answer)).toEqual([]);
    expect(answer.found).toBe(true);
    const edges = new Map(answer.edges.map((edge) => [edge.id, edge]));
    for (const path of answer.paths) {
      expect(path.nodes[0]).toBe(AERISCA);
      expect(path.nodes.at(-1)).toBe(BRENT);
      expect(path.edges).toHaveLength(path.length);
      path.edges.forEach((id, index) => {
        const edge = edges.get(id);
        const ends = new Set([edge?.source, edge?.target]);
        expect(ends.has(path.nodes[index]) && ends.has(path.nodes[index + 1]), id).toBe(true);
      });
    }
    expect(answer.note).toMatch(/not an influence, transmission or causal chain/);
  });

  it("describes components without calling them economic systems", async () => {
    const components = await graphApi.components(options);
    expect(contractViolations("ComponentsResponse", components)).toEqual([]);
    expect(components.note).toMatch(
      /does not mean the entities form an integrated economic system/,
    );
  });
});

describe("safety", () => {
  it("is read-only", async () => {
    for (const path of [
      "/api/v1/graph/nodes",
      `/api/v1/graph/nodes/${encodeURIComponent(DELTRIN)}`,
    ]) {
      const response = await fetch(`${baseUrl}${path}`, { method: "POST", headers: signedIn });
      expect(response.status, path).toBe(405);
    }
  });

  it("rejects malformed node keys", async () => {
    const response = await fetch(
      `${baseUrl}/api/v1/graph/nodes/${encodeURIComponent("Company:X Y")}`,
      { headers: signedIn },
    );
    expect(response.status).toBe(422);
  });
});
