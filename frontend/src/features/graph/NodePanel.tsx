/**
 * Everything the graph knows about one node — and what it does not know. Identifiers,
 * the source records it was built from, how entity resolution treated it, its
 * relationships, live data availability and, for companies and industries, the variables
 * linked to it by assumed-effect edges (labelled direct or via the industry).
 */
import { Fragment } from "react";
import { Link } from "react-router";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { Icon } from "@/components/Icon";
import { ErrorState, LoadingState } from "@/components/States";
import { useApiResource } from "@/hooks/useApiResource";
import { formatCalendarDate, formatCount, formatDateTime, plural } from "@/lib/format";
import { graphApi } from "@/services/api";
import type {
  GraphEdgeSummary,
  GraphExposure,
  GraphNodeDetail,
  GraphNodeSummary,
} from "@/types/api";
import styles from "./Details.module.css";
import {
  DATA_STATUS_LABEL,
  EVIDENCE_ENCODING,
  NATURE_ENCODING,
  NODE_TYPE_ENCODING,
} from "./encoding";
import { EvidenceSwatch, NatureSwatch, TypeGlyph } from "./GraphGlyph";
import type { Selection } from "./useGraphExplorer";
import type { GraphView } from "./view";

export interface NodeActions {
  onSelect: (selection: Selection) => void;
  onFocus?: (id: string) => void;
  onExpand?: (id: string) => void;
  onCollapse?: (id: string) => void;
  onFindPath?: (node: Pick<GraphNodeSummary, "id" | "name" | "type">) => void;
  onClose: () => void;
}

export function NodeButton({
  node,
  onSelect,
}: {
  node: Pick<GraphNodeSummary, "id" | "name" | "type" | "data_status">;
  onSelect: (selection: Selection) => void;
}) {
  return (
    <button
      type="button"
      className={styles.nodeLink}
      onClick={() => onSelect({ kind: "node", id: node.id })}
    >
      <TypeGlyph
        type={node.type}
        size={11}
        hollow={node.data_status === "definition_only" ? true : undefined}
      />
      {node.name}
    </button>
  );
}

export function NatureBadge({ nature }: { nature: GraphNodeSummary["nature"] }) {
  const encoding = NATURE_ENCODING[nature];
  return (
    <Badge
      tone={nature === "real" ? "outline" : "warning"}
      icon={<NatureSwatch nature={nature} size={12} />}
      title={encoding.description}
    >
      {encoding.label}
    </Badge>
  );
}

/** Where a series' or instrument's values live in the Data Explorer. */
function dataHref(detail: GraphNodeDetail): string | null {
  if (!detail.data) return null;
  const id = encodeURIComponent(detail.data.record_id);
  return detail.data.kind === "series" ? `/data/series/${id}` : `/data/instruments/${id}`;
}

function DataAvailability({ detail }: { detail: GraphNodeDetail }) {
  const data = detail.data;
  if (!data) return null;
  const href = dataHref(detail);
  return (
    <section className={styles.section} aria-labelledby={`${detail.id}-data`}>
      <h3 className={styles.sectionTitle} id={`${detail.id}-data`}>
        Stored data
      </h3>
      <dl className={styles.facts}>
        <dt>Values</dt>
        <dd>
          {data.value_count
            ? `${formatCount(data.value_count)} stored`
            : "None stored — only the definition is in RUMIN"}
        </dd>
        {data.first && data.last && (
          <>
            <dt>Period</dt>
            <dd>
              {formatCalendarDate(data.first)} – {formatCalendarDate(data.last)}
            </dd>
          </>
        )}
        {data.kind === "series" && (
          <>
            <dt>Last retrieved</dt>
            <dd>{data.last_retrieved_at ? formatDateTime(data.last_retrieved_at) : "Never"}</dd>
          </>
        )}
      </dl>
      {href && (
        <Link className={styles.inlineLink} to={href}>
          Open in the Data Explorer
          <Icon name="arrowRight" size={12} />
        </Link>
      )}
      <p className={styles.note}>Historical values only — nothing here is live or real-time.</p>
    </section>
  );
}

function Exposures({
  exposures,
  onSelect,
}: {
  exposures: readonly GraphExposure[];
  onSelect: (selection: Selection) => void;
}) {
  const direct = exposures.filter((item) => item.kind === "direct");
  const viaIndustry = exposures.filter((item) => item.kind === "via_industry");
  const group = (title: string, items: readonly GraphExposure[], hint: string) =>
    items.length > 0 && (
      <div className={styles.subsection}>
        <p className={styles.subsectionTitle}>
          {title} <span className={styles.muted}>· {hint}</span>
        </p>
        <ul className={styles.list}>
          {items.map((item) => (
            <li key={`${item.kind}-${item.edge.id}`} className={styles.item}>
              <p className={styles.line}>
                <NodeButton node={item.variable} onSelect={onSelect} />
                <button
                  type="button"
                  className={styles.relation}
                  onClick={() => onSelect({ kind: "edge", id: item.edge.id })}
                >
                  {item.edge.label}
                  {item.via ? ` ${item.via.name}` : ""}
                </button>
              </p>
              <p className={styles.meta}>
                <EvidenceSwatch status={item.edge.evidence_status} width={18} />
                {EVIDENCE_ENCODING[item.edge.evidence_status].label}
                {item.edge.qualifiers.polarity && item.edge.qualifiers.polarity !== "not_applicable"
                  ? ` · assumed ${item.edge.qualifiers.polarity}`
                  : ""}
                {item.edge.is_illustrative ? " · illustrative" : ""}
              </p>
              <p className={styles.note}>{item.explanation}</p>
            </li>
          ))}
        </ul>
      </div>
    );
  return (
    <section className={styles.section} aria-label="Assumed exposures">
      <h3 className={styles.sectionTitle}>Variables assumed to affect it</h3>
      {exposures.length === 0 ? (
        <p className={styles.muted}>No assumed-effect relationships are recorded.</p>
      ) : (
        <>
          {group("Stated for it", direct, "direct")}
          {group("Stated for its industry", viaIndustry, "indirect, via the industry")}
        </>
      )}
      <p className={styles.note}>
        These are model assumptions, not measured exposures: they say nothing about size or timing,
        and a link stated for an industry does not mean every company in it is affected, or affected
        equally.
      </p>
    </section>
  );
}

function ShownRelationships({
  view,
  nodeId,
  onSelect,
}: {
  view: GraphView;
  nodeId: string;
  onSelect: (selection: Selection) => void;
}) {
  const edges = [...view.edges.values()].filter(
    (edge) => edge.source === nodeId || edge.target === nodeId,
  );
  if (edges.length === 0) return null;
  const describe = (edge: GraphEdgeSummary) => {
    const outgoing = edge.source === nodeId;
    const other = view.nodes.get(outgoing ? edge.target : edge.source);
    return { outgoing, other };
  };
  return (
    <section className={styles.section} aria-label="Relationships shown on the canvas">
      <h3 className={styles.sectionTitle}>
        Shown on the canvas <span className={styles.count}>{edges.length}</span>
      </h3>
      <ul className={styles.list}>
        {edges.map((edge) => {
          const { outgoing, other } = describe(edge);
          return (
            <li key={edge.id} className={styles.compactItem}>
              <button
                type="button"
                className={styles.relationRow}
                onClick={() => onSelect({ kind: "edge", id: edge.id })}
                aria-label={`${outgoing || !edge.directed ? edge.label : `${other?.name ?? ""} ${edge.label} this node`}${outgoing || !edge.directed ? ` ${other?.name ?? ""}` : ""}: ${EVIDENCE_ENCODING[edge.evidence_status].label}. Show the evidence.`}
              >
                <EvidenceSwatch status={edge.evidence_status} width={18} arrow={edge.directed} />
                <span>
                  {outgoing || !edge.directed ? (
                    <>
                      <span className={styles.verb}>{edge.label}</span> {other?.name}
                    </>
                  ) : (
                    <>
                      {other?.name} <span className={styles.verb}>{edge.label}</span> this
                    </>
                  )}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function NodeBody({
  detail,
  view,
  isFocus,
  isExpanded,
  busy,
  actions,
}: {
  detail: GraphNodeDetail;
  view: GraphView | null;
  isFocus: boolean;
  isExpanded: boolean;
  busy: boolean;
  actions: NodeActions;
}) {
  const shown = view?.nodes.get(detail.id)?.shownDegree ?? 0;
  const hidden = Math.max(0, detail.degree - shown);
  const data = DATA_STATUS_LABEL[detail.data_status];
  const encoding = NODE_TYPE_ENCODING[detail.type];

  return (
    <div className={styles.details}>
      <header className={styles.header}>
        <p className={styles.kind}>
          <TypeGlyph type={detail.type} />
          {encoding.label}
        </p>
        <button
          type="button"
          className={styles.close}
          onClick={actions.onClose}
          aria-label="Close details"
        >
          <Icon name="close" size={14} />
        </button>
        <h2 className={styles.name}>{detail.name}</h2>
        <div className={styles.badges}>
          <NatureBadge nature={detail.nature} />
          {detail.quality_status === "warning" && (
            <Badge tone="warning" icon={<Icon name="alert" size={11} />}>
              Flagged for review
            </Badge>
          )}
          {data && <Badge tone="neutral">{data}</Badge>}
        </div>
      </header>
      <p className={styles.subtitle}>{detail.subtitle}</p>
      {detail.description && <p className={styles.description}>{detail.description}</p>}

      <div className={styles.actions}>
        {!isFocus && actions.onFocus && (
          <Button size="sm" variant="primary" onClick={() => actions.onFocus?.(detail.id)}>
            Explore from here
          </Button>
        )}
        {actions.onExpand &&
          !isFocus &&
          (isExpanded ? (
            <Button size="sm" onClick={() => actions.onCollapse?.(detail.id)}>
              Hide its neighbours
            </Button>
          ) : (
            <Button
              size="sm"
              onClick={() => actions.onExpand?.(detail.id)}
              disabled={busy || hidden === 0}
              title={hidden === 0 ? "Every connection is already shown." : undefined}
            >
              {busy ? "Loading neighbours…" : `Show neighbours${hidden ? ` (+${hidden})` : ""}`}
            </Button>
          ))}
        {actions.onFindPath && (
          <Button
            size="sm"
            variant="ghost"
            onClick={() =>
              actions.onFindPath?.({ id: detail.id, name: detail.name, type: detail.type })
            }
          >
            Find a path from here
          </Button>
        )}
      </div>

      <dl className={styles.facts}>
        <dt>Connections</dt>
        <dd>
          {plural(detail.degree, "edge")}
          {detail.degree > 0 && (
            <span className={styles.muted}>
              {" "}
              · {detail.out_degree} outgoing, {detail.in_degree} incoming
              {view ? ` · ${shown} shown` : ""}
            </span>
          )}
          <span className={styles.secondary}>
            A count of recorded edges: data coverage, not importance.
          </span>
        </dd>
        {detail.identifiers.map((identifier) => (
          <Fragment key={`${identifier.scheme}-${identifier.value}`}>
            <dt>{identifier.label}</dt>
            <dd className="mono">{identifier.value}</dd>
          </Fragment>
        ))}
        {detail.identifiers.length === 0 && (
          <>
            <dt>Identifiers</dt>
            <dd className={styles.muted}>
              None external{detail.nature === "fictional" ? " (fictional record)" : ""} — known by
              its RUMIN key <span className="mono">{detail.id}</span>
            </dd>
          </>
        )}
      </dl>

      {detail.exposures && <Exposures exposures={detail.exposures} onSelect={actions.onSelect} />}
      <DataAvailability detail={detail} />
      {view && <ShownRelationships view={view} nodeId={detail.id} onSelect={actions.onSelect} />}

      {detail.relationships.length > 0 && (
        <section className={styles.section} aria-label="All relationships by type">
          <h3 className={styles.sectionTitle}>All relationships by type</h3>
          <table className={styles.table}>
            <thead>
              <tr>
                <th scope="col">Relationship</th>
                <th scope="col">Direction</th>
                <th scope="col" className={styles.number}>
                  Edges
                </th>
              </tr>
            </thead>
            <tbody>
              {detail.relationships.map((item) => (
                <tr key={`${item.type}-${item.direction}`}>
                  <td>{item.label}</td>
                  <td className={styles.muted}>{item.direction}</td>
                  <td className={styles.number}>{formatCount(item.count)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      <section className={styles.section} aria-label="Where it comes from">
        <h3 className={styles.sectionTitle}>Built from</h3>
        {detail.sources.length === 0 ? (
          <p className={styles.muted}>
            No source record: this node is derived from a code other records share (see below).
          </p>
        ) : (
          <ul className={styles.list}>
            {detail.sources.map((source) => (
              <li key={`${source.table}-${source.record_id}`} className={styles.compactItem}>
                <span className="mono">
                  {source.table}/{source.record_id}
                </span>
                <span className={styles.muted}>
                  {source.dataset_id
                    ? ` · ${source.dataset_id}${source.dataset_version ? ` ${source.dataset_version}` : ""}`
                    : ""}
                  {source.fields?.length ? ` · fields: ${source.fields.join(", ")}` : ""}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      {detail.resolution.length > 0 && (
        <section className={styles.section} aria-label="Entity resolution">
          <h3 className={styles.sectionTitle}>Entity resolution</h3>
          <ul className={styles.list}>
            {detail.resolution.map((decision) => (
              <li
                key={`${decision.method}-${decision.outcome}-${decision.source}-${decision.identifier ?? ""}`}
                className={styles.item}
              >
                <p className={styles.meta}>
                  {decision.method.replace("_", " ")} · {decision.outcome.replace("_", " ")}
                  {decision.identifier ? (
                    <>
                      {" · "}
                      <span className="mono">{decision.identifier}</span>
                    </>
                  ) : null}
                </p>
                <p className={styles.note}>{decision.rationale}</p>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className={styles.section} aria-label="Quality">
        <h3 className={styles.sectionTitle}>Quality checks</h3>
        {detail.issues.length === 0 ? (
          <p className={styles.muted}>No validation issues for this node in the latest build.</p>
        ) : (
          <ul className={styles.list}>
            {detail.issues.map((issue) => (
              <li key={issue.id} className={styles.item}>
                <p className={styles.meta}>
                  <span className="mono">{issue.rule}</span> · {issue.severity} · {issue.outcome}
                </p>
                <p className={styles.note}>{issue.message}</p>
              </li>
            ))}
          </ul>
        )}
      </section>

      <p className={styles.footnote}>
        In the graph since build #{detail.first_build_id}; last changed in build #
        {detail.changed_build_id}. Key <span className="mono">{detail.id}</span>
        {detail.component ? ` · component ${detail.component}` : ""}.
      </p>
    </div>
  );
}

export function NodePanel({
  nodeId,
  view,
  isFocus,
  isExpanded,
  busy,
  actions,
}: {
  nodeId: string;
  view: GraphView | null;
  isFocus: boolean;
  isExpanded: boolean;
  busy: boolean;
  actions: NodeActions;
}) {
  const resource = useApiResource(`graph-node:${nodeId}`, () => graphApi.node(nodeId));
  if (resource.status === "loading") {
    return <LoadingState label="Loading the node's details…" lines={6} />;
  }
  if (resource.status === "error") {
    return (
      <div className={styles.details}>
        <ErrorState
          error={resource.error}
          title="This node's details could not be loaded"
          onRetry={resource.reload}
        />
      </div>
    );
  }
  return (
    <NodeBody
      detail={resource.data}
      view={view}
      isFocus={isFocus}
      isExpanded={isExpanded}
      busy={busy}
      actions={actions}
    />
  );
}
