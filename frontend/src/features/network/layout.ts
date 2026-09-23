/**
 * Network layout: layered ordering refined by a force simulation, computed once.
 *
 * - Layered: kinds sit in columns left → right — economic variables (drivers),
 *   industries, companies, countries — mirroring how an assumed effect travels through
 *   the model. Within each column, a barycentre heuristic orders nodes to minimise
 *   edge crossings; a short force simulation then relaxes the spacing.
 * - Deterministic: sorted inputs and a seeded random source mean the same data always
 *   produces the same picture (and stable tests).
 * - Static: it runs synchronously (a few ms for this dataset) instead of animating
 *   forever; filters hide elements without re-running it, so the mental map stays put.
 *
 * The function is pure, so it can move into a Web Worker when graphs grow (Phase 3),
 * and its output (plain coordinates) is renderer-agnostic — the same positions can feed
 * the Three.js scene planned for Phase 8.
 */
import {
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  forceX,
  forceY,
  type SimulationLinkDatum,
  type SimulationNodeDatum,
} from "d3-force";
import type { EntityKind } from "@/types/api";

export interface LayoutNodeInput {
  id: string;
  kind: EntityKind;
  radius: number;
}

export interface LayoutEdgeInput {
  source: string;
  target: string;
  category: "economic" | "structural";
}

export interface Point {
  x: number;
  y: number;
}

export interface Bounds {
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
}

export interface Layout {
  positions: Map<string, Point>;
  bounds: Bounds;
  /** "horizontal": kinds in columns (left → right). "vertical": kinds in rows (top → bottom). */
  orientation: "horizontal" | "vertical";
}

export interface LayoutOptions {
  spread?: number;
  iterations?: number;
  seed?: number;
}

interface SimNode extends SimulationNodeDatum {
  id: string;
  kind: EntityKind;
  radius: number;
}

interface SimLink extends SimulationLinkDatum<SimNode> {
  category: LayoutEdgeInput["category"];
}

/** Column (horizontal position) per kind, as a fraction of `spread`. */
const COLUMN: Record<EntityKind, number> = {
  economic_variable: -1,
  industry: -0.34,
  company: 0.34,
  country: 1,
};

const COLUMN_ORDER: readonly EntityKind[] = ["economic_variable", "industry", "company", "country"];

const compareIds = (a: string, b: string) => (a < b ? -1 : a > b ? 1 : 0);

/**
 * Edges in a canonical order. The simulation applies link forces in input order, so
 * without this the same graph delivered in a different order (e.g. by a different
 * database) would settle into a slightly different picture.
 */
function canonicalEdges(edges: readonly LayoutEdgeInput[]): LayoutEdgeInput[] {
  return [...edges].sort(
    (a, b) =>
      compareIds(a.source, b.source) ||
      compareIds(a.target, b.target) ||
      compareIds(a.category, b.category),
  );
}

/**
 * Initial vertical order per column using the barycentre heuristic from layered graph
 * drawing (Sugiyama et al.): each node moves towards the average position of its
 * neighbours, sweeping the columns back and forth. This removes most edge crossings
 * before the force simulation refines spacing.
 */
export function barycentricOrder(
  nodes: readonly LayoutNodeInput[],
  edges: readonly LayoutEdgeInput[],
  sweeps = 12,
): Map<string, number> {
  const columns = COLUMN_ORDER.map((kind) =>
    nodes
      .filter((node) => node.kind === kind)
      .map((node) => node.id)
      .sort(),
  );
  const neighbours = new Map<string, string[]>(nodes.map((node) => [node.id, []]));
  for (const edge of canonicalEdges(edges)) {
    neighbours.get(edge.source)?.push(edge.target);
    neighbours.get(edge.target)?.push(edge.source);
  }
  // Positions are normalised to [0, 1] within each column so columns of different
  // lengths can be compared.
  const position = new Map<string, number>();
  const assign = (column: string[]) =>
    column.forEach((id, index) => {
      position.set(id, column.length > 1 ? index / (column.length - 1) : 0.5);
    });
  columns.forEach(assign);

  const sweepOrder = [...columns.keys(), ...[...columns.keys()].reverse()];
  for (let sweep = 0; sweep < sweeps; sweep += 1) {
    for (const columnIndex of sweepOrder) {
      const column = columns[columnIndex];
      if (!column || column.length < 2) continue;
      const barycentre = new Map(
        column.map((id) => {
          const around = (neighbours.get(id) ?? [])
            .map((other) => position.get(other))
            .filter((value): value is number => value !== undefined);
          const current = position.get(id) ?? 0.5;
          return [
            id,
            around.length ? around.reduce((sum, value) => sum + value, 0) / around.length : current,
          ];
        }),
      );
      column.sort(
        (a, b) => (barycentre.get(a) ?? 0) - (barycentre.get(b) ?? 0) || (a < b ? -1 : 1),
      );
      assign(column);
    }
  }
  return position;
}

/** Small, fast, seedable PRNG (mulberry32). */
export function seededRandom(seed: number): () => number {
  let state = seed | 0;
  return () => {
    state = (state + 0x6d2b79f5) | 0;
    let t = Math.imul(state ^ (state >>> 15), 1 | state);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function computeLayout(
  nodes: readonly LayoutNodeInput[],
  edges: readonly LayoutEdgeInput[],
  { spread = 360, iterations = 300, seed = 11 }: LayoutOptions = {},
): Layout {
  const random = seededRandom(seed);
  const order = barycentricOrder(nodes, edges);
  const columnSize = new Map<EntityKind, number>();
  for (const node of nodes) columnSize.set(node.kind, (columnSize.get(node.kind) ?? 0) + 1);
  const rowGap = 44;
  const targetY = (node: LayoutNodeInput) => {
    const size = columnSize.get(node.kind) ?? 1;
    return ((order.get(node.id) ?? 0.5) - 0.5) * (size - 1) * rowGap;
  };

  const simNodes: SimNode[] = [...nodes]
    .sort((a, b) => compareIds(a.id, b.id))
    .map((node) => ({ ...node, x: COLUMN[node.kind] * spread, y: targetY(node) }));
  const ids = new Set(simNodes.map((node) => node.id));
  const simLinks: SimLink[] = canonicalEdges(edges)
    .filter((edge) => ids.has(edge.source) && ids.has(edge.target))
    .map((edge) => ({ source: edge.source, target: edge.target, category: edge.category }));
  const targets = new Map(simNodes.map((node) => [node.id, targetY(node)]));

  // The layered positions do most of the work; forces only relax spacing, so columns
  // stay readable and links pull related entities gently towards each other.
  const simulation = forceSimulation<SimNode, SimLink>(simNodes)
    .randomSource(random)
    .alpha(0.6)
    .force(
      "link",
      forceLink<SimNode, SimLink>(simLinks)
        .id((node) => node.id)
        .distance((link) => (link.category === "structural" ? 150 : 170))
        .strength((link) => (link.category === "structural" ? 0.02 : 0.05)),
    )
    .force("charge", forceManyBody<SimNode>().strength(-90).distanceMax(220))
    .force("collide", forceCollide<SimNode>((node) => node.radius + 13).strength(1))
    .force("x", forceX<SimNode>((node) => COLUMN[node.kind] * spread).strength(0.6))
    .force("y", forceY<SimNode>((node) => targets.get(node.id) ?? 0).strength(0.22))
    .stop();

  for (let i = 0; i < iterations; i += 1) simulation.tick();

  const positions = new Map<string, Point>();
  const bounds: Bounds = { minX: Infinity, minY: Infinity, maxX: -Infinity, maxY: -Infinity };
  for (const node of simNodes) {
    const x = node.x ?? 0;
    const y = node.y ?? 0;
    positions.set(node.id, { x, y });
    bounds.minX = Math.min(bounds.minX, x - node.radius);
    bounds.minY = Math.min(bounds.minY, y - node.radius);
    bounds.maxX = Math.max(bounds.maxX, x + node.radius);
    bounds.maxY = Math.max(bounds.maxY, y + node.radius);
  }
  if (positions.size === 0) {
    return { positions, bounds: { minX: 0, minY: 0, maxX: 0, maxY: 0 }, orientation: "horizontal" };
  }
  return { positions, bounds, orientation: "horizontal" };
}

/**
 * The same layout rotated a quarter turn: columns become rows. Used on portrait screens,
 * where a left-to-right flow would have to shrink until nothing is legible.
 */
export function transposeLayout(layout: Layout, layerSpacing = 0.62): Layout {
  // `layerSpacing` < 1 brings the rows closer together: a phone is tall, but not as
  // tall as the layout is wide.
  const positions = new Map<string, Point>();
  for (const [id, point] of layout.positions) {
    positions.set(id, { x: point.y, y: point.x * layerSpacing });
  }
  const { minX, minY, maxX, maxY } = layout.bounds;
  return {
    positions,
    bounds: { minX: minY, minY: minX * layerSpacing, maxX: maxY, maxY: maxX * layerSpacing },
    orientation: layout.orientation === "horizontal" ? "vertical" : "horizontal",
  };
}
