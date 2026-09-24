/**
 * What drives an entity's simulated results: the latest stored execution's contributions
 * per scenario change (the models' Shapley credits, stored with the runs — never recomputed
 * here), as amounts, shares of the change and effects per unit of each change.
 *
 * Each line is a table whose bars grow from zero (right for an increase, left for a
 * decrease), one hue for every change: the row label says which change it is, and the
 * value is always printed. Everything here is simulated under the scenario's figures and
 * assumptions, and says so.
 */
import { Link } from "react-router";
import { Badge } from "@/components/Badge";
import { cx } from "@/lib/cx";
import { formatDateTime } from "@/lib/format";
import type { DriverAnalysis, DriverLine, IntelligenceDrivers } from "@/types/api";
import { change as changeText, money, percent, stored } from "./format";
import styles from "./Intelligence.module.css";

/** Plotting only: a bar's length as a share of the largest magnitude on the line. */
function magnitude(value: string): number {
  const number = Math.abs(Number(value));
  return Number.isFinite(number) ? number : 0;
}

function LineBars({ line }: { line: DriverLine }) {
  const largest = Math.max(
    magnitude(line.change),
    ...line.contributions.map((item) => magnitude(item.value)),
    1,
  );
  const bar = (value: string) => {
    const width = (magnitude(value) / largest) * 50;
    const negative = value.trim().startsWith("-");
    return (
      <span className={styles.barTrack} aria-hidden="true">
        <span className={styles.barZero} />
        <span
          className={cx(styles.bar, negative && styles.barNegative)}
          style={
            negative ? { right: "50%", width: `${width}%` } : { left: "50%", width: `${width}%` }
          }
        />
      </span>
    );
  };
  const titleId = `drivers-${line.id}`;
  return (
    <figure className={styles.barsFigure}>
      <figcaption id={titleId} className={styles.barsCaption}>
        <span className={styles.barsTitle}>{line.label}</span>{" "}
        <span className={cx(styles.muted, "tabular")}>
          {money(line.change, line.currency, true)} ({percent(line.percent_change)}) on a baseline
          of {money(line.baseline, line.currency)}
        </span>
      </figcaption>
      <table className={styles.bars} aria-labelledby={titleId}>
        <thead className="visually-hidden">
          <tr>
            <th scope="col">Change</th>
            <th scope="col">Contribution</th>
            <th scope="col">Amount</th>
            <th scope="col">Share of the change</th>
          </tr>
        </thead>
        <tbody>
          {line.contributions.map((item) => (
            <tr key={item.variable_id}>
              <th scope="row">{item.name}</th>
              <td className={styles.barCell}>{bar(item.value)}</td>
              <td className="tabular">{money(item.value, line.currency, true)}</td>
              <td className={cx("tabular", styles.muted)}>
                {item.share_of_change !== null
                  ? `${percent(item.share_of_change, false)} of it`
                  : ""}
              </td>
            </tr>
          ))}
          {line.residual !== "0" && (
            <tr>
              <th scope="row">Unattributed</th>
              <td className={styles.barCell}>{bar(line.residual)}</td>
              <td className="tabular">{money(line.residual, line.currency, true)}</td>
              <td />
            </tr>
          )}
          <tr className={styles.barsTotal}>
            <th scope="row">Change in {line.label.toLowerCase()}</th>
            <td className={styles.barCell}>{bar(line.change)}</td>
            <td className="tabular">{money(line.change, line.currency, true)}</td>
            <td />
          </tr>
        </tbody>
      </table>
    </figure>
  );
}

function PerUnit({ drivers }: { drivers: DriverAnalysis }) {
  const line = drivers.lines.find((item) => item.id === drivers.headline);
  const rows = line?.contributions.filter((item) => item.per_unit !== null) ?? [];
  if (!line || rows.length === 0) return null;
  return (
    <table className={styles.table}>
      <caption>
        {line.label} per unit of each change: an average over the scenario's change, not a slope
      </caption>
      <thead>
        <tr>
          <th scope="col">Change</th>
          <th scope="col">Size in the scenario</th>
          <th scope="col">Per unit</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((item) => {
          const change = drivers.changes.find((c) => c.variable_id === item.variable_id);
          return (
            <tr key={item.variable_id}>
              <th scope="row">{item.name}</th>
              <td className="tabular">
                {change
                  ? changeText(
                      change.value,
                      change.change_type === "percent_change" ? "percent" : "percentage_points",
                    )
                  : "—"}
              </td>
              <td className="tabular">
                {money(item.per_unit, line.currency, true)} per {item.per_unit_label}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

export function DriversView({ found }: { found: IntelligenceDrivers | null }) {
  const drivers = found?.drivers ?? null;
  if (!found || !drivers) {
    return (
      <div className={styles.emptyBlock}>
        <p>{found?.note ?? "No completed execution is stored for this entity."}</p>
      </div>
    );
  }
  const execution = drivers.execution;
  return (
    <div className={styles.drivers}>
      <p className={styles.driversHead}>
        <Badge tone="outline">Simulated, not a forecast</Badge>
        <span>
          From the stored execution of{" "}
          <Link
            to={`/scenarios/${encodeURIComponent(execution.scenario_id)}?execution=${encodeURIComponent(execution.id)}`}
          >
            “{execution.scenario_name}”, version {execution.version}
          </Link>
          {execution.finished_at && <>, completed {formatDateTime(execution.finished_at)}</>}, over{" "}
          {execution.horizon_months} months.
        </span>
      </p>
      {drivers.unstated.length > 0 && (
        <ul className={styles.notice} aria-label="Exposure not stated in the graph">
          {drivers.unstated.map((item) => (
            <li key={item.model_id}>{item.message}</li>
          ))}
        </ul>
      )}
      <div className={styles.barsGrid}>
        {drivers.lines
          .filter((line) => line.contributions.length > 0)
          .map((line) => (
            <LineBars key={line.id} line={line} />
          ))}
      </div>
      <PerUnit drivers={drivers} />
      {drivers.sensitivity && (
        <table className={styles.table}>
          <caption>
            Stored sensitivity analysis of {drivers.sensitivity.metric_label.toLowerCase()}: each
            quantity moved one at a time
          </caption>
          <thead>
            <tr>
              <th scope="col">Quantity</th>
              <th scope="col">Spread of the result</th>
            </tr>
          </thead>
          <tbody>
            {drivers.sensitivity.ranking.map((item) => (
              <tr key={item.target}>
                <th scope="row">{item.label}</th>
                <td className="tabular">{money(item.spread, execution.currency)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <div className={styles.twoColumns}>
        <section aria-label="Figures entered">
          <h4 className={styles.detailTitle}>Figures entered by the user (not RUMIN data)</h4>
          <table className={styles.facts}>
            <tbody>
              {drivers.figures.map((item) => (
                <tr key={item.label}>
                  <th scope="row">{item.label}</th>
                  <td className="tabular">
                    {stored(item.value)} {item.unit}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
        <section aria-label="Models and assumptions">
          <h4 className={styles.detailTitle}>Models</h4>
          <ul className={styles.plainList}>
            {drivers.models.map((model) => (
              <li key={model.run_id}>
                {model.name} <span className={styles.muted}>{model.version}</span>
              </li>
            ))}
          </ul>
          {drivers.not_modelled.length > 0 && (
            <p className={styles.note}>Not modelled: {drivers.not_modelled.join(", ")}.</p>
          )}
          <details className={styles.fold}>
            <summary>Assumptions of the runs ({drivers.assumptions.length})</summary>
            <ul className={styles.plainList}>
              {drivers.assumptions.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </details>
        </section>
      </div>
      <ul className={styles.plainList}>
        {drivers.notes.map((note) => (
          <li key={note} className={styles.muted}>
            {note}
          </li>
        ))}
      </ul>
    </div>
  );
}
