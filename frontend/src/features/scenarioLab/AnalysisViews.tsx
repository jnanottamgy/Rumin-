/**
 * The views that read a set of results: the months, the stress cases and the one-at-a-time
 * sensitivity analysis. Charts follow RUMIN's chart rules — one emphasised series in sky
 * blue with the rest as grey context, thin marks, hairline axes — and every chart has a
 * table with the exact values beside it.
 */
import { Fragment, useState } from "react";
import { Button } from "@/components/Button";
import { Icon } from "@/components/Icon";
import { EmptyState, ErrorState } from "@/components/States";
import { useApiResource } from "@/hooks/useApiResource";
import { describeError } from "@/lib/apiClient";
import { cx } from "@/lib/cx";
import { formatExact, toNumber } from "@/lib/decimal";
import { labApi } from "@/services/api";
import type { LabSensitivity, ResultLine, ScenarioPlan, ScenarioResults } from "@/types/api";
import { changeLabel, compactMoney, fullMoney, metricValue, unitShort } from "./format";
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

// --- Sensitivity ---------------------------------------------------------------------------------

function Tornado({ analysis }: { analysis: LabSensitivity }) {
  const base = toNumber(analysis.base);
  const order = new Map(analysis.ranking.map((entry, index) => [entry.target, index]));
  const items = [...analysis.items].sort(
    (a, b) => (order.get(a.target) ?? 999) - (order.get(b.target) ?? 999),
  );
  const extremes = items.flatMap((item) =>
    item.range ? [toNumber(item.range.low), toNumber(item.range.high)] : [],
  );
  const low = Math.min(base, ...extremes);
  const high = Math.max(base, ...extremes);
  const pad = (high - low) * 0.06 || Math.abs(base) * 0.01 || 1;
  const scale = (value: number) => ((value - (low - pad)) / (high - low + 2 * pad)) * 100;
  const moneyMetric = analysis.metric_kind === "line_change";
  const show = (value: string) =>
    moneyMetric
      ? compactMoney(value)
      : metricValue(value, analysis.metric === "interest_coverage" ? "times" : "ratio");
  return (
    <div className={styles.tornado}>
      <p className={styles.caption}>
        Each bar spans the lowest to the highest {analysis.metric_label.toLowerCase()} reached while
        only that quantity moved; the rule marks the execution's own value ({show(analysis.base)}).
      </p>
      <ul className={styles.tornadoRows}>
        {items.map((item) => (
          <li key={item.target}>
            <span className={styles.tornadoLabel}>
              {item.label}
              <span className={styles.rowNote}>
                {item.points.map((point) => formatExact(point.value)).join(" / ")}{" "}
                {unitShort(item.unit)} · base {formatExact(item.base_value)} {unitShort(item.unit)}
              </span>
            </span>
            <span className={styles.tornadoTrack}>
              <span className={styles.tornadoBase} style={{ left: `${scale(base)}%` }} />
              {item.range && (
                <span
                  className={styles.tornadoBar}
                  style={{
                    left: `${scale(toNumber(item.range.low))}%`,
                    width: `${Math.max(0.5, scale(toNumber(item.range.high)) - scale(toNumber(item.range.low)))}%`,
                  }}
                />
              )}
            </span>
            <span className={styles.tornadoValues}>
              {item.range
                ? `${show(item.range.low)} to ${show(item.range.high)}`
                : "No valid point"}
              {item.points
                .filter((point) => point.skipped)
                .map((point) => (
                  <span key={point.role} className={styles.rowNote}>
                    {point.role} skipped: {point.skipped}
                  </span>
                ))}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function SensitivityView({ executionId }: { executionId: string | null }) {
  const key = executionId ? `lab:sensitivity:${executionId}` : "lab:sensitivity:none";
  const analyses = useApiResource(key, () =>
    executionId ? labApi.sensitivity.list(executionId) : Promise.resolve({ items: [] }),
  );
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (!executionId) {
    return (
      <EmptyState title="Sensitivity needs a stored execution">
        Execute the scenario first: the analysis re-evaluates its stored model runs, one quantity at
        a time.
      </EmptyState>
    );
  }
  const latest = analyses.status === "success" ? analyses.data.items[0] : undefined;
  const run = async () => {
    setRunning(true);
    setError(null);
    try {
      await labApi.sensitivity.create(executionId, { metric: null, inputs: [] });
      analyses.reload();
    } catch (failure) {
      setError(describeError(failure));
    } finally {
      setRunning(false);
    }
  };
  return (
    <div className={styles.sensitivityView}>
      <div className={styles.viewToolbar}>
        <Button
          size="sm"
          onClick={() => void run()}
          disabled={running}
          icon={<Icon name="play" size={14} />}
        >
          {running ? "Running…" : latest ? "Run again" : "Run the analysis"}
        </Button>
        <p className={styles.caption}>
          One quantity at a time — each change, the model assumptions — with every other value as
          executed. This is sensitivity analysis, not a probability: no Monte Carlo simulation is
          run.
        </p>
      </div>
      {error && <p className={styles.errorText}>{error}</p>}
      {analyses.status === "error" && (
        <ErrorState error={analyses.error} onRetry={analyses.reload} />
      )}
      {latest ? (
        <>
          <p className={styles.caption}>
            {latest.metric_label}: {latest.evaluations} evaluations in {latest.duration_ms} ms ·
            stored, hash {latest.result_hash.slice(0, 12)}
          </p>
          <Tornado analysis={latest} />
        </>
      ) : (
        analyses.status === "success" && (
          <p className={styles.caption}>No analysis yet for this execution.</p>
        )
      )}
    </div>
  );
}
