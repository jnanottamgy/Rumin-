/**
 * The 3D universe's pure modules on the real sample graph (fixtures captured from a
 * backend): strata, the layout (deterministic, stable as the view grows), camera maths,
 * keyboard navigation, label placement, the scene's marks and the scenario overlay.
 */
import { describe, expect, it } from "vitest";
import { DEFAULT_FILTERS } from "@/features/graph/useGraphExplorer";
import {
  basis,
  easeOut,
  eye,
  FOV,
  fitDistance,
  frameAll,
  framing,
  interpolate,
  MAX_PHI,
  MIN_PHI,
  MIN_RADIUS,
  pan,
  rotate,
  zoom,
} from "@/features/universe/camera";
import { keyAction, nearestInDirection } from "@/features/universe/keyboard";
import { placeLabels } from "@/features/universe/labels";
import { enclosing, hash, layout3d, seeded } from "@/features/universe/layout3d";
import {
  buildOverlay,
  EDGE_ROLE_LABEL,
  graphKey,
  overlayNodeKeys,
} from "@/features/universe/overlay";
import { activeSet, buildScene, labelPriority, nodeSize } from "@/features/universe/scene";
import { heightOf, STRATA, STRATUM_GAP, stratumOf } from "@/features/universe/strata";
import { applyFilters } from "@/features/universe/universeView";
import type { GraphEdgeSummary, GraphNodeSummary, GraphNodeType } from "@/types/api";
import { COMPANY, universeFixtures, VARIABLE } from "../fixtures/universe";

const graph = () => {
  const nodes = universeFixtures.nodes().items;
  const edges = universeFixtures.edges().items;
  return { nodes, edges };
};

const layoutOf = (
  nodes: GraphNodeSummary[],
  edges: GraphEdgeSummary[],
  previous?: Map<string, { x: number; y: number; z: number }>,
) =>
  layout3d(
    nodes.map((node) => ({ id: node.id, type: node.type })),
    edges.map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      category: edge.category,
    })),
    previous ? { previous } : {},
  );

describe("strata", () => {
  it("give every node type one stratum, drivers above companies above places", () => {
    const types: GraphNodeType[] = [
      "country",
      "currency",
      "sector",
      "industry",
      "company",
      "economic_variable",
      "data_series",
      "instrument",
      "market",
    ];
    for (const type of types) expect(STRATA).toContain(stratumOf(type));
    expect(heightOf("economic_variable")).toBeGreaterThan(heightOf("industry"));
    expect(heightOf("industry")).toBeGreaterThan(heightOf("company"));
    expect(heightOf("company")).toBeGreaterThan(heightOf("country"));
    expect(heightOf("data_series")).toBe(2 * STRATUM_GAP);
  });
});

describe("the layout", () => {
  it("places every node of the sample graph on its stratum, the same way every time", () => {
    const { nodes, edges } = graph();
    const first = layoutOf(nodes, edges);
    const again = layoutOf([...nodes].reverse(), [...edges].reverse());
    expect(first.positions.size).toBe(nodes.length);
    for (const node of nodes) {
      const point = first.positions.get(node.id);
      expect(point).toBeDefined();
      expect(point?.y).toBe(heightOf(node.type));
      expect(Number.isFinite(point?.x)).toBe(true);
      expect(Number.isFinite(point?.z)).toBe(true);
      expect(again.positions.get(node.id)).toEqual(point);
    }
    expect(first.radius).toBeGreaterThan(0);
  });

  it("keeps placed nodes still and starts new ones beside the node that brought them", () => {
    const { nodes, edges } = graph();
    const neighbourhood = universeFixtures.neighborhoodCompany();
    const firstIds = new Set(neighbourhood.nodes.map((node) => node.id));
    const firstNodes = nodes.filter((node) => firstIds.has(node.id));
    const first = layoutOf(firstNodes, edges);
    const grown = layout3d(
      nodes.map((node) => ({ id: node.id, type: node.type })),
      edges.map((edge) => ({ ...edge })),
      { previous: first.positions },
    );
    for (const [id, point] of first.positions) expect(grown.positions.get(id)).toEqual(point);
    const added = nodes.filter((node) => !firstIds.has(node.id));
    expect(added.length).toBeGreaterThan(0);
    for (const node of added) expect(grown.positions.get(node.id)).toBeDefined();
  });

  it("hashes and seeds deterministically", () => {
    expect(hash("company:a")).toBe(hash("company:a"));
    expect(hash("company:a")).not.toBe(hash("company:b"));
    const one = seeded(3);
    const two = seeded(3);
    expect([one(), one(), one()]).toEqual([two(), two(), two()]);
    expect(enclosing(new Map()).radius).toBeGreaterThan(0);
  });
});

describe("the camera", () => {
  const view = framing({ x: 0, y: 0, z: 0 }, 100, 1.6);

  it("frames a sphere, orbits within the poles and zooms within its limits", () => {
    const from = eye(view);
    expect(Math.hypot(from.x, from.y, from.z)).toBeCloseTo(view.radius, 6);
    expect(fitDistance(100, 1.6)).toBeGreaterThan(100);
    expect(fitDistance(100, 0.5)).toBeGreaterThan(fitDistance(100, 1.6));
    expect(rotate(view, 0, 10).phi).toBe(MAX_PHI);
    expect(rotate(view, 0, -10).phi).toBe(MIN_PHI);
    expect(zoom(view, 0.0001).radius).toBe(MIN_RADIUS);
  });

  it("fits every point of the real layout in view, closer than a bounding sphere would", () => {
    const { nodes, edges } = graph();
    const layout = layoutOf(nodes, edges);
    const points = [...layout.positions.values()];
    const aspect = 1.6;
    const orbit = frameAll(points, aspect);
    const { right, up, forward } = basis(orbit);
    const from = eye(orbit);
    const tanV = Math.tan((FOV * Math.PI) / 360);
    let widest = 0;
    for (const point of points) {
      const d = { x: point.x - from.x, y: point.y - from.y, z: point.z - from.z };
      const depth = d.x * forward.x + d.y * forward.y + d.z * forward.z;
      expect(depth).toBeGreaterThan(0);
      const x = (d.x * right.x + d.y * right.y + d.z * right.z) / (depth * tanV * aspect);
      const y = (d.x * up.x + d.y * up.y + d.z * up.z) / (depth * tanV);
      // Inside the view, in normalised device coordinates, with the margin kept.
      expect(Math.abs(x)).toBeLessThanOrEqual(1 / 1.12 + 1e-9);
      expect(Math.abs(y)).toBeLessThanOrEqual(1 / 1.12 + 1e-9);
      widest = Math.max(widest, Math.abs(x), Math.abs(y));
    }
    // Tight: some point reaches the margin.
    expect(widest).toBeGreaterThan(0.85);
    expect(orbit.radius).toBeLessThan(fitDistance(layout.radius, aspect));
  });

  it("pans along the screen and flies between views the short way round", () => {
    const { right, up } = basis(view);
    expect(Math.hypot(right.x, right.y, right.z)).toBeCloseTo(1, 6);
    expect(Math.abs(right.y)).toBeLessThan(1e-9);
    expect(up.y).toBeGreaterThan(0);
    const moved = pan(view, 0.5, 0);
    expect(moved.target.x * right.x + moved.target.z * right.z).toBeLessThan(0);
    const a = { ...view, theta: 3.1 };
    const b = { ...view, theta: -3.1 };
    const half = interpolate(a, b, 0.5);
    expect(Math.abs(Math.cos(half.theta) + 1)).toBeLessThan(0.01);
    expect(interpolate(a, b, 1).radius).toBeCloseTo(b.radius, 6);
    expect(easeOut(0)).toBe(0);
    expect(easeOut(1)).toBe(1);
    expect(easeOut(0.5)).toBeGreaterThan(0.5);
  });
});

describe("the keyboard", () => {
  it("maps keys to actions and leaves browser shortcuts alone", () => {
    expect(keyAction({ key: "ArrowLeft" })).toEqual({ type: "move", direction: "left" });
    expect(keyAction({ key: "ArrowLeft", shiftKey: true })).toMatchObject({ type: "rotate" });
    expect(keyAction({ key: "+" })).toMatchObject({ type: "zoom" });
    expect(keyAction({ key: "Enter" })).toEqual({ type: "focus" });
    expect(keyAction({ key: "e" })).toEqual({ type: "expand" });
    expect(keyAction({ key: "C" })).toEqual({ type: "collapse" });
    expect(keyAction({ key: "r" })).toEqual({ type: "reset" });
    expect(keyAction({ key: "Escape" })).toEqual({ type: "clear" });
    expect(keyAction({ key: "r", ctrlKey: true })).toBeNull();
    expect(keyAction({ key: "a" })).toBeNull();
  });

  it("moves to the nearest node on screen in the direction pressed", () => {
    const points = [
      { id: "right-near", x: 140, y: 102, visible: true },
      { id: "right-far", x: 300, y: 100, visible: true },
      { id: "up", x: 100, y: 20, visible: true },
      { id: "hidden", x: 110, y: 100, visible: false },
      { id: "steep", x: 104, y: 180, visible: true },
    ];
    const from = { x: 100, y: 100 };
    expect(nearestInDirection(from, points, "right")).toBe("right-near");
    expect(nearestInDirection(from, points, "up")).toBe("up");
    expect(nearestInDirection(from, points, "down")).toBe("steep");
    expect(nearestInDirection(from, points, "left")).toBeNull();
  });
});

describe("filters on the whole build", () => {
  it("keep the API's meaning: node types keep nodes, the rest keep edges", () => {
    const { nodes, edges } = graph();
    const all = applyFilters(nodes, edges, DEFAULT_FILTERS);
    expect(all.nodes).toHaveLength(50);
    expect(all.edges).toHaveLength(97);

    // Illustrative relationships are left out; the records they join are not.
    const recorded = applyFilters(nodes, edges, { ...DEFAULT_FILTERS, includeIllustrative: false });
    expect(recorded.nodes).toHaveLength(50);
    expect(recorded.edges).toHaveLength(edges.filter((edge) => !edge.is_illustrative).length);
    expect(recorded.edges.every((edge) => !edge.is_illustrative)).toBe(true);

    const companies = applyFilters(nodes, edges, { ...DEFAULT_FILTERS, nodeTypes: ["company"] });
    expect(companies.nodes.every((node) => node.type === "company")).toBe(true);
    // Never an edge to a node that is not kept.
    const kept = new Set(companies.nodes.map((node) => node.id));
    expect(companies.edges.every((edge) => kept.has(edge.source) && kept.has(edge.target))).toBe(
      true,
    );

    const backed = applyFilters(nodes, edges, {
      ...DEFAULT_FILTERS,
      evidenceStatuses: ["evidence_backed"],
    });
    expect(backed.edges.every((edge) => edge.evidence_status === "evidence_backed")).toBe(true);
    expect(backed.edges.length).toBeGreaterThan(0);
  });
});

describe("labels", () => {
  const at = (id: string, x: number, y: number, priority: number, visible = true) => ({
    id,
    text: `Label ${id}`,
    x,
    y,
    visible,
    priority,
    depth: 1,
  });

  it("place the most important names first, on either side, never overlapping or outside", () => {
    const placed = placeLabels(
      [
        at("first", 200, 100, 1000),
        at("second", 200, 100, 500),
        at("third", 200, 100, 100),
        at("edge", 395, 300, 50),
        at("behind", 50, 50, 2000, false),
        at("outside", 100, 2, 40),
      ],
      400,
      400,
    );
    expect(placed.map((label) => [label.id, label.side])).toEqual([
      ["first", "right"],
      ["second", "left"],
      ["edge", "left"],
    ]);
  });

  it("start a name beyond its node's edge, and anchor it where the box starts", () => {
    const [right] = placeLabels([{ ...at("big", 100, 100, 500), radius: 20 }], 400, 400, {
      gap: 5,
    });
    expect(right).toMatchObject({ side: "right", x: 125, y: 100 });
    const [left] = placeLabels([{ ...at("big", 390, 100, 500), radius: 20 }], 400, 400, {
      gap: 5,
    });
    // On the left, `x` is the box's right edge.
    expect(left).toMatchObject({ side: "left", x: 365 });
  });

  it("keep a name off other nodes, unless it is the selection's and no side is free", () => {
    const obstacles = [
      { id: "a", x: 100, y: 100, r: 8 },
      { id: "right", x: 140, y: 100, r: 10 },
      { id: "left", x: 60, y: 100, r: 10 },
    ];
    expect(placeLabels([at("a", 100, 100, 500)], 400, 400, { obstacles })).toEqual([]);
    const [selected] = placeLabels([at("a", 100, 100, 1000)], 400, 400, { obstacles });
    expect(selected?.id).toBe("a");
    // Its own node never blocks it.
    const alone = placeLabels([at("a", 100, 100, 100)], 400, 400, {
      obstacles: [{ id: "a", x: 100, y: 100, r: 8 }],
    });
    expect(alone).toHaveLength(1);
  });

  it("move an essential name just above or below its node when both sides are taken", () => {
    // Two names already placed level with the node, one on each side of it.
    const blocks = [
      { ...at("blockR", 205, 200, 5000), sides: ["right" as const] },
      { ...at("blockL", 195, 200, 5000), sides: ["left" as const] },
    ];
    const placed = placeLabels(
      [...blocks, at("selected", 200, 200, 1000), at("ordinary", 200, 200, 500)],
      400,
      400,
    );
    const selected = placed.find((label) => label.id === "selected");
    expect(selected).toBeDefined();
    expect(Math.abs((selected?.y ?? 200) - 200)).toBe(16);
    expect(placed.some((label) => label.id === "ordinary")).toBe(false);
  });

  it("shift the strata's names inside the canvas instead of leaving them out", () => {
    const [stratum] = placeLabels(
      [{ ...at("stratum:industries", 20, 200, 10_000), sides: ["left"], clamp: true }],
      400,
      400,
    );
    expect(stratum?.side).toBe("left");
    // The box's right edge is far enough in for the whole name to fit.
    expect(stratum?.x).toBeGreaterThanOrEqual("Label stratum:industries".length * 6.4);
  });
});

describe("the scene", () => {
  const { nodes, edges } = graph();
  const positions = layoutOf(nodes, edges).positions;

  it("draws the graph's own marks: shape by type, pattern by evidence, size by kind only", () => {
    const scene = buildScene({
      nodes,
      edges,
      positions,
      focus: null,
      selection: null,
      hover: null,
      overlay: null,
    });
    expect(scene.nodes).toHaveLength(nodes.length);
    expect(scene.edges).toHaveLength(edges.length);
    const company = scene.nodes.find((node) => node.id === COMPANY);
    expect(company).toMatchObject({ shape: "dot", nature: "fictional", tone: "normal" });
    expect(company?.size).toBe(nodeSize("company"));
    const variable = scene.nodes.find((node) => node.id === VARIABLE);
    expect(variable?.shape).toBe("diamond");
    const patterns = new Set(scene.edges.map((edge) => edge.pattern));
    expect(patterns).toEqual(new Set(["solid", "dash", "dashdot"]));
    for (const edge of scene.edges) {
      const source = edges.find((item) => item.id === edge.id);
      expect(edge.economic).toBe(source?.category === "economic");
    }
  });

  it("emphasises a selection with what it touches and sets the rest back", () => {
    const scene = buildScene({
      nodes,
      edges,
      positions,
      focus: COMPANY,
      selection: { kind: "node", id: COMPANY },
      hover: null,
      overlay: null,
    });
    const touching = edges.filter((edge) => edge.source === COMPANY || edge.target === COMPANY);
    const emphasised = scene.edges.filter((edge) => edge.tone === "emphasis");
    expect(emphasised.map((edge) => edge.id).sort()).toEqual(
      touching.map((edge) => edge.id).sort(),
    );
    expect(scene.nodes.find((node) => node.id === COMPANY)).toMatchObject({
      selected: true,
      focus: true,
      tone: "emphasis",
    });
    expect(scene.nodes.some((node) => node.tone === "dimmed")).toBe(true);
    expect(activeSet({ kind: "edge", id: "missing" }, edges)).toBeNull();
  });

  it("orders labels: selection, pointer, focus, overlay, neighbours, then connectedness", () => {
    const scene = buildScene({
      nodes,
      edges,
      positions,
      focus: VARIABLE,
      selection: { kind: "node", id: COMPANY },
      hover: null,
      overlay: null,
    });
    const byId = new Map(scene.nodes.map((node) => [node.id, node]));
    const none = new Set<string>();
    const selected = byId.get(COMPANY);
    const focus = byId.get(VARIABLE);
    if (!selected || !focus) throw new Error("missing nodes");
    expect(labelPriority(selected, 1, null, none)).toBeGreaterThan(
      labelPriority(focus, 99, null, none),
    );
  });
});

describe("the scenario overlay", () => {
  const overlay = buildOverlay(
    universeFixtures.execution(),
    universeFixtures.pathways(),
    universeFixtures.results(),
  );

  it("maps pathway nodes to graph keys, and model internals to none", () => {
    expect(graphKey("change:var_brent_crude")).toBe("variable:var_brent_crude");
    expect(graphKey("airline_fuel_cost:variable:var_jet_fuel")).toBe("variable:var_jet_fuel");
    expect(graphKey("company:co_aerisca_airways")).toBe(COMPANY);
    expect(graphKey("airline_fuel_cost:output:fuel_cost_change")).toBeNull();
    expect(graphKey("line:revenue")).toBeNull();
  });

  it("marks what the execution changed, simulated, propagated, cited and left out", () => {
    expect(overlay.scenarioName).toBe("Oil, rupee and rates on Aerisca");
    expect(overlay.status).toBe("completed");
    expect(overlay.buildId).toBe(1);
    expect(overlay.entity?.key).toBe(COMPANY);
    expect(overlay.changes.map((change) => [change.key, change.value, change.unit])).toEqual([
      ["variable:var_brent_crude", "20", "%"],
      ["variable:var_usd_inr", "5", "%"],
      ["variable:var_rbi_repo_rate", "0.5", "percentage points"],
    ]);
    expect(overlay.nodes.get(VARIABLE)).toBe("changed");
    expect(overlay.nodes.get("variable:var_jet_fuel")).toBe("modelled");
    expect(overlay.nodes.get(COMPANY)).toBe("entity");
    expect(overlay.nodes.get("industry:ind_air_transport")).toBe("context");

    const roles = [...overlay.edges.values()].map((edge) => edge.role);
    expect(roles.filter((role) => role === "propagated")).toHaveLength(1);
    expect(roles.filter((role) => role === "cited")).toHaveLength(3);
    expect(roles.filter((role) => role === "unmodelled")).toHaveLength(11);
    const propagated = [...overlay.edges.values()].find((edge) => edge.role === "propagated");
    expect(propagated).toMatchObject({
      source: VARIABLE,
      target: "variable:var_jet_fuel",
      coefficient: "1",
      lagMonths: 1,
      model: { id: "airline_fuel_cost", version: "1.1.0" },
    });
    const graphEdges = new Set(universeFixtures.edges().items.map((edge) => edge.id));
    for (const id of overlay.edges.keys()) expect(graphEdges.has(id)).toBe(true);
    expect(EDGE_ROLE_LABEL.unmodelled).toContain("no included model");
  });

  it("keeps the simulated lines as stored, with the models and versions", () => {
    expect(overlay.currency).toBe("INR");
    expect(overlay.horizonMonths).toBe(12);
    expect(overlay.lines.find((line) => line.id === "operating_profit")).toMatchObject({
      baseline: "50000000",
      change: "-6325000",
      percentChange: "-12.65",
    });
    expect(overlay.models.map((model) => `${model.id} ${model.version}`)).toEqual([
      "airline_fuel_cost 1.1.0",
      "fx_exposure 1.0.0",
      "floating_rate_interest 1.0.0",
    ]);
    const keys = overlayNodeKeys(overlay);
    const graphNodes = new Set(universeFixtures.nodes().items.map((node) => node.id));
    for (const key of keys) expect(graphNodes.has(key)).toBe(true);
  });

  it("dims what the overlay does not touch and emphasises its modelled relationships", () => {
    const { nodes, edges } = graph();
    const positions = layoutOf(nodes, edges).positions;
    const scene = buildScene({
      nodes,
      edges,
      positions,
      focus: null,
      selection: null,
      hover: null,
      overlay,
    });
    const propagated = scene.edges.find((edge) => edge.role === "propagated");
    expect(propagated).toMatchObject({ tone: "emphasis" });
    expect(propagated?.width).toBeGreaterThan(3);
    expect(scene.edges.find((edge) => edge.role === "unmodelled")?.tone).toBe("dimmed");
    expect(scene.nodes.find((node) => node.id === COMPANY)).toMatchObject({
      role: "entity",
      tone: "emphasis",
    });
  });
});
