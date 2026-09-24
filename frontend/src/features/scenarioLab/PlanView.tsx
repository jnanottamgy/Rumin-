/**
 * The plan: which models apply to the scenario and why, which change each model
 * simulates, what blocks execution, and the companies the knowledge graph ties to the
 * changed variables — marked with the model that simulates each tie, or "no model".
 */
import { Badge } from "@/components/Badge";
import { Icon } from "@/components/Icon";
import type { ScenarioPlan } from "@/types/api";
import { changeLabel, EVIDENCE_LABEL, MODEL_STATUS_LABEL } from "./format";
import styles from "./ScenarioLab.module.css";

export function PlanView({ plan }: { plan: ScenarioPlan }) {
  const errors = plan.issues.filter((issue) => issue.severity === "error");
  const warnings = plan.issues.filter((issue) => issue.severity === "warning");
  const titles = new Map(plan.models.map((model) => [model.model_id, model.title]));
  return (
    <div className={styles.planView}>
      <section className={styles.planStatus} data-executable={plan.executable ? "true" : "false"}>
        <Icon name={plan.executable ? "check" : "alert"} size={16} />
        <div>
          <p className={styles.planHeadline}>
            {plan.executable
              ? "Ready to execute"
              : `${errors.length === 1 ? "1 problem stops" : `${errors.length} problems stop`} execution`}
          </p>
          <p className={styles.caption}>
            Knowledge graph:{" "}
            {plan.graph.freshness === "not_built"
              ? "not built"
              : `build #${plan.graph.build_id} (${plan.graph.freshness})`}
            {plan.entity ? ` · ${plan.entity.name}` : " · no company chosen"}
          </p>
        </div>
      </section>

      {errors.length > 0 && (
        <ul className={styles.issueList} aria-label="Problems">
          {errors.map((issue) => (
            <li key={`${issue.code}-${issue.field}-${issue.message}`} data-severity="error">
              <Icon name="alert" size={12} />
              <span>{issue.message}</span>
            </li>
          ))}
        </ul>
      )}

      <section>
        <h3 className={styles.sectionTitle}>Changes and the models that simulate them</h3>
        <table className={styles.table}>
          <thead>
            <tr>
              <th scope="col">Change</th>
              <th scope="col">Simulated by</th>
            </tr>
          </thead>
          <tbody>
            {plan.changes.map((change) => (
              <tr key={change.variable_id}>
                <th scope="row">
                  {change.name}{" "}
                  <span className="tabular">{changeLabel(change.value, change.unit)}</span>
                </th>
                <td>
                  {change.modelled
                    ? change.models.map((id) => titles.get(id) ?? id).join(", ")
                    : (change.reason ?? "Not planned yet")}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section>
        <h3 className={styles.sectionTitle}>Every model, and why</h3>
        <ul className={styles.planModels}>
          {plan.models.map((model) => (
            <li key={model.model_id} data-status={model.status}>
              <div className={styles.modelRowHeader}>
                <p className={styles.modelTitle}>
                  {model.title} <span className={styles.laneVersion}>v{model.version}</span>
                </p>
                <Badge
                  tone={
                    model.status === "included"
                      ? "good"
                      : model.status === "blocked"
                        ? "warning"
                        : "outline"
                  }
                >
                  {MODEL_STATUS_LABEL[model.status]}
                </Badge>
              </div>
              <ul className={styles.reasons}>
                {model.reasons.map((reason) => (
                  <li key={reason}>{reason}</li>
                ))}
              </ul>
              {model.exposure.chains.length > 0 && (
                <p className={styles.caption}>
                  Graph exposure:{" "}
                  {model.exposure.chains
                    .map((chain) =>
                      chain
                        .map(
                          (edge) =>
                            `${edge.edge_type.replaceAll("_", " ")} (${EVIDENCE_LABEL[edge.evidence_status] ?? edge.evidence_status})`,
                        )
                        .join(" · "),
                    )
                    .join("; ")}
                </p>
              )}
            </li>
          ))}
        </ul>
      </section>

      {warnings.length > 0 && (
        <section>
          <h3 className={styles.sectionTitle}>Notes and cautions</h3>
          <ul className={styles.issueList}>
            {warnings.map((issue) => (
              <li key={`${issue.code}-${issue.field}-${issue.message}`} data-severity="warning">
                <Icon name="info" size={12} />
                <span>{issue.message}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {plan.affected && (
        <section>
          <h3 className={styles.sectionTitle}>Companies the graph ties to these changes</h3>
          <p className={styles.caption}>{plan.affected.note}</p>
          <table className={styles.table}>
            <thead>
              <tr>
                <th scope="col">Company</th>
                <th scope="col">Stated tie</th>
                <th scope="col">Simulated by</th>
              </tr>
            </thead>
            <tbody>
              {plan.affected.entities.flatMap((entry) =>
                entry.exposures.map((exposure, index) => (
                  <tr
                    key={`${entry.entity.key}-${exposure.changed_variable}-${exposure.relationship}-${exposure.exposed_variable}`}
                  >
                    {index === 0 && (
                      <th scope="row" rowSpan={entry.exposures.length}>
                        {entry.entity.name}
                        {entry.entity.nature === "fictional" && (
                          <span className={styles.rowNote}>fictional</span>
                        )}
                      </th>
                    )}
                    <td>
                      {plan.affected?.variables[`variable:${exposure.changed_variable}`] ??
                        exposure.changed_variable}
                      {exposure.via.length > 0 &&
                        ` → ${exposure.via.map((id) => plan.affected?.variables[`variable:${id}`] ?? id).join(" → ")}`}
                      {" · "}
                      {exposure.relationship.replaceAll("_", " ")}
                      {exposure.industry ? ` (via ${exposure.industry.name})` : ""}
                    </td>
                    <td>
                      {exposure.models.length ? (
                        exposure.models.map((id) => titles.get(id) ?? id).join(", ")
                      ) : (
                        <span className={styles.muted}>No model</span>
                      )}
                    </td>
                  </tr>
                )),
              )}
            </tbody>
          </table>
          {plan.affected.truncated && (
            <p className={styles.caption}>Showing the first {plan.affected.limit} companies.</p>
          )}
        </section>
      )}
    </div>
  );
}
