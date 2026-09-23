/**
 * The explorer's visible graph — always derived, never edited in place.
 *
 * The explorer remembers only what the reader asked for (a focus, a depth, the nodes they
 * expanded, in order) and the server's answers. `buildView` merges those answers:
 *
 * - nodes and edges are keyed by their stable IDs, so a node reached twice appears once;
 * - an edge is shown only when both of its ends are shown;
 * - at most `limit` nodes are shown, and the ones left out are counted, never dropped
 *   silently;
 * - expansions apply in the order they were made; one whose node is no longer shown
 *   (after a filter change, say) is skipped and reported as such;
 * - a breadth-first pass from the focus over the shown edges gives each node its hops
 *   from the focus and a parent, which the radial layout uses.
 *
 * No financial logic lives here: which relationships exist, and what they mean, is decided
 * by the backend. This module only combines answers.
 */
import type {
  GraphEdgeSummary,
  GraphNeighborhood,
  GraphNodeSummary,
  GraphPath,
  GraphPaths,
} from "@/types/api";
import { typeRank } from "./encoding";

export interface ViewNode extends GraphNodeSummary {
  /** Hops from the focus over the shown edges (direction ignored). */
  hops: number;
  /** The node it hangs from in the layout tree; null for the focus and unreached nodes. */
  parent: string | null;
  /** The node whose neighbourhood first brought it into view (new nodes grow from it). */
  origin: string;
  /** Shown edges that touch it (compare with `degree`, which counts all its edges). */
  shownDegree: number;
}

export type Answer<T> =
  | { status: "pending" }
  | { status: "ready"; data: T }
  | { status: "failed"; error: unknown };

export type ExpansionOutcome =
  | { id: string; status: "applied"; added: number; hidden: number; truncated: boolean }
  | { id: string; status: "pending" }
  | { id: string; status: "failed"; error: unknown }
  | { id: string; status: "skipped" };

export interface GraphView {
  focus: string;
  nodes: Map<string, ViewNode>;
  edges: Map<string, GraphEdgeSummary>;
  /** Node IDs in the order they entered the view (deterministic). */
  order: string[];
  /** Nodes the server returned that the visible-node limit left out. */
  hiddenByLimit: number;
  /** The focus neighbourhood itself was cut short by its node limit on the server. */
  focusTruncated: boolean;
  unexploredByType: Record<string, number>;
  expansions: ExpansionOutcome[];
  maxHops: number;
}

/** Deterministic neighbour order: by type, then name, then key. */
export function compareNodes(a: GraphNodeSummary, b: GraphNodeSummary): number {
  return (
    typeRank(a.type) - typeRank(b.type) ||
    a.name.localeCompare(b.name, "en", { sensitivity: "base" }) ||
    (a.id < b.id ? -1 : a.id > b.id ? 1 : 0)
  );
}

interface Draft {
  nodes: Map<string, GraphNodeSummary & { origin: string }>;
  order: string[];
  edges: Map<string, GraphEdgeSummary>;
}

function addNode(draft: Draft, node: GraphNodeSummary, origin: string) {
  draft.nodes.set(node.id, { ...stripDepth(node), origin });
  draft.order.push(node.id);
}

/** Neighbourhood nodes carry `depth` (hops from *their* centre); the view recomputes hops. */
function stripDepth(node: GraphNodeSummary & { depth?: number }): GraphNodeSummary {
  const { depth: _depth, ...summary } = node;
  return summary;
}

function addEdges(draft: Draft, edges: readonly GraphEdgeSummary[]) {
  for (const edge of edges) {
    if (draft.nodes.has(edge.source) && draft.nodes.has(edge.target)) {
      draft.edges.set(edge.id, edge);
    }
  }
}

/**
 * Breadth-first search from the focus over the shown edges, ignoring direction. Returns
 * hops and the layout parent of every reached node; neighbours are visited in a fixed
 * order, so the same view always yields the same tree.
 */
export function spanningTree(
  focus: string,
  nodes: ReadonlyMap<string, GraphNodeSummary>,
  edges: Iterable<GraphEdgeSummary>,
): { hops: Map<string, number>; parent: Map<string, string | null> } {
  const adjacency = new Map<string, string[]>();
  for (const edge of edges) {
    for (const [a, b] of [
      [edge.source, edge.target],
      [edge.target, edge.source],
    ] as const) {
      if (!nodes.has(a) || !nodes.has(b)) continue;
      const list = adjacency.get(a);
      if (list) list.push(b);
      else adjacency.set(a, [b]);
    }
  }
  const hops = new Map<string, number>();
  const parent = new Map<string, string | null>();
  if (!nodes.has(focus)) return { hops, parent };
  hops.set(focus, 0);
  parent.set(focus, null);
  const queue = [focus];
  for (let head = 0; head < queue.length; head += 1) {
    const current = queue[head] as string;
    const next = [...new Set(adjacency.get(current) ?? [])]
      .filter((id) => !hops.has(id))
      .map((id) => nodes.get(id) as GraphNodeSummary)
      .sort(compareNodes);
    for (const node of next) {
      hops.set(node.id, (hops.get(current) ?? 0) + 1);
      parent.set(node.id, current);
      queue.push(node.id);
    }
  }
  return { hops, parent };
}

function finish(
  focus: string,
  draft: Draft,
  rest: Omit<GraphView, "focus" | "nodes" | "edges" | "order" | "maxHops">,
): GraphView {
  const { hops, parent } = spanningTree(focus, draft.nodes, draft.edges.values());
  const shownDegree = new Map<string, number>();
  for (const edge of draft.edges.values()) {
    shownDegree.set(edge.source, (shownDegree.get(edge.source) ?? 0) + 1);
    shownDegree.set(edge.target, (shownDegree.get(edge.target) ?? 0) + 1);
  }
  let maxHops = 0;
  for (const value of hops.values()) maxHops = Math.max(maxHops, value);
  const nodes = new Map<string, ViewNode>();
  for (const id of draft.order) {
    const node = draft.nodes.get(id);
    if (!node) continue;
    nodes.set(id, {
      ...node,
      // A node the search cannot reach (it should not happen) sits one ring further out.
      hops: hops.get(id) ?? maxHops + 1,
      parent: parent.get(id) ?? null,
      shownDegree: shownDegree.get(id) ?? 0,
    });
  }
  return { focus, nodes, edges: draft.edges, order: draft.order, maxHops, ...rest };
}

/**
 * Merge a focus neighbourhood and the expansions made from it into one view of at most
 * `limit` nodes.
 */
export function buildView(
  focusAnswer: GraphNeighborhood,
  expansions: readonly { id: string; answer: Answer<GraphNeighborhood> }[],
  limit: number,
): GraphView {
  const focus = focusAnswer.center.id;
  const draft: Draft = { nodes: new Map(), order: [], edges: new Map() };
  let hiddenByLimit = 0;

  for (const node of focusAnswer.nodes) {
    if (draft.nodes.has(node.id)) continue;
    if (draft.nodes.size >= limit) {
      hiddenByLimit += 1;
      continue;
    }
    addNode(draft, node, focus);
  }
  addEdges(draft, focusAnswer.edges);

  const outcomes: ExpansionOutcome[] = [];
  for (const { id, answer } of expansions) {
    if (!draft.nodes.has(id)) {
      outcomes.push({ id, status: "skipped" });
      continue;
    }
    if (answer.status !== "ready") {
      outcomes.push(
        answer.status === "pending"
          ? { id, status: "pending" }
          : { id, status: "failed", error: answer.error },
      );
      continue;
    }
    let added = 0;
    let hidden = 0;
    for (const node of answer.data.nodes) {
      if (draft.nodes.has(node.id)) continue;
      if (draft.nodes.size >= limit) {
        hidden += 1;
        continue;
      }
      addNode(draft, node, id);
      added += 1;
    }
    addEdges(draft, answer.data.edges);
    hiddenByLimit += hidden;
    outcomes.push({ id, status: "applied", added, hidden, truncated: answer.data.truncated });
  }

  return finish(focus, draft, {
    hiddenByLimit,
    focusTruncated: focusAnswer.truncated,
    unexploredByType: focusAnswer.unexplored_by_type,
    expansions: outcomes,
  });
}

/**
 * The union of the shortest paths found between two nodes, as a view: each node's `hops`
 * is its position along the paths (all shortest paths have the same length, so a node
 * has one position whichever path it is on).
 */
export function buildPathView(answer: GraphPaths): GraphView {
  const summaries = new Map(answer.nodes.map((node) => [node.id, node]));
  const edges = new Map(answer.edges.map((edge) => [edge.id, edge]));
  const draft: Draft = { nodes: new Map(), order: [], edges: new Map() };
  const position = new Map<string, number>();
  const parent = new Map<string, string | null>();

  const include = (path: GraphPath) => {
    path.nodes.forEach((id, index) => {
      const summary = summaries.get(id);
      if (!summary) return;
      if (!draft.nodes.has(id)) {
        addNode(draft, summary, path.nodes[0] ?? id);
        position.set(id, index);
        parent.set(id, index === 0 ? null : (path.nodes[index - 1] ?? null));
      }
    });
    for (const id of path.edges) {
      const edge = edges.get(id);
      if (edge) draft.edges.set(id, edge);
    }
  };
  if (answer.paths.length === 0) {
    addNode(draft, answer.source, answer.source.id);
    position.set(answer.source.id, 0);
    if (answer.target.id !== answer.source.id) {
      addNode(draft, answer.target, answer.target.id);
      position.set(answer.target.id, 1);
    }
  }
  for (const path of answer.paths) include(path);

  const shownDegree = new Map<string, number>();
  for (const edge of draft.edges.values()) {
    shownDegree.set(edge.source, (shownDegree.get(edge.source) ?? 0) + 1);
    shownDegree.set(edge.target, (shownDegree.get(edge.target) ?? 0) + 1);
  }
  const nodes = new Map<string, ViewNode>();
  let maxHops = 0;
  for (const id of draft.order) {
    const node = draft.nodes.get(id);
    if (!node) continue;
    const hops = position.get(id) ?? 0;
    maxHops = Math.max(maxHops, hops);
    nodes.set(id, {
      ...node,
      hops,
      parent: parent.get(id) ?? null,
      shownDegree: shownDegree.get(id) ?? 0,
    });
  }
  return {
    focus: answer.source.id,
    nodes,
    edges: draft.edges,
    order: draft.order,
    maxHops,
    hiddenByLimit: 0,
    focusTruncated: false,
    unexploredByType: {},
    expansions: [],
  };
}

/** The edges of a view that touch `id`, and the nodes at their other ends. */
export function incidentTo(view: GraphView, id: string) {
  const nodeIds = new Set<string>([id]);
  const edgeIds = new Set<string>();
  for (const edge of view.edges.values()) {
    if (edge.source === id || edge.target === id) {
      edgeIds.add(edge.id);
      nodeIds.add(edge.source);
      nodeIds.add(edge.target);
    }
  }
  return { nodeIds, edgeIds };
}
