/**
 * The four kinds of analysis the Lab offers, stated plainly where each is used, with the
 * current one marked. Closed by default: the essentials stay on screen, the distinctions
 * are one click away.
 */
import styles from "./Analyses.module.css";

export type AnalysisKind = "scenario" | "stress" | "sensitivity" | "stochastic";

const KINDS: { id: AnalysisKind; name: string; where: string; text: string }[] = [
  {
    id: "scenario",
    name: "Scenario analysis",
    where: "Pathway, Months, the results panel",
    text: "One defined set of changes, evaluated once: the execution itself.",
  },
  {
    id: "stress",
    name: "Stress testing",
    where: "Stress",
    text: "The same changes at the adverse or extreme magnitudes you choose.",
  },
  {
    id: "sensitivity",
    name: "Sensitivity analysis",
    where: "Sensitivity",
    text: "One or two quantities moved over chosen values, everything else as executed. It shows how much a result depends on them, not how likely any value is.",
  },
  {
    id: "stochastic",
    name: "Stochastic analysis",
    where: "Uncertainty",
    text: "Many draws from distributions you state. The spread is conditional on those assumptions: not a forecast, and not the probability of any outcome.",
  },
];

export function AnalysisTypes({ current }: { current: AnalysisKind }) {
  const active = KINDS.find((kind) => kind.id === current);
  return (
    <details className={styles.types}>
      <summary>
        This is <strong>{active?.name.toLowerCase()}</strong> — how it differs from the other kinds
      </summary>
      <ul className={styles.typesList}>
        {KINDS.map((kind) => (
          <li key={kind.id} aria-current={kind.id === current ? "true" : undefined}>
            <span className={styles.typeName}>{kind.name}</span>
            <span className={styles.typeWhere}>In the Lab: {kind.where}</span>
            <span className={styles.typeText}>{kind.text}</span>
          </li>
        ))}
      </ul>
    </details>
  );
}
