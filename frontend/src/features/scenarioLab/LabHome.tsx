/**
 * The Lab's home: templates built on implemented models (and the ones not offered, with
 * the reason), and every saved scenario with its latest execution.
 */
import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router";
import { Badge } from "@/components/Badge";
import { Button, ButtonLink } from "@/components/Button";
import { Icon } from "@/components/Icon";
import { EmptyState, ErrorState, LoadingState } from "@/components/States";
import { useApiResource } from "@/hooks/useApiResource";
import { formatDateTime } from "@/lib/format";
import { api, labApi } from "@/services/api";
import type { EconomicVariable, ScenarioTemplateSummary } from "@/types/api";
import { changeLabel, compactMoney, percentValue, STATUS_LABEL } from "./format";
import styles from "./ScenarioLab.module.css";

const CATEGORY: Record<string, string> = {
  commodity: "Commodity",
  currency: "Currency",
  interest_rate: "Interest rate",
  energy_cost: "Energy cost",
  combined: "Combined",
};

interface Change {
  variable_id: string;
  change_type: string;
  value: string;
}

/**
 * A change as "Brent crude oil price +20 %", with the name and unit the variable declares
 * (a rate moves in percentage points, a price by a percentage or in its own unit).
 */
function changeText(change: Change, variables: ReadonlyMap<string, EconomicVariable>): string {
  const variable = variables.get(change.variable_id);
  const rule = variable?.scenario_rules.find((item) => item.change_type === change.change_type);
  const unit = rule?.unit_label ?? (change.change_type === "percent_change" ? "%" : "");
  return `${variable?.name ?? change.variable_id} ${changeLabel(change.value, unit)}`;
}

function TemplateCard({
  template,
  variables,
}: {
  template: ScenarioTemplateSummary;
  variables: ReadonlyMap<string, EconomicVariable>;
}) {
  return (
    <li className={styles.templateCard}>
      <p className={styles.templateCategory}>{CATEGORY[template.category] ?? template.category}</p>
      <h3 className={styles.templateTitle}>{template.title}</h3>
      <p className={styles.templateQuestion}>{template.question}</p>
      <ul className={styles.templateChanges} aria-label="Changes">
        {template.changes.map((change) => (
          <li key={change.variable_id} className="tabular">
            {changeText(change, variables)}
          </li>
        ))}
      </ul>
      <p className={styles.templateModels}>
        {template.models.map((model) => `${model.title} v${model.version}`).join(" · ")}
      </p>
      {template.suggested_entities.length > 0 && (
        <p className={styles.caption}>
          The graph states the exposure of{" "}
          {template.suggested_entities.map((entity) => entity.name).join(", ")}.
        </p>
      )}
      <ButtonLink
        to={`/scenarios/new?template=${encodeURIComponent(template.id)}`}
        size="sm"
        variant="secondary"
        iconAfter={<Icon name="arrowRight" size={14} />}
      >
        Start from this template
      </ButtonLink>
    </li>
  );
}

export function LabHome() {
  const templates = useApiResource("lab:templates", () => labApi.templates());
  const scenarios = useApiResource("scenarios", () => api.scenarios.list());
  const variableList = useApiResource("variables", () => api.variables());
  const variables = useMemo(
    () => new Map((variableList.data?.items ?? []).map((item) => [item.id, item])),
    [variableList.data],
  );
  const [selected, setSelected] = useState<string[]>([]);
  const navigate = useNavigate();

  const toggle = (id: string) =>
    setSelected((previous) =>
      previous.includes(id) ? previous.filter((item) => item !== id) : [...previous, id].slice(-6),
    );

  return (
    <div className={styles.home}>
      <section aria-labelledby="templates-heading">
        <div className={styles.homeHeader}>
          <div>
            <p className="eyebrow">Start</p>
            <h2 id="templates-heading" className={styles.homeTitle}>
              Templates
            </h2>
            <p className={styles.caption}>
              Each is built on implemented models; its required inputs, validation rules and outputs
              come from the models' definitions. None carries company figures.
            </p>
          </div>
          <ButtonLink
            to="/scenarios/new"
            variant="ghost"
            size="sm"
            icon={<Icon name="plus" size={14} />}
          >
            Blank scenario
          </ButtonLink>
        </div>
        {templates.status === "loading" && <LoadingState lines={3} />}
        {templates.status === "error" && (
          <ErrorState error={templates.error} onRetry={templates.reload} />
        )}
        {templates.status === "success" && (
          <>
            <ul className={styles.templateGrid}>
              {templates.data.items.map((template) => (
                <TemplateCard key={template.id} template={template} variables={variables} />
              ))}
            </ul>
            <ul className={styles.unsupported} aria-label="Templates not offered">
              {templates.data.unsupported.map((item) => (
                <li key={item.id}>
                  <Badge tone="outline">Not offered</Badge>
                  <strong>{item.title}.</strong> {item.reason}
                </li>
              ))}
            </ul>
          </>
        )}
      </section>

      <section aria-labelledby="library-heading">
        <div className={styles.homeHeader}>
          <div>
            <p className="eyebrow">Library</p>
            <h2 id="library-heading" className={styles.homeTitle}>
              Saved scenarios
            </h2>
          </div>
          <Button
            size="sm"
            variant="secondary"
            disabled={selected.length < 2}
            onClick={() =>
              navigate(`/scenarios/compare?${selected.map((id) => `execution=${id}`).join("&")}`)
            }
          >
            Compare {selected.length || ""} executions
          </Button>
        </div>
        {scenarios.status === "loading" && <LoadingState lines={3} />}
        {scenarios.status === "error" && (
          <ErrorState error={scenarios.error} onRetry={scenarios.reload} />
        )}
        {scenarios.status === "success" &&
          (scenarios.data.items.length === 0 ? (
            <EmptyState title="No saved scenarios yet">
              Start from a template or a blank scenario.
            </EmptyState>
          ) : (
            <div className={styles.tableScroll}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th scope="col">
                      <span className="visually-hidden">Compare</span>
                    </th>
                    <th scope="col">Scenario</th>
                    <th scope="col">Version</th>
                    <th scope="col">Latest execution</th>
                    <th scope="col">Updated</th>
                  </tr>
                </thead>
                <tbody>
                  {scenarios.data.items.map((scenario) => {
                    const latest = scenario.latest_execution;
                    return (
                      <tr key={scenario.id}>
                        <td>
                          {latest?.status === "completed" && (
                            <input
                              type="checkbox"
                              aria-label={`Compare the latest execution of ${scenario.name}`}
                              checked={selected.includes(latest.id)}
                              onChange={() => toggle(latest.id)}
                            />
                          )}
                        </td>
                        <th scope="row">
                          <Link to={`/scenarios/${scenario.id}`}>{scenario.name}</Link>
                          <span className={styles.rowNote}>
                            {scenario.shocks
                              .map((shock) => changeText(shock, variables))
                              .join(" · ")}
                          </span>
                        </th>
                        <td>v{scenario.current_version}</td>
                        <td>
                          {latest ? (
                            <>
                              <Badge
                                tone={
                                  latest.status === "completed"
                                    ? "good"
                                    : latest.status === "failed"
                                      ? "critical"
                                      : "outline"
                                }
                              >
                                {STATUS_LABEL[latest.status]}
                              </Badge>
                              {latest.headline[0] && (
                                <span className={styles.rowNote}>
                                  {latest.headline[0].label}:{" "}
                                  {compactMoney(latest.headline[0].change)}{" "}
                                  {latest.headline[0].currency} (
                                  {percentValue(latest.headline[0].percent_change)})
                                </span>
                              )}
                            </>
                          ) : (
                            <span className={styles.muted}>Not executed</span>
                          )}
                        </td>
                        <td>{formatDateTime(scenario.updated_at)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ))}
      </section>
    </div>
  );
}
