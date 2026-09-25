/**
 * The universe's layout: strata by kind, and a seeded force layout within them.
 *
 * - **Height is kind** (`strata.ts`): fixed per node type, never computed.
 * - **Horizontal position is connection**: a force simulation in the horizontal plane pulls
 *   connected nodes together — also across strata, so a company sits under its industry and
 *   near its country — and pushes nodes of the same stratum apart.
 * - **Deterministic**: sorted inputs, a seeded random source and a fixed number of ticks, so
 *   the same data always gives the same picture (and stable tests).
 * - **Stable as the view grows**: nodes placed before keep their positions exactly; new
 *   nodes start beside the node that brought them in and settle around the fixed ones. A
 *   reader never loses what they were looking at when they expand a node.
 *
 * Pure: plain coordinates in, plain coordinates out, for any renderer.
 */
import {
  type Force,
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  forceX,
  forceY,
  type SimulationLinkDatum,
  type SimulationNodeDatum,
} from "d3-force";
import type { GraphNodeType } from "@/types/api";
import { heightOf, type StratumId, stratumOf } from "./strata";

export interface Vec3 {
  x: number;
  y: number;
  z: number;
}

export interface LayoutNode {
  id: string;
  type: GraphNodeType;
}

export interface LayoutEdge {
  id: string;
  source: string;
  target: string;
  category: "economic" | "structural";
}

export interface Layout3D {
  positions: Map<string, Vec3>;
  /** The centre of the laid-out nodes and the radius of a sphere that holds them. */
  center: Vec3;
  radius: number;
}

export interface LayoutOptions {
  seed?: number;
  /** Positions to keep: nodes found here do not move. */
  previous?: ReadonlyMap<string, Vec3>;
  /** For new nodes: the node that brought each into view (it starts beside it). */
  anchors?: ReadonlyMap<string, string>;
  /** Ticks of the simulation; by default fewer for large graphs. */
  iterations?: number;
}

interface SimNode extends SimulationNodeDatum {
  id: string;
  stratum: StratumId;
  height: number;
}

interface SimLink extends SimulationLinkDatum<SimNode> {
  category: LayoutEdge["category"];
}

const DEFAULT_SEED = 8;
const NEW_NODE_OFFSET = 26;

/** FNV-1a: a stable 32-bit hash of an id, for deterministic starting angles. */
export function hash(text: string): number {
  let value = 0x811c9dc5;
  for (let index = 0; index < text.length; index += 1) {
    value ^= text.charCodeAt(index);
    value = Math.imul(value, 0x01000193);
  }
  return value >>> 0;
}

/** A small seeded random source (mulberry32). */
export function seeded(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) | 0;
    let mixed = Math.imul(state ^ (state >>> 15), 1 | state);
    mixed = (mixed + Math.imul(mixed ^ (mixed >>> 7), 61 | mixed)) ^ mixed;
    return ((mixed ^ (mixed >>> 14)) >>> 0) / 4294967296;
  };
}

const byId = <T extends { id: string }>(a: T, b: T) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0);

/** A force that applies only to some of the simulation's nodes (repulsion per stratum). */
function within(inner: Force<SimNode, SimLink>, keep: (node: SimNode) => boolean) {
  const force = (alpha: number) => inner(alpha);
  force.initialize = (nodes: SimNode[], random: () => number) =>
    inner.initialize?.(nodes.filter(keep), random);
  return force as Force<SimNode, SimLink>;
}

function startingPoint(
  node: LayoutNode,
  spread: number,
  placed: ReadonlyMap<string, Vec3>,
  anchor: string | undefined,
  neighbours: ReadonlyMap<string, readonly string[]>,
): { x: number; z: number } {
  const turn = (hash(node.id) / 4294967296) * Math.PI * 2;
  const beside =
    (anchor ? placed.get(anchor) : undefined) ??
    (neighbours.get(node.id) ?? []).map((id) => placed.get(id)).find(Boolean);
  if (beside) {
    return {
      x: beside.x + Math.cos(turn) * NEW_NODE_OFFSET,
      z: beside.z + Math.sin(turn) * NEW_NODE_OFFSET,
    };
  }
  const reach = spread * Math.sqrt((hash(`${node.id}#r`) % 1000) / 1000);
  return { x: Math.cos(turn) * reach, z: Math.sin(turn) * reach };
}

export function layout3d(
  nodes: readonly LayoutNode[],
  edges: readonly LayoutEdge[],
  options: LayoutOptions = {},
): Layout3D {
  const sorted = [...nodes].sort(byId);
  const known = new Set(sorted.map((node) => node.id));
  const links = edges
    .filter(
      (edge) => edge.source !== edge.target && known.has(edge.source) && known.has(edge.target),
    )
    .sort(byId);
  const previous = options.previous ?? new Map<string, Vec3>();
  const neighbours = new Map<string, string[]>();
  for (const edge of links) {
    for (const [from, to] of [
      [edge.source, edge.target],
      [edge.target, edge.source],
    ] as const) {
      const list = neighbours.get(from);
      if (list) list.push(to);
      else neighbours.set(from, [to]);
    }
  }
  const spread = 34 * Math.sqrt(Math.max(sorted.length, 1));
  let moving = 0;
  const simNodes: SimNode[] = sorted.map((node) => {
    const base = { id: node.id, stratum: stratumOf(node.type).id, height: heightOf(node.type) };
    const kept = previous.get(node.id);
    if (kept) return { ...base, x: kept.x, y: kept.z, fx: kept.x, fy: kept.z };
    moving += 1;
    const start = startingPoint(node, spread, previous, options.anchors?.get(node.id), neighbours);
    return { ...base, x: start.x, y: start.z };
  });

  if (moving > 0) {
    const firstLayout = moving === simNodes.length;
    // Fewer ticks for larger views: each tick costs O(n log n), and the layout runs on the
    // main thread (measured in docs/universe/performance.md).
    const size = sorted.length;
    const iterations =
      options.iterations ??
      (firstLayout ? (size > 1000 ? 120 : size > 300 ? 180 : 300) : size > 300 ? 90 : 150);
    const simulation = forceSimulation<SimNode, SimLink>(simNodes)
      .randomSource(seeded(options.seed ?? DEFAULT_SEED))
      .alpha(firstLayout ? 1 : 0.5)
      .stop();
    simulation.force(
      "link",
      forceLink<SimNode, SimLink>(
        links.map((edge) => ({
          source: edge.source,
          target: edge.target,
          category: edge.category,
        })),
      )
        .id((node) => node.id)
        .distance((link) => (link.category === "economic" ? 58 : 44)),
    );
    const strata = new Set(simNodes.map((node) => node.stratum));
    for (const stratum of strata) {
      simulation.force(
        `charge-${stratum}`,
        within(
          forceManyBody<SimNode>().strength(-170).distanceMax(420),
          (node) => node.stratum === stratum,
        ),
      );
    }
    simulation.force("collide", forceCollide<SimNode>(15));
    simulation.force("x", forceX<SimNode>(0).strength(0.025));
    simulation.force("z", forceY<SimNode>(0).strength(0.025));
    simulation.tick(iterations);
  }

  const positions = new Map<string, Vec3>();
  for (const node of simNodes) {
    positions.set(node.id, { x: node.x ?? 0, y: node.height, z: node.y ?? 0 });
  }
  return { positions, ...enclosing(positions) };
}

/** The centre and radius of a sphere holding every position (for framing the camera). */
export function enclosing(positions: ReadonlyMap<string, Vec3>): { center: Vec3; radius: number } {
  if (positions.size === 0) return { center: { x: 0, y: 0, z: 0 }, radius: 100 };
  let x = 0;
  let y = 0;
  let z = 0;
  for (const point of positions.values()) {
    x += point.x;
    y += point.y;
    z += point.z;
  }
  const center = { x: x / positions.size, y: y / positions.size, z: z / positions.size };
  let radius = 0;
  for (const point of positions.values()) {
    radius = Math.max(
      radius,
      Math.hypot(point.x - center.x, point.y - center.y, point.z - center.z),
    );
  }
  return { center, radius: Math.max(radius + 20, 60) };
}
