import { describe, expect, it } from "vitest";
import {
  buildPathView,
  buildView,
  compareNodes,
  incidentTo,
  spanningTree,
} from "@/features/graph/view";
import type { GraphNeighborhood } from "@/types/api";
import { AERISCA, AIR_TRANSPORT, DELTRIN, graphFixtures } from "../fixtures/graph";

const ready = (data: GraphNeighborhood) => ({ status: "ready" as const, data });

describe("buildView", () => {
  it("shows exactly the nodes and edges of the focus neighbourhood", () => {
    const answer = graphFixtures.neighborhoodDeltrin();
    const view = buildView(answer, [], 100);
    expect(view.focus).toBe(DELTRIN);
    expect([...view.nodes.keys()].sort()).toEqual(answer.nodes.map((node) => node.id).sort());
    expect([...view.edges.keys()].sort()).toEqual(answer.edges.map((edge) => edge.id).sort());
    expect(view.hiddenByLimit).toBe(0);
    expect(view.focusTruncated).toBe(false);
  });

  it("merges an expansion without duplicating nodes or edges", () => {
    const focus = graphFixtures.neighborhoodDeltrin();
    const expansion = graphFixtures.neighborhoodAerisca();
    const view = buildView(focus, [{ id: AERISCA, answer: ready(expansion) }], 100);

    const expectedNodes = new Set([...focus.nodes, ...expansion.nodes].map((node) => node.id));
    expect(view.nodes.size).toBe(expectedNodes.size);
    expect(view.order).toHaveLength(expectedNodes.size);
    const expectedEdges = new Set([...focus.edges, ...expansion.edges].map((edge) => edge.id));
    expect(view.edges.size).toBe(expectedEdges.size);
    expect(view.expansions).toEqual([
      { id: AERISCA, status: "applied", added: 1, hidden: 0, truncated: false },
    ]);
    // The new node grows out of the node that brought it in, one hop further out.
    const added = view.nodes.get(AIR_TRANSPORT);
    expect(added?.origin).toBe(AERISCA);
    expect(added?.hops).toBe(2);
  });

  it("never shows an edge whose other end is not shown", () => {
    const view = buildView(graphFixtures.neighborhoodDeltrin(), [], 3);
    expect(view.nodes.size).toBe(3);
    for (const edge of view.edges.values()) {
      expect(view.nodes.has(edge.source) && view.nodes.has(edge.target), edge.id).toBe(true);
    }
  });

  it("counts the nodes a limit leaves out instead of dropping them silently", () => {
    const answer = graphFixtures.neighborhoodDeltrin();
    const expansion = graphFixtures.neighborhoodAerisca();
    const view = buildView(answer, [{ id: AERISCA, answer: ready(expansion) }], 4);
    expect(view.nodes.size).toBe(4);
    expect(view.nodes.has(AERISCA)).toBe(true);
    const shown = new Set(view.nodes.keys());
    const leftOut =
      answer.nodes.length - 4 + expansion.nodes.filter((node) => !shown.has(node.id)).length;
    expect(view.hiddenByLimit).toBe(leftOut);
    expect(view.expansions[0]).toMatchObject({ id: AERISCA, status: "applied", added: 0 });
  });

  it("reports pending, failed and skipped expansions without changing the drawing", () => {
    const focus = graphFixtures.neighborhoodDeltrin();
    const base = buildView(focus, [], 100);
    const view = buildView(
      focus,
      [
        { id: AERISCA, answer: { status: "pending" } },
        { id: "company:co_skyvara_air", answer: { status: "failed", error: new Error("boom") } },
        { id: "company:not_in_view", answer: ready(graphFixtures.neighborhoodAerisca()) },
      ],
      100,
    );
    expect(view.expansions.map((item) => item.status)).toEqual(["pending", "failed", "skipped"]);
    expect([...view.nodes.keys()]).toEqual([...base.nodes.keys()]);
    expect(view.edges.size).toBe(base.edges.size);
  });

  it("counts shown edges per node, so hidden connections can be reported", () => {
    const view = buildView(graphFixtures.neighborhoodDeltrin(), [], 100);
    const deltrin = view.nodes.get(DELTRIN);
    expect(deltrin?.shownDegree).toBe(incidentTo(view, DELTRIN).edgeIds.size);
    expect(deltrin?.degree).toBeGreaterThanOrEqual(deltrin?.shownDegree ?? 0);
  });
});

describe("spanningTree", () => {
  it("gives every node its shortest hop count and a parent one hop closer", () => {
    const view = buildView(
      graphFixtures.neighborhoodDeltrin(),
      [{ id: AERISCA, answer: ready(graphFixtures.neighborhoodAerisca()) }],
      100,
    );
    const { hops, parent } = spanningTree(view.focus, view.nodes, view.edges.values());
    expect(hops.get(DELTRIN)).toBe(0);
    expect(parent.get(DELTRIN)).toBeNull();
    for (const [id, value] of hops) {
      if (id === DELTRIN) continue;
      const up = parent.get(id);
      expect(up, id).toBeTruthy();
      expect(hops.get(up as string), id).toBe(value - 1);
    }
  });

  it("is deterministic whatever order the edges arrive in", () => {
    const view = buildView(graphFixtures.neighborhoodDeltrin(), [], 100);
    const forward = spanningTree(view.focus, view.nodes, [...view.edges.values()]);
    const reversed = spanningTree(view.focus, view.nodes, [...view.edges.values()].reverse());
    expect([...reversed.parent.entries()].sort()).toEqual([...forward.parent.entries()].sort());
  });
});

describe("compareNodes", () => {
  it("orders by type, then name, then key", () => {
    const nodes = graphFixtures.neighborhoodDeltrin().nodes;
    const sorted = [...nodes].sort(compareNodes);
    const again = [...nodes].reverse().sort(compareNodes);
    expect(again.map((node) => node.id)).toEqual(sorted.map((node) => node.id));
    expect(sorted[0]?.type).toBe("country");
  });
});

describe("buildPathView", () => {
  it("places every node at its position along the shortest paths", () => {
    const answer = graphFixtures.pathsAeriscaBrent();
    const view = buildPathView(answer);
    expect(view.focus).toBe(answer.source.id);
    expect(view.maxHops).toBe(answer.length);
    for (const path of answer.paths) {
      path.nodes.forEach((id, index) => {
        expect(view.nodes.get(id)?.hops, id).toBe(index);
      });
      for (const edge of path.edges) expect(view.edges.has(edge)).toBe(true);
    }
  });

  it("shows the two ends, unconnected, when no path was found", () => {
    const answer = graphFixtures.pathsNone();
    expect(answer.found).toBe(false);
    const view = buildPathView(answer);
    expect([...view.nodes.keys()].sort()).toEqual([answer.source.id, answer.target.id].sort());
    expect(view.edges.size).toBe(0);
  });
});
