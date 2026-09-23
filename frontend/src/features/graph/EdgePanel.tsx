/**
 * Why a connection exists. Every evidence record behind the edge — the source record,
 * dataset and version, what the source says, the rule and transformation that made the
 * edge, when it was retrieved and recorded — with the evidence status's definition and
 * what this kind of edge does *not* mean. Nothing is inferred here: all of it comes from
 * the API, and missing provenance is shown as missing.
 */
import { Badge } from "@/components/Badge";
import { Icon } from "@/components/Icon";
import { ErrorState, LoadingState } from "@/components/States";
import { ExternalLink } from "@/features/data/Provenance";
import { useApiResource } from "@/hooks/useApiResource";
import { formatCalendarDate, formatDateTime } from "@/lib/format";
import { graphApi } from "@/services/api";
import type { GraphEdgeDetail, GraphEvidence } from "@/types/api";
import styles from "./Details.module.css";
import { POLARITY_TEXT, STRENGTH_TEXT } from "./encoding";
import { EvidenceSwatch } from "./GraphGlyph";
import { NodeButton } from "./NodePanel";
import type { Selection } from "./useGraphExplorer";

const SOURCE_KIND: Record<GraphEvidence["source_kind"], string> = {
  reference_dataset: "Reference dataset record",
  series_catalogue: "Series catalogue entry",
  price_file_manifest: "Price-file manifest",
  classification_standard: "Published classification",
};

/** Only web links are rendered as links. */
function safeUrl(url: string | null): string | null {
  if (!url) return null;
  return /^https?:\/\//i.test(url) ? url : null;
}

function EvidenceRecord({ item, index }: { item: GraphEvidence; index: number }) {
  const url = safeUrl(item.citation_url);
  return (
    <li className={styles.evidence}>
      <p className={styles.evidenceHead}>
        <span className={styles.evidenceIndex}>{index + 1}</span>
        {SOURCE_KIND[item.source_kind]}
        <Badge tone="outline">{item.derivation === "direct" ? "Direct" : "Derived"}</Badge>
      </p>
      <dl className={styles.facts}>
        <dt>Source record</dt>
        <dd>
          <span className="mono">
            {item.source_table}/{item.source_record_id}
          </span>
        </dd>
        <dt>Dataset</dt>
        <dd>
          {item.dataset_id ? (
            <>
              <span className="mono">{item.dataset_id}</span>
              {item.dataset_version ? ` · version ${item.dataset_version}` : ""}
            </>
          ) : (
            <span className={styles.muted}>Not tied to a dataset</span>
          )}
        </dd>
        <dt>What it says</dt>
        <dd>{item.statement}</dd>
        <dt>Rule</dt>
        <dd>
          <span className="mono">{item.rule}</span>
          <span className={styles.secondary}>{item.rule_description}</span>
        </dd>
        <dt>Transformation</dt>
        <dd>{item.transformation}</dd>
        {item.derivation === "derived" && (
          <>
            <dt>Derived from</dt>
            <dd>
              {item.derived_from.length ? (
                item.derived_from.map((ref) => (
                  <span key={ref} className={`mono ${styles.block}`}>
                    {ref}
                  </span>
                ))
              ) : (
                <span className={styles.muted}>Not recorded</span>
              )}
            </dd>
          </>
        )}
        <dt>Citation</dt>
        <dd>
          {item.citation ? (
            url ? (
              <ExternalLink href={url}>{item.citation}</ExternalLink>
            ) : (
              item.citation
            )
          ) : (
            <span className={styles.muted}>None — the record does not cite an outside source</span>
          )}
        </dd>
        <dt>Retrieved</dt>
        <dd>
          {item.retrieved_at ? (
            formatDateTime(item.retrieved_at)
          ) : (
            <span className={styles.muted}>Not applicable (not provider data)</span>
          )}
        </dd>
        <dt>Recorded in RUMIN</dt>
        <dd>
          {item.recorded_at ? (
            formatDateTime(item.recorded_at)
          ) : (
            <span className={styles.muted}>Not recorded</span>
          )}
        </dd>
      </dl>
    </li>
  );
}

function Qualifiers({ edge }: { edge: GraphEdgeDetail }) {
  const q = edge.qualifiers;
  const rows = [
    q.polarity && { label: "Assumed direction", value: POLARITY_TEXT[q.polarity] ?? q.polarity },
    q.strength && { label: "Assumed strength", value: STRENGTH_TEXT[q.strength] ?? q.strength },
    q.evidence_level && { label: "Curated evidence level", value: q.evidence_level },
    q.rationale && { label: "Rationale", value: q.rationale },
    q.stated_difference && { label: "How they differ", value: q.stated_difference },
  ].filter(Boolean) as { label: string; value: string }[];
  if (!rows.length) return null;
  return (
    <section className={styles.section} aria-label="Stated qualifiers">
      <h3 className={styles.sectionTitle}>As the source states it</h3>
      <dl className={styles.facts}>
        {rows.map((row) => (
          <FactPair key={row.label} label={row.label}>
            {row.value}
          </FactPair>
        ))}
      </dl>
    </section>
  );
}

function FactPair({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <>
      <dt>{label}</dt>
      <dd>{children}</dd>
    </>
  );
}

function EdgeBody({
  edge,
  onSelect,
  onClose,
}: {
  edge: GraphEdgeDetail;
  onSelect: (selection: Selection) => void;
  onClose: () => void;
}) {
  return (
    <div className={styles.details}>
      <header className={styles.header}>
        <p className={styles.kind}>
          <EvidenceSwatch status={edge.evidence_status} width={20} arrow={edge.directed} />
          {edge.category === "economic" ? "Economic relationship" : "Structural link"}
        </p>
        <button type="button" className={styles.close} onClick={onClose} aria-label="Close details">
          <Icon name="close" size={14} />
        </button>
        <h2 className={styles.edgeTitle}>
          <NodeButton node={edge.source_node} onSelect={onSelect} />
          <span className={styles.verb}>
            {edge.label} {edge.directed ? "→" : "↔"}
          </span>
          <NodeButton node={edge.target_node} onSelect={onSelect} />
        </h2>
        <div className={styles.badges}>
          <Badge tone="outline" icon={<EvidenceSwatch status={edge.evidence_status} width={16} />}>
            {edge.evidence_status_label}
          </Badge>
          {edge.is_illustrative && (
            <Badge tone="warning" icon={<Icon name="alert" size={11} />}>
              Illustrative — sample network
            </Badge>
          )}
          {edge.historical && <Badge tone="neutral">Historical</Badge>}
          {edge.quality_status === "warning" && (
            <Badge tone="warning" icon={<Icon name="alert" size={11} />}>
              Flagged for review
            </Badge>
          )}
        </div>
      </header>

      <section className={styles.section} aria-label="Why this connection exists">
        <h3 className={styles.sectionTitle}>Why this connection exists</h3>
        <p className={styles.description}>{edge.explanation}</p>
      </section>

      <section className={styles.section} aria-label="Evidence status">
        <h3 className={styles.sectionTitle}>
          <span className={styles.inline}>
            <EvidenceSwatch status={edge.evidence_status} width={22} />
            {edge.evidence_status_label}
          </span>
        </h3>
        <p className={styles.note}>{edge.evidence_status_definition}</p>
      </section>

      <Qualifiers edge={edge} />

      <section className={styles.section} aria-label="Evidence records">
        <h3 className={styles.sectionTitle}>
          Evidence <span className={styles.count}>{edge.evidence.length}</span>
        </h3>
        {edge.evidence.length === 0 ? (
          <p className={styles.warning}>
            <Icon name="alert" size={14} /> No evidence record is attached to this edge.
          </p>
        ) : (
          <ol className={styles.list}>
            {edge.evidence.map((item, index) => (
              <EvidenceRecord
                key={`${item.rule}-${item.source_record_id}`}
                item={item}
                index={index}
              />
            ))}
          </ol>
        )}
      </section>

      <section className={styles.section} aria-label="Validity">
        <h3 className={styles.sectionTitle}>When it applies</h3>
        <p className={styles.note}>
          {edge.valid_from || edge.valid_to ? (
            <>
              {edge.valid_from ? `From ${formatCalendarDate(edge.valid_from)}` : "Start not stated"}
              {" · "}
              {edge.valid_to ? `until ${formatCalendarDate(edge.valid_to)}` : "no end stated"}
              {edge.historical ? " — this period has ended." : ""}
            </>
          ) : (
            "No validity period is stated: the source does not say when the relationship began or ends."
          )}
        </p>
      </section>

      <section className={styles.section} aria-label="Limitations">
        <h3 className={styles.sectionTitle}>What it does not mean</h3>
        <p className={styles.note}>{edge.caveat}</p>
        <p className={styles.note}>
          <span className={styles.muted}>Meaning of “{edge.label}”: </span>
          {edge.type_description}
        </p>
      </section>

      <p className={styles.footnote}>
        Edge <span className="mono">{edge.id}</span> · type{" "}
        <span className="mono">{edge.type}</span> · in the graph since build #{edge.first_build_id}
        {", last changed in build #"}
        {edge.changed_build_id}.
      </p>
    </div>
  );
}

export function EdgePanel({
  edgeId,
  onSelect,
  onClose,
}: {
  edgeId: string;
  onSelect: (selection: Selection) => void;
  onClose: () => void;
}) {
  const resource = useApiResource(`graph-edge:${edgeId}`, () => graphApi.edge(edgeId));
  if (resource.status === "loading") {
    return <LoadingState label="Loading the relationship's evidence…" lines={6} />;
  }
  if (resource.status === "error") {
    return (
      <div className={styles.details}>
        <ErrorState
          error={resource.error}
          title="This relationship's evidence could not be loaded"
          onRetry={resource.reload}
        />
      </div>
    );
  }
  return <EdgeBody edge={resource.data} onSelect={onSelect} onClose={onClose} />;
}
