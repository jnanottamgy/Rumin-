/**
 * The evidence margin: the sources an answer cites, set beside it in the order they are
 * first cited. A citation in the text ([E2]) and its source are linked both ways — hovering
 * or focusing one marks the other — so a reader can check every figure without leaving the
 * answer. Each source says what kind of knowledge it is (by a mark and a word, never colour
 * alone), where it comes from, for which period, when it was read, in which unit, and — for
 * simulations — which models, versions and assumptions produced it.
 */
import { Link } from "react-router";
import { cx } from "@/lib/cx";
import { formatExact, isDecimalString } from "@/lib/decimal";
import { formatDateTime } from "@/lib/format";
import type { AnalystEvidence, AnalystKnowledge } from "@/types/api";
import styles from "./Analyst.module.css";
import { EVIDENCE_STATUS, internalLink, KNOWLEDGE } from "./format";

export type Highlight = { active: string | null; setActive: (id: string | null) => void };

function Glyph({ children }: { children: React.ReactNode }) {
  return (
    <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true" className={styles.mark}>
      {children}
    </svg>
  );
}

/**
 * A small mark per kind of knowledge: shape, not colour, tells them apart. The shapes are
 * RUMIN's knowledge labels (docs/design-system.md): a filled circle is an observation, a
 * ring an assumption, a filled square a person's figure, a hatched square a simulated
 * result (dashed when it is a preview, not stored); an open square is a RUMIN record.
 */
export function KnowledgeMark({ kind }: { kind: AnalystKnowledge }) {
  switch (kind) {
    case "observed":
      return (
        <Glyph>
          <circle cx="5" cy="5" r="4" fill="currentColor" />
        </Glyph>
      );
    case "record":
      return (
        <Glyph>
          <rect x="1.5" y="1.5" width="7" height="7" fill="none" stroke="currentColor" />
        </Glyph>
      );
    case "relationship":
      return (
        <Glyph>
          <circle cx="2" cy="5" r="1.6" fill="currentColor" />
          <circle cx="8" cy="5" r="1.6" fill="currentColor" />
          <path d="M3 5h4" stroke="currentColor" />
        </Glyph>
      );
    case "finding":
      return (
        <Glyph>
          <path d="M5 1 9 9H1z" fill="currentColor" />
        </Glyph>
      );
    case "user_input":
      return (
        <Glyph>
          <rect x="1" y="1" width="8" height="8" fill="currentColor" />
        </Glyph>
      );
    case "assumption":
      return (
        <Glyph>
          <circle cx="5" cy="5" r="3.5" fill="none" stroke="currentColor" />
        </Glyph>
      );
    case "simulated":
      return (
        <Glyph>
          <rect x="1.5" y="1.5" width="7" height="7" fill="none" stroke="currentColor" />
          <path d="M1.5 6.5 6.5 1.5M3.5 8.5l5-5" stroke="currentColor" />
        </Glyph>
      );
    default:
      return (
        <Glyph>
          <rect
            x="1.5"
            y="1.5"
            width="7"
            height="7"
            fill="none"
            stroke="currentColor"
            strokeDasharray="1.5 1.5"
          />
          <path d="M1.5 6.5 6.5 1.5M3.5 8.5l5-5" stroke="currentColor" />
        </Glyph>
      );
  }
}

/** Citation chips for one [E1, E4] group, linked to the margin. */
export function Citations({
  ids,
  evidence,
  highlight,
  prefix,
}: {
  ids: readonly string[];
  evidence: Map<string, AnalystEvidence>;
  highlight: Highlight;
  prefix: string;
}) {
  return (
    <span className={styles.citations}>
      {ids.map((id) => {
        const item = evidence.get(id);
        return (
          <a
            key={id}
            href={`#${prefix}${id}`}
            className={cx(
              styles.cite,
              highlight.active === id && styles.citeActive,
              !item && styles.citeMissing,
            )}
            aria-label={item ? `Source ${id}: ${item.title}` : `Source ${id} (missing)`}
            onMouseEnter={() => highlight.setActive(id)}
            onMouseLeave={() => highlight.setActive(null)}
            onFocus={() => highlight.setActive(id)}
            onBlur={() => highlight.setActive(null)}
            onClick={(event) => {
              const target = event.currentTarget.ownerDocument.getElementById(
                event.currentTarget.getAttribute("href")?.slice(1) ?? "",
              );
              if (target) {
                event.preventDefault();
                target.scrollIntoView({ block: "nearest" });
                target.focus({ preventScroll: true });
              }
            }}
          >
            {id}
          </a>
        );
      })}
    </span>
  );
}

function valueText(value: string): string {
  return isDecimalString(value) ? formatExact(value) : value;
}

function Values({ values }: { values: Record<string, string> }) {
  const entries = Object.entries(values);
  if (!entries.length) return null;
  return (
    <dl className={styles.values}>
      {entries.slice(0, 24).map(([key, value]) => (
        <div key={key}>
          <dt>{key.replaceAll("_", " ")}</dt>
          <dd className="tabular">{valueText(value)}</dd>
        </div>
      ))}
      {entries.length > 24 && (
        <div>
          <dt>and</dt>
          <dd>{entries.length - 24} more values</dd>
        </div>
      )}
    </dl>
  );
}

export function EvidenceCard({
  item,
  highlight,
  prefix,
}: {
  item: AnalystEvidence;
  highlight: Highlight;
  prefix: string;
}) {
  const kind = KNOWLEDGE[item.kind];
  const facts: string[] = [];
  if (item.period) facts.push(item.period);
  if (item.unit) facts.push(item.unit);
  if (item.currency) facts.push(item.currency);
  const status = item.evidence_status
    ? (EVIDENCE_STATUS[item.evidence_status] ?? item.evidence_status)
    : null;
  const provenance = Object.entries(item.provenance ?? {});
  return (
    <li
      id={`${prefix}${item.id}`}
      tabIndex={-1}
      className={cx(styles.source, highlight.active === item.id && styles.sourceActive)}
      onMouseEnter={() => highlight.setActive(item.id)}
      onMouseLeave={() => highlight.setActive(null)}
    >
      <p className={styles.sourceHead}>
        <span className={styles.sourceId}>{item.id}</span>
        <span className={styles.sourceKind} title={kind.note}>
          <KnowledgeMark kind={item.kind} />
          {kind.label}
        </span>
      </p>
      <p className={styles.sourceTitle}>
        {internalLink(item.source.link) ? (
          <Link to={item.source.link}>{item.title}</Link>
        ) : (
          item.title
        )}
      </p>
      {facts.length > 0 && <p className={styles.sourceFacts}>{facts.join(", ")}</p>}
      {(status || item.grade) && (
        <p className={styles.sourceFacts}>
          {status && <>Evidence status: {status}</>}
          {item.grade && <>Evidence grade: {item.grade} (the weakest step, not a probability)</>}
        </p>
      )}
      <details className={styles.sourceMore}>
        <summary>Details</summary>
        {item.detail && <p>{item.detail}</p>}
        <Values values={item.values ?? {}} />
        {(item.models?.length ?? 0) > 0 && (
          <p>
            Models: <span className="mono">{item.models?.join(", ")}</span>
          </p>
        )}
        {(item.assumptions?.length ?? 0) > 0 && (
          <ul className={styles.assumptions}>
            {item.assumptions?.map((text) => (
              <li key={text}>{text}</li>
            ))}
          </ul>
        )}
        {provenance.length > 0 && (
          <dl className={styles.values}>
            {provenance.map(([key, value]) => (
              <div key={key}>
                <dt>{key.replaceAll("_", " ")}</dt>
                <dd>{value}</dd>
              </div>
            ))}
          </dl>
        )}
        <p className={styles.sourceFacts}>
          Read {formatDateTime(item.retrieved_at)} by <span className="mono">{item.tool}</span>
          {item.as_of && <>; data as of {item.as_of}</>}
        </p>
      </details>
    </li>
  );
}

export function EvidenceMargin({
  cited,
  others,
  highlight,
  prefix,
}: {
  cited: AnalystEvidence[];
  others: AnalystEvidence[];
  highlight: Highlight;
  prefix: string;
}) {
  return (
    <aside className={styles.margin} aria-label="Sources for this answer">
      <p className={styles.marginTitle}>
        Sources <span className={styles.count}>{cited.length}</span>
      </p>
      {cited.length === 0 ? (
        <p className={styles.muted}>This answer cites no stored record.</p>
      ) : (
        <ol className={styles.sources}>
          {cited.map((item) => (
            <EvidenceCard key={item.id} item={item} highlight={highlight} prefix={prefix} />
          ))}
        </ol>
      )}
      {others.length > 0 && (
        <details className={styles.others}>
          <summary>Also read, not cited ({others.length})</summary>
          <ol className={styles.sources}>
            {others.map((item) => (
              <EvidenceCard key={item.id} item={item} highlight={highlight} prefix={prefix} />
            ))}
          </ol>
        </details>
      )}
    </aside>
  );
}
