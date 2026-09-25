import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { Badge } from "@/components/Badge";
import { EpistemicBadge } from "@/components/EpistemicBadge";
import { PageHeader } from "@/components/PageHeader";
import { EmptyState, ErrorState, LoadingState } from "@/components/States";
import { EntityDetails } from "@/features/network/EntityDetails";
import { NetworkCanvas, type NetworkCanvasHandle } from "@/features/network/NetworkCanvas";
import { NetworkFilters, type NetworkView, ViewSwitch } from "@/features/network/NetworkFilters";
import { NetworkLegend } from "@/features/network/NetworkLegend";
import { NetworkTable } from "@/features/network/NetworkTable";
import { useNetworkExplorer } from "@/features/network/useNetworkExplorer";
import { type NetworkGraph, useNetworkGraph } from "@/features/network/useNetworkGraph";
import { useMediaQuery } from "@/hooks/useMediaQuery";
import styles from "./UniversePage.module.css";

function Explorer({ graph, initialFocus }: { graph: NetworkGraph; initialFocus: string | null }) {
  const { model } = graph;
  // Phones: rows instead of columns, and names only for what is in focus.
  const portrait = useMediaQuery("(max-width: 40rem)");
  const layout = portrait ? graph.portraitLayout : graph.layout;
  const explorer = useNetworkExplorer(
    model,
    initialFocus && model.nodeById.has(initialFocus) ? initialFocus : null,
  );
  const [view, setView] = useState<NetworkView>("graph");
  const canvasRef = useRef<NetworkCanvasHandle>(null);
  const [, setSearchParams] = useSearchParams();
  const { selectedId, select, visible } = explorer;

  // Mirror the selection in the URL (?focus=…) so a view can be linked to and shared.
  useEffect(() => {
    setSearchParams(
      (current) => {
        const next = new URLSearchParams(current);
        if (selectedId) next.set("focus", selectedId);
        else next.delete("focus");
        return next;
      },
      { replace: true },
    );
  }, [selectedId, setSearchParams]);

  const onSelect = useCallback((id: string | null) => select(id), [select]);

  return (
    <div className={styles.explorer}>
      <NetworkFilters
        model={model}
        explorer={explorer}
        onPick={(node) => {
          if (!explorer.filters.kinds.has(node.kind)) explorer.toggleKind(node.kind);
          select(node.id);
          canvasRef.current?.centerOn(node.id);
        }}
      />
      <div className={styles.workspace} data-has-selection={Boolean(selectedId)}>
        <div className={styles.stage}>
          <div className={styles.toolbar}>
            <p className={styles.count} aria-live="polite">
              Showing {visible.nodeIds.size} of {model.nodes.length} entities ·{" "}
              {visible.edgeIds.size} of {model.edges.length} links
            </p>
            {explorer.isFiltered && (
              <button type="button" className={styles.reset} onClick={explorer.resetFilters}>
                Reset filters
              </button>
            )}
            <div className={styles.toolbarEnd}>
              <ViewSwitch view={view} onChange={setView} />
            </div>
          </div>
          {view === "graph" ? (
            <>
              <NetworkCanvas
                ref={canvasRef}
                model={model}
                layout={layout}
                visible={visible}
                selectedId={selectedId}
                onSelect={onSelect}
                mode="explore"
                labels={portrait ? "selected" : "all"}
                ariaLabel={`Financial network: ${visible.nodeIds.size} entities and ${visible.edgeIds.size} links shown. Tab to move between entities, Enter to select, Escape to clear. The table view lists the same data.`}
                className={styles.canvas}
              />
              <NetworkLegend compact={portrait} />
            </>
          ) : (
            <NetworkTable
              model={model}
              visible={visible}
              selectedId={selectedId}
              onSelect={(id) => select(id)}
            />
          )}
        </div>
        <aside className={styles.details} aria-label="Selected entity">
          {selectedId ? (
            <EntityDetails
              model={model}
              nodeId={selectedId}
              onSelect={(id) => select(id)}
              onClose={() => select(null)}
            />
          ) : (
            <div className={styles.hint}>
              <p className={styles.hintTitle}>Select an entity</p>
              <p>
                Click a node, search above, or tab through the network. Its relationships,
                references and provenance appear here.
              </p>
              <p className={styles.hintNote}>
                Read left to right: economic variables, the industries and companies they are
                assumed to affect, and the countries those companies are domiciled in. Every
                relationship is a modelling assumption; the panel shows how well each one is
                supported.
              </p>
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}

export function UniversePage() {
  const network = useNetworkGraph();
  const [searchParams] = useSearchParams();
  const dataset = network.graph?.model.dataset;

  return (
    <div className={styles.page}>
      <PageHeader
        compact
        eyebrow="Financial Universe"
        title="How the sample economy connects"
        meta={
          <>
            {dataset && (
              <Badge tone="outline">
                {dataset.is_illustrative ? "Illustrative dataset" : dataset.name} · v
                {dataset.version}
              </Badge>
            )}
            <EpistemicBadge category="assumption" suffix="every relationship" />
            <Link className={styles.headerLink} to="/universe/3d">
              The knowledge graph in 3D
            </Link>
          </>
        }
      />
      {network.status === "loading" && <LoadingState label="Loading the network…" lines={5} />}
      {network.status === "error" && <ErrorState error={network.error} onRetry={network.reload} />}
      {network.graph &&
        (network.graph.model.nodes.length === 0 ? (
          <EmptyState title="No dataset is loaded">
            Load the sample data with <span className="mono">python -m app.db.seed</span> in{" "}
            <span className="mono">backend/</span>, then reload this page.
          </EmptyState>
        ) : (
          <Explorer graph={network.graph} initialFocus={searchParams.get("focus")} />
        ))}
    </div>
  );
}
