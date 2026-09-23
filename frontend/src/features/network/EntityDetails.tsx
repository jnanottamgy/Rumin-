/**
 * Everything RUMIN knows about the selected entity — and what it does not know.
 * Relationships are listed with their evidence level; missing data is stated, not hidden.
 */
import { Badge } from "@/components/Badge";
import { EpistemicBadge } from "@/components/EpistemicBadge";
import { Icon } from "@/components/Icon";
import { formatFrequency } from "@/lib/format";
import type { Entity } from "@/types/api";
import styles from "./EntityDetails.module.css";
import {
  describeEffect,
  EVIDENCE_LABEL,
  KIND_ENCODING,
  POLARITY_LABEL,
  POLARITY_SYMBOL,
  STRENGTH_LABEL,
} from "./encoding";
import { KindGlyph } from "./KindGlyph";
import type { GraphEdge, GraphModel } from "./model";

function EntityLink({
  model,
  id,
  onSelect,
}: {
  model: GraphModel;
  id: string;
  onSelect: (id: string) => void;
}) {
  const node = model.nodeById.get(id);
  if (!node) return <span className="mono">{id}</span>;
  return (
    <button type="button" className={styles.entityLink} onClick={() => onSelect(id)}>
      <KindGlyph kind={node.kind} size={11} />
      {node.label}
    </button>
  );
}

function Facts({
  entity,
  model,
  onSelect,
}: {
  entity: Entity;
  model: GraphModel;
  onSelect: (id: string) => void;
}) {
  switch (entity.kind) {
    case "company":
      return (
        <dl className={styles.facts}>
          <dt>Industry</dt>
          <dd>
            <EntityLink model={model} id={entity.industry_id} onSelect={onSelect} />
          </dd>
          <dt>Country</dt>
          <dd>
            <EntityLink model={model} id={entity.country_id} onSelect={onSelect} />
          </dd>
          <dt>Financial data</dt>
          <dd className={styles.muted}>
            {entity.is_fictional
              ? "None — fictional company; no figures are stored"
              : "Not loaded (financial data arrives in Phase 2)"}
          </dd>
        </dl>
      );
    case "industry": {
      const members = (model.incident.get(entity.id) ?? []).filter(
        (edge) => edge.type === "in_industry",
      ).length;
      return (
        <dl className={styles.facts}>
          <dt>Classification</dt>
          <dd>
            {entity.classification_system} · Division{" "}
            <span className="mono">{entity.classification_code}</span>
          </dd>
          <dt>Sample companies</dt>
          <dd>{members}</dd>
        </dl>
      );
    }
    case "country":
      return (
        <dl className={styles.facts}>
          <dt>ISO code</dt>
          <dd className="mono">{entity.iso_alpha2}</dd>
          <dt>Currency</dt>
          <dd className="mono">{entity.currency_code}</dd>
        </dl>
      );
    case "economic_variable":
      return (
        <dl className={styles.facts}>
          <dt>Unit</dt>
          <dd>{entity.unit}</dd>
          <dt>Frequency</dt>
          <dd>{formatFrequency(entity.frequency)}</dd>
          <dt>Economy</dt>
          <dd>
            {entity.country_id ? (
              <EntityLink model={model} id={entity.country_id} onSelect={onSelect} />
            ) : (
              "Global benchmark"
            )}
          </dd>
          <dt>Observations</dt>
          <dd>
            <EpistemicBadge category="observation" suffix="none loaded (Phase 2)" />
          </dd>
        </dl>
      );
  }
}

function RelationshipItem({
  edge,
  model,
  selfId,
  onSelect,
}: {
  edge: GraphEdge;
  model: GraphModel;
  selfId: string;
  onSelect: (id: string) => void;
}) {
  const outgoing = edge.source === selfId;
  const otherId = outgoing ? edge.target : edge.source;
  const label = model.types.get(edge.type)?.label ?? edge.type;
  const data = edge.data;
  const sourceName = model.nodeById.get(edge.source)?.label ?? edge.source;
  const targetName = model.nodeById.get(edge.target)?.label ?? edge.target;
  const effect =
    data.category === "economic"
      ? describeEffect(data.type, data.polarity, sourceName, targetName)
      : null;

  return (
    <li className={styles.relationship}>
      {/* Reads as a sentence: "supplies Aerisca Airways" / "Anvaya Bank lends to this company". */}
      <p className={styles.relationshipLine}>
        {outgoing || !edge.directed ? (
          <>
            <span className={styles.direction}>{label}</span>
            <EntityLink model={model} id={otherId} onSelect={onSelect} />
          </>
        ) : (
          <>
            <EntityLink model={model} id={otherId} onSelect={onSelect} />
            <span className={styles.direction}>
              {label} this{" "}
              {KIND_ENCODING[model.nodeById.get(selfId)?.kind ?? "company"].label.toLowerCase()}
            </span>
          </>
        )}
      </p>
      {data.category === "economic" ? (
        <>
          <p className={styles.relationshipMeta}>
            {data.polarity !== "not_applicable" && (
              <span title={POLARITY_LABEL[data.polarity]}>
                {POLARITY_SYMBOL[data.polarity]} {POLARITY_LABEL[data.polarity]}
              </span>
            )}
            <span>{STRENGTH_LABEL[data.strength]}</span>
            <span>{EVIDENCE_LABEL[data.evidence_level]}</span>
          </p>
          {effect && <p className={styles.effect}>{effect}</p>}
          <p className={styles.rationale}>{data.rationale}</p>
        </>
      ) : (
        <p className={styles.relationshipMeta}>
          <span>Structural · derived from {data.derived_from}</span>
        </p>
      )}
    </li>
  );
}

export function EntityDetails({
  model,
  nodeId,
  onSelect,
  onClose,
}: {
  model: GraphModel;
  nodeId: string;
  onSelect: (id: string) => void;
  onClose: () => void;
}) {
  const node = model.nodeById.get(nodeId);
  if (!node) return null;
  const { entity } = node;
  const incident = model.incident.get(nodeId) ?? [];
  const economic = incident.filter((edge) => edge.category === "economic");
  const structural = incident.filter((edge) => edge.category === "structural");

  return (
    <article className={styles.details} aria-labelledby={`details-${nodeId}`}>
      <header className={styles.header}>
        <p className={styles.kind}>
          <KindGlyph kind={node.kind} />
          {KIND_ENCODING[node.kind].label}
        </p>
        <button
          type="button"
          className={styles.close}
          onClick={onClose}
          aria-label="Clear selection"
        >
          <Icon name="close" />
        </button>
        <h2 id={`details-${nodeId}`} className={styles.name}>
          {entity.name}
        </h2>
        <div className={styles.badges}>
          {entity.is_fictional ? (
            <Badge tone="outline">Fictional</Badge>
          ) : (
            <Badge tone="neutral">Real-world concept</Badge>
          )}
          <Badge tone="neutral">{node.degree} connections</Badge>
        </div>
      </header>

      <p className={styles.description}>{entity.description}</p>

      <Facts entity={entity} model={model} onSelect={onSelect} />

      {entity.reference && (
        <p className={styles.reference}>
          <span className={styles.referenceLabel}>Reference</span>
          {entity.reference}
          {entity.reference_url && (
            <>
              {" "}
              <a href={entity.reference_url} target="_blank" rel="noopener noreferrer">
                Source <Icon name="external" size={12} style={{ display: "inline" }} />
              </a>
            </>
          )}
        </p>
      )}

      <section className={styles.section}>
        <h3 className={styles.sectionTitle}>
          Economic relationships
          <EpistemicBadge category="assumption" />
        </h3>
        {economic.length ? (
          <ul className={styles.relationships}>
            {economic.map((edge) => (
              <RelationshipItem
                key={edge.id}
                edge={edge}
                model={model}
                selfId={nodeId}
                onSelect={onSelect}
              />
            ))}
          </ul>
        ) : (
          <p className={styles.muted}>No curated relationships in the sample dataset.</p>
        )}
      </section>

      {structural.length > 0 && (
        <section className={styles.section}>
          <h3 className={styles.sectionTitle}>Structural links</h3>
          <ul className={styles.relationships}>
            {structural.map((edge) => (
              <RelationshipItem
                key={edge.id}
                edge={edge}
                model={model}
                selfId={nodeId}
                onSelect={onSelect}
              />
            ))}
          </ul>
        </section>
      )}

      <footer className={styles.provenance}>
        Source: {model.dataset?.name ?? "unknown dataset"}
        {model.dataset ? ` v${model.dataset.version}` : ""}. Relationships are modelling
        assumptions, not empirical findings.
      </footer>
    </article>
  );
}
