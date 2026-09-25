/**
 * The views that read a set of results: the months and the stress cases (the sensitivity
 * and uncertainty analyses are in `SensitivityViews` and `UncertaintyView`). Charts follow
 * RUMIN's chart rules — one emphasised series in sky blue with the rest as grey context,
 * thin marks, hairline axes — and every chart has a table with the exact values beside it.
 */
import { Fragment, useState } from "react";
import { EmptyState } from "@/components/States";
import { cx } from "@/lib/cx";
import { formatExact, toNumber } from "@/lib/decimal";
import type { ResultLine, ScenarioPlan, ScenarioResults } from "@/types/api";
import { AnalysisTypes } from "./AnalysisTypes";
import { changeLabel, compactMoney, fullMoney, metricValue } from "./format";
import styles from "./ScenarioLab.module.css";

// --- Months -------------------------------------------------------------------------------------

export function MonthsView({ results }: { results: ScenarioResults }) {
  const currency = results.currency;
  const { start_month: start, end_month: end } = results.timing;
  // Mark the months the changes last only when that is not simply every month.
  const partial = start > 1 || end < results.horizon_months;
  return (
    <div className={styles.tableScroll}>
      <table className={cx(styles.table, styles.monthsTable)}>
        <caption className={styles.tableCaption}>
          Change in each line by simulated month, {currency}. Simulated values, not forecasts.
          {partial && ` The changes last months ${start}–${end} (marked).`}
        </caption>
        <thead>
          <tr>
            <th scope="col">Month</th>
            {results.lines.map((line) => (
              <th key={line.id} scope="col" className={styles.numeric}>
                {line.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {Array.from({ length: results.horizon_months }, (_, index) => {
            const month = index + 1;
            const events = results.timeline.events.filter((event) => event.month === month);
            const inWindow = partial && month >= start && month <= end;
            return (
              // biome-ignore lint/suspicious/noArrayIndexKey: months are positional
              <Fragment key={index}>
                <tr className={events.length > 0 ? styles.annotatedRow : undefined}>
                  <th scope="row" className={inWindow ? styles.windowMonth : undefined}>
                    {month}
                  </th>
                  {results.lines.map((line) => (
                    <td
                      key={line.id}
                      className={styles.numeric}
                      title={fullMoney(line.monthly[index] ?? "0", currency, true)}
                    >
                      {compactMoney(line.monthly[index] ?? "0")}
                    </td>
                  ))}
                </tr>
                {events.length > 0 && (
                  <tr className={styles.eventRow}>
                    <td colSpan={results.lines.length + 1}>
                      Month {month}: {events.map((event) => event.label).join("; ")}
                    </td>
                  </tr>
                )}
              </Fragment>
            );
          })}
          <tr className={styles.totalRow}>
            <th scope="row">Total</th>
            {results.lines.map((line) => (
              <td
                key={line.id}
                className={styles.numeric}
                title={fullMoney(line.change, currency, true)}
              >
                {compactMoney(line.change)}
              </td>
            ))}
          </tr>
        </tbody>
      </table>
    </div>
  );
}

// --- Stress cases --------------------------------------------------------------------------------

function StressChart({ cases }: { cases: { name: string; value: string; emphasis: boolean }[] }) {
  const numbers = cases.map((item) => toNumber(item.value));
  const low = Math.min(0, ...numbers);
  const high = Math.max(0, ...numbers);
  const span = high - low || 1;
  const zeroAt = ((0 - low) / span) * 100;
  return (
    <ul className={styles.barChart}>
      {cases.map((item, index) => {
        const at = ((toNumber(item.value) - low) / span) * 100;
        return (
          <li key={item.name}>
            <span className={styles.barName}>{item.name}</span>
            <span className={styles.barTrack}>
              <span className={styles.barZero} style={{ left: `${zeroAt}%` }} />
              <span
                className={styles.barFill}
                data-emphasis={item.emphasis ? "true" : undefined}
                style={{
                  left: `${Math.min(at, zeroAt)}%`,
                  width: `${Math.max(0.6, Math.abs(at - zeroAt))}%`,
                }}
                title={item.value}
              />
            </span>
            <span className={styles.barValue}>{compactMoney(cases[index]?.value ?? "0")}</span>
          </li>
        );
      })}
    </ul>
  );
}

export function StressView({
  results,
  changes,
}: {
  results: ScenarioResults;
  /** The plan's changes, for their names and units. */
  changes: ScenarioPlan["changes"];
}) {
  const [lineId, setLineId] = useState<string>(
    results.lines.find((line) => line.id === "profit_before_tax")?.id ??
      results.lines.find((line) => line.id === "operating_profit")?.id ??
      results.lines[0]?.id ??
      "",
  );
  if (results.stress_cases.length === 0) {
    return (
      <EmptyState title="No stress cases">
        Add stress cases in the controls — other magnitudes of the same changes, such as a base, a
        stress and an extreme case — and they are evaluated with the same models and assumptions.
      </EmptyState>
    );
  }
  const line = results.lines.find((item) => item.id === lineId);
  const lineOf = (lines: ResultLine[]) => lines.find((item) => item.id === lineId);
  const cases = [
    { name: "Scenario", value: line?.change ?? "0", emphasis: true },
    ...results.stress_cases.map((item) => ({
      name: item.name,
      value: lineOf(item.lines)?.change ?? "0",
      emphasis: false,
    })),
  ];
  return (
    <div className={styles.stressView}>
      <AnalysisTypes current="stress" />
      <div className={styles.viewToolbar}>
        <label className={styles.inlineSelect}>
          <span>Line</span>
          <select value={lineId} onChange={(event) => setLineId(event.target.value)}>
            {results.lines.map((item) => (
              <option key={item.id} value={item.id}>
                {item.label}
              </option>
            ))}
          </select>
        </label>
        <p className={styles.caption}>
          Change in {line?.label.toLowerCase()} over the horizon, {results.currency}. Same models
          and assumptions; only the changes' magnitudes differ. Not ranked: which case matters
          depends on your objective.
        </p>
      </div>
      <StressChart cases={cases} />
      <div className={styles.tableScroll}>
        <table className={cx(styles.table, styles.monthsTable)}>
          <caption className={styles.tableCaption}>
            Change over the horizon in each line, {results.currency}, and each metric in the case.
          </caption>
          <thead>
            <tr>
              <th scope="col">Case</th>
              <th scope="col">Changes</th>
              {results.lines.map((item) => (
                <th key={item.id} scope="col" className={styles.numeric}>
                  {item.label}
                </th>
              ))}
              {results.metrics.map((metric) => (
                <th key={metric.id} scope="col" className={styles.numeric}>
                  {metric.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            <tr data-emphasis="true">
              <th scope="row">Scenario</th>
              <td>—</td>
              {results.lines.map((item) => (
                <td key={item.id} className={styles.numeric}>
                  {compactMoney(item.change)}
                </td>
              ))}
              {results.metrics.map((metric) => (
                <td key={metric.id} className={styles.numeric}>
                  {metricValue(metric.scenario, metric.unit)}
                </td>
              ))}
            </tr>
            {results.stress_cases.map((item) => (
              <tr key={item.name}>
                <th scope="row">{item.name}</th>
                <td className={styles.caseChanges}>
                  {item.scale && (
                    <span className={styles.rowNote}>Scaled × {formatExact(item.scale)}</span>
                  )}
                  {Object.entries(item.changes).map(([variable, value]) => {
                    const change = changes.find((entry) => entry.variable_id === variable);
                    return (
                      <span key={variable} className={styles.caseChange}>
                        {change?.name ?? variable}{" "}
                        <span className="tabular">{changeLabel(value, change?.unit ?? "")}</span>
                      </span>
                    );
                  })}
                </td>
                {results.lines.map((resultLine) => (
                  <td key={resultLine.id} className={styles.numeric}>
                    {compactMoney(
                      item.lines.find((entry) => entry.id === resultLine.id)?.change ?? "0",
                    )}
                  </td>
                ))}
                {results.metrics.map((metric) => {
                  const value = item.metrics.find((entry) => entry.id === metric.id);
                  return (
                    <td key={metric.id} className={styles.numeric}>
                      {value ? metricValue(value.scenario, value.unit) : "—"}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
