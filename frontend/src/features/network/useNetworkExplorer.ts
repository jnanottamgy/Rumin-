import { useCallback, useMemo, useState } from "react";
import type { EdgeType, EntityKind } from "@/types/api";
import {
  defaultFilters,
  type GraphModel,
  KIND_ORDER,
  type NetworkFilters,
  visibleSubgraph,
} from "./model";

/** Selection and filter state for an interactive network view. */
export function useNetworkExplorer(model: GraphModel, initialSelectedId: string | null = null) {
  const [selectedId, setSelectedId] = useState<string | null>(initialSelectedId);
  const [filters, setFilters] = useState<NetworkFilters>(() => defaultFilters(model));
  const visible = useMemo(() => visibleSubgraph(model, filters), [model, filters]);

  // A node hidden by a filter cannot stay selected.
  const effectiveSelectedId = selectedId && visible.nodeIds.has(selectedId) ? selectedId : null;

  const toggleKind = useCallback((kind: EntityKind) => {
    setFilters((current) => {
      const kinds = new Set(current.kinds);
      if (kinds.has(kind)) kinds.delete(kind);
      else kinds.add(kind);
      return { ...current, kinds };
    });
  }, []);

  const toggleEdgeType = useCallback((type: EdgeType) => {
    setFilters((current) => {
      const edgeTypes = new Set(current.edgeTypes);
      if (edgeTypes.has(type)) edgeTypes.delete(type);
      else edgeTypes.add(type);
      return { ...current, edgeTypes };
    });
  }, []);

  const setCategoryVisible = useCallback(
    (category: "economic" | "structural", on: boolean) => {
      setFilters((current) => {
        const edgeTypes = new Set(current.edgeTypes);
        for (const [type, info] of model.types) {
          if (info.category !== category) continue;
          if (on) edgeTypes.add(type);
          else edgeTypes.delete(type);
        }
        return { ...current, edgeTypes };
      });
    },
    [model],
  );

  const resetFilters = useCallback(() => setFilters(defaultFilters(model)), [model]);

  const isFiltered =
    filters.kinds.size < KIND_ORDER.length || filters.edgeTypes.size < model.types.size;

  return {
    selectedId: effectiveSelectedId,
    select: setSelectedId,
    filters,
    visible,
    toggleKind,
    toggleEdgeType,
    setCategoryVisible,
    resetFilters,
    isFiltered,
  };
}

export type NetworkExplorer = ReturnType<typeof useNetworkExplorer>;
