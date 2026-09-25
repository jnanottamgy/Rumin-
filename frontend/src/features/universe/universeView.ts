/**
 * The whole graph as a `GraphView` — the shape the explorer's panels, table and legend
 * already read — with the explorer's filters applied in the browser (the whole build is
 * loaded only when it is small; see `useWholeGraph`).
 */
import type { ExplorerFilters } from "@/features/graph/useGraphExplorer";
import { compareNodes, type GraphView, spanningTree, type ViewNode } from "@/features/graph/view";
import type { GraphEdgeSummary, GraphNodeSummary } from "@/types/api";

/**
 * The explorer's filters, applied to a loaded graph with the API's meaning: node types keep
 * nodes; relationship types, evidence statuses and *Include illustrative* keep edges (an
 * illustrative edge is left out, the records it joins are not). Direction is relative to a
 * focus, so it does not apply to the whole build.
 */
export function applyFilters(
  nodes: readonly GraphNodeSummary[],
  edges: readonly GraphEdgeSummary[],
  filters: ExplorerFilters,
): { nodes: GraphNodeSummary[]; edges: GraphEdgeSummary[] } {
  const types = new Set(filters.nodeTypes);
  const kept = nodes.filter((node) => types.size === 0 || types.has(node.type));
  const ids = new Set(kept.map((node) => node.id));
  const edgeTypes = new Set(filters.edgeTypes);
  const statuses = new Set(filters.evidenceStatuses);
  const keptEdges = edges.filter(
    (edge) =>
      ids.has(edge.source) &&
      ids.has(edge.target) &&
      (edgeTypes.size === 0 || edgeTypes.has(edge.type)) &&
      (statuses.size === 0 || statuses.has(edge.evidence_status)) &&
      (filters.includeIllustrative || !edge.is_illustrative),
  );
  return { nodes: kept, edges: keptEdges };
}

/** The node with the most edges shown (ties: the explorer's usual order). */
export function mostConnected(
  nodes: readonly GraphNodeSummary[],
  edges: readonly GraphEdgeSummary[],
): string | null {
  const degree = new Map<string, number>();
  for (const edge of edges) {
    degree.set(edge.source, (degree.get(edge.source) ?? 0) + 1);
    degree.set(edge.target, (degree.get(edge.target) ?? 0) + 1);
  }
  const ranked = [...nodes].sort(
    (a, b) => (degree.get(b.id) ?? 0) - (degree.get(a.id) ?? 0) || compareNodes(a, b),
  );
  return ranked[0]?.id ?? null;
}

/**
 * A view of the whole (filtered) graph. Hops count from `centre` — the selection, or the
 * most connected node — so the panels can say how far anything is from it.
 */
export function universeView(
  nodes: readonly GraphNodeSummary[],
  edges: readonly GraphEdgeSummary[],
  centre: string | null,
): GraphView | null {
  const focus =
    centre && nodes.some((node) => node.id === centre) ? centre : mostConnected(nodes, edges);
  if (!focus) return null;
  const byId = new Map(nodes.map((node) => [node.id, node]));
  const shown = edges.filter((edge) => byId.has(edge.source) && byId.has(edge.target));
  const { hops, parent } = spanningTree(focus, byId, shown);
  const shownDegree = new Map<string, number>();
  for (const edge of shown) {
    shownDegree.set(edge.source, (shownDegree.get(edge.source) ?? 0) + 1);
    shownDegree.set(edge.target, (shownDegree.get(edge.target) ?? 0) + 1);
  }
  let maxHops = 0;
  for (const value of hops.values()) maxHops = Math.max(maxHops, value);
  const order = [...nodes].sort(compareNodes).map((node) => node.id);
  const viewNodes = new Map<string, ViewNode>();
  for (const id of order) {
    const node = byId.get(id) as GraphNodeSummary;
    viewNodes.set(id, {
      ...node,
      hops: hops.get(id) ?? maxHops + 1,
      parent: parent.get(id) ?? null,
      origin: focus,
      shownDegree: shownDegree.get(id) ?? 0,
    });
  }
  return {
    focus,
    nodes: viewNodes,
    edges: new Map(shown.map((edge) => [edge.id, edge])),
    order,
    hiddenByLimit: 0,
    focusTruncated: false,
    unexploredByType: {},
    expansions: [],
    maxHops,
  };
}
