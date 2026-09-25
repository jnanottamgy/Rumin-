/**
 * Baseline against scenario, line by line: what the models computed and the Lab added up.
 *
 * The baseline is the user's own figures over the horizon, held constant — an input, not a
 * forecast. Every scenario value is simulated. A line no included model covers is listed as
 * not modelled (which is not the same as unchanged); cash flow is never shown, because no
 * model covers working capital, tax or investment.
 */
import { Fragment, useState } from "react";
import { Link } from "react-router";
import { Badge } from "@/components/Badge";
import { Icon } from "@/components/Icon";
import { ScrollRegion } from "@/components/ScrollRegion";
import { formatUnitValue } from "@/features/simulation/format";
import { KnowledgeLabel } from "@/features/simulation/knowledge";
import type { ModelResult, ResultLine, ScenarioResults } from "@/types/api";
import { compactMoney, fullMoney, metricChange, metricValue, percentValue } from "./format";
import styles from "./ScenarioLab.module.css";

const HEADLINE_ORDER = [
  "profit_before_tax",
  "operating_profit",
  "operating_costs",
  "interest_expense",
  "revenue",
];

export function headlineLine(results: ScenarioResults): ResultLine | undefined {
  for (const id of HEADLINE_ORDER) {
    const line = results.lines.find((item) => item.id === id);
    if (line) return line;
  }
  return results.lines[0];
}

/** A model output's unit as the Phase 4 formatter reads it ("currency" → "INR"). */
export function outputUnit(unit: string, currency: string): string {
  if (unit === "currency") return currency;
  if (unit === "currency_per_year") return `${currency} per year`;
  if (unit === "currency_per_month") return `${currency} per month`;
  if (unit === "usd_per_year") return "USD per year";
  return unit;
}

function Arrow({ direction }: { direction: string }) {
  if (direction === "none") return <span aria-hidden="true">·</span>;
  return <Icon name={direction === "up" ? "arrowUp" : "arrowDown"} size={12} />;
}

function effectText(effect: string): string {
  if (effect === "raises_profit") return "raises profit";
  if (effect === "reduces_profit") return "reduces profit";
  return "no effect";
}

function LineRows({
  line,
  changeNames,
  currency,
}: {
  line: ResultLine;
  changeNames: Map<string, string>;
  currency: string;
}) {
  const [open, setOpen] = useState(false);
  const expandable = line.items.length > 0 || Object.keys(line.by_change).length > 0;
  return (
    <>
      <tr className={styles.lineRow} data-total={line.items.length === 0 ? "true" : undefined}>
        <th scope="row">
          {expandable ? (
            <button
              type="button"
              className={styles.rowToggle}
              aria-expanded={open}
              onClick={() => setOpen((value) => !value)}
            >
              <Icon name={open ? "chevronDown" : "chevronRight"} size={11} />
              {line.label}
            </button>
          ) : (
            line.label
          )}
          {line.note && <span className={styles.rowNote}>{line.note}</span>}
        </th>
        <td className="tabular" title={fullMoney(line.baseline, currency)}>
          {compactMoney(line.baseline, false)}
        </td>
        <td className="tabular" title={fullMoney(line.scenario, currency)}>
          {compactMoney(line.scenario, false)}
        </td>
        <td className="tabular" title={fullMoney(line.change, currency, true)}>
          <span className={styles.change}>
            <Arrow direction={line.direction} />
            {compactMoney(line.change)}
          </span>
          <span className={styles.effect}>
            {percentValue(line.percent_change)}
            <br />
            {effectText(line.effect)}
          </span>
        </td>
      </tr>
      {open && (
        <tr className={styles.detailRow}>
          <td colSpan={4}>
            {line.items.length > 0 && (
              <dl className={styles.itemList}>
                {line.items.map((item) => (
                  <div key={`${item.model_id}-${item.item}`}>
                    <dt>
                      {item.label}
                      <span className={styles.itemModel}>{item.model_id.replaceAll("_", " ")}</span>
                    </dt>
                    <dd className="tabular">{fullMoney(item.value, currency, true)}</dd>
                  </div>
                ))}
              </dl>
            )}
            {Object.keys(line.by_change).length > 0 && (
              <>
                <p className={styles.itemHeading}>By change (Shapley values within each model)</p>
                <dl className={styles.itemList}>
                  {Object.entries(line.by_change).map(([variable, value]) => (
                    <div key={variable}>
                      <dt>{changeNames.get(variable) ?? variable}</dt>
                      <dd className="tabular">{fullMoney(value, currency, true)}</dd>
                    </div>
                  ))}
                </dl>
              </>
            )}
          </td>
        </tr>
      )}
    </>
  );
}

function ModelCard({ model, currency }: { model: ModelResult; currency: string }) {
  return (
    <li className={styles.modelCard}>
      <div className={styles.modelCardHeader}>
        <p className={styles.modelTitle}>{model.title}</p>
        <Badge tone="outline">v{model.version}</Badge>
      </div>
      <dl className={styles.keyOutputs}>
        {model.key_outputs.map((output) => (
          <div key={output.id}>
            <dt>{output.label}</dt>
            <dd className="tabular">
              {formatUnitValue(output.value, outputUnit(output.unit, currency), {
                signed: output.kind === "simulated",
              })}
            </dd>
          </div>
        ))}
      </dl>
      {model.warnings.length > 0 && (
        <ul className={styles.warningList}>
          {model.warnings.map((warning) => (
            <li key={`${warning.code}-${warning.field ?? ""}`}>
              <Icon name="alert" size={12} /> {warning.message}
            </li>
          ))}
        </ul>
      )}
      {model.run_id && (
        <Link className={styles.runLink} to={`/simulation/runs/${model.run_id}`}>
          Open the stored model run <Icon name="arrowRight" size={12} />
        </Link>
      )}
    </li>
  );
}

export function ResultsPanel({
  results,
  changeNames,
  source,
}: {
  results: ScenarioResults;
  changeNames: Map<string, string>;
  /** Where the numbers come from: a stored execution or an unstored preview. */
  source: "execution" | "preview";
}) {
  const currency = results.currency;
  const headline = headlineLine(results);
  return (
    <div className={styles.results}>
      {headline && (
        <section className={styles.hero} aria-label="Headline result">
          <p className="eyebrow">Change in {headline.label.toLowerCase()}</p>
          <p className={styles.heroFigure}>
            {compactMoney(headline.change)}
            <span className={styles.heroUnit}>{currency}</span>
          </p>
          <p className={styles.heroMeta}>
            {percentValue(headline.percent_change)} against your baseline of{" "}
            {compactMoney(headline.baseline, false)} {currency} over {results.horizon_months} months
          </p>
          <p className={styles.heroKnowledge}>
            <KnowledgeLabel kind="simulated" />
            <span>{source === "execution" ? "Stored execution" : "Live preview — not stored"}</span>
          </p>
        </section>
      )}

      <section aria-labelledby="lines-heading">
        <h3 id="lines-heading" className={styles.sectionTitle}>
          Baseline against scenario
        </h3>
        <ScrollRegion className={styles.tableScroll}>
          <table className={styles.linesTable}>
            <caption className="visually-hidden">
              Each line over the horizon in {currency}: your baseline, the scenario, and the change
              with its percentage and its effect on profit
            </caption>
            <thead>
              <tr>
                <th scope="col">Line</th>
                <th scope="col">Baseline</th>
                <th scope="col">Scenario</th>
                <th scope="col">Change</th>
              </tr>
            </thead>
            <tbody>
              {results.lines.map((line) => (
                <Fragment key={line.id}>
                  <LineRows line={line} changeNames={changeNames} currency={currency} />
                </Fragment>
              ))}
            </tbody>
          </table>
        </ScrollRegion>
        <p className={styles.caption}>
          {currency}, over the {results.horizon_months}-month horizon. Baseline: your annual figures
          × {results.horizon_months}/12, held constant.
        </p>
      </section>

      {results.metrics.length > 0 && (
        <section aria-labelledby="metrics-heading">
          <h3 id="metrics-heading" className={styles.sectionTitle}>
            Metrics
          </h3>
          <dl className={styles.metrics}>
            {results.metrics.map((metric) => (
              <div key={metric.id}>
                <dt>{metric.label}</dt>
                <dd>
                  <span className="tabular">{metricValue(metric.baseline, metric.unit)}</span>
                  <Icon name="arrowRight" size={12} />
                  <span className={styles.metricScenario}>
                    {metricValue(metric.scenario, metric.unit)}
                  </span>
                  <span className={styles.metricChange}>
                    {metricChange(metric.change, metric.change_unit)}
                  </span>
                </dd>
              </div>
            ))}
          </dl>
        </section>
      )}

      <section aria-labelledby="not-modelled-heading">
        <h3 id="not-modelled-heading" className={styles.sectionTitle}>
          Not modelled
        </h3>
        <ul className={styles.notModelled}>
          {results.not_modelled.map((item) => (
            <li key={item.id}>
              <strong>{item.label}</strong> — {item.reason}
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="models-heading">
        <h3 id="models-heading" className={styles.sectionTitle}>
          Models used
        </h3>
        <ul className={styles.modelCards}>
          {results.models.map((model) => (
            <ModelCard key={model.model_id} model={model} currency={currency} />
          ))}
        </ul>
      </section>
      <p className={styles.note}>{results.note}</p>
    </div>
  );
}
