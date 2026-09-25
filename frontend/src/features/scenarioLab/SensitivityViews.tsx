/**
 * Sensitivity analysis of a stored execution: one quantity at a time (a tornado of the
 * spread each causes) or two together (a grid with the interaction of every cell). The
 * quantities, their values and the line or metric are the user's choice; each model's
 * default variation is the starting point. Deterministic — no probabilities — and stored.
 */
import { useMemo, useState } from "react";
import { Button } from "@/components/Button";
import { Icon } from "@/components/Icon";
import { EmptyState, ErrorState, LoadingState } from "@/components/States";
import { Notice } from "@/features/data/DataNature";
import { invalidateResource, setResourceData, useApiResource } from "@/hooks/useApiResource";
import { formatExact, toNumber } from "@/lib/decimal";
import { labApi } from "@/services/api";
import type {
  AnalysisTarget,
  AnalysisTargets,
  JointResults,
  LabSensitivity,
  ScenarioAnalysis,
} from "@/types/api";
import styles from "./Analyses.module.css";
import { AnalysisTypes } from "./AnalysisTypes";
import {
  type AxisDraft,
  defaultMetric,
  formatMetric,
  formatMetricChange,
  formatQuantity,
  jointRequest,
  sensitivityRequest,
  variationBounds,
} from "./analysisForm";
import { unitShort } from "./format";
import lab from "./ScenarioLab.module.css";
import { errorMessages } from "./UncertaintyView";

function variationText(target: AnalysisTarget): string {
  const variation = target.default_variation;
  if (!variation) return "no default variation: give values";
  const bounds = variationBounds(target);
  const step =
    variation.mode === "relative"
      ? `±${formatExact(variation.step)} %`
      : `±${formatQuantity(variation.step, target)}`;
  return bounds
    ? `${step}: ${formatQuantity(bounds[0], target)} and ${formatQuantity(bounds[1], target)}`
    : step;
}

function MetricSelect({
  targets,
  value,
  onChange,
}: {
  targets: AnalysisTargets;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className={styles.label}>
      Line or metric
      <select
        className={styles.select}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      >
        {targets.metrics.map((item) => (
          <option key={item.id} value={item.id}>
            {item.label}
            {item.kind === "line_change" ? " (change)" : ""}
          </option>
        ))}
      </select>
    </label>
  );
}

function Errors({ messages }: { messages: string[] }) {
  if (!messages.length) return null;
  return (
    <div className={styles.errors} role="alert">
      {messages.map((message) => (
        <p key={message}>
          <Icon name="alert" size={14} /> {message}
        </p>
      ))}
    </div>
  );
}

// --- One at a time --------------------------------------------------------------------------

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
  const show = (value: string) => formatMetric(value, analysis.metric);
  return (
    <div className={lab.tornado}>
      <p className={lab.caption}>
        Each bar spans the lowest to the highest {analysis.metric_label.toLowerCase()} reached while
        only that quantity moved; the rule marks the execution's own value ({show(analysis.base)}).
      </p>
      <ul className={lab.tornadoRows}>
        {items.map((item) => (
          <li key={item.target}>
            <span className={lab.tornadoLabel}>
              {item.label}
              <span className={lab.rowNote}>
                {item.points.map((point) => formatExact(point.value)).join(" / ")}{" "}
                {unitShort(item.unit)} · base {formatExact(item.base_value)} {unitShort(item.unit)}
              </span>
            </span>
            <span className={lab.tornadoTrack}>
              <span className={lab.tornadoBase} style={{ left: `${scale(base)}%` }} />
              {item.range && (
                <span
                  className={lab.tornadoBar}
                  style={{
                    left: `${scale(toNumber(item.range.low))}%`,
                    width: `${Math.max(0.5, scale(toNumber(item.range.high)) - scale(toNumber(item.range.low)))}%`,
                  }}
                />
              )}
            </span>
            <span className={lab.tornadoValues}>
              {item.range
                ? `${show(item.range.low)} to ${show(item.range.high)}`
                : "No valid point"}
              {item.points
                .filter((point) => point.skipped)
                .map((point) => (
                  <span key={point.role} className={lab.rowNote}>
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

function OneAtATime({ executionId, targets }: { executionId: string; targets: AnalysisTargets }) {
  const key = `lab:sensitivity:${executionId}`;
  const analyses = useApiResource(key, () => labApi.sensitivity.list(executionId));
  const labels = useMemo(
    () => new Map(targets.targets.map((target) => [target.id, target.label])),
    [targets],
  );
  const [metric, setMetric] = useState(() => defaultMetric(targets.metrics));
  const [chosen, setChosen] = useState<Map<string, string>>(
    () =>
      new Map(
        targets.targets
          .filter((target) => target.kind === "change")
          .map((target) => [target.id, ""]),
      ),
  );
  const [running, setRunning] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);
  const limit = targets.limits.sensitivity.max_items;
  const latest = analyses.status === "success" ? analyses.data.items[0] : undefined;

  const run = async () => {
    const drafts: AxisDraft[] = [...chosen].map(([target, values]) => ({ target, values }));
    const built = sensitivityRequest(metric, drafts, labels);
    setErrors(built.errors);
    if (!built.request) return;
    setRunning(true);
    try {
      await labApi.sensitivity.create(executionId, built.request);
      analyses.reload();
    } catch (failure) {
      setErrors(errorMessages(failure));
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className={lab.sensitivityView}>
      <form
        className={styles.form}
        aria-label="One quantity at a time"
        onSubmit={(event) => {
          event.preventDefault();
          void run();
        }}
      >
        <div className={styles.formRow}>
          <MetricSelect targets={targets} value={metric} onChange={setMetric} />
          <p className={lab.caption}>
            Chosen {chosen.size} of at most {limit}. Leave the values empty to use each model's
            default variation.
          </p>
        </div>
        <fieldset className={styles.checkList}>
          <legend className="visually-hidden">Quantities to vary</legend>
          {targets.targets.map((target) => {
            const on = chosen.has(target.id);
            return (
              <div key={target.id} className={styles.checkItem}>
                <input
                  type="checkbox"
                  id={`one-${target.id}`}
                  checked={on}
                  disabled={!on && chosen.size >= limit}
                  onChange={(event) => {
                    const next = new Map(chosen);
                    if (event.target.checked) next.set(target.id, "");
                    else next.delete(target.id);
                    setChosen(next);
                  }}
                />
                <label htmlFor={`one-${target.id}`}>
                  {target.label}
                  <span className={lab.rowNote}>
                    As executed {formatQuantity(target.base_value, target)} ·{" "}
                    {variationText(target)}
                  </span>
                </label>
                {on ? (
                  <input
                    type="text"
                    className={styles.input}
                    aria-label={`Values for ${target.label}`}
                    placeholder="Default"
                    value={chosen.get(target.id) ?? ""}
                    onChange={(event) =>
                      setChosen(new Map(chosen).set(target.id, event.target.value))
                    }
                  />
                ) : (
                  <span />
                )}
              </div>
            );
          })}
        </fieldset>
        <Errors messages={errors} />
        <div className={styles.formActions}>
          <Button
            type="submit"
            disabled={running || chosen.size === 0}
            icon={<Icon name="play" size={14} />}
          >
            {running ? "Running…" : "Run the analysis"}
          </Button>
          <p className={lab.caption}>
            One quantity at a time, every other value as executed. Points outside a range, or that
            break a model's rule, are skipped and reported — never clipped.
          </p>
        </div>
      </form>
      {analyses.status === "error" && (
        <ErrorState error={analyses.error} onRetry={analyses.reload} />
      )}
      {latest ? (
        <section className={styles.section} aria-label="Latest one-at-a-time analysis">
          <p className={lab.caption}>
            {latest.metric_label}: {latest.evaluations} evaluations in {latest.duration_ms} ms ·
            stored, hash {latest.result_hash.slice(0, 12)}
          </p>
          {latest.caveats.map((caveat) => (
            <Notice key={caveat} tone="warning" title="Computed before a correction">
              {caveat}
            </Notice>
          ))}
          <Tornado analysis={latest} />
        </section>
      ) : (
        analyses.status === "success" && (
          <p className={lab.caption}>No analysis yet for this execution.</p>
        )
      )}
    </div>
  );
}

// --- Two together ---------------------------------------------------------------------------

export function JointGrid({ results }: { results: JointResults }) {
  const [show, setShow] = useState<"change" | "interaction">("change");
  const { rows, columns, cells, summary, metric } = results;
  const rowBase = rows.values.indexOf(rows.base_value);
  const columnBase = columns.values.indexOf(columns.base_value);
  const q = (value: string, unit: string | null) => {
    const short = unitShort(unit);
    const text = formatExact(value);
    return short ? `${text}${short === "%" ? " %" : ` ${short}`}` : text;
  };
  const largest = summary.largest_interaction;
  const skipped = cells.flatMap((row, i) =>
    row.flatMap((cell, j) =>
      cell.skipped
        ? [
            {
              key: `${i}-${j}`,
              row: rows.values[i],
              column: columns.values[j],
              reason: cell.skipped,
            },
          ]
        : [],
    ),
  );
  return (
    <section className={styles.section} aria-label="Two quantities together">
      <p className={lab.caption}>
        {summary.additive
          ? `The two effects add up: moving both changes the ${results.metric_label.toLowerCase()} by the sum of moving each alone (interactions within ${summary.tolerance}).`
          : largest
            ? `Moving both together differs from the sum of moving each alone by up to ${formatMetricChange(largest.value, metric)} (${rows.label} ${q(rows.values[largest.row] ?? "", rows.unit)}, ${columns.label} ${q(columns.values[largest.column] ?? "", columns.unit)}).`
            : "No interaction could be computed."}
      </p>
      <div className={styles.formActions}>
        <fieldset className={lab.segmented}>
          <legend className="visually-hidden">Show in each cell</legend>
          <button type="button" aria-pressed={show === "change"} onClick={() => setShow("change")}>
            Change from the execution
          </button>
          <button
            type="button"
            aria-pressed={show === "interaction"}
            onClick={() => setShow("interaction")}
          >
            Interaction
          </button>
        </fieldset>
      </div>
      <div className={lab.tableScroll}>
        <table className={`${lab.table} ${styles.grid}`}>
          <caption className={lab.tableCaption}>
            {show === "change"
              ? `${results.metric_label}: change from the execution's value (${formatMetric(results.base, metric)}), by ${rows.label} (rows) and ${columns.label} (columns).`
              : `Interaction: the change moving both adds to the sum of moving each alone. Zero means the effects simply add.`}
          </caption>
          <thead>
            <tr>
              <th scope="col">
                {rows.label} ↓ · {columns.label} →
              </th>
              {columns.values.map((value, j) => (
                <th
                  key={value}
                  scope="col"
                  className={lab.numeric}
                  data-base={j === columnBase ? "true" : undefined}
                >
                  {q(value, columns.unit)}
                  {j === columnBase && <span className={styles.baseMark}>as executed</span>}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {cells.map((row, i) => (
              <tr key={rows.values[i]}>
                <th scope="row" data-base={i === rowBase ? "true" : undefined}>
                  {q(rows.values[i] ?? "", rows.unit)}
                  {i === rowBase && <span className={styles.baseMark}>as executed</span>}
                </th>
                {row.map((cell, j) => {
                  const value = show === "change" ? cell.delta : cell.interaction;
                  return (
                    <td
                      // biome-ignore lint/suspicious/noArrayIndexKey: grid cells are positional
                      key={j}
                      className={lab.numeric}
                      data-base={i === rowBase && j === columnBase ? "true" : undefined}
                      data-skipped={cell.skipped ? "true" : undefined}
                      title={cell.skipped ?? undefined}
                    >
                      {cell.skipped ? "skipped" : formatMetricChange(value, metric)}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {skipped.length > 0 && (
        <ul className={styles.notes}>
          {skipped.map((item) => (
            <li key={item.key}>
              {rows.label} {q(item.row ?? "", rows.unit)}, {columns.label}{" "}
              {q(item.column ?? "", columns.unit)}: {item.reason}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function TwoTogether({ executionId, targets }: { executionId: string; targets: AnalysisTargets }) {
  const listKey = `lab:analyses:${executionId}`;
  const analyses = useApiResource(listKey, () => labApi.analyses.list(executionId));
  const [metric, setMetric] = useState(() => defaultMetric(targets.metrics));
  const changes = targets.targets.filter((target) => target.kind === "change");
  const [rows, setRows] = useState<AxisDraft>({
    target: changes[0]?.id ?? targets.targets[0]?.id ?? "",
    values: "",
  });
  const [columns, setColumns] = useState<AxisDraft>({
    target: changes[1]?.id ?? targets.targets.find((target) => target.id !== rows.target)?.id ?? "",
    values: "",
  });
  const [running, setRunning] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const history =
    analyses.status === "success"
      ? analyses.data.items.filter((item) => item.kind === "joint_sensitivity")
      : [];
  const shownId = selected ?? history[0]?.id ?? null;
  const shown = useApiResource(`lab:analysis:${executionId}:${shownId ?? "none"}`, () =>
    shownId
      ? labApi.analyses.get(executionId, shownId)
      : Promise.resolve(null as ScenarioAnalysis | null),
  );
  const byId = new Map(targets.targets.map((target) => [target.id, target]));

  const run = async () => {
    const built = jointRequest(metric, rows, columns);
    setErrors(built.errors);
    if (!built.request) return;
    setRunning(true);
    try {
      const created = await labApi.analyses.create(executionId, built.request);
      setResourceData(`lab:analysis:${executionId}:${created.id}`, created);
      invalidateResource(listKey);
      setSelected(created.id);
    } catch (failure) {
      setErrors(errorMessages(failure));
    } finally {
      setRunning(false);
    }
  };

  const axisField = (label: string, draft: AxisDraft, set: (next: AxisDraft) => void) => {
    const target = byId.get(draft.target);
    return (
      <div className={styles.formRow}>
        <label className={styles.label}>
          {label}
          <select
            className={styles.select}
            value={draft.target}
            onChange={(event) => set({ target: event.target.value, values: "" })}
          >
            {targets.targets.map((item) => (
              <option key={item.id} value={item.id}>
                {item.label}
              </option>
            ))}
          </select>
          {target && (
            <span className={styles.hint}>
              As executed {formatQuantity(target.base_value, target)} · {variationText(target)}
            </span>
          )}
        </label>
        <label className={styles.label}>
          Values
          <input
            className={`${styles.input} ${styles.inputWide}`}
            value={draft.values}
            placeholder="Default variation"
            onChange={(event) => set({ ...draft, values: event.target.value })}
          />
          <span className={styles.hint}>
            Up to six, separated by commas; the executed value is added
          </span>
        </label>
      </div>
    );
  };

  return (
    <div className={lab.sensitivityView}>
      <form
        className={styles.form}
        aria-label="Two quantities together"
        onSubmit={(event) => {
          event.preventDefault();
          void run();
        }}
      >
        <MetricSelect targets={targets} value={metric} onChange={setMetric} />
        {axisField("Rows", rows, setRows)}
        {axisField("Columns", columns, setColumns)}
        <Errors messages={errors} />
        <div className={styles.formActions}>
          <Button type="submit" disabled={running} icon={<Icon name="play" size={14} />}>
            {running ? "Running…" : "Run the grid"}
          </Button>
          <p className={lab.caption}>
            Every combination of the two quantities' values (at most{" "}
            {targets.limits.joint.max_axis_points} × {targets.limits.joint.max_axis_points}),
            everything else as executed.
          </p>
        </div>
      </form>
      {history.length > 1 && (
        <label className={lab.inlineSelect}>
          <span>Stored grids</span>
          <select
            className={styles.select}
            value={shownId ?? ""}
            onChange={(event) => setSelected(event.target.value)}
          >
            {history.map((item) => (
              <option key={item.id} value={item.id}>
                {item.quantities.join(" × ")} · {item.metric_label}
              </option>
            ))}
          </select>
        </label>
      )}
      {shown.status === "error" && <ErrorState error={shown.error} onRetry={shown.reload} />}
      {shown.status === "success" && shown.data?.joint && <JointGrid results={shown.data.joint} />}
      {analyses.status === "success" && history.length === 0 && (
        <p className={lab.caption}>No grid for this execution yet.</p>
      )}
    </div>
  );
}

// --- The tab --------------------------------------------------------------------------------

export function SensitivityView({ executionId }: { executionId: string | null }) {
  const [mode, setMode] = useState<"one" | "two">("one");
  const targets = useApiResource(`lab:analysis-targets:${executionId ?? ""}`, () =>
    executionId ? labApi.analyses.targets(executionId) : Promise.reject(new Error("No execution.")),
  );
  if (!executionId) {
    return (
      <EmptyState title="Sensitivity needs a stored execution">
        Execute the scenario first: the analysis re-evaluates its stored model runs.
      </EmptyState>
    );
  }
  return (
    <div className={lab.sensitivityView}>
      <AnalysisTypes current="sensitivity" />
      <fieldset className={lab.segmented}>
        <legend className="visually-hidden">Sensitivity analysis</legend>
        <button type="button" aria-pressed={mode === "one"} onClick={() => setMode("one")}>
          One at a time
        </button>
        <button type="button" aria-pressed={mode === "two"} onClick={() => setMode("two")}>
          Two together
        </button>
      </fieldset>
      {targets.status === "loading" && (
        <LoadingState label="Reading what this execution can vary" />
      )}
      {targets.status === "error" && <ErrorState error={targets.error} onRetry={targets.reload} />}
      {targets.status === "success" &&
        (mode === "one" ? (
          <OneAtATime executionId={executionId} targets={targets.data} />
        ) : (
          <TwoTogether executionId={executionId} targets={targets.data} />
        ))}
    </div>
  );
}
