import { describe, expect, it } from "vitest";
import { columnLayout, radialLayout, smallestGap } from "@/features/graph/layout";
import { interpolate, startPositions } from "@/features/graph/useAnimatedPositions";
import { buildPathView, buildView, type GraphView, type ViewNode } from "@/features/graph/view";
import type { GraphEdgeSummary, GraphNeighborhood } from "@/types/api";
import { AERISCA, AIR_TRANSPORT, DELTRIN, graphFixtures } from "../fixtures/graph";

const ready = (data: GraphNeighborhood) => ({ status: "ready" as const, data });

/** A synthetic star-of-stars view: a centre, `spokes` neighbours, each with `leaves`. */
function syntheticView(spokes: number, leaves: number): GraphView {
  const nodes = new Map<string, ViewNode>();
  const edges = new Map<string, GraphEdgeSummary>();
  const node = (id: string, hops: number, parent: string | null): ViewNode => ({
    id,
    type: "company",
    name: id,
    subtitle: "",
    nature: "fictional",
    quality_status: "validated",
    degree: 1,
    primary_identifier: null,
    data_status: "not_applicable",
    hops,
    parent,
    origin: parent ?? id,
    shownDegree: 1,
  });
  const edge = (source: string, target: string): GraphEdgeSummary => ({
    id: `e-${source}-${target}`,
    type: "supplies_to",
    category: "economic",
    source,
    target,
    directed: true,
    label: "supplies",
    description: "",
    evidence_status: "model_assumption",
    is_illustrative: true,
    quality_status: "validated",
    valid_from: null,
    valid_to: null,
    historical: false,
    qualifiers: {},
  });
  nodes.set("company:centre", node("company:centre", 0, null));
  for (let s = 0; s < spokes; s += 1) {
    const spoke = `company:s${String(s).padStart(3, "0")}`;
    nodes.set(spoke, node(spoke, 1, "company:centre"));
    edges.set(`e-${s}`, edge("company:centre", spoke));
    for (let l = 0; l < leaves; l += 1) {
      const leaf = `${spoke}-l${String(l).padStart(3, "0")}`;
      nodes.set(leaf, node(leaf, 2, spoke));
      edges.set(`e-${s}-${l}`, edge(spoke, leaf));
    }
  }
  return {
    focus: "company:centre",
    nodes,
    edges,
    order: [...nodes.keys()],
    hiddenByLimit: 0,
    focusTruncated: false,
    unexploredByType: {},
    expansions: [],
    maxHops: leaves ? 2 : 1,
  };
}

const distance = (a: { x: number; y: number }, b: { x: number; y: number }) =>
  Math.hypot(a.x - b.x, a.y - b.y);

describe("radialLayout", () => {
  const view = buildView(
    graphFixtures.neighborhoodDeltrin(),
    [{ id: AERISCA, answer: ready(graphFixtures.neighborhoodAerisca()) }],
    100,
  );
  const layout = radialLayout(view);

  it("puts the focus at the centre and every node on the ring of its hop count", () => {
    expect(layout.positions.get(DELTRIN)).toEqual({ x: 0, y: 0 });
    for (const node of view.nodes.values()) {
      if (node.id === DELTRIN) continue;
      const point = layout.positions.get(node.id);
      expect(point, node.id).toBeDefined();
      expect(distance(point as { x: number; y: number }, { x: 0, y: 0 })).toBeCloseTo(
        layout.rings[node.hops] as number,
        0,
      );
    }
    expect(layout.positions.size).toBe(view.nodes.size);
  });

  it("places rings further out with every hop", () => {
    for (let index = 1; index < layout.rings.length; index += 1) {
      expect(layout.rings[index] as number).toBeGreaterThan(layout.rings[index - 1] as number);
    }
    expect(view.nodes.get(AIR_TRANSPORT)?.hops).toBe(2);
  });

  it("is deterministic", () => {
    const again = radialLayout(view);
    expect([...again.positions.entries()]).toEqual([...layout.positions.entries()]);
  });

  it("keeps neighbours on a ring at least the minimum arc apart", () => {
    const big = syntheticView(12, 11);
    const result = radialLayout(big, { minArc: 24 });
    for (let hops = 1; hops <= 2; hops += 1) {
      const points = [...big.nodes.values()]
        .filter((node) => node.hops === hops)
        .map((node) => result.positions.get(node.id) as { x: number; y: number });
      let closest = Number.POSITIVE_INFINITY;
      for (let i = 0; i < points.length; i += 1) {
        for (let j = i + 1; j < points.length; j += 1) {
          closest = Math.min(closest, distance(points[i] as never, points[j] as never));
        }
      }
      // A chord is a little shorter than its arc; allow for that and for rounding.
      expect(closest, `ring ${hops}`).toBeGreaterThan(24 * 0.95);
    }
  });

  it("keeps a subtree inside its parent's wedge", () => {
    const big = syntheticView(6, 5);
    const result = radialLayout(big);
    const angle = (id: string) => {
      const point = result.positions.get(id) as { x: number; y: number };
      return Math.atan2(point.y, point.x);
    };
    for (const node of big.nodes.values()) {
      if (node.hops !== 2 || !node.parent) continue;
      const delta = Math.abs(
        Math.atan2(
          Math.sin(angle(node.id) - angle(node.parent)),
          Math.cos(angle(node.id) - angle(node.parent)),
        ),
      );
      // Six equal wedges of 60°: a leaf is within 30° of its spoke.
      expect(delta, node.id).toBeLessThanOrEqual(Math.PI / 6 + 1e-6);
    }
  });

  it("writes labels along the radius only on crowded rings", () => {
    const sparse = radialLayout(syntheticView(5, 0), { horizontalLabelLimit: 10 });
    expect([...sparse.labelAngle.values()].every((value) => value === null)).toBe(true);
    const crowded = radialLayout(syntheticView(20, 0), { horizontalLabelLimit: 10 });
    const angles = [...crowded.labelAngle.entries()].filter(([id]) => id !== "company:centre");
    expect(angles.every(([, value]) => typeof value === "number")).toBe(true);
  });

  it("handles a focus with no neighbours", () => {
    const lonely = syntheticView(0, 0);
    const result = radialLayout(lonely);
    expect(result.positions.get("company:centre")).toEqual({ x: 0, y: 0 });
    expect(result.rings).toEqual([0]);
  });
});

describe("smallestGap", () => {
  it("measures the smallest gap around the circle, wrapping at 2π", () => {
    expect(smallestGap([0])).toBeCloseTo(Math.PI * 2);
    expect(smallestGap([0, Math.PI])).toBeCloseTo(Math.PI);
    expect(smallestGap([0.1, Math.PI * 2 - 0.1, 1])).toBeCloseTo(0.2);
  });
});

describe("columnLayout", () => {
  it("lays paths out left to right by position along the path", () => {
    const view = buildPathView(graphFixtures.pathsAeriscaBrent());
    const layout = columnLayout(view, { columnGap: 200, rowGap: 80 });
    for (const node of view.nodes.values()) {
      expect(layout.positions.get(node.id)?.x, node.id).toBe(node.hops * 200);
    }
    // Nodes in one column never overlap.
    const byColumn = new Map<number, number[]>();
    for (const point of layout.positions.values()) {
      byColumn.set(point.x, [...(byColumn.get(point.x) ?? []), point.y]);
    }
    for (const ys of byColumn.values()) expect(new Set(ys).size).toBe(ys.length);
  });
});

describe("animation helpers", () => {
  it("starts new nodes at the position of the node that brought them in", () => {
    const displayed = new Map([["a", { x: 10, y: 20 }]]);
    const target = new Map([
      ["a", { x: 50, y: 50 }],
      ["b", { x: 100, y: 0 }],
    ]);
    const start = startPositions(displayed, target, (id) => (id === "b" ? "a" : undefined));
    expect(start.get("a")).toEqual({ x: 10, y: 20 });
    expect(start.get("b")).toEqual({ x: 10, y: 20 });
  });

  it("interpolates between two layouts", () => {
    const from = new Map([["a", { x: 0, y: 0 }]]);
    const to = new Map([["a", { x: 10, y: -10 }]]);
    expect(interpolate(from, to, 0.5).get("a")).toEqual({ x: 5, y: -5 });
    expect(interpolate(from, to, 1).get("a")).toEqual({ x: 10, y: -10 });
  });
});
