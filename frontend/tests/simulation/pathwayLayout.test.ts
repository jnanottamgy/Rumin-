/** The pathway layout: layers by distance to the result, placeholders, no overlaps. */
import { describe, expect, it } from "vitest";
import { layoutPathway, smoothPath } from "@/features/simulation/pathwayLayout";
import { simulationFixtures } from "../fixtures/simulation";

const node = (id: string) => ({ id });
const link = (source: string, target: string) => ({ source, target });

describe("pathway layout", () => {
  it("places each node as close as possible to what it feeds", () => {
    const layout = layoutPathway(
      [node("a"), node("b"), node("c"), node("x")],
      [link("a", "b"), link("b", "c"), link("x", "c")],
      { width: 800 },
    );
    const layer = Object.fromEntries(layout.nodes.map((item) => [item.node.id, item.layer]));
    expect(layer).toEqual({ a: 0, b: 1, x: 1, c: 2 });
  });

  it("routes a link that skips a layer beside the nodes of that layer", () => {
    const layout = layoutPathway(
      [node("a"), node("b"), node("c")],
      [link("a", "b"), link("b", "c"), link("a", "c")],
      { width: 800 },
    );
    const long = layout.links.find((item) => item.link.source === "a" && item.link.target === "c");
    const middle = layout.nodes.find((item) => item.node.id === "b");
    // Through a placeholder: in and out of layer 1, clear of node b.
    expect(long?.points).toHaveLength(4);
    const pass = long?.points[1];
    expect(pass && middle && (pass.x < middle.x || pass.x > middle.x + middle.width)).toBe(true);
  });

  it("never overlaps nodes, and is deterministic", () => {
    const { nodes, links } = simulationFixtures.explanation().pathway;
    const first = layoutPathway(nodes, links, { width: 720 });
    const second = layoutPathway(nodes, links, { width: 720 });
    expect(first).toEqual(second);
    expect(first.fits).toBe(true);
    for (const a of first.nodes) {
      for (const b of first.nodes) {
        if (a === b || a.layer !== b.layer) continue;
        expect(a.x + a.width <= b.x || b.x + b.width <= a.x).toBe(true);
      }
    }
    // The final result is alone in the last layer.
    const last = first.nodes.filter((item) => item.layer === first.layers - 1);
    expect(last.map((item) => item.node.id)).toEqual(["output:operating_profit_change"]);
  });

  it("reports when the drawing cannot fit, so a list is shown instead", () => {
    const { nodes, links } = simulationFixtures.explanation().pathway;
    expect(layoutPathway(nodes, links, { width: 320 }).fits).toBe(false);
  });

  it("survives a cycle without looping", () => {
    const layout = layoutPathway([node("a"), node("b")], [link("a", "b"), link("b", "a")], {
      width: 400,
    });
    expect(layout.nodes).toHaveLength(2);
  });

  it("draws smooth vertical flows", () => {
    expect(smoothPath([])).toBe("");
    expect(
      smoothPath([
        { x: 10, y: 0 },
        { x: 10, y: 50 },
      ]),
    ).toBe("M10.0 0.0 L10.0 50.0");
    expect(
      smoothPath([
        { x: 0, y: 0 },
        { x: 40, y: 100 },
      ]),
    ).toBe("M0.0 0.0 C0.0 50.0 40.0 50.0 40.0 100.0");
  });
});
