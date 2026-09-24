/**
 * The impact pathway's layout, on the pathway the backend computed for the reference
 * scenario: four columns, one lane per model, graph context left to the lane header, no
 * overlaps, lines in accounting order with the metrics under them.
 */
import { describe, expect, it } from "vitest";
import {
  chainOf,
  columnOf,
  layoutPathway,
  NODE_HEIGHT,
  type PathwayLayout,
  type PlacedNode,
} from "@/features/scenarioLab/pathwayLayout";
import { labFixtures } from "../fixtures/lab";

const pathway = labFixtures.pathway();

/** Consecutive pairs of a list. */
function pairs<T>(items: readonly T[]): [T, T][] {
  return items.slice(1).map((item, index) => [items[index] as T, item]);
}

function placed(layout: PathwayLayout, id: string): PlacedNode {
  const node = layout.nodes.find((item) => item.id === id);
  if (!node) throw new Error(`${id} was not placed`);
  return node;
}

describe("pathway layout", () => {
  const layout = layoutPathway(pathway, { width: 900 });

  it("draws four columns: changes, variables, line items, then lines and metrics", () => {
    expect(layout.columns.map((column) => column.label)).toEqual([
      "Changes",
      "Variables moved",
      "Line items",
      "Lines",
    ]);
    const revenue = placed(layout, "line:revenue");
    expect(revenue.column).toBe("outcome");
    expect(revenue.node && columnOf(revenue.node)).toBe("outcome");
    expect(layout.headings).toEqual([expect.objectContaining({ text: "Metrics" })]);
  });

  it("places every step but graph context, which carries no value", () => {
    const steps = pathway.nodes.filter((node) => node.kind !== "context").map((node) => node.id);
    expect(layout.nodes.map((node) => node.id).sort()).toEqual([...steps].sort());
    expect(layout.links.flatMap((link) => link.links).some((link) => link.kind === "cited")).toBe(
      false,
    );
    // Each lane carries the relationships its model cites, for its header.
    const airline = layout.lanes.find((lane) => lane.id === "airline_fuel_cost");
    expect(airline?.context.map((link) => link.label)).toEqual(["affects costs of", "operates in"]);
  });

  it("draws every computed link once", () => {
    const computed = pathway.links.filter((link) => link.kind !== "cited");
    expect(layout.links.flatMap((link) => link.links)).toHaveLength(computed.length);
  });

  it("keeps each model's variables and line items inside its lane", () => {
    for (const lane of layout.lanes) {
      const members = layout.nodes.filter((node) => node.group === lane.id);
      expect(members.length).toBeGreaterThan(0);
      for (const node of members) {
        expect(node.y).toBeGreaterThanOrEqual(lane.y);
        expect(node.y + NODE_HEIGHT).toBeLessThanOrEqual(lane.y + lane.height);
        expect(node.x).toBeGreaterThanOrEqual(lane.x);
        expect(node.x + node.width).toBeLessThanOrEqual(lane.x + lane.width);
      }
    }
    // Lanes do not overlap.
    const lanes = [...layout.lanes].sort((a, b) => a.y - b.y);
    for (const [previous, next] of pairs(lanes)) {
      expect(next.y).toBeGreaterThan(previous.y + previous.height);
    }
  });

  it("never overlaps two steps in a column", () => {
    const byColumn = new Map<string, PlacedNode[]>();
    for (const node of layout.nodes) {
      byColumn.set(node.column, [...(byColumn.get(node.column) ?? []), node]);
    }
    for (const nodes of byColumn.values()) {
      const sorted = [...nodes].sort((a, b) => a.y - b.y);
      for (const [above, below] of pairs(sorted)) {
        expect(below.y).toBeGreaterThanOrEqual(above.y + NODE_HEIGHT);
      }
    }
  });

  it("keeps the lines in accounting order, with the metrics under them", () => {
    const order = [
      "line:revenue",
      "line:operating_costs",
      "line:operating_profit",
      "line:interest_expense",
      "line:profit_before_tax",
      "metric:operating_margin",
      "metric:interest_coverage",
    ].map((id) => placed(layout, id).y);
    expect(order).toEqual([...order].sort((a, b) => a - b));
  });

  it("fits the frame it is given, down to a minimum node width", () => {
    expect(layout.width).toBeLessThanOrEqual(900);
    const narrow = layoutPathway(pathway, { width: 300 });
    expect(narrow.columns.every((column) => column.width === 120)).toBe(true);
    expect(narrow.width).toBeGreaterThan(300); // the canvas scrolls rather than squashing
  });

  it("collapses a model to one step, re-routing its links and hiding the ones inside", () => {
    const collapsed = layoutPathway(pathway, { width: 900, collapsed: new Set(["fx_exposure"]) });
    expect(collapsed.nodes.some((node) => node.group === "fx_exposure" && node.node)).toBe(false);
    const group = placed(collapsed, "group:fx_exposure");
    expect(group.collapsed).toBe(true);
    const into = collapsed.links.filter((link) => link.target === "group:fx_exposure");
    const out = collapsed.links.filter((link) => link.source === "group:fx_exposure");
    expect(into.map((link) => link.source)).toEqual(["change:var_usd_inr"]);
    expect(out.map((link) => link.target).sort()).toEqual(["line:operating_costs", "line:revenue"]);
    expect(collapsed.links.some((link) => link.source === link.target)).toBe(false);
  });

  it("follows a step's chain upstream and downstream", () => {
    const chain = chainOf(layout, "airline_fuel_cost:variable:var_jet_fuel");
    expect(chain.nodes).toContain("change:var_brent_crude");
    expect(chain.nodes).toContain("airline_fuel_cost:output:fuel_cost_change");
    expect(chain.nodes).toContain("line:profit_before_tax");
    expect(chain.nodes).toContain("metric:operating_margin");
    // The interest model is not on this chain.
    expect(chain.nodes).not.toContain("floating_rate_interest:variable:var_rbi_repo_rate");
    const upstream = chainOf(layout, "line:interest_expense", ["up"]);
    expect([...upstream.nodes].sort()).toEqual([
      "change:var_rbi_repo_rate",
      "floating_rate_interest:output:repo_interest_change",
      "floating_rate_interest:variable:var_rbi_repo_rate",
      "line:interest_expense",
    ]);
  });
});
