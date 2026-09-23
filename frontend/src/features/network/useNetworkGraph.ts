import { useMemo } from "react";
import { useApiResource } from "@/hooks/useApiResource";
import { api } from "@/services/api";
import type { NetworkResponse } from "@/types/api";
import { nodeRadius } from "./encoding";
import { computeLayout, type Layout, transposeLayout } from "./layout";
import { buildGraphModel, type GraphModel } from "./model";

export interface NetworkGraph {
  model: GraphModel;
  /** Layers as columns, for landscape viewports. */
  layout: Layout;
  /** Layers as rows, for portrait phones. */
  portraitLayout: Layout;
}

// One model + layout per loaded network, shared by every view (landing, dashboard,
// universe): the graph looks identical everywhere and is laid out only once.
const graphs = new WeakMap<NetworkResponse, NetworkGraph>();

export function graphFor(network: NetworkResponse): NetworkGraph {
  const cached = graphs.get(network);
  if (cached) return cached;
  const model = buildGraphModel(network);
  const layout = computeLayout(
    model.nodes.map((node) => ({
      id: node.id,
      kind: node.kind,
      radius: nodeRadius(node.kind, node.degree),
    })),
    model.edges.map((edge) => ({
      source: edge.source,
      target: edge.target,
      category: edge.category,
    })),
  );
  const graph = { model, layout, portraitLayout: transposeLayout(layout) };
  graphs.set(network, graph);
  return graph;
}

export const NETWORK_RESOURCE = "network";

export function useNetworkGraph() {
  const resource = useApiResource(NETWORK_RESOURCE, () => api.network());
  const graph = useMemo(
    () => (resource.status === "success" ? graphFor(resource.data) : null),
    [resource.status, resource.data],
  );
  return { ...resource, graph };
}
