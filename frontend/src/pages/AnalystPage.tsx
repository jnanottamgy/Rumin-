import { useEffect } from "react";
import { Badge } from "@/components/Badge";
import { EpistemicBadge } from "@/components/EpistemicBadge";
import { Icon } from "@/components/Icon";
import { PageHeader } from "@/components/PageHeader";
import { Panel } from "@/components/Panel";
import { StatusIndicator } from "@/components/StatusIndicator";
import { useApiResource } from "@/hooks/useApiResource";
import { api } from "@/services/api";
import styles from "./AnalystPage.module.css";

const EXAMPLE_QUESTIONS = [
  "Which assumptions connect the Brent crude price to Aerisca Airways?",
  "Why does the model treat the RBI policy rate's effect on bank revenue as mixed?",
  "Which inputs of my oil-shock scenario drove the largest simulated change, and how uncertain is it?",
];

const PRINCIPLES = [
  {
    title: "Grounded in RUMIN's own data",
    text: "Answers draw on the knowledge graph, scenario inputs and simulation runs — not on unstated knowledge.",
  },
  {
    title: "Every claim labelled",
    text: "Each statement says whether it rests on an observation, an assumption, a scenario input or a simulated output.",
  },
  {
    title: "Sources cited",
    text: "Answers link to the entities, relationships and datasets they use, with provenance.",
  },
  {
    title: "No predictions or advice",
    text: "It explains model behaviour. It does not forecast markets or give investment advice.",
  },
];

/**
 * The AI Analyst entry point. Nothing on this page calls a model: it describes what
 * the analyst will do, and the composer is disabled with an explanation.
 */
export function AnalystPage() {
  const system = useApiResource("system", () => api.system());
  const capability = system.data?.capabilities.find((item) => item.id === "ai_analyst");

  useEffect(() => {
    document.title = "AI Analyst — RUMIN";
  }, []);

  return (
    <div className={styles.page}>
      <PageHeader
        eyebrow="AI Analyst · Planned for Phase 7"
        title="Ask questions about the model"
        description="A future assistant that explains RUMIN's assumptions and simulated outputs in plain language — grounded in the network, with every claim labelled and sourced."
        meta={
          <StatusIndicator
            tone="planned"
            label="Not available in this build"
            detail={capability?.note ?? "No AI model is connected."}
          />
        }
      />

      <div className={styles.grid}>
        <Panel title="Preview of the conversation" eyebrow="Interface">
          <div className={styles.transcript} aria-hidden="true">
            <p className={styles.placeholderLine} />
            <p className={styles.placeholderLine} />
            <p className={styles.placeholderLineShort} />
          </div>
          <form className={styles.composer} onSubmit={(event) => event.preventDefault()}>
            <label htmlFor="analyst-question" className="visually-hidden">
              Question for the AI Analyst (not available yet)
            </label>
            <textarea
              id="analyst-question"
              rows={3}
              disabled
              placeholder="The AI Analyst is not connected in this build. Nothing you type here would be sent anywhere."
            />
            <div className={styles.composerFooter}>
              <Badge tone="outline">No model connected · no requests are made</Badge>
              <button type="submit" disabled className={styles.send}>
                Ask <Icon name="arrowRight" size={14} />
              </button>
            </div>
          </form>
        </Panel>

        <div className={styles.side}>
          <Panel title="How it will stay honest" eyebrow="Design principles">
            <ol className={styles.principles}>
              {PRINCIPLES.map((principle) => (
                <li key={principle.title}>
                  <strong>{principle.title}</strong>
                  <span>{principle.text}</span>
                </li>
              ))}
            </ol>
          </Panel>
          <Panel title="Questions it is being designed for" eyebrow="Examples">
            <ul className={styles.examples}>
              {EXAMPLE_QUESTIONS.map((question) => (
                <li key={question}>“{question}”</li>
              ))}
            </ul>
            <p className={styles.dependency}>
              Answers about simulated outputs depend on the simulation engine (Phase 4); every
              answer will distinguish <EpistemicBadge category="assumption" /> from{" "}
              <EpistemicBadge category="simulated_output" />.
            </p>
          </Panel>
        </div>
      </div>
    </div>
  );
}
