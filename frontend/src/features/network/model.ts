/**
 * The frontend graph model: validation at the API boundary, indexes for fast lookups,
 * neighbourhoods for selection, and filtering. Pure functions — no React, no DOM.
 */
import type {
  DatasetSummary,
  EdgeType,
  Entity,
  EntityKind,
  NetworkEdge,
  NetworkResponse,
  RelationshipTypeInfo,
} from "@/types/api";

export class NetworkDataError extends Error {
  readonly problems: string[];

  constructor(problems: string[]) {
    super(
      `The network data from the API is inconsistent (${problems.length} problem${
        problems.length === 1 ? "" : "s"
      }). ${problems[0] ?? ""}`,
    );
    this.name = "NetworkDataError";
    this.problems = problems;
  }
}

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null;

/**
 * Checks the structural integrity of a network payload before anything renders it:
 * unique IDs, known relationship types, and edges that only connect existing nodes.
 * A broken graph fails loudly here instead of drawing lines into empty space.
 */
export function validateNetwork(payload: unknown): NetworkResponse {
  if (!isRecord(payload)) throw new NetworkDataError(["The response is not a JSON object."]);
  const { nodes, edges, relationship_types: types } = payload;
  const shapeProblems = [
    Array.isArray(nodes) ? null : "`nodes` is missing or not a list.",
    Array.isArray(edges) ? null : "`edges` is missing or not a list.",
    Array.isArray(types) ? null : "`relationship_types` is missing or not a list.",
  ].filter((problem): problem is string => problem !== null);
  if (shapeProblems.length > 0) throw new NetworkDataError(shapeProblems);

  const problems: string[] = [];
  const nodeIds = new Set<string>();
  for (const [index, node] of (nodes as unknown[]).entries()) {
    const entity = isRecord(node) ? node.entity : undefined;
    if (
      !isRecord(node) ||
      typeof node.id !== "string" ||
      !isRecord(entity) ||
      typeof entity.kind !== "string" ||
      typeof entity.name !== "string"
    ) {
      problems.push(`Node #${index} is malformed.`);
      continue;
    }
    if (nodeIds.has(node.id)) problems.push(`Duplicate node ID "${node.id}".`);
    if (entity.id !== node.id) problems.push(`Node "${node.id}" wraps a different entity.`);
    nodeIds.add(node.id);
  }

  const typeIds = new Set(
    (types as unknown[]).map((type) => (isRecord(type) ? type.type : undefined)),
  );
  const edgeIds = new Set<string>();
  for (const [index, edge] of (edges as unknown[]).entries()) {
    if (
      !isRecord(edge) ||
      typeof edge.id !== "string" ||
      typeof edge.source_id !== "string" ||
      typeof edge.target_id !== "string" ||
      typeof edge.type !== "string"
    ) {
      problems.push(`Edge #${index} is malformed.`);
      continue;
    }
    if (edgeIds.has(edge.id)) problems.push(`Duplicate edge ID "${edge.id}".`);
    edgeIds.add(edge.id);
    for (const end of [edge.source_id, edge.target_id]) {
      if (!nodeIds.has(end)) problems.push(`Edge "${edge.id}" points to unknown node "${end}".`);
    }
    if (edge.source_id === edge.target_id) problems.push(`Edge "${edge.id}" is a self-loop.`);
    if (!typeIds.has(edge.type))
      problems.push(`Edge "${edge.id}" has unknown type "${edge.type}".`);
  }

  if (problems.length > 0) throw new NetworkDataError(problems);
  return payload as unknown as NetworkResponse;
}

// --- Graph model -------------------------------------------------------------------------

export interface GraphNode {
  id: string;
  kind: EntityKind;
  label: string;
  degree: number;
  entity: Entity;
}

export interface GraphEdge {
  id: string;
  type: EdgeType;
  category: "economic" | "structural";
  source: string;
  target: string;
  directed: boolean;
  data: NetworkEdge;
}

export interface GraphModel {
  nodes: GraphNode[];
  edges: GraphEdge[];
  nodeById: Map<string, GraphNode>;
  edgeById: Map<string, GraphEdge>;
  incident: Map<string, GraphEdge[]>;
  types: Map<EdgeType, RelationshipTypeInfo>;
  dataset: DatasetSummary | null;
}

export const KIND_ORDER: readonly EntityKind[] = [
  "economic_variable",
  "industry",
  "company",
  "country",
];

export function buildGraphModel(network: NetworkResponse): GraphModel {
  const nodes: GraphNode[] = network.nodes
    .map((node) => ({
      id: node.id,
      kind: node.entity.kind,
      label: node.entity.name,
      degree: node.degree,
      entity: node.entity,
    }))
    .sort(
      (a, b) =>
        KIND_ORDER.indexOf(a.kind) - KIND_ORDER.indexOf(b.kind) || a.label.localeCompare(b.label),
    );
  const edges: GraphEdge[] = network.edges.map((edge) => ({
    id: edge.id,
    type: edge.type,
    category: edge.category,
    source: edge.source_id,
    target: edge.target_id,
    directed: edge.directed,
    data: edge,
  }));

  const incident = new Map<string, GraphEdge[]>(nodes.map((node) => [node.id, []]));
  for (const edge of edges) {
    incident.get(edge.source)?.push(edge);
    incident.get(edge.target)?.push(edge);
  }

  return {
    nodes,
    edges,
    nodeById: new Map(nodes.map((node) => [node.id, node])),
    edgeById: new Map(edges.map((edge) => [edge.id, edge])),
    incident,
    types: new Map(network.relationship_types.map((type) => [type.type, type])),
    dataset: network.dataset,
  };
}

export interface Subgraph {
  nodeIds: Set<string>;
  edgeIds: Set<string>;
}

/** The selected node, its direct neighbours, and the edges between them and it. */
export function neighborhood(model: GraphModel, nodeId: string, visible?: Subgraph): Subgraph {
  const nodeIds = new Set<string>([nodeId]);
  const edgeIds = new Set<string>();
  for (const edge of model.incident.get(nodeId) ?? []) {
    if (visible && !visible.edgeIds.has(edge.id)) continue;
    edgeIds.add(edge.id);
    nodeIds.add(edge.source === nodeId ? edge.target : edge.source);
  }
  return { nodeIds, edgeIds };
}

// --- Filters -----------------------------------------------------------------------------

export interface NetworkFilters {
  kinds: ReadonlySet<EntityKind>;
  edgeTypes: ReadonlySet<EdgeType>;
}

export function defaultFilters(model: GraphModel): NetworkFilters {
  return {
    kinds: new Set(KIND_ORDER),
    edgeTypes: new Set(model.types.keys()),
  };
}

/** Nodes of visible kinds, and visible-type edges whose two ends are both visible. */
export function visibleSubgraph(model: GraphModel, filters: NetworkFilters): Subgraph {
  const nodeIds = new Set(
    model.nodes.filter((node) => filters.kinds.has(node.kind)).map((node) => node.id),
  );
  const edgeIds = new Set(
    model.edges
      .filter(
        (edge) =>
          filters.edgeTypes.has(edge.type) && nodeIds.has(edge.source) && nodeIds.has(edge.target),
      )
      .map((edge) => edge.id),
  );
  return { nodeIds, edgeIds };
}

/** Case-insensitive search over entity names and IDs, best matches first. */
export function searchNodes(model: GraphModel, query: string, limit = 6): GraphNode[] {
  const needle = query.trim().toLowerCase();
  if (!needle) return [];
  return model.nodes
    .map((node) => {
      const label = node.label.toLowerCase();
      const rank = label.startsWith(needle)
        ? 0
        : label.split(/\s+/).some((word) => word.startsWith(needle))
          ? 1
          : label.includes(needle) || node.id.includes(needle)
            ? 2
            : -1;
      return { node, rank };
    })
    .filter(({ rank }) => rank >= 0)
    .sort((a, b) => a.rank - b.rank || a.node.label.localeCompare(b.node.label))
    .slice(0, limit)
    .map(({ node }) => node);
}
