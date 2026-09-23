/**
 * Deterministic layouts for the explorer — no force simulation.
 *
 * **Radial tree** (explore mode): the focus sits at the centre and every other node on a
 * ring whose number is its hops from the focus, so distance from the centre always means
 * the same thing. Each node owns a wedge of the circle proportional to the number of
 * leaves below it in the breadth-first tree, and sits in the middle of its wedge; children
 * share their parent's wedge, so a subtree stays together and edges rarely cross. Ring
 * radii grow until neighbours on a ring are at least `minArc` apart. Cost: O(n log n).
 *
 * **Columns** (paths): position along the path left to right, alternatives stacked.
 *
 * The same input always gives the same picture, which keeps expansion stable: new nodes
 * take new wedges and the rest of the tree moves only as much as it must.
 */
import type { GraphNodeSummary } from "@/types/api";
import { nodeRadius } from "./encoding";
import { compareNodes, type GraphView, type ViewNode } from "./view";

export interface Point {
  x: number;
  y: number;
}

export interface Bounds {
  minX: number;
  maxX: number;
  minY: number;
  maxY: number;
}

export interface GraphLayout {
  kind: "radial" | "columns";
  positions: Map<string, Point>;
  /**
   * Label placement per node: an angle (radians) to write the label along, pointing away
   * from the centre, or null for a horizontal label.
   */
  labelAngle: Map<string, number | null>;
  /** Ring radii by hops (radial only), for the faint guide circles. */
  rings: number[];
  bounds: Bounds;
}

export interface RadialOptions {
  firstRing?: number;
  ringGap?: number;
  minArc?: number;
  /** Rings with more nodes than this get labels written along the radius. */
  horizontalLabelLimit?: number;
}

const TAU = Math.PI * 2;
const START = -Math.PI / 2;

export function boundsOf(
  positions: ReadonlyMap<string, Point>,
  nodes: ReadonlyMap<string, GraphNodeSummary>,
): Bounds {
  let minX = Number.POSITIVE_INFINITY;
  let maxX = Number.NEGATIVE_INFINITY;
  let minY = Number.POSITIVE_INFINITY;
  let maxY = Number.NEGATIVE_INFINITY;
  for (const [id, point] of positions) {
    const node = nodes.get(id);
    const r = node ? nodeRadius(node.type, node.degree) : 6;
    minX = Math.min(minX, point.x - r);
    maxX = Math.max(maxX, point.x + r);
    minY = Math.min(minY, point.y - r);
    maxY = Math.max(maxY, point.y + r);
  }
  if (!Number.isFinite(minX)) return { minX: -1, maxX: 1, minY: -1, maxY: 1 };
  return { minX, maxX, minY, maxY };
}

/** Smallest angular gap between consecutive angles on a circle (2π for one angle). */
export function smallestGap(angles: readonly number[]): number {
  if (angles.length < 2) return TAU;
  const sorted = [...angles].sort((a, b) => a - b);
  let gap = TAU - ((sorted[sorted.length - 1] as number) - (sorted[0] as number));
  for (let index = 1; index < sorted.length; index += 1) {
    gap = Math.min(gap, (sorted[index] as number) - (sorted[index - 1] as number));
  }
  return Math.max(gap, 1e-6);
}

export function radialLayout(view: GraphView, options: RadialOptions = {}): GraphLayout {
  const { firstRing = 130, ringGap = 110, minArc = 24, horizontalLabelLimit = 10 } = options;
  const nodes = [...view.nodes.values()];
  const children = new Map<string, ViewNode[]>();
  const orphans: ViewNode[] = [];
  for (const node of nodes) {
    if (node.id === view.focus) continue;
    if (node.parent && view.nodes.has(node.parent)) {
      const list = children.get(node.parent);
      if (list) list.push(node);
      else children.set(node.parent, [node]);
    } else {
      orphans.push(node);
    }
  }
  for (const list of children.values()) list.sort(compareNodes);
  orphans.sort(compareNodes);

  // Leaves below each node (post-order; the tree is shallow, so recursion is safe).
  const leaves = new Map<string, number>();
  const countLeaves = (id: string): number => {
    const list = children.get(id) ?? [];
    const total = list.length ? list.reduce((sum, child) => sum + countLeaves(child.id), 0) : 1;
    leaves.set(id, total);
    return total;
  };
  countLeaves(view.focus);

  const angle = new Map<string, number>();
  const assign = (id: string, from: number, to: number) => {
    angle.set(id, (from + to) / 2);
    const list = children.get(id) ?? [];
    const total = list.reduce((sum, child) => sum + (leaves.get(child.id) ?? 1), 0);
    let cursor = from;
    for (const child of list) {
      const share = ((to - from) * (leaves.get(child.id) ?? 1)) / Math.max(total, 1);
      assign(child.id, cursor, cursor + share);
      cursor += share;
    }
  };
  assign(view.focus, START, START + TAU);

  // Nodes the tree could not reach share one outer ring, evenly spaced.
  const orphanIds = new Set(orphans.map((node) => node.id));
  const ringOf = (node: ViewNode) => (orphanIds.has(node.id) ? view.maxHops + 1 : node.hops);
  orphans.forEach((node, index) => {
    angle.set(node.id, START + (TAU * (index + 0.5)) / orphans.length);
  });

  // Ring radii: at least one gap further out than the previous ring, and wide enough that
  // neighbours on the ring are `minArc` apart.
  const byRing = new Map<number, number[]>();
  for (const node of nodes) {
    if (node.id === view.focus) continue;
    const hops = ringOf(node);
    const list = byRing.get(hops);
    const value = angle.get(node.id) ?? 0;
    if (list) list.push(value);
    else byRing.set(hops, [value]);
  }
  const deepest = Math.max(0, ...byRing.keys());
  const rings = [0];
  for (let hops = 1; hops <= deepest; hops += 1) {
    const previous = rings[hops - 1] as number;
    const floor = hops === 1 ? firstRing : previous + ringGap;
    const angles = byRing.get(hops) ?? [];
    rings.push(Math.max(floor, angles.length ? minArc / smallestGap(angles) : 0));
  }

  const positions = new Map<string, Point>();
  const labelAngle = new Map<string, number | null>();
  for (const node of nodes) {
    if (node.id === view.focus) {
      positions.set(node.id, { x: 0, y: 0 });
      labelAngle.set(node.id, null);
      continue;
    }
    const hops = ringOf(node);
    const theta = angle.get(node.id) ?? 0;
    const radius = rings[Math.min(hops, rings.length - 1)] ?? firstRing;
    positions.set(node.id, {
      x: Math.round(Math.cos(theta) * radius * 10) / 10,
      y: Math.round(Math.sin(theta) * radius * 10) / 10,
    });
    labelAngle.set(node.id, (byRing.get(hops)?.length ?? 0) > horizontalLabelLimit ? theta : null);
  }

  return {
    kind: "radial",
    positions,
    labelAngle,
    rings,
    bounds: boundsOf(positions, view.nodes),
  };
}

export function columnLayout(
  view: GraphView,
  { columnGap = 210, rowGap = 78 }: { columnGap?: number; rowGap?: number } = {},
): GraphLayout {
  const columns = new Map<number, string[]>();
  for (const id of view.order) {
    const node = view.nodes.get(id);
    if (!node) continue;
    const list = columns.get(node.hops);
    if (list) list.push(id);
    else columns.set(node.hops, [id]);
  }
  const positions = new Map<string, Point>();
  const labelAngle = new Map<string, number | null>();
  for (const [hops, ids] of columns) {
    ids.forEach((id, row) => {
      positions.set(id, { x: hops * columnGap, y: (row - (ids.length - 1) / 2) * rowGap });
      labelAngle.set(id, null);
    });
  }
  return {
    kind: "columns",
    positions,
    labelAngle,
    rings: [],
    bounds: boundsOf(positions, view.nodes),
  };
}
