/**
 * The context column of the Scenario Lab: for the variables a scenario changes, what is
 * observed (A), what the model assumes (B), what has been simulated (D) and what is
 * uncertain (E). The inputs themselves (C) live in the editor.
 *
 * Nothing here computes an effect. The assumptions list is a lookup of the model's
 * relationships — not a result — and says so.
 */
import { Link } from "react-router";
import { EpistemicBadge } from "@/components/EpistemicBadge";
import {
  describeEffect,
  EVIDENCE_LABEL,
  POLARITY_SYMBOL,
  STRENGTH_LABEL,
} from "@/features/network/encoding";
import { KindGlyph } from "@/features/network/KindGlyph";
import type { GraphModel } from "@/features/network/model";
import styles from "./ScenarioContext.module.css";

function AssumptionsInScope({ model, variableIds }: { model: GraphModel; variableIds: string[] }) {
  if (variableIds.length === 0) {
    return (
      <p className={styles.muted}>Choose a variable to see what the model assumes about it.</p>
    );
  }
  return (
    <div className={styles.scope}>
      {variableIds.map((variableId) => {
        const variable = model.nodeById.get(variableId);
        const edges = (model.incident.get(variableId) ?? []).filter(
          (edge) => edge.category === "economic" && edge.source === variableId,
        );
        return (
          <div key={variableId} className={styles.variable}>
            <p className={styles.variableName}>
              <KindGlyph kind="economic_variable" />
              {variable?.label ?? variableId}
              <Link to={`/universe?focus=${variableId}`} className={styles.inUniverse}>
                View in Universe
              </Link>
            </p>
            {edges.length ? (
              <ul className={styles.edges}>
                {edges.map((edge) => {
                  const data = edge.data;
                  const target = model.nodeById.get(edge.target);
                  if (data.category !== "economic" || !target) return null;
                  const effect = describeEffect(
                    data.type,
                    data.polarity,
                    variable?.label ?? variableId,
                    target.label,
                  );
                  return (
                    <li key={edge.id}>
                      <p className={styles.edgeLine}>
                        <span className={styles.verb}>
                          {model.types.get(edge.type)?.label ?? edge.type}
                        </span>{" "}
                        <KindGlyph kind={target.kind} size={10} /> {target.label}
                      </p>
                      <p className={styles.edgeMeta}>
                        {POLARITY_SYMBOL[data.polarity]} {data.polarity} ·{" "}
                        {STRENGTH_LABEL[data.strength]} · {EVIDENCE_LABEL[data.evidence_level]}
                      </p>
                      {effect && <p className={styles.effect}>{effect}</p>}
                    </li>
                  );
                })}
              </ul>
            ) : (
              <p className={styles.muted}>No outgoing relationships in the model.</p>
            )}
          </div>
        );
      })}
    </div>
  );
}

export function ScenarioContext({
  model,
  variableIds,
}: {
  model: GraphModel | null;
  variableIds: string[];
}) {
  return (
    <div className={styles.context}>
      <section className={styles.block} aria-labelledby="scenario-outputs">
        <header className={styles.blockHeader}>
          <h3 id="scenario-outputs">Simulated outputs</h3>
          <EpistemicBadge category="simulated_output" />
        </header>
        <div className={styles.placeholder}>
          <p className={styles.placeholderTitle}>Not simulated</p>
          <p>
            This build has no simulation engine, so no effects have been computed. The engine is
            planned for Phase 4. RUMIN will not show projected effects until an engine has computed
            them.
          </p>
        </div>
      </section>

      <section className={styles.block} aria-labelledby="scenario-assumptions">
        <header className={styles.blockHeader}>
          <h3 id="scenario-assumptions">Model assumptions in scope</h3>
          <EpistemicBadge category="assumption" />
        </header>
        <p className={styles.note}>
          The model's direct relationships from the variables you change: where an effect could
          travel. This is a lookup of assumptions, not a result.
        </p>
        {model ? (
          <AssumptionsInScope model={model} variableIds={variableIds} />
        ) : (
          <p className={styles.muted}>The network could not be loaded.</p>
        )}
      </section>

      <section className={styles.block} aria-labelledby="scenario-observations">
        <header className={styles.blockHeader}>
          <h3 id="scenario-observations">Historical observations</h3>
          <EpistemicBadge category="observation" />
        </header>
        <p className={styles.muted}>
          RUMIN stores no observations for these variables themselves. Related historical series
          from cited sources, where they exist, are in the Data Explorer and linked to the variables
          in the knowledge graph.
        </p>
      </section>

      <section className={styles.block} aria-labelledby="scenario-uncertainty">
        <header className={styles.blockHeader}>
          <h3 id="scenario-uncertainty">Uncertainty</h3>
          <EpistemicBadge category="uncertainty" />
        </header>
        <p className={styles.muted}>
          Every relationship in the sample dataset is illustrative, and strengths are ordinal (weak,
          moderate, strong) rather than estimated. Future outputs will carry ranges and state the
          assumptions that produced them.
        </p>
      </section>
    </div>
  );
}
