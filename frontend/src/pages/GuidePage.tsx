/**
 * Getting started (Phase 10): what RUMIN is, and short starter tasks that each end in a
 * working page. Everything described here exists in this build; what does not exist is
 * said plainly under "Limits". Nothing blocks the way: the guide is a page to read, not a
 * tour to sit through.
 */
import { Link } from "react-router";
import { ROLE_LABEL, useAccess } from "@/app/session";
import { EPISTEMIC, EPISTEMIC_ORDER, EpistemicGlyph } from "@/components/EpistemicBadge";
import { Icon } from "@/components/Icon";
import { PageHeader } from "@/components/PageHeader";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import styles from "./GuidePage.module.css";

interface Task {
  id: string;
  title: string;
  why: string;
  steps: readonly string[];
  link: { to: string; label: string };
  /** Shown when the person's role cannot finish the task. */
  needsWrite?: string;
}

const TASKS: readonly Task[] = [
  {
    id: "network",
    title: "Explore the network",
    why: "How companies, industries, countries and economic variables connect, and why each link exists.",
    steps: [
      "In the Universe, select a company to see its links; the list view shows the same as a table.",
      "In the Graph, search for a name (try “Aerisca”), open its neighbourhood, and find paths between two entities.",
      "Open any relationship to read its evidence: what it rests on, and whether it is recorded or assumed.",
    ],
    link: {
      to: "/graph?focus=company%3Aco_aerisca_airways",
      label: "Open Aerisca Airways in the graph",
    },
  },
  {
    id: "scenario",
    title: "Run a what-if scenario",
    why: "What a change — crude oil, the rupee, a policy rate — does to a company, through the models that apply.",
    steps: [
      "Start from the template “Crude oil shock on an airline”.",
      "Choose the company and enter the figures the plan asks for: currency, annual revenue and operating costs, the jet fuel price, the exchange rate (typed, or taken from a stored series).",
      "Watch the live preview; the Plan tab says which models apply, why, and what is still missing. Nothing is stored yet.",
      "Save and execute: the execution is stored with its model runs, can be explained step by step and re-run exactly.",
      "Change a figure, execute again, and compare the two executions from the History tab.",
    ],
    link: { to: "/scenarios/new?template=crude_oil_airline", label: "Start from the template" },
    needsWrite:
      "Your role can follow every step up to saving; saving and executing need the analyst role.",
  },
  {
    id: "analyses",
    title: "Test how much a result depends on its inputs",
    why: "Sensitivity and uncertainty, computed again from a stored execution.",
    steps: [
      "On an executed scenario, the Sensitivity tab varies one quantity at a time, or two together on a grid.",
      "The Uncertainty tab draws the quantities from distributions you state (Monte Carlo) and shows the spread of the result, with its seed so it can be reproduced.",
      "The distributions are your assumptions, not estimates RUMIN has made.",
    ],
    link: { to: "/scenarios", label: "Open the Scenario Lab" },
    needsWrite: "Your role can read stored analyses; running new ones needs the analyst role.",
  },
  {
    id: "findings",
    title: "Read the findings",
    why: "What the stored data, the graph and stored executions say, each finding with the evidence it rests on.",
    steps: [
      "Open a finding to see its evidence chain and how strong that evidence is.",
      "Open an entity's dossier for its exposure, drivers, signals, history and sources.",
    ],
    link: { to: "/intelligence", label: "Open Financial Intelligence" },
  },
  {
    id: "analyst",
    title: "Ask the AI Analyst",
    why: "Questions about exposure, relationships, stored data, scenarios and findings.",
    steps: [
      "Pick a suggested question or write your own.",
      "Every figure in an answer cites the record it comes from; open the sources to check them.",
      "Your conversations are private to you.",
    ],
    link: { to: "/analyst", label: "Open the Analyst" },
  },
  {
    id: "provenance",
    title: "Check where the data came from",
    why: "Every stored value carries its source, licence, retrieval time and quality checks.",
    steps: [
      "In Data, open a series to see its source, licence, the response it came from, revisions and quality issues.",
      "In System, see which dataset is loaded and what this build can and cannot do.",
      "In Simulation, each model lists its equations, assumptions and the checks it passes (the verification register).",
    ],
    link: { to: "/data", label: "Open the Data Explorer" },
  },
];

const LIMITS: readonly string[] = [
  "The sample network is illustrative: its companies are fictional, and its relationships are recorded or assumed, not measured.",
  "Provider data is historical and never live; RUMIN has no live market data.",
  "Simulations are deterministic calculations under stated assumptions — not forecasts. Uncertainty comes only from distributions you state.",
  "The AI Analyst answers from RUMIN's records and says when it cannot; when a language model is configured, its answers are checked against the evidence they cite.",
  "Nothing in RUMIN is investment advice.",
];

export function GuidePage() {
  useDocumentTitle("Getting started");
  const { role, canWrite } = useAccess();

  return (
    <div className={styles.page}>
      <PageHeader
        eyebrow="Guide"
        title="Getting started"
        description="RUMIN maps how companies, industries and economic variables connect, runs what-if scenarios through registered models, and turns what it holds into findings with their evidence. These short tasks each end in a working page."
      />

      <section className={styles.section} aria-labelledby="guide-knowledge">
        <h2 id="guide-knowledge" className={styles.heading}>
          Five kinds of knowledge, always labelled
        </h2>
        <ul className={styles.kinds}>
          {EPISTEMIC_ORDER.map((category) => (
            <li key={category}>
              <EpistemicGlyph category={category} size={14} />
              <span>
                <strong>{EPISTEMIC[category].label}</strong> — {EPISTEMIC[category].description}
              </span>
            </li>
          ))}
        </ul>
      </section>

      <section className={styles.section} aria-labelledby="guide-tasks">
        <h2 id="guide-tasks" className={styles.heading}>
          Starter tasks
        </h2>
        <ol className={styles.tasks}>
          {TASKS.map((task) => (
            <li key={task.id} className={styles.task} aria-labelledby={`task-${task.id}`}>
              <h3 id={`task-${task.id}`} className={styles.taskTitle}>
                {task.title}
              </h3>
              <p className={styles.why}>{task.why}</p>
              <ol className={styles.steps}>
                {task.steps.map((step) => (
                  <li key={step}>{step}</li>
                ))}
              </ol>
              {task.needsWrite && !canWrite && <p className={styles.note}>{task.needsWrite}</p>}
              <Link className={styles.taskLink} to={task.link.to}>
                {task.link.label}
                <Icon name="arrowRight" size={14} />
              </Link>
            </li>
          ))}
        </ol>
      </section>

      <div className={styles.columns}>
        <section className={styles.section} aria-labelledby="guide-role">
          <h2 id="guide-role" className={styles.heading}>
            What your role allows
          </h2>
          <p>
            You are signed in as {role ? <strong>{ROLE_LABEL[role].toLowerCase()}</strong> : "—"}.
          </p>
          <ul className={styles.plain}>
            <li>
              <strong>Viewer</strong>: reads everything in the workspace and previews scenarios;
              stores nothing.
            </li>
            <li>
              <strong>Analyst</strong>: also saves and executes scenarios, runs simulations and
              analyses, and changes their own work.
            </li>
            <li>
              <strong>Administrator</strong>: also changes anyone's work, and manages people from
              the account menu.
            </li>
          </ul>
        </section>

        <section className={styles.section} aria-labelledby="guide-limits">
          <h2 id="guide-limits" className={styles.heading}>
            Limits to keep in mind
          </h2>
          <ul className={styles.plain}>
            {LIMITS.map((limit) => (
              <li key={limit}>{limit}</li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  );
}
