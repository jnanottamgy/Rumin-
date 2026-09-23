/**
 * What kind of knowledge each simulation value is. The engine labels every input and
 * output; the page shows the label with one glyph per kind — shape, not colour, so the
 * distinction survives colour-blindness, greyscale print and forced colours.
 *
 * Circles and squares split what is *given* from what is *calculated*:
 * filled circle = historical data, filled square = a figure you entered, ring = an
 * assumption, sky diamond = a scenario change (the one thing you vary); open square =
 * derived by the model from the inputs, hatched square = simulated under the scenario.
 */
import styles from "./Simulation.module.css";

export type KnowledgeKind =
  | "historical_data"
  | "user_input"
  | "assumption"
  | "scenario_input"
  | "setting"
  | "derived"
  | "simulated";

export const KNOWLEDGE: Record<KnowledgeKind, { label: string; description: string }> = {
  historical_data: {
    label: "Historical data",
    description: "A value RUMIN stores from a cited source, with its period and licence.",
  },
  user_input: {
    label: "Your figure",
    description: "A figure you entered about the company. RUMIN does not check it.",
  },
  assumption: {
    label: "Assumption",
    description: "A parameter of the model: stated, with a default and a rationale.",
  },
  scenario_input: {
    label: "Scenario change",
    description: "The change you are exploring — the one thing the scenario varies.",
  },
  setting: { label: "Setting", description: "How the calculation is run, e.g. its horizon." },
  derived: {
    label: "Derived",
    description: "Calculated from the inputs alone; the same with or without the scenario.",
  },
  simulated: {
    label: "Simulated",
    description:
      "Calculated under the scenario: a result of the stated assumptions, not a forecast.",
  },
};

export const KNOWLEDGE_ORDER: readonly KnowledgeKind[] = [
  "scenario_input",
  "historical_data",
  "user_input",
  "assumption",
  "derived",
  "simulated",
];

/** Maps the API's labels (inputs: `knowledge`; outputs: `kind`) onto the glyph set. */
export function knowledgeOf(value: string): KnowledgeKind {
  if (value === "simulated_output") return "simulated";
  return value in KNOWLEDGE ? (value as KnowledgeKind) : "derived";
}

export function KnowledgeGlyph({ kind, size = 12 }: { kind: KnowledgeKind; size?: number }) {
  return (
    <svg
      className={styles.knowledgeGlyph}
      data-kind={kind}
      width={size}
      height={size}
      viewBox="0 0 12 12"
      aria-hidden="true"
      focusable="false"
    >
      {kind === "historical_data" && <circle cx="6" cy="6" r="4.2" className={styles.glyphFill} />}
      {kind === "user_input" && (
        <rect x="2" y="2" width="8" height="8" className={styles.glyphFill} />
      )}
      {kind === "assumption" && <circle cx="6" cy="6" r="4" className={styles.glyphStroke} />}
      {kind === "scenario_input" && (
        <path d="M6 1.2 10.8 6 6 10.8 1.2 6Z" className={styles.glyphAccent} />
      )}
      {kind === "setting" && <path d="M2.2 6h7.6" className={styles.glyphStroke} />}
      {kind === "derived" && (
        <rect x="2" y="2" width="8" height="8" className={styles.glyphStroke} />
      )}
      {kind === "simulated" && (
        <>
          <rect x="1.8" y="1.8" width="8.4" height="8.4" className={styles.glyphStroke} />
          <path d="M1.8 10.2 10.2 1.8M1.8 6 6 1.8M6 10.2 10.2 6" className={styles.glyphHatch} />
        </>
      )}
    </svg>
  );
}

/** A glyph with its label, e.g. in lists and tables. */
export function KnowledgeLabel({ kind }: { kind: KnowledgeKind }) {
  return (
    <span className={styles.knowledgeLabel} title={KNOWLEDGE[kind].description}>
      <KnowledgeGlyph kind={kind} />
      {KNOWLEDGE[kind].label}
    </span>
  );
}

/** The key to the glyphs, shown once on the page. */
export function KnowledgeKey() {
  return (
    <dl className={styles.knowledgeKey} aria-label="How values are labelled">
      {KNOWLEDGE_ORDER.map((kind) => (
        <div key={kind}>
          <dt>
            <KnowledgeGlyph kind={kind} />
            {KNOWLEDGE[kind].label}
          </dt>
          <dd>{KNOWLEDGE[kind].description}</dd>
        </div>
      ))}
    </dl>
  );
}
