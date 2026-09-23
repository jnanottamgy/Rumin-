/**
 * The five kinds of knowledge RUMIN distinguishes. Every value shown in the product is
 * labelled with one of these, using the same glyph everywhere — shape, not colour, so
 * the distinction survives colour-blindness, greyscale print and forced-colours mode.
 */
import { cx } from "@/lib/cx";
import styles from "./EpistemicBadge.module.css";

export type EpistemicCategory =
  | "observation"
  | "assumption"
  | "scenario_input"
  | "simulated_output"
  | "uncertainty";

export const EPISTEMIC: Record<
  EpistemicCategory,
  { label: string; letter: string; description: string }
> = {
  observation: {
    label: "Observation",
    letter: "A",
    description: "Historical data collected from a cited source.",
  },
  assumption: {
    label: "Assumption",
    letter: "B",
    description: "A rule, parameter or relationship defined by the model.",
  },
  scenario_input: {
    label: "Scenario input",
    letter: "C",
    description: "A value you change to explore a “what if”.",
  },
  simulated_output: {
    label: "Simulated output",
    letter: "D",
    description: "A result computed by a simulation engine.",
  },
  uncertainty: {
    label: "Uncertainty",
    letter: "E",
    description: "The limits and ranges attached to any of the above.",
  },
};

export const EPISTEMIC_ORDER: readonly EpistemicCategory[] = [
  "observation",
  "assumption",
  "scenario_input",
  "simulated_output",
  "uncertainty",
];

export function EpistemicGlyph({
  category,
  size = 12,
}: {
  category: EpistemicCategory;
  size?: number;
}) {
  return (
    <svg
      className={styles.glyph}
      data-category={category}
      width={size}
      height={size}
      viewBox="0 0 12 12"
      aria-hidden="true"
      focusable="false"
    >
      {category === "observation" && <circle cx="6" cy="6" r="4.2" className={styles.fill} />}
      {category === "assumption" && <circle cx="6" cy="6" r="4" className={styles.stroke} />}
      {category === "scenario_input" && (
        <path d="M6 1.2 10.8 6 6 10.8 1.2 6Z" className={styles.accentFill} />
      )}
      {category === "simulated_output" && (
        <>
          <rect x="1.8" y="1.8" width="8.4" height="8.4" className={styles.stroke} />
          <path d="M1.8 10.2 10.2 1.8M1.8 6 6 1.8M6 10.2 10.2 6" className={styles.hatch} />
        </>
      )}
      {category === "uncertainty" && (
        <path
          d="M1 4.6c1.6-1.6 3.2 1.6 5 0s3.4-1.6 5 0M1 8c1.6-1.6 3.2 1.6 5 0s3.4-1.6 5 0"
          className={styles.stroke}
        />
      )}
    </svg>
  );
}

export function EpistemicBadge({
  category,
  suffix,
  className,
}: {
  category: EpistemicCategory;
  suffix?: string;
  className?: string;
}) {
  const { label, description } = EPISTEMIC[category];
  return (
    <span className={cx(styles.badge, className)} data-category={category} title={description}>
      <EpistemicGlyph category={category} />
      <span>
        {label}
        {suffix && <span className={styles.suffix}> · {suffix}</span>}
      </span>
    </span>
  );
}
