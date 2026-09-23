import { describe, expect, it } from "vitest";
import { nodeRadius } from "@/features/network/encoding";
import {
  barycentricOrder,
  computeLayout,
  type LayoutEdgeInput,
  type LayoutNodeInput,
  seededRandom,
  transposeLayout,
} from "@/features/network/layout";
import { buildGraphModel } from "@/features/network/model";
import type { EntityKind } from "@/types/api";
import { networkFixture } from "../fixtures";

function layoutInputs() {
  const model = buildGraphModel(networkFixture());
  const nodes: LayoutNodeInput[] = model.nodes.map((node) => ({
    id: node.id,
    kind: node.kind,
    radius: nodeRadius(node.kind, node.degree),
  }));
  const edges: LayoutEdgeInput[] = model.edges.map((edge) => ({
    source: edge.source,
    target: edge.target,
    category: edge.category,
  }));
  return { model, nodes, edges };
}

describe("computeLayout", () => {
  const { nodes, edges } = layoutInputs();
  const layout = computeLayout(nodes, edges);

  it("places every node at a finite position inside the bounds", () => {
    expect(layout.positions.size).toBe(nodes.length);
    for (const [id, point] of layout.positions) {
      expect(Number.isFinite(point.x), id).toBe(true);
      expect(Number.isFinite(point.y), id).toBe(true);
      expect(point.x).toBeGreaterThanOrEqual(layout.bounds.minX);
      expect(point.x).toBeLessThanOrEqual(layout.bounds.maxX);
      expect(point.y).toBeGreaterThanOrEqual(layout.bounds.minY);
      expect(point.y).toBeLessThanOrEqual(layout.bounds.maxY);
    }
  });

  it("is deterministic: the same data always produces the same picture", () => {
    const again = computeLayout([...nodes].reverse(), [...edges].reverse());
    for (const [id, point] of layout.positions) {
      expect(again.positions.get(id)).toEqual(point);
    }
  });

  it("reads left to right: variables, industries, companies, countries", () => {
    const meanX = (kind: EntityKind) => {
      const xs = nodes
        .filter((node) => node.kind === kind)
        .map((node) => layout.positions.get(node.id)?.x ?? Number.NaN);
      return xs.reduce((sum, x) => sum + x, 0) / xs.length;
    };
    const order = ["economic_variable", "industry", "company", "country"] as const;
    const means = order.map(meanX);
    expect(means).toEqual([...means].sort((a, b) => a - b));
    expect(layout.orientation).toBe("horizontal");
  });

  it("keeps nodes apart", () => {
    const placed = nodes.map((node) => ({ node, point: layout.positions.get(node.id) }));
    for (const [index, a] of placed.entries()) {
      for (const b of placed.slice(index + 1)) {
        if (!a.point || !b.point) throw new Error("unplaced node");
        const distance = Math.hypot(a.point.x - b.point.x, a.point.y - b.point.y);
        expect(distance, `${a.node.id} ↔ ${b.node.id}`).toBeGreaterThan(
          Math.max(a.node.radius, b.node.radius),
        );
      }
    }
  });

  it("handles an empty graph", () => {
    const empty = computeLayout([], []);
    expect(empty.positions.size).toBe(0);
    expect(empty.bounds).toEqual({ minX: 0, minY: 0, maxX: 0, maxY: 0 });
  });
});

describe("barycentricOrder", () => {
  it("normalises positions within each column to [0, 1]", () => {
    const { nodes, edges } = layoutInputs();
    const order = barycentricOrder(nodes, edges);
    expect(order.size).toBe(nodes.length);
    for (const value of order.values()) {
      expect(value).toBeGreaterThanOrEqual(0);
      expect(value).toBeLessThanOrEqual(1);
    }
  });

  it("pulls connected nodes level with each other", () => {
    // v1 → i2 and v2 → i1: a crossing that the heuristic should undo.
    const nodes: LayoutNodeInput[] = [
      { id: "v1", kind: "economic_variable", radius: 5 },
      { id: "v2", kind: "economic_variable", radius: 5 },
      { id: "i1", kind: "industry", radius: 5 },
      { id: "i2", kind: "industry", radius: 5 },
    ];
    const edges: LayoutEdgeInput[] = [
      { source: "v1", target: "i2", category: "economic" },
      { source: "v2", target: "i1", category: "economic" },
    ];
    const order = barycentricOrder(nodes, edges);
    expect(Math.sign((order.get("v1") ?? 0) - (order.get("v2") ?? 0))).toBe(
      Math.sign((order.get("i2") ?? 0) - (order.get("i1") ?? 0)),
    );
  });
});

describe("transposeLayout", () => {
  it("turns columns into rows for portrait screens", () => {
    const { nodes, edges } = layoutInputs();
    const layout = computeLayout(nodes, edges);
    const portrait = transposeLayout(layout, 0.5);
    expect(portrait.orientation).toBe("vertical");
    const [id, point] = [...layout.positions][0] ?? [];
    if (!id || !point) throw new Error("empty layout");
    expect(portrait.positions.get(id)).toEqual({ x: point.y, y: point.x * 0.5 });
    expect(portrait.bounds.minX).toBe(layout.bounds.minY);
    expect(portrait.bounds.maxY).toBe(layout.bounds.maxX * 0.5);
  });
});

describe("seededRandom", () => {
  it("repeats its sequence for the same seed and stays within [0, 1)", () => {
    const a = seededRandom(11);
    const b = seededRandom(11);
    const values = Array.from({ length: 50 }, () => a());
    expect(values).toEqual(Array.from({ length: 50 }, () => b()));
    for (const value of values) {
      expect(value).toBeGreaterThanOrEqual(0);
      expect(value).toBeLessThan(1);
    }
    expect(seededRandom(12)()).not.toBe(values[0]);
  });
});
