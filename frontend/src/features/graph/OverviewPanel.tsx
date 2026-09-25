/**
 * The map view's side panel: the latest build's validation report, graph metrics with
 * their definitions and limitations, and entry points into the graph. Metrics describe
 * the data RUMIN holds — how much of it there is and how it is linked — never the
 * economy, and never a ranking of companies.
 */
import { Badge } from "@/components/Badge";
import { Icon } from "@/components/Icon";
import { ErrorState, LoadingState } from "@/components/States";
import { useApiResource } from "@/hooks/useApiResource";
import { formatCount, formatDateTime, plural } from "@/lib/format";
import { graphApi } from "@/services/api";
import type { GraphNodeType, GraphOverview } from "@/types/api";
import styles from "./Details.module.css";
import { EVIDENCE_ENCODING, EVIDENCE_ORDER, NODE_TYPE_ENCODING } from "./encoding";
import { EvidenceSwatch, TypeGlyph } from "./GraphGlyph";
import panel from "./OverviewPanel.module.css";

interface Metrics {
  node_count?: number;
  edge_count?: number;
  edges_by_evidence_status?: Record<string, number>;
  illustrative_edges?: number;
  components?: { count: number; largest: number; isolated_nodes: number };
  degree?: { average: number; median: number; maximum: number };
  density?: number;
  provenance?: { edges_with_evidence: number; edges_with_citation: number; derived_edges: number };
}

const percent = (part: number, whole: number) =>
  whole ? `${Math.round((part / whole) * 1000) / 10}%` : "—";

function metricValue(id: string, metrics: Metrics): string {
  switch (id) {
    case "node_count":
      return formatCount(metrics.node_count ?? 0);
    case "edge_count":
      return formatCount(metrics.edge_count ?? 0);
    case "components":
      return metrics.components
        ? `${formatCount(metrics.components.count)} (largest ${formatCount(metrics.components.largest)}; ${formatCount(metrics.components.isolated_nodes)} isolated)`
        : "—";
    case "average_degree":
      return metrics.degree
        ? `${metrics.degree.average} (median ${metrics.degree.median}; max ${metrics.degree.maximum})`
        : "—";
    case "density":
      return metrics.density === undefined ? "—" : String(metrics.density);
    case "provenance_coverage": {
      const edges = metrics.edge_count ?? 0;
      const p = metrics.provenance;
      return p
        ? `${percent(p.edges_with_evidence, edges)} with evidence; ${percent(p.edges_with_citation, edges)} with a citation`
        : "—";
    }
    default:
      return "—";
  }
}

function MostConnected({ onFocus }: { onFocus: (id: string) => void }) {
  const top = useApiResource("graph-most-connected", () =>
    graphApi.search({ sort: "-degree", limit: 6 }),
  );
  if (top.status === "loading") return <LoadingState label="Loading…" lines={2} />;
  if (top.status === "error") return <ErrorState error={top.error} onRetry={top.reload} />;
  return (
    <ul className={styles.list}>
      {top.data.items.map((node) => (
        <li key={node.id} className={styles.compactItem}>
          <button type="button" className={panel.pick} onClick={() => onFocus(node.id)}>
            <TypeGlyph type={node.type} size={12} />
            <span className={panel.pickName}>{node.name}</span>
            <span className={panel.pickMeta}>{plural(node.degree, "edge")}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}

export function OverviewPanel({
  overview,
  onFocus,
}: {
  overview: GraphOverview;
  onFocus: (id: string) => void;
}) {
  const build = overview.build;
  const metrics = overview.metrics as Metrics;
  const byStatus = metrics.edges_by_evidence_status ?? {};
  if (!build) return null;
  return (
    <div className={styles.details}>
      <header className={panel.header}>
        <p className={styles.kind}>Build #{build.id}</p>
        <h2 className={styles.name}>The graph at a glance</h2>
        <p className={styles.subtitle}>
          {build.finished_at ? `Built ${formatDateTime(build.finished_at)}` : "Build in progress"}
          {build.duration_ms !== null ? ` in ${formatCount(build.duration_ms)} ms` : ""} · rules
          version {build.rules_version}
        </p>
        <p className={styles.note}>{overview.freshness.message}</p>
      </header>

      <section className={styles.section} aria-label="Validation report">
        <h3 className={styles.sectionTitle}>Validation report</h3>
        <table className={styles.table}>
          <thead>
            <tr>
              <th scope="col">
                <span className="visually-hidden">Records</span>
              </th>
              <th scope="col" className={styles.number}>
                Processed
              </th>
              <th scope="col" className={styles.number}>
                Valid
              </th>
              <th scope="col" className={styles.number}>
                Flagged
              </th>
              <th scope="col" className={styles.number}>
                Rejected
              </th>
            </tr>
          </thead>
          <tbody>
            {(["nodes", "edges"] as const).map((kind) => (
              <tr key={kind}>
                <th scope="row">{kind === "nodes" ? "Nodes" : "Edges"}</th>
                <td className={styles.number}>{formatCount(build[kind].processed)}</td>
                <td className={styles.number}>{formatCount(build[kind].valid)}</td>
                <td className={styles.number}>{formatCount(build[kind].flagged)}</td>
                <td className={styles.number}>{formatCount(build[kind].rejected)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className={styles.note}>
          Counted by the build itself: {plural(build.error_count, "error")},{" "}
          {plural(build.warning_count, "warning")}, {plural(build.info_count, "note")}.
        </p>
      </section>

      <section className={styles.section} aria-label="Edges by evidence status">
        <h3 className={styles.sectionTitle}>Edges by evidence status</h3>
        <ul className={styles.list}>
          {EVIDENCE_ORDER.filter((status) => byStatus[status]).map((status) => (
            <li key={status} className={styles.compactItem}>
              <span className={panel.row}>
                <EvidenceSwatch status={status} />
                <span className={panel.rowLabel}>{EVIDENCE_ENCODING[status].label}</span>
                <span className={panel.rowValue}>{formatCount(byStatus[status] ?? 0)}</span>
              </span>
            </li>
          ))}
        </ul>
        <p className={styles.note}>
          {formatCount(metrics.illustrative_edges ?? 0)} of {formatCount(metrics.edge_count ?? 0)}{" "}
          edges are illustrative: they touch the fictional sample network or sample data.
        </p>
      </section>

      <section className={styles.section} aria-label="Graph metrics">
        <h3 className={styles.sectionTitle}>Metrics</h3>
        <dl className={panel.metrics}>
          {overview.metric_definitions.map((metric) => (
            <div key={metric.id} className={panel.metric}>
              <dt>{metric.label}</dt>
              <dd className={panel.metricValue}>{metricValue(metric.id, metrics)}</dd>
              <dd>
                <details className={panel.definition}>
                  <summary>What it means</summary>
                  <p>
                    <strong>Definition.</strong> {metric.definition}
                  </p>
                  <p>
                    <strong>Calculation.</strong> {metric.calculation}
                  </p>
                  <p>
                    <strong>Reading it.</strong> {metric.interpretation}
                  </p>
                  <p>
                    <strong>Limitations.</strong> {metric.limitations}
                  </p>
                </details>
              </dd>
            </div>
          ))}
        </dl>
      </section>

      <section className={styles.section} aria-label="Most connected nodes">
        <h3 className={styles.sectionTitle}>Start from a well-connected node</h3>
        <MostConnected onFocus={onFocus} />
        <p className={styles.note}>
          Ordered by recorded edges — how much RUMIN's data says about a node, not how important it
          is. Hubs such as countries are highly connected by construction.
        </p>
      </section>

      <section className={styles.section} aria-label="About this graph">
        <h3 className={styles.sectionTitle}>Read this first</h3>
        <ul className={panel.notes}>
          {overview.notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      </section>
    </div>
  );
}

export function TypeNodeList({
  type,
  onFocus,
  onClose,
}: {
  type: GraphNodeType;
  onFocus: (id: string) => void;
  onClose: () => void;
}) {
  const list = useApiResource(`graph-type:${type}`, () =>
    graphApi.search({ types: [type], sort: "-degree", limit: 50 }),
  );
  const encoding = NODE_TYPE_ENCODING[type];
  return (
    <div className={styles.details}>
      <header className={styles.header}>
        <p className={styles.kind}>
          <TypeGlyph type={type} />
          Listed from the map
        </p>
        <button type="button" className={styles.close} onClick={onClose} aria-label="Close list">
          <Icon name="close" size={14} />
        </button>
        <h2 className={styles.name}>{encoding.plural}</h2>
      </header>
      {list.status === "loading" && (
        <LoadingState label={`Loading ${encoding.plural}…`} lines={4} />
      )}
      {list.status === "error" && <ErrorState error={list.error} onRetry={list.reload} />}
      {list.status === "success" && (
        <>
          <p className={styles.note}>
            Choose one to explore its neighbourhood.
            {list.data.total > list.data.items.length
              ? ` Showing ${list.data.items.length} of ${formatCount(list.data.total)}, most connected first — search to find the rest.`
              : ` ${plural(list.data.total, encoding.label.toLowerCase(), encoding.plural.toLowerCase())}, most connected first.`}
          </p>
          <ul className={styles.list}>
            {list.data.items.map((node) => (
              <li key={node.id} className={styles.compactItem}>
                <button type="button" className={panel.pick} onClick={() => onFocus(node.id)}>
                  <TypeGlyph
                    type={node.type}
                    size={12}
                    hollow={node.data_status === "definition_only" ? true : undefined}
                  />
                  <span className={panel.pickText}>
                    <span className={panel.pickName}>{node.name}</span>
                    <span className={panel.pickMeta}>{node.subtitle}</span>
                  </span>
                  <span className={panel.pickMeta}>{plural(node.degree, "edge")}</span>
                  {node.ambiguous && <Badge tone="warning">Shared name</Badge>}
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
