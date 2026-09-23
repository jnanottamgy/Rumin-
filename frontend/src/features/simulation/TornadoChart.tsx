/**
 * One-at-a-time sensitivity as a tornado: one row per input, ordered by how far the
 * result moves (the engine ranks them). Each bar spans the lowest to the highest result
 * reached while only that input changed; the vertical rule is the run's own result.
 *
 * Shape, not colour, tells the points apart: a hollow circle is the result with the
 * input lowered, a filled circle with it raised, a tick a listed value. Points the model
 * could not accept (outside an input's range) are listed with the reason, never drawn.
 */
import { formatExact, toNumber } from "@/lib/decimal";
import type { SensitivityAnalysis, SensitivityItem } from "@/types/api";
import { formatUnitValue } from "./format";
import styles from "./Simulation.module.css";

function variation(item: SensitivityItem, unitLabel: string): string {
  const values = item.points.map((point) => formatExact(point.value));
  const joined = item.mode === "values" ? values.join(", ") : values.join(" and ");
  return `${joined}${unitLabel ? ` ${unitLabel}` : ""} (run: ${formatExact(item.base_value)})`;
}

export function TornadoChart({
  analysis,
  metricUnit,
  unitLabels,
}: {
  analysis: SensitivityAnalysis;
  metricUnit: string;
  /** Display labels for the inputs' units (e.g. "USD per kilolitre"). */
  unitLabels: Record<string, string>;
}) {
  const metric = analysis.metric;
  const base = toNumber(analysis.base[metric] ?? "0");
  const order = new Map(analysis.ranking.map((entry, index) => [entry.input, index]));
  const items = [...analysis.items].sort(
    (a, b) => (order.get(a.input) ?? 999) - (order.get(b.input) ?? 999),
  );
  const extremes = items.flatMap((item) =>
    item.range ? [toNumber(item.range.low), toNumber(item.range.high)] : [],
  );
  const low = Math.min(base, ...extremes);
  const high = Math.max(base, ...extremes);
  const pad = (high - low) * 0.06 || Math.abs(base) * 0.01 || 1;
  const scale = (value: number) => ((value - (low - pad)) / (high - low + 2 * pad)) * 100;
  const baseAt = scale(base);

  return (
    <div className={styles.tornado}>
      <div className={styles.chartLegend} aria-hidden="true">
        <span className={styles.legendItem}>
          <span className={styles.pointKey} data-role="low" />
          Input lowered
        </span>
        <span className={styles.legendItem}>
          <span className={styles.pointKey} data-role="high" />
          Input raised
        </span>
        <span className={styles.legendItem}>
          <span className={styles.baseKey} />
          The run's result: {formatUnitValue(analysis.base[metric], metricUnit)}
        </span>
      </div>
      <table className={styles.barTable}>
        <caption className="visually-hidden">
          Sensitivity of {analysis.metric_label}, one input at a time
        </caption>
        <thead>
          <tr>
            <th scope="col">Input</th>
            <th scope="col">Result range</th>
            <th scope="col">
              <span className="visually-hidden">Bar</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => {
            const usable = item.points.filter((point) => point.outputs);
            const skipped = item.points.filter((point) => point.skipped);
            return (
              <tr key={item.input}>
                <th scope="row" className={styles.barLabel}>
                  <span>{item.label}</span>
                  <span className={styles.barSub}>
                    {variation(item, unitLabels[item.input] ?? "")}
                  </span>
                  {skipped.map((point) => (
                    <span key={point.role} className={styles.barSkipped}>
                      {formatExact(point.value)} not used: {point.skipped}
                    </span>
                  ))}
                </th>
                <td className={styles.barValue}>
                  {item.range ? (
                    <>
                      {formatUnitValue(item.range.low, metricUnit)}
                      <span className={styles.barSub}>
                        to {formatUnitValue(item.range.high, metricUnit)}
                      </span>
                    </>
                  ) : (
                    "No result"
                  )}
                </td>
                <td className={styles.barCell} aria-hidden="true">
                  <span className={styles.barBase} style={{ left: `${baseAt}%` }} />
                  {item.range && (
                    <span
                      className={styles.bar}
                      data-tone="range"
                      style={{
                        left: `${scale(toNumber(item.range.low))}%`,
                        width: `${Math.max(
                          0.4,
                          scale(toNumber(item.range.high)) - scale(toNumber(item.range.low)),
                        )}%`,
                      }}
                    />
                  )}
                  {usable.map((point) => (
                    <span
                      key={point.role}
                      className={styles.point}
                      data-role={
                        point.role === "low" ? "low" : point.role === "high" ? "high" : "value"
                      }
                      style={{ left: `${scale(toNumber(point.outputs?.[metric] ?? "0"))}%` }}
                      title={`${formatExact(point.value)}: ${formatUnitValue(
                        point.outputs?.[metric],
                        metricUnit,
                      )}`}
                    />
                  ))}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
