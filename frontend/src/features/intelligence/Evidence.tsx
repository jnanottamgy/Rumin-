/**
 * Evidence, shown the same way everywhere.
 *
 * - The **grade** of a finding is its weakest link. It is drawn as a line pattern with its
 *   word beside it — the knowledge graph's own patterns for relationship evidence (dashes
 *   for curated, dash-dot for assumed, dots for unverified), a heavy solid line for stored
 *   observations and short dashes for simulations — never by colour alone.
 * - The **chain** lists every link a finding rests on, in order: what was observed, how it
 *   was calculated, which relationships connect it, which records and simulations it cites
 *   and the thresholds that selected it. The link that sets the grade is marked.
 */
import { Link } from "react-router";
import { EVIDENCE_ENCODING } from "@/features/graph/encoding";
import { cx } from "@/lib/cx";
import { formatRounded, isDecimalString } from "@/lib/decimal";
import type { EvidenceGrade, EvidenceStep, InsightEvidence, IntelligenceRef } from "@/types/api";
import { BASIS, GRADE, refHref, refLabel } from "./format";
import styles from "./Intelligence.module.css";

export function GradeLine({ grade, width = 26 }: { grade: EvidenceGrade; width?: number }) {
  const spec = GRADE[grade];
  return (
    <svg
      className={styles.gradeLine}
      width={width}
      height="8"
      viewBox={`0 0 ${width} 8`}
      aria-hidden="true"
      focusable="false"
    >
      <line
        x1="1"
        y1="4"
        x2={width - 1}
        y2="4"
        stroke="currentColor"
        strokeWidth={spec.width}
        strokeDasharray={spec.dash ?? undefined}
        strokeLinecap={grade === "unverified" ? "round" : "butt"}
      />
    </svg>
  );
}

export function GradeMark({
  grade,
  statement,
  compact = false,
}: {
  grade: EvidenceGrade;
  statement?: string;
  compact?: boolean;
}) {
  return (
    <span className={cx(styles.grade, compact && styles.gradeCompact)} title={statement}>
      <GradeLine grade={grade} />
      <span>{GRADE[grade].label}</span>
    </span>
  );
}

function StatusLine({ status }: { status: string }) {
  const encoding = EVIDENCE_ENCODING[status as keyof typeof EVIDENCE_ENCODING];
  if (!encoding) return null;
  return (
    <span className={styles.status}>
      <svg width="22" height="8" viewBox="0 0 22 8" aria-hidden="true" focusable="false">
        <line
          x1="1"
          y1="4"
          x2="21"
          y2="4"
          stroke="currentColor"
          strokeWidth="1.6"
          strokeDasharray={encoding.dash ?? undefined}
          strokeLinecap={encoding.linecap}
        />
      </svg>
      {encoding.label}
    </span>
  );
}

export function RefLinks({
  refs,
  scenarios,
}: {
  refs: readonly IntelligenceRef[];
  scenarios?: ReadonlyMap<string, string>;
}) {
  const shown = refs.filter((ref) => ref.kind !== "calculation");
  if (!shown.length) return null;
  return (
    <ul className={styles.refs} aria-label="Records cited">
      {shown.map((ref) => {
        const href = refHref(ref, scenarios);
        const label = refLabel(ref);
        return (
          <li key={`${ref.kind}:${ref.id}`}>
            {href ? <Link to={href}>{label}</Link> : <span>{label}</span>}
          </li>
        );
      })}
    </ul>
  );
}

function stepValue(step: EvidenceStep): string | null {
  if (step.value === null || !isDecimalString(step.value)) return step.value;
  const unit = step.unit === "percentage_points" ? "pp" : step.unit === "percent" ? "%" : step.unit;
  return `${formatRounded(step.value, 6)}${unit ? ` ${unit}` : ""}`;
}

/** The signature element: every link a finding rests on, the weakest one marked. */
export function EvidenceChain({
  chain,
  evidence,
  scenarios,
}: {
  chain: readonly EvidenceStep[];
  evidence: InsightEvidence;
  scenarios?: ReadonlyMap<string, string>;
}) {
  return (
    <div className={styles.chainBlock}>
      <ol className={styles.chain} aria-label="Evidence chain">
        {chain.map((step, index) => {
          const weakest = index === evidence.weakest_step;
          const value = stepValue(step);
          return (
            <li
              // biome-ignore lint/suspicious/noArrayIndexKey: a chain is ordered and fixed
              key={index}
              className={cx(styles.link, styles[`basis_${step.basis}`], weakest && styles.weakest)}
            >
              <span className={styles.linkMark} aria-hidden="true" />
              <div className={styles.linkBody}>
                <p className={styles.linkHead}>
                  <span className={styles.basis}>{BASIS[step.basis]}</span>
                  {step.evidence_status && <StatusLine status={step.evidence_status} />}
                  {weakest && <span className={styles.setsGrade}>Sets the grade</span>}
                </p>
                <p className={styles.linkText}>{step.text}</p>
                {value && step.basis !== "relationship" && (
                  <p className={cx(styles.linkValue, "tabular")}>{value}</p>
                )}
                <RefLinks refs={step.refs} scenarios={scenarios} />
              </div>
            </li>
          );
        })}
      </ol>
      <p className={styles.gradeStatement}>
        <GradeMark grade={evidence.grade} />
        <span>{evidence.statement}</span>
      </p>
    </div>
  );
}
