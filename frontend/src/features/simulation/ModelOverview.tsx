/**
 * A model before any run: what it calculates, how a change travels through it (the
 * pathway from its definition, and whether the knowledge graph confirms the relationship
 * it relies on), its assumptions and limitations, and its equations.
 */
import { Badge } from "@/components/Badge";
import { StatusIndicator } from "@/components/StatusIndicator";
import type { SimulationModelDetail } from "@/types/api";
import { KnowledgeKey } from "./knowledge";
import { PathwayDiagram } from "./PathwayDiagram";
import { definitionPathway } from "./presentation";
import styles from "./Simulation.module.css";

export function ModelOverview({ model }: { model: SimulationModelDetail }) {
  const pathway = definitionPathway(model);
  const unconfirmed = model.transmission_rules.filter((rule) => !rule.graph_edge);
  return (
    <article className={styles.results} aria-labelledby="model-title">
      <header className={styles.resultsHeader}>
        <div>
          <h2 id="model-title" className={styles.resultsTitle}>
            {model.name}
          </h2>
          <p className={styles.resultsMeta}>
            Version {model.version}. {model.domain}.
          </p>
        </div>
        <Badge tone="outline">{model.status === "preview" ? "Preview" : model.status}</Badge>
      </header>
      <p className={styles.lead}>{model.description}</p>

      {model.graph_freshness !== "current" || unconfirmed.length > 0 ? (
        <StatusIndicator
          tone="warning"
          label={
            model.graph_freshness === "not_built"
              ? "The knowledge graph has not been built"
              : unconfirmed.length > 0
                ? "The knowledge graph does not confirm every relationship this model uses"
                : "The knowledge graph is older than its sources"
          }
          detail={
            unconfirmed.length > 0
              ? "Changes that need an unconfirmed relationship will be refused. Build the graph with make graph."
              : undefined
          }
        />
      ) : (
        <StatusIndicator
          tone="good"
          label={`The knowledge graph (build #${model.graph_build_id}) confirms the relationships this model uses`}
        />
      )}

      <PathwayDiagram
        nodes={pathway.nodes}
        links={pathway.links}
        animationKey={null}
        title="How a change travels through this model"
      />

      <p className={styles.emptyPrompt}>
        Enter the figures and the change to explore, then run the model. Every run is stored with
        its inputs, its calculation steps and the knowledge-graph snapshot it used.
      </p>

      <section>
        <h3 className={styles.figureTitle}>How values are labelled</h3>
        <KnowledgeKey />
      </section>

      <div className={styles.statementColumns}>
        <section>
          <h3 className={styles.figureTitle}>Assumptions</h3>
          <ol className={styles.statements}>
            {model.assumptions.map((item) => (
              <li key={item.id}>
                <span className="mono">{item.id}</span>
                <p>{item.text}</p>
              </li>
            ))}
          </ol>
        </section>
        <section>
          <h3 className={styles.figureTitle}>Limitations</h3>
          <ol className={styles.statements}>
            {model.limitations.map((item) => (
              <li key={item.id}>
                <span className="mono">{item.id}</span>
                <p>{item.text}</p>
              </li>
            ))}
          </ol>
        </section>
      </div>
    </article>
  );
}
