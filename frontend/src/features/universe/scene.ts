/**
 * What the renderer draws, decided without it: one record per node and per edge, with its
 * position, mark and tone. The renderer only turns these into pixels, so everything that
 * carries meaning is here, in plain data, and tested.
 *
 * The marks are the knowledge graph's own (`features/graph/encoding.ts`): shape by type,
 * outline for hollow kinds and for series or instruments without stored values, a halo for
 * fictional or sample records, a line pattern for the evidence status, weight for the
 * category, an arrowhead for direction. **Sky blue is emphasis only** — the selection and
 * what it touches, or an overlay's modelled pathway — and **dimming** sets the rest back.
 */
import { type GlyphShape, isHollow, NODE_TYPE_ENCODING } from "@/features/graph/encoding";
import type {
  EvidenceStatus,
  GraphEdgeSummary,
  GraphNodeSummary,
  GraphNodeType,
  NodeNature,
} from "@/types/api";
import type { Vec3 } from "./layout3d";
import type { OverlayEdgeRole, OverlayNodeRole } from "./overlay";

export type Pattern = "solid" | "dash" | "dashdot" | "dot";
export type Tone = "normal" | "emphasis" | "dimmed";

export const PATTERN_BY_STATUS: Record<EvidenceStatus, Pattern> = {
  evidence_backed: "solid",
  analyst_created: "dash",
  model_assumption: "dashdot",
  unverified: "dot",
};

/** World units per unit of the 2D glyph radius: node sizes follow the kind, nothing else. */
export const NODE_SCALE = 1.35;

export interface SceneNode {
  id: string;
  type: GraphNodeType;
  shape: GlyphShape;
  position: Vec3;
  /** Radius in world units. */
  size: number;
  hollow: boolean;
  nature: NodeNature;
  tone: Tone;
  role: OverlayNodeRole | null;
  selected: boolean;
  focus: boolean;
  name: string;
}

export interface SceneEdge {
  id: string;
  source: string;
  target: string;
  from: Vec3;
  to: Vec3;
  pattern: Pattern;
  /** Screen width in pixels. */
  width: number;
  directed: boolean;
  economic: boolean;
  tone: Tone;
  role: OverlayEdgeRole | null;
  selected: boolean;
}

export interface SceneSelection {
  kind: "node" | "edge";
  id: string;
}

export interface SceneOverlay {
  nodes: ReadonlyMap<string, OverlayNodeRole>;
  edges: ReadonlyMap<string, { role: OverlayEdgeRole }>;
}

export interface SceneInput {
  nodes: Iterable<GraphNodeSummary>;
  edges: Iterable<GraphEdgeSummary>;
  positions: ReadonlyMap<string, Vec3>;
  focus: string | null;
  selection: SceneSelection | null;
  hover: SceneSelection | null;
  overlay: SceneOverlay | null;
}

export interface SceneModel {
  nodes: SceneNode[];
  edges: SceneEdge[];
}

export function nodeSize(type: GraphNodeType): number {
  return NODE_TYPE_ENCODING[type].baseRadius * NODE_SCALE;
}

function edgeWidthPx(
  edge: GraphEdgeSummary,
  role: OverlayEdgeRole | null,
  active: boolean,
): number {
  const base = edge.category === "economic" ? 2 : 1.4;
  const emphasis = role === "propagated" ? 1.6 : role === "cited" ? 0.6 : 0;
  return base + emphasis + (active ? 0.6 : 0);
}

/**
 * The set of nodes and edges to emphasise for a selection (or the pointer): a node with its
 * edges and neighbours, or an edge with its two ends.
 */
export function activeSet(
  target: SceneSelection | null,
  edges: readonly GraphEdgeSummary[],
): { nodes: Set<string>; edges: Set<string> } | null {
  if (!target) return null;
  const nodes = new Set<string>();
  const active = new Set<string>();
  if (target.kind === "node") {
    nodes.add(target.id);
    for (const edge of edges) {
      if (edge.source === target.id || edge.target === target.id) {
        active.add(edge.id);
        nodes.add(edge.source);
        nodes.add(edge.target);
      }
    }
  } else {
    const edge = edges.find((item) => item.id === target.id);
    if (!edge) return null;
    active.add(edge.id);
    nodes.add(edge.source);
    nodes.add(edge.target);
  }
  return { nodes, edges: active };
}

export function buildScene(input: SceneInput): SceneModel {
  const nodeList = [...input.nodes].filter((node) => input.positions.has(node.id));
  const shown = new Set(nodeList.map((node) => node.id));
  const edgeList = [...input.edges].filter(
    (edge) => shown.has(edge.source) && shown.has(edge.target),
  );
  const target = input.hover ?? input.selection;
  const active = activeSet(target, edgeList);
  const overlay = input.overlay;

  const toneOfNode = (id: string): Tone => {
    if (active) return active.nodes.has(id) ? "emphasis" : "dimmed";
    if (overlay) return overlay.nodes.has(id) ? "emphasis" : "dimmed";
    return "normal";
  };
  const toneOfEdge = (id: string): Tone => {
    if (active) return active.edges.has(id) ? "emphasis" : "dimmed";
    if (overlay) {
      const role = overlay.edges.get(id)?.role;
      return role === "propagated" || role === "cited" ? "emphasis" : "dimmed";
    }
    return "normal";
  };

  const nodes: SceneNode[] = nodeList.map((node) => ({
    id: node.id,
    type: node.type,
    shape: NODE_TYPE_ENCODING[node.type].shape,
    position: input.positions.get(node.id) as Vec3,
    size: nodeSize(node.type),
    hollow: isHollow(node),
    nature: node.nature,
    tone: toneOfNode(node.id),
    role: overlay?.nodes.get(node.id) ?? null,
    selected: input.selection?.kind === "node" && input.selection.id === node.id,
    focus: input.focus === node.id,
    name: node.name,
  }));

  const edges: SceneEdge[] = edgeList.map((edge) => {
    const role = overlay?.edges.get(edge.id)?.role ?? null;
    const tone = toneOfEdge(edge.id);
    return {
      id: edge.id,
      source: edge.source,
      target: edge.target,
      from: input.positions.get(edge.source) as Vec3,
      to: input.positions.get(edge.target) as Vec3,
      pattern: PATTERN_BY_STATUS[edge.evidence_status],
      width: edgeWidthPx(edge, role, tone === "emphasis"),
      directed: edge.directed,
      economic: edge.category === "economic",
      tone,
      role,
      selected: input.selection?.kind === "edge" && input.selection.id === edge.id,
    };
  });
  return { nodes, edges };
}

/**
 * How much a node's name matters for labelling (see `labels.ts`): the selection, the node
 * under the pointer, the focus and an overlay's nodes first, then what the selection
 * touches, then the most connected (degree is data coverage, used here only to choose
 * which names to write when space runs out).
 */
export function labelPriority(
  node: SceneNode,
  degree: number,
  hover: SceneSelection | null,
  neighbours: ReadonlySet<string>,
): number {
  if (node.selected) return 1000;
  if (hover?.kind === "node" && hover.id === node.id) return 950;
  if (node.focus) return 900;
  if (node.role === "changed" || node.role === "entity") return 850;
  if (node.role) return 800;
  if (neighbours.has(node.id)) return 600;
  if (node.tone === "dimmed") return Math.min(degree, 50);
  return 100 + Math.min(degree, 400);
}
