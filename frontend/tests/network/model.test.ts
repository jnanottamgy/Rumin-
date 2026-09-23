import { describe, expect, it } from "vitest";
import {
  buildGraphModel,
  defaultFilters,
  KIND_ORDER,
  NetworkDataError,
  neighborhood,
  searchNodes,
  validateNetwork,
  visibleSubgraph,
} from "@/features/network/model";
import type { NetworkResponse } from "@/types/api";
import { networkFixture } from "../fixtures";

const problemsOf = (payload: unknown): string[] => {
  try {
    validateNetwork(payload);
  } catch (error) {
    if (error instanceof NetworkDataError) return error.problems;
    throw error;
  }
  return [];
};

describe("validateNetwork", () => {
  it("accepts the API's network payload", () => {
    const network = networkFixture();
    expect(problemsOf(network)).toEqual([]);
    expect(network.nodes).toHaveLength(30);
    expect(network.edges).toHaveLength(71);
  });

  it("rejects payloads that are not a network", () => {
    expect(problemsOf(null)).toEqual(["The response is not a JSON object."]);
    expect(problemsOf({ nodes: [] })).toEqual([
      "`edges` is missing or not a list.",
      "`relationship_types` is missing or not a list.",
    ]);
  });

  it("rejects an edge that points to a node that does not exist", () => {
    const network: NetworkResponse = networkFixture();
    const edge = network.edges[0];
    if (!edge) throw new Error("fixture has no edges");
    edge.target_id = "co_does_not_exist";
    expect(problemsOf(network)).toEqual([
      `Edge "${edge.id}" points to unknown node "co_does_not_exist".`,
    ]);
    expect(() => validateNetwork(network)).toThrow(/inconsistent \(1 problem\)/);
  });

  it("rejects duplicate IDs, self-loops, unknown types and malformed records", () => {
    const network = networkFixture();
    const [first, second] = network.nodes;
    const [edgeA, edgeB, edgeC] = network.edges;
    if (!first || !second || !edgeA || !edgeB || !edgeC) throw new Error("fixture too small");
    second.id = first.id;
    edgeA.target_id = edgeA.source_id;
    edgeB.type = "teleports_to" as typeof edgeB.type;
    (network.edges as unknown[]).push({ id: 42 });

    const problems = problemsOf(network);
    expect(problems).toEqual(
      expect.arrayContaining([
        `Duplicate node ID "${first.id}".`,
        `Node "${first.id}" wraps a different entity.`,
        `Edge "${edgeA.id}" is a self-loop.`,
        `Edge "${edgeB.id}" has unknown type "teleports_to".`,
        "Edge #71 is malformed.",
      ]),
    );
  });
});

describe("graph model", () => {
  const model = buildGraphModel(networkFixture());

  it("indexes every node and edge", () => {
    expect(model.nodes).toHaveLength(30);
    expect(model.edges).toHaveLength(71);
    expect(model.nodeById.get("co_deltrin_refining")?.label).toBe("Deltrin Refining");
    expect(model.types.size).toBe(10);
    expect(model.dataset?.is_illustrative).toBe(true);
  });

  it("orders nodes by kind (drivers first), then by name", () => {
    const kinds = model.nodes.map((node) => KIND_ORDER.indexOf(node.kind));
    expect(kinds).toEqual([...kinds].sort((a, b) => a - b));
    const companies = model.nodes.filter((node) => node.kind === "company").map((n) => n.label);
    expect(companies).toEqual([...companies].sort((a, b) => a.localeCompare(b)));
  });

  it("records each edge against both of its ends, matching the API's degree", () => {
    for (const node of model.nodes) {
      expect(model.incident.get(node.id)).toHaveLength(node.degree);
    }
  });

  it("finds a node's direct neighbourhood and nothing further", () => {
    const hood = neighborhood(model, "co_deltrin_refining");
    const incident = model.incident.get("co_deltrin_refining") ?? [];
    expect(hood.edgeIds.size).toBe(incident.length);
    for (const edge of incident) {
      expect(hood.nodeIds.has(edge.source)).toBe(true);
      expect(hood.nodeIds.has(edge.target)).toBe(true);
    }
    // Every node in the neighbourhood is the selection or one hop from it.
    for (const id of hood.nodeIds) {
      if (id === "co_deltrin_refining") continue;
      expect(incident.some((edge) => edge.source === id || edge.target === id)).toBe(true);
    }
  });

  it("limits a neighbourhood to what is visible", () => {
    const filters = defaultFilters(model);
    const visible = visibleSubgraph(model, {
      ...filters,
      kinds: new Set(KIND_ORDER.filter((kind) => kind !== "country")),
    });
    const hood = neighborhood(model, "co_deltrin_refining", visible);
    for (const id of hood.nodeIds) expect(model.nodeById.get(id)?.kind).not.toBe("country");
  });
});

describe("filters", () => {
  const model = buildGraphModel(networkFixture());

  it("shows everything by default", () => {
    const visible = visibleSubgraph(model, defaultFilters(model));
    expect(visible.nodeIds.size).toBe(30);
    expect(visible.edgeIds.size).toBe(71);
  });

  it("hides the edges of hidden nodes, so no line points into empty space", () => {
    const visible = visibleSubgraph(model, {
      ...defaultFilters(model),
      kinds: new Set(KIND_ORDER.filter((kind) => kind !== "company")),
    });
    expect(visible.nodeIds.size).toBe(18);
    for (const id of visible.edgeIds) {
      const edge = model.edgeById.get(id);
      expect(edge && visible.nodeIds.has(edge.source) && visible.nodeIds.has(edge.target)).toBe(
        true,
      );
    }
  });

  it("filters by relationship type", () => {
    const visible = visibleSubgraph(model, {
      ...defaultFilters(model),
      edgeTypes: new Set(["domiciled_in"]),
    });
    expect(visible.edgeIds.size).toBe(12); // one per (fictional) company
  });
});

describe("searchNodes", () => {
  const model = buildGraphModel(networkFixture());

  it("ranks name prefixes first and ignores case", () => {
    const labels = searchNodes(model, "in").map((node) => node.label);
    expect(labels[0]).toBe("India");
    expect(labels.length).toBeLessThanOrEqual(6);
  });

  it("matches words inside names and IDs", () => {
    expect(searchNodes(model, "refining").map((node) => node.id)).toContain("co_deltrin_refining");
    expect(searchNodes(model, "var_brent").map((node) => node.id)).toEqual(["var_brent_crude"]);
  });

  it("returns nothing for a blank query", () => {
    expect(searchNodes(model, "   ")).toEqual([]);
  });
});
