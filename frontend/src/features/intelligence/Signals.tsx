/**
 * Signals: defined calculations, each shown with its answer and with how it was reached —
 * definition, method, inputs, period, the thresholds it used, its evidence and its
 * limitations. A signal is not a score; when the data are too short or the calculation
 * is undefined, it says so.
 */
import { cx } from "@/lib/cx";
import { formatRounded, isDecimalString } from "@/lib/decimal";
import type { InsightFact, IntelligenceSignal, SignalSpec } from "@/types/api";
import { GradeMark, RefLinks } from "./Evidence";
import { SIGNAL_LEVEL_WORD } from "./format";
import styles from "./Intelligence.module.css";

function value(fact: InsightFact): string {
  if (fact.value === null) return "—";
  if (!isDecimalString(fact.value)) return fact.value;
  const unit =
    fact.unit === "percentage_points" ? "pp" : fact.unit === "percent" ? "%" : (fact.unit ?? "");
  return `${formatRounded(fact.value, 4)}${unit && unit !== "count" ? ` ${unit}` : ""}`;
}

export function SignalCard({ signal, spec }: { signal: IntelligenceSignal; spec?: SignalSpec }) {
  const thresholds = Object.entries(signal.thresholds);
  return (
    <article className={styles.signal} aria-label={signal.name}>
      <header className={styles.signalHead}>
        <h4 className={styles.signalName}>{signal.name}</h4>
        <p className={cx(styles.signalLevel, signal.status !== "computed" && styles.muted)}>
          {signal.level_label ?? SIGNAL_LEVEL_WORD[signal.status] ?? signal.status}
        </p>
      </header>
      <p className={styles.signalSummary}>{signal.summary}</p>
      {signal.values.length > 0 && (
        <table className={styles.facts}>
          <tbody>
            {signal.values.map((fact) => (
              <tr key={fact.label}>
                <th scope="row">{fact.label}</th>
                <td className="tabular">{value(fact)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p className={styles.signalMeta}>
        <span>{signal.period.label}</span>
        <GradeMark grade={signal.evidence.grade} statement={signal.evidence.statement} compact />
      </p>
      <details className={styles.fold}>
        <summary>How it is computed</summary>
        {spec && (
          <dl className={styles.method}>
            <dt>Question</dt>
            <dd>{spec.question}</dd>
            <dt>Definition</dt>
            <dd>{spec.definition}</dd>
            <dt>Calculation</dt>
            <dd>{spec.method}</dd>
            <dt>Inputs</dt>
            <dd>{spec.inputs}</dd>
          </dl>
        )}
        {thresholds.length > 0 && (
          <p className={styles.muted}>
            Thresholds used:{" "}
            {thresholds.map(([name, item]) => `${name.replaceAll("_", " ")} ${item}`).join(", ")}.
          </p>
        )}
        <RefLinks refs={signal.inputs} />
        <ul className={styles.plainList}>
          {signal.limitations.map((item) => (
            <li key={item} className={styles.muted}>
              {item}
            </li>
          ))}
        </ul>
      </details>
    </article>
  );
}

export function SignalGrid({
  signals,
  specs,
}: {
  signals: readonly IntelligenceSignal[];
  specs: readonly SignalSpec[];
}) {
  return (
    <div className={styles.signals}>
      {signals.map((signal) => (
        <SignalCard
          key={`${signal.id}:${signal.subject.id}`}
          signal={signal}
          spec={specs.find((item) => item.id === signal.id)}
        />
      ))}
    </div>
  );
}
