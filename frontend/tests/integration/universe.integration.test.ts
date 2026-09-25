/**
 * Integration: what the 3D universe reads, against a running backend.
 *
 * `scripts/smoke_test.sh` builds the knowledge graph from the sample dataset (fictional
 * companies, illustrative relationships), the series catalogue (definitions only) and a
 * three-row SYNTHETIC price file. The overlay test executes the backend tests' reference
 * scenario with HYPOTHETICAL round figures; the executed scenario is kept, as every
 * executed scenario is.
 */
import { describe, expect, it } from "vitest";
import { DEFAULT_FILTERS } from "@/features/graph/useGraphExplorer";
import { layout3d } from "@/features/universe/layout3d";
import { buildOverlay, overlayNodeKeys } from "@/features/universe/overlay";
import { buildScene } from "@/features/universe/scene";
import { applyFilters, universeView } from "@/features/universe/universeView";
import { readWholeGraph, withinBudget } from "@/features/universe/useUniverseData";
import { graphApi, labApi } from "@/services/api";
import { contractViolations } from "./contract";
import { executeReference } from "./reference";

const baseUrl = process.env.RUMIN_API_URL?.replace(/\/+$/, "");
if (!baseUrl)
  throw new Error("Set RUMIN_API_URL to a running RUMIN API (see scripts/smoke_test.sh)");
const options = { baseUrl };

describe("the whole build", () => {
  it("is read page by page: every node and edge of the current build, exactly once", async () => {
    const overview = await graphApi.overview(options);
    const build = overview.build;
    expect(build).not.toBeNull();
    expect(withinBudget(build?.node_count ?? 0, build?.edge_count ?? 0)).toBe(true);

    const graph = await readWholeGraph(options);
    expect(graph.truncated).toBe(false);
    expect(graph.nodes).toHaveLength(build?.node_count ?? -1);
    expect(graph.edges).toHaveLength(build?.edge_count ?? -1);
    expect(new Set(graph.nodes.map((node) => node.id)).size).toBe(graph.nodes.length);
    expect(new Set(graph.edges.map((edge) => edge.id)).size).toBe(graph.edges.length);
    const ids = new Set(graph.nodes.map((node) => node.id));
    for (const edge of graph.edges) {
      expect(ids.has(edge.source)).toBe(true);
      expect(ids.has(edge.target)).toBe(true);
    }
    expect(
      contractViolations("Page_NodeSearchResult_", await graphApi.nodePage(0, options)),
    ).toEqual([]);
    expect(
      contractViolations("Page_GraphEdgeSummary_", await graphApi.edgePage(0, options)),
    ).toEqual([]);
  });

  it("lays out and marks every record it read, the same way twice", async () => {
    const graph = await readWholeGraph(options);
    const { nodes, edges } = applyFilters(graph.nodes, graph.edges, DEFAULT_FILTERS);
    const view = universeView(nodes, edges, null);
    expect(view?.nodes.size).toBe(graph.nodes.length);
    const input = {
      nodes: nodes.map((node) => ({ id: node.id, type: node.type })),
      edges: edges.map((edge) => ({
        id: edge.id,
        source: edge.source,
        target: edge.target,
        category: edge.category,
      })),
    };
    const first = layout3d(input.nodes, input.edges, {});
    const second = layout3d(input.nodes, input.edges, {});
    for (const node of nodes) {
      const point = first.positions.get(node.id);
      expect(point).toBeDefined();
      expect(
        Number.isFinite(point?.x) && Number.isFinite(point?.y) && Number.isFinite(point?.z),
      ).toBe(true);
      expect(second.positions.get(node.id)).toEqual(point);
    }
    const scene = buildScene({
      nodes,
      edges,
      positions: first.positions,
      focus: null,
      selection: null,
      hover: null,
      overlay: null,
    });
    expect(scene.nodes).toHaveLength(nodes.length);
    expect(scene.edges).toHaveLength(edges.length);
  });
});

describe("the scenario overlay", () => {
  it("lays a stored execution over the graph with records the graph holds", async () => {
    const { execution } = await executeReference(
      `Universe overlay ${Date.now().toString(36)}`,
      options,
    );
    const [pathway, results] = await Promise.all([
      labApi.pathways(execution.id, options),
      labApi.results(execution.id, options),
    ]);
    const overlay = buildOverlay(execution, pathway, results);
    expect(overlay.status).toBe("completed");
    expect(overlay.entity?.key).toBe("company:co_aerisca_airways");
    expect(overlay.changes.map((change) => change.key).sort()).toEqual([
      "variable:var_brent_crude",
      "variable:var_rbi_repo_rate",
      "variable:var_usd_inr",
    ]);

    const graph = await readWholeGraph(options);
    const nodeIds = new Set(graph.nodes.map((node) => node.id));
    const edgesById = new Map(graph.edges.map((edge) => [edge.id, edge]));
    for (const key of overlayNodeKeys(overlay)) expect(nodeIds.has(key)).toBe(true);
    // Every relationship the overlay marks is a current edge of the graph, between the
    // records it says.
    for (const [id, edge] of overlay.edges) {
      const stored = edgesById.get(id);
      expect(stored).toBeDefined();
      if (edge.source) expect(stored?.source).toBe(edge.source);
      if (edge.target) expect(stored?.target).toBe(edge.target);
    }
    const propagated = [...overlay.edges.values()].filter((edge) => edge.role === "propagated");
    expect(propagated.length).toBeGreaterThan(0);
    for (const edge of propagated) expect(edge.model?.id).toBeTruthy();

    // The figures are the stored results, unchanged.
    expect(overlay.lines.map((line) => [line.id, line.change])).toEqual(
      results.lines.map((line) => [line.id, line.change]),
    );
    expect(overlay.models.map((model) => model.id).sort()).toEqual(
      execution.runs.map((run) => run.model_id).sort(),
    );
  });
});
