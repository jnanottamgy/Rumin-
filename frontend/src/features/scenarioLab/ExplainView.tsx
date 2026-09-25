/**
 * "What caused this?" — one line or metric traced back to its causes, from what the
 * execution and its model runs stored: the Lab's equation and terms, each change's
 * contribution, then for each model its changes and inputs → equations → the intermediate
 * steps of a worked month → the graph relationships and transmission paths → its output.
 * With the model version, assumptions, data snapshot and limitations. Nothing here is
 * generated text: every sentence is a stored definition or a computed value.
 */
import { useState } from "react";
import { Link } from "react-router";
import { Badge } from "@/components/Badge";
import { ScrollRegion } from "@/components/ScrollRegion";
import { EmptyState, ErrorState, LoadingState } from "@/components/States";
import { formatUnitValue } from "@/features/simulation/format";
import { KnowledgeLabel, knowledgeOf } from "@/features/simulation/knowledge";
import { useApiResource } from "@/hooks/useApiResource";
import { formatExact } from "@/lib/decimal";
import { labApi } from "@/services/api";
import type { ExplainedModel, ScenarioResults } from "@/types/api";
import { changeLabel, EVIDENCE_LABEL, fullMoney } from "./format";
import styles from "./ScenarioLab.module.css";

function stepValue(value: string, unit: string, currency: string): string {
  const mapped = unit === "currency" ? currency : unit.replace("currency", currency);
  return formatUnitValue(value, mapped);
}

type ExplainedInput = ExplainedModel["inputs"][number];

/** An input's value as a reader expects it; nothing is computed, only worded. */
function inputText(input: ExplainedInput, entity: ScenarioResults["entity"]): string {
  if (input.value === null) return "—";
  // The engine's timing settings: a duration of 0 lasts to the end of the horizon.
  if (input.id === "shock_duration_months" && Number(input.value) === 0)
    return "to the end of the horizon";
  if (input.id === "shock_start_month") return `month ${formatExact(input.value)}`;
  if (entity && input.value === entity.key) return entity.name;
  if (input.unit_label === "months")
    return `${formatExact(input.value)} ${input.value === "1" ? "month" : "months"}`;
  return `${formatExact(input.value)} ${input.unit_label}`;
}

function ModelTrace({
  model,
  title,
  currency,
  entity,
}: {
  model: ExplainedModel;
  title: string;
  currency: string;
  entity: ScenarioResults["entity"];
}) {
  const edges = Object.entries(model.graph.transmission).filter(([, edge]) => edge);
  const cited = Object.entries(model.graph.supporting).filter(([, edge]) => edge);
  return (
    <article className={styles.trace}>
      <header className={styles.traceHeader}>
        <p className={styles.modelTitle}>{title}</p>
        <Badge tone="outline">v{model.version}</Badge>
        <Link to={`/simulation/runs/${model.run_id}`} className={styles.runLink}>
          Stored run
        </Link>
      </header>
      <ol className={styles.traceSteps}>
        <li>
          <h4>Changes and inputs</h4>
          <ul className={styles.inputList}>
            {[...model.changes, ...model.inputs].map((input) => (
              <li key={input.id}>
                <KnowledgeLabel kind={knowledgeOf(input.knowledge)} />
                <span>{input.label}</span>
                <span className="tabular">{inputText(input, entity)}</span>
                {input.source === "default" && <Badge tone="outline">Default</Badge>}
              </li>
            ))}
          </ul>
        </li>
        <li>
          <h4>Equations</h4>
          <ul className={styles.formulaList}>
            {model.equations.map((equation) => (
              <li key={equation.id}>
                <span className={styles.equationId}>{equation.id}</span>
                <span>
                  <span className={styles.equationName}>{equation.name}</span>
                  <code>{equation.formula}</code>
                  {equation.assumptions.map((item) => (
                    <span key={item.id} className={styles.rowNote}>
                      {item.id}: {item.text}
                    </span>
                  ))}
                </span>
              </li>
            ))}
          </ul>
        </li>
        <li>
          <h4>
            Intermediate steps
            {model.worked_month !== null && ` — month ${model.worked_month} worked through`}
          </h4>
          <ScrollRegion className={styles.tableScroll}>
            <table className={styles.table} aria-label={`Intermediate steps of ${title}`}>
              <thead>
                <tr>
                  <th scope="col">Equation</th>
                  <th scope="col">Step</th>
                  <th scope="col">Result</th>
                </tr>
              </thead>
              <tbody>
                {model.steps.map((step) => (
                  <tr key={step.sequence}>
                    <td className={styles.equationId}>{step.equation}</td>
                    <td>
                      {step.label}
                      {step.month !== null && (
                        <span className={styles.rowNote}>month {step.month}</span>
                      )}
                    </td>
                    <td className="tabular">
                      {step.output.symbol} ={" "}
                      {stepValue(step.output.value, step.output.unit, currency)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </ScrollRegion>
        </li>
        <li>
          <h4>Graph relationships and transmission</h4>
          {edges.length === 0 && cited.length === 0 ? (
            <p className={styles.caption}>
              This model applies the changes directly; no relationship is propagated.
            </p>
          ) : (
            <ul className={styles.edgeList}>
              {edges.map(([rule, edge]) => (
                <li key={rule}>
                  <Badge tone="accent">Propagated · {rule}</Badge>
                  {String((edge as Record<string, unknown>).description ?? "")}
                  <span className={styles.rowNote}>
                    {EVIDENCE_LABEL[String((edge as Record<string, unknown>).evidence_status)] ??
                      ""}
                  </span>
                </li>
              ))}
              {cited.map(([rule, edge]) => (
                <li key={rule}>
                  <Badge tone="outline">Cited · {rule}</Badge>
                  {String((edge as Record<string, unknown>).description ?? "")}
                </li>
              ))}
              {model.transmission.map((path) => (
                <li key={`${path.input}-${path.nodes.join(">")}`} className={styles.pathLine}>
                  {path.nodes.map((node) => model.graph.names[node] ?? node).join(" → ")}
                  <span className={styles.rowNote}>
                    β {formatExact(path.coefficient)} · lag {path.lag} · months {path.first_month}–
                    {path.last_month ?? "end"}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </li>
        <li>
          <h4>Outputs</h4>
          <dl className={styles.itemList}>
            {model.items.map((item) => (
              <div key={item.output}>
                <dt>{item.label}</dt>
                <dd className="tabular">{fullMoney(item.value, currency, true)}</dd>
              </div>
            ))}
          </dl>
        </li>
      </ol>
      {(model.data.length > 0 || model.limitations.length > 0 || model.warnings.length > 0) && (
        <details className={styles.traceMore}>
          <summary>Data, limitations and warnings</summary>
          {model.data.map((item) => (
            <p key={item.series_id} className={styles.caption}>
              {item.series_name}, {item.period_label}: {formatExact(item.value)} — {item.license}
              {item.attribution ? `, ${item.attribution}` : ""}
            </p>
          ))}
          <ul className={styles.statementList}>
            {model.limitations.map((item) => (
              <li key={item.id}>
                <span className={styles.equationId}>{item.id}</span> {item.text}
              </li>
            ))}
            {model.warnings.map((item) => (
              <li key={`${item.code}-${item.field}`}>
                <span className={styles.equationId}>!</span> {item.message}
              </li>
            ))}
          </ul>
        </details>
      )}
    </article>
  );
}

export function ExplainView({
  executionId,
  results,
}: {
  executionId: string | null;
  results: ScenarioResults | null;
}) {
  const targets = [
    ...(results?.lines.map((line) => ({ id: line.id, label: line.label })) ?? []),
    ...(results?.metrics.map((metric) => ({ id: metric.id, label: metric.label })) ?? []),
  ];
  const [target, setTarget] = useState<string>(
    targets.find((item) => item.id === "profit_before_tax")?.id ??
      targets.find((item) => item.id === "operating_profit")?.id ??
      targets[0]?.id ??
      "operating_profit",
  );
  const explanation = useApiResource(
    executionId ? `lab:explain:${executionId}:${target}` : "lab:explain:none",
    () => (executionId ? labApi.explanation(executionId, target) : Promise.resolve(null)),
  );
  if (!executionId || !results) {
    return (
      <EmptyState title="Explanations come from a stored execution">
        Execute the scenario: the explanation is assembled from what the execution and its model
        runs stored, so it can never drift from the calculation.
      </EmptyState>
    );
  }
  const currency = results.currency;
  return (
    <div className={styles.explainView}>
      <div className={styles.viewToolbar}>
        <label className={styles.inlineSelect}>
          <span>What caused</span>
          <select value={target} onChange={(event) => setTarget(event.target.value)}>
            {targets.map((item) => (
              <option key={item.id} value={item.id}>
                {item.label}
              </option>
            ))}
          </select>
        </label>
      </div>
      {explanation.status === "loading" && <LoadingState lines={5} />}
      {explanation.status === "error" && (
        <ErrorState error={explanation.error} onRetry={explanation.reload} />
      )}
      {explanation.status === "success" && explanation.data && (
        <>
          <ol className={styles.chain} aria-label="The chain from changes to result">
            {explanation.data.chain.map((step) => (
              <li key={step}>{step}</li>
            ))}
          </ol>
          <section className={styles.explainSummary}>
            <p className={styles.equationLine}>
              <span className={styles.equationId}>{explanation.data.equation.id}</span>
              <code>{explanation.data.equation.formula}</code>
            </p>
            <p className={styles.caption}>{explanation.data.equation.explanation}</p>
            {explanation.data.terms.length > 0 && (
              <dl className={styles.itemList}>
                {explanation.data.terms.map((term) => (
                  <div key={term.id}>
                    <dt>{term.label}</dt>
                    <dd className="tabular">{fullMoney(term.change, currency, true)}</dd>
                  </div>
                ))}
              </dl>
            )}
            {explanation.data.by_change.length > 0 && (
              <>
                <h4 className={styles.itemHeading}>Contribution of each change</h4>
                <dl className={styles.itemList}>
                  {explanation.data.by_change.map((item) => (
                    <div key={item.variable_id}>
                      <dt>
                        {item.name}
                        {item.change && item.unit && (
                          <span className={styles.rowNote}>
                            {changeLabel(item.change, item.unit)}
                          </span>
                        )}
                      </dt>
                      <dd className="tabular">{fullMoney(item.value, currency, true)}</dd>
                    </div>
                  ))}
                </dl>
                <p className={styles.caption}>{explanation.data.method.contributions}</p>
              </>
            )}
          </section>
          {explanation.data.models.map((model) => (
            <ModelTrace
              key={model.model_id}
              model={model}
              title={
                results.models.find((item) => item.model_id === model.model_id)?.title ??
                model.model_id
              }
              currency={currency}
              entity={results.entity}
            />
          ))}
          <p className={styles.caption}>{explanation.data.method.source}</p>
        </>
      )}
    </div>
  );
}
