/**
 * Historical context: the stored values of the series recorded as related measures of an
 * entity's exposure variables, the changes that met their threshold and the revisions the
 * provider made — observed data — and, set apart and labelled, the model interpretation of
 * the latest observed change through the entity's stored scenario. Then the executions
 * stored for the entity.
 */
import { Link } from "react-router";
import { Badge } from "@/components/Badge";
import { type ChartPoint, dateTime, nextPeriodFollows } from "@/features/data/chartMath";
import { TimeSeriesChart } from "@/features/data/TimeSeriesChart";
import { cx } from "@/lib/cx";
import { formatDateTime, formatPeriod } from "@/lib/format";
import type { ExecutionRef, Interpretation, NotInterpreted, SeriesAnalysis } from "@/types/api";
import { change, money, percent, stored } from "./format";
import styles from "./Intelligence.module.css";

const TREND: Record<string, string> = {
  rising: "Rising",
  falling: "Falling",
  no_clear_direction: "No clear direction",
  exact_line: "On a straight line",
};
const VOLATILITY: Record<string, string> = {
  high: "High for this series",
  not_high: "Not high for this series",
  insufficient_history: "Not enough history",
};
const ANOMALY: Record<string, string> = {
  unusual: "Unusual",
  not_unusual: "Not unusual",
  undefined: "Undefined (no spread in earlier changes)",
  insufficient_history: "Not enough history",
};

function SeriesBlock({ analysis }: { analysis: SeriesAnalysis }) {
  const subject = analysis.subject;
  const points: ChartPoint[] = analysis.points.map((point) => ({
    key: point.label,
    time: dateTime(point.start),
    value: Number(point.value),
    flagged: point.quality_status === "warning",
  }));
  const detected = new Set(analysis.detected.map((item) => item.later.label));
  return (
    <section className={styles.series} aria-label={subject.name}>
      <header className={styles.seriesHead}>
        <h4 className={styles.seriesName}>
          <Link to={`/data/series/${encodeURIComponent(subject.id)}`}>{subject.name}</Link>
        </h4>
        <p className={styles.muted}>
          {subject.unit}, {subject.frequency}, {subject.dataset.name} ({subject.dataset.license})
          {subject.dataset.is_illustrative && ", sample data"}
        </p>
        {subject.variable_relation && (
          <p className={styles.caveat}>Not the variable itself: {subject.variable_relation}</p>
        )}
      </header>
      {points.length > 1 && (
        <TimeSeriesChart
          points={points}
          label={subject.name}
          unit={subject.unit}
          contiguous={nextPeriodFollows(subject.frequency)}
          describe={(index) => {
            const point = analysis.points[index];
            if (!point) return { title: "", value: "", notes: [] };
            return {
              title: `${formatPeriod(point.label)}, ${subject.unit}`,
              value: stored(point.value),
              notes: [
                point.revision > 1 ? `Revision ${point.revision}` : "",
                detected.has(point.label) ? "Change from the previous value met the threshold" : "",
              ].filter(Boolean),
            };
          }}
          endLabel={(index) => stored(analysis.points[index]?.value)}
        />
      )}
      <dl className={styles.readings}>
        <div>
          <dt>Latest change</dt>
          <dd className="tabular">
            {analysis.latest
              ? `${change(analysis.latest.value, subject.change_unit)}, ${analysis.latest.earlier.label} to ${analysis.latest.later.label}`
              : "—"}
          </dd>
        </div>
        <div>
          <dt>
            Trend,{" "}
            {analysis.trend ? `${analysis.trend.first} to ${analysis.trend.last}` : "latest window"}
          </dt>
          <dd>{analysis.trend ? TREND[analysis.trend.direction] : "Not enough values"}</dd>
        </div>
        <div>
          <dt>Volatility</dt>
          <dd>
            {analysis.volatility ? VOLATILITY[analysis.volatility.level] : "Not enough values"}
          </dd>
        </div>
        <div>
          <dt>Latest change against earlier ones</dt>
          <dd>{analysis.anomaly ? ANOMALY[analysis.anomaly.level] : "—"}</dd>
        </div>
      </dl>
      {analysis.detected.length > 0 && (
        <table className={styles.table}>
          <caption>
            Changes in the latest window that meet the threshold (
            {analysis.threshold_name.replaceAll("_", " ")} {analysis.threshold})
          </caption>
          <thead>
            <tr>
              <th scope="col">From</th>
              <th scope="col">To</th>
              <th scope="col">Values</th>
              <th scope="col">Change</th>
            </tr>
          </thead>
          <tbody>
            {analysis.detected.map((item) => (
              <tr key={item.later.label}>
                <td>{formatPeriod(item.earlier.label)}</td>
                <td>{formatPeriod(item.later.label)}</td>
                <td className="tabular">
                  {stored(item.earlier.value)} → {stored(item.later.value)}
                </td>
                <td className="tabular">{change(item.value, subject.change_unit)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {analysis.revisions.length > 0 && (
        <table className={styles.table}>
          <caption>Revisions by the provider (both values are kept)</caption>
          <thead>
            <tr>
              <th scope="col">Period</th>
              <th scope="col">Before</th>
              <th scope="col">After</th>
              <th scope="col">Revision</th>
            </tr>
          </thead>
          <tbody>
            {analysis.revisions.map((item) => (
              <tr key={item.revised_id}>
                <td>{formatPeriod(item.label)}</td>
                <td className="tabular">{stored(item.previous)}</td>
                <td className="tabular">{stored(item.revised)}</td>
                <td className="tabular">
                  {item.change ? change(item.change, subject.change_unit) : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

function InterpretationBlock({ item }: { item: Interpretation }) {
  const headline = item.lines.find((line) => line.id === item.headline);
  return (
    <section className={styles.interpretation} aria-label="Model interpretation">
      <p className={styles.interpretationHead}>
        <Badge tone="outline">Model interpretation, computed on request</Badge>
        <span className={styles.muted}>Not stored, not an observation, not a forecast</span>
      </p>
      <p>
        The latest observed change in {item.series_name} (
        {change(item.observed.value, item.observed_unit)}, {item.observed.earlier.label} to{" "}
        {item.observed.later.label}) applied alone, as{" "}
        {item.applied_type === "percent_change"
          ? percent(item.applied)
          : change(item.applied, "percentage_points")}{" "}
        to {item.variable_name}, through “{item.scenario_name}” (version {item.version}):
      </p>
      <table className={styles.table}>
        <thead>
          <tr>
            <th scope="col">Line</th>
            <th scope="col">Baseline</th>
            <th scope="col">Change</th>
            <th scope="col">In percent</th>
          </tr>
        </thead>
        <tbody>
          {item.lines.map((line) => (
            <tr key={line.id} className={cx(line.id === headline?.id && styles.rowEmphasis)}>
              <th scope="row">{line.label}</th>
              <td className="tabular">{money(line.baseline, line.currency)}</td>
              <td className="tabular">{money(line.change, line.currency, true)}</td>
              <td className="tabular">{percent(line.percent_change)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {item.stated_difference && (
        <p className={styles.caveat}>The series is not the variable: {item.stated_difference}</p>
      )}
      <p className={styles.muted}>{item.note}</p>
    </section>
  );
}

export function HistoryView({
  series,
  interpretations,
  notInterpreted,
  executions,
}: {
  series: readonly SeriesAnalysis[];
  interpretations: readonly Interpretation[];
  notInterpreted: readonly NotInterpreted[];
  executions: readonly ExecutionRef[];
}) {
  return (
    <div className={styles.history}>
      <section aria-label="Observed data">
        <h3 className={styles.sectionTitle}>Observed data</h3>
        {series.length === 0 ? (
          <p className={styles.emptyLine}>
            No stored values for the series that measure this entity's exposure variables. Retrieve
            them from the Data Explorer's command line to see how they have moved.
          </p>
        ) : (
          series.map((analysis) => <SeriesBlock key={analysis.subject.id} analysis={analysis} />)
        )}
      </section>
      {(interpretations.length > 0 || notInterpreted.length > 0) && (
        <section aria-label="Through the stored scenario">
          <h3 className={styles.sectionTitle}>The latest observed change, through the models</h3>
          {interpretations.map((item) => (
            <InterpretationBlock key={`${item.series_id}:${item.execution_id}`} item={item} />
          ))}
          {notInterpreted.map((item) => (
            <p key={`${item.series_id}:${item.variable_id}`} className={styles.muted}>
              {item.series_id}: {item.reason}
            </p>
          ))}
        </section>
      )}
      <section aria-label="Stored executions">
        <h3 className={styles.sectionTitle}>Stored executions</h3>
        {executions.length === 0 ? (
          <p className={styles.emptyLine}>No completed execution is stored for this entity.</p>
        ) : (
          <table className={styles.table}>
            <thead>
              <tr>
                <th scope="col">Scenario</th>
                <th scope="col">Completed</th>
                <th scope="col">Graph build</th>
                <th scope="col">Result hash</th>
              </tr>
            </thead>
            <tbody>
              {executions.map((item) => (
                <tr key={item.id}>
                  <th scope="row">
                    <Link
                      to={`/scenarios/${encodeURIComponent(item.scenario_id)}?execution=${encodeURIComponent(item.id)}`}
                    >
                      {item.scenario_name}, version {item.version}
                    </Link>
                  </th>
                  <td>{item.finished_at ? formatDateTime(item.finished_at) : "—"}</td>
                  <td className="tabular">
                    {item.graph_build_id ? `#${item.graph_build_id}` : "—"}
                  </td>
                  <td className={cx("tabular", styles.hash)}>
                    {item.result_hash?.slice(0, 12) ?? "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
