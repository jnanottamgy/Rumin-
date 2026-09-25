/**
 * Uncertainty: Monte Carlo analyses of a stored execution.
 *
 * The form asks for explicit distributions — nothing is drawn from a distribution the user
 * has not stated. A starting point can be taken from each model's default variation, and it
 * says so. Results lead with the spread of the chosen line or metric (percentiles with the
 * interval the draws support), then the histogram, what drove the spread, every line, the
 * diagnostics and the configuration that reproduces the run. Every figure is the backend's;
 * the browser only formats.
 */
import { useMemo, useState } from "react";
import { Button } from "@/components/Button";
import { Icon } from "@/components/Icon";
import { EmptyState, ErrorState, LoadingState } from "@/components/States";
import { invalidateResource, setResourceData, useApiResource } from "@/hooks/useApiResource";
import { ApiError, describeError } from "@/lib/apiClient";
import { formatRounded, toNumber } from "@/lib/decimal";
import { formatDateTime } from "@/lib/format";
import { labApi } from "@/services/api";
import type {
  AnalysisTarget,
  AnalysisTargets,
  AnalysisVerification,
  MonteCarloResults,
  ScenarioAnalysis,
} from "@/types/api";
import styles from "./Analyses.module.css";
import { AnalysisTypes } from "./AnalysisTypes";
import {
  type DistributionKind,
  defaultMetric,
  formatMetric,
  formatQuantity,
  formatShare,
  type MonteCarloDraft,
  monteCarloRequest,
  type QuantityDraft,
  startingPoint,
} from "./analysisForm";
import { ConvergenceChart } from "./ConvergenceChart";
import { DistributionChart, type DistributionMarker } from "./DistributionChart";
import lab from "./ScenarioLab.module.css";

/** Every message an API error carries: its details first (they name the field's problem). */
export function errorMessages(error: unknown): string[] {
  if (error instanceof ApiError && error.details.length) {
    return error.details.map((detail) => detail.message);
  }
  return [describeError(error)];
}

const KIND_LABEL: Record<DistributionKind, string> = {
  uniform: "Uniform",
  triangular: "Triangular",
  discrete: "Discrete",
};

function rangeText(target: AnalysisTarget): string {
  const low = target.minimum === null ? "no minimum" : formatQuantity(target.minimum, target);
  const high = target.maximum === null ? "no maximum" : formatQuantity(target.maximum, target);
  const lowWord = target.minimum_exclusive ? "above" : "from";
  const highWord = target.maximum_exclusive ? "below" : "to";
  return `${lowWord} ${low} ${highWord} ${high}`;
}

// --- The form -------------------------------------------------------------------------------

function QuantityEditor({
  draft,
  target,
  onChange,
  onRemove,
}: {
  draft: QuantityDraft;
  target: AnalysisTarget;
  onChange: (next: QuantityDraft) => void;
  onRemove: () => void;
}) {
  const kinds: DistributionKind[] = target.integer
    ? ["discrete"]
    : ["uniform", "triangular", "discrete"];
  const id = `q-${target.id.replaceAll(":", "-")}`;
  const field = (name: keyof QuantityDraft, label: string, hint?: string) => (
    <label className={styles.label}>
      {label}
      <input
        className={
          name === "values" || name === "weights"
            ? `${styles.input} ${styles.inputWide}`
            : styles.input
        }
        value={draft[name]}
        inputMode="decimal"
        onChange={(event) => onChange({ ...draft, [name]: event.target.value })}
      />
      {hint && <span className={styles.hint}>{hint}</span>}
    </label>
  );
  return (
    <li className={styles.quantityRow} aria-labelledby={id}>
      <div className={styles.quantityHeader}>
        <div>
          <p id={id} className={lab.itemHeading}>
            {target.label}
          </p>
          <p className={styles.hint}>
            As executed {formatQuantity(target.base_value, target)} · valid {rangeText(target)}
            {target.integer ? " · whole months" : ` · up to ${target.max_decimals} decimals`}
          </p>
        </div>
        <Button size="sm" variant="ghost" onClick={onRemove} icon={<Icon name="close" size={12} />}>
          Remove
        </Button>
      </div>
      <div className={styles.formRow}>
        <label className={styles.label}>
          Distribution
          <select
            className={styles.select}
            value={draft.kind}
            onChange={(event) =>
              onChange({ ...draft, kind: event.target.value as DistributionKind })
            }
          >
            {kinds.map((kind) => (
              <option key={kind} value={kind}>
                {KIND_LABEL[kind]}
              </option>
            ))}
          </select>
        </label>
        {draft.kind === "discrete" ? (
          <>
            {field("values", "Values", "Separated by commas")}
            {field("weights", "Weights", "Optional; equal when empty")}
          </>
        ) : (
          <>
            {field("low", "Low")}
            {draft.kind === "triangular" && field("mode", "Most likely")}
            {field("high", "High")}
          </>
        )}
      </div>
    </li>
  );
}

function MonteCarloForm({
  targets,
  running,
  errors,
  onRun,
}: {
  targets: AnalysisTargets;
  running: boolean;
  errors: string[];
  onRun: (draft: MonteCarloDraft) => void;
}) {
  const byId = useMemo(
    () => new Map(targets.targets.map((target) => [target.id, target])),
    [targets],
  );
  const [draft, setDraft] = useState<MonteCarloDraft>(() => ({
    metric: defaultMetric(targets.metrics),
    draws: String(targets.limits.monte_carlo.default_draws),
    seed: "",
    threshold: "",
    quantities: [],
  }));
  const unused = targets.targets.filter(
    (target) => !draft.quantities.some((item) => item.target === target.id),
  );
  const [adding, setAdding] = useState("");
  const full = draft.quantities.length >= targets.limits.monte_carlo.max_quantities;
  const add = (ids: string[]) =>
    setDraft((previous) => ({
      ...previous,
      quantities: [
        ...previous.quantities,
        ...ids.flatMap((id) => {
          const target = byId.get(id);
          return target ? [startingPoint(target)] : [];
        }),
      ].slice(0, targets.limits.monte_carlo.max_quantities),
    }));
  const changes = unused.filter((target) => target.kind === "change").map((target) => target.id);
  const metric = targets.metrics.find((item) => item.id === draft.metric);

  return (
    <form
      className={styles.form}
      aria-label="Monte Carlo analysis"
      onSubmit={(event) => {
        event.preventDefault();
        onRun(draft);
      }}
    >
      <div className={styles.formRow}>
        <label className={styles.label}>
          Line or metric
          <select
            className={styles.select}
            value={draft.metric}
            onChange={(event) => setDraft({ ...draft, metric: event.target.value })}
          >
            {targets.metrics.map((item) => (
              <option key={item.id} value={item.id}>
                {item.label}
                {item.kind === "line_change" ? " (change)" : ""}
              </option>
            ))}
          </select>
        </label>
        <label className={styles.label}>
          Draws
          <input
            className={styles.input}
            value={draft.draws}
            inputMode="numeric"
            onChange={(event) => setDraft({ ...draft, draws: event.target.value })}
          />
          <span className={styles.hint}>
            {targets.limits.monte_carlo.min_draws}–
            {targets.limits.monte_carlo.max_draws.toLocaleString("en")}
          </span>
        </label>
        <label className={styles.label}>
          Seed
          <input
            className={`${styles.input} ${styles.inputWide}`}
            value={draft.seed}
            inputMode="numeric"
            placeholder="Chosen and recorded"
            onChange={(event) => setDraft({ ...draft, seed: event.target.value })}
          />
          <span className={styles.hint}>The same seed reproduces every draw</span>
        </label>
        <label className={styles.label}>
          Threshold
          <input
            className={styles.input}
            value={draft.threshold}
            inputMode="decimal"
            placeholder="Optional"
            onChange={(event) => setDraft({ ...draft, threshold: event.target.value })}
          />
          <span className={styles.hint}>
            {metric?.kind === "metric_value"
              ? "e.g. a covenant level, as a plain number"
              : "e.g. -10000000"}
          </span>
        </label>
      </div>

      <div className={styles.section}>
        <h4 className={lab.sectionTitle}>Quantities and their distributions</h4>
        {draft.quantities.length === 0 ? (
          <p className={lab.caption}>
            No quantity yet. Every distribution is an assumption you state: RUMIN holds no data to
            estimate one from.
          </p>
        ) : (
          <>
            <p className={lab.caption}>
              Starting points come from each model's default variation, as a uniform range (whole
              months: the low, executed and high values). They are your assumptions — edit them.
              Quantities are drawn independently of each other.
            </p>
            <ul className={styles.quantityList}>
              {draft.quantities.map((item, index) => {
                const target = byId.get(item.target);
                if (!target) return null;
                return (
                  <QuantityEditor
                    key={item.target}
                    draft={item}
                    target={target}
                    onChange={(next) =>
                      setDraft((previous) => ({
                        ...previous,
                        quantities: previous.quantities.map((entry, position) =>
                          position === index ? next : entry,
                        ),
                      }))
                    }
                    onRemove={() =>
                      setDraft((previous) => ({
                        ...previous,
                        quantities: previous.quantities.filter((_, position) => position !== index),
                      }))
                    }
                  />
                );
              })}
            </ul>
          </>
        )}
        <div className={styles.formActions}>
          <label className={lab.inlineSelect}>
            <span className="visually-hidden">Quantity to add</span>
            <select
              className={styles.select}
              value={adding}
              disabled={full || unused.length === 0}
              onChange={(event) => setAdding(event.target.value)}
            >
              <option value="">Choose a quantity…</option>
              {unused.map((target) => (
                <option key={target.id} value={target.id}>
                  {target.label}
                </option>
              ))}
            </select>
          </label>
          <Button
            size="sm"
            variant="secondary"
            disabled={!adding || full}
            onClick={() => {
              add([adding]);
              setAdding("");
            }}
          >
            Add
          </Button>
          {changes.length > 0 && !full && (
            <Button size="sm" variant="ghost" onClick={() => add(changes)}>
              Add the scenario's changes
            </Button>
          )}
        </div>
      </div>

      {errors.length > 0 && (
        <div className={styles.errors} role="alert">
          {errors.map((message) => (
            <p key={message}>
              <Icon name="alert" size={14} /> {message}
            </p>
          ))}
        </div>
      )}
      <div className={styles.formActions}>
        <Button
          type="submit"
          disabled={running || draft.quantities.length === 0}
          icon={<Icon name="play" size={14} />}
        >
          {running ? "Drawing…" : "Run the analysis"}
        </Button>
        <p className={lab.caption}>
          Each draw re-evaluates the execution's stored model runs. Draws that break a model's rule
          are rejected and counted, never adjusted. Stored with its seed.
        </p>
      </div>
    </form>
  );
}

// --- The result -----------------------------------------------------------------------------

function Figure({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className={styles.figure}>
      <span className={styles.figureLabel}>{label}</span>
      <span className={styles.figureValue}>{value}</span>
      {note && <span className={styles.figureNote}>{note}</span>}
    </div>
  );
}

function correlationBar(value: string | null) {
  if (value === null) return <span className={lab.muted}>—</span>;
  const number = toNumber(value);
  const left = number < 0 ? 50 + number * 50 : 50;
  const width = Math.abs(number) * 50;
  return (
    <>
      <span className={styles.correlation} aria-hidden="true">
        <span style={{ left: `${left}%`, width: `${width}%` }} />
      </span>
      <span className="tabular">{formatRounded(value, 2)}</span>
    </>
  );
}

function Reproduce({ executionId, analysis }: { executionId: string; analysis: ScenarioAnalysis }) {
  const [check, setCheck] = useState<AnalysisVerification | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const config = analysis.config;
  return (
    <details className={styles.details}>
      <summary>Configuration and reproducibility</summary>
      <div className={styles.section}>
        <table className={lab.table}>
          <tbody>
            <tr>
              <th scope="row">Seed</th>
              <td className="tabular">{config.seed}</td>
            </tr>
            <tr>
              <th scope="row">Draws</th>
              <td className="tabular">{config.draws}</td>
            </tr>
            <tr>
              <th scope="row">Random numbers</th>
              <td>
                {config.generator} · sampler {config.sampler_version}
              </td>
            </tr>
            <tr>
              <th scope="row">Versions</th>
              <td>
                Analysis {config.analysis_version} · Lab {config.lab_version} · engine{" "}
                {config.engine_version}
              </td>
            </tr>
            {config.runs.map((run) => (
              <tr key={run.run_id}>
                <th scope="row">
                  {run.model_id} {run.version}
                </th>
                <td>
                  Run <code>{run.run_id.slice(0, 8)}</code> · inputs hash{" "}
                  <code>{run.inputs_hash.slice(0, 12)}</code> · graph build{" "}
                  {run.graph_build_id ?? "none"}
                </td>
              </tr>
            ))}
            <tr>
              <th scope="row">Result hash</th>
              <td>
                <code>{analysis.result_hash.slice(0, 16)}</code>
              </td>
            </tr>
          </tbody>
        </table>
        <div className={styles.formActions}>
          <Button
            size="sm"
            variant="secondary"
            disabled={running}
            onClick={async () => {
              setRunning(true);
              setError(null);
              try {
                setCheck(await labApi.analyses.verify(executionId, analysis.id));
              } catch (failure) {
                setError(describeError(failure));
              } finally {
                setRunning(false);
              }
            }}
          >
            {running ? "Running again…" : "Run again and compare"}
          </Button>
          <span role="status" className={lab.caption}>
            {check && (
              <>
                <Icon name={check.reproduced ? "check" : "alert"} size={12} /> {check.message}
              </>
            )}
            {error}
          </span>
        </div>
      </div>
    </details>
  );
}

export function MonteCarloResult({
  executionId,
  analysis,
  results,
  currency,
  targets = [],
}: {
  executionId: string;
  analysis: ScenarioAnalysis;
  results: MonteCarloResults;
  currency: string;
  /** What the execution can vary, for the quantities' units. */
  targets?: readonly AnalysisTarget[];
}) {
  const byId = new Map(targets.map((target) => [target.id, target]));
  const metric = results.metric;
  const format = (value: string) => formatMetric(value, metric);
  const summary = results.summary;
  const percentile = (p: number) => summary.percentiles.find((item) => item.p === p);
  const p5 = percentile(5);
  const p50 = percentile(50);
  const p95 = percentile(95);
  const markers: DistributionMarker[] = [
    ...(p5 ? [{ id: "p5", label: "P5", value: p5.value, tone: "percentile" as const }] : []),
    ...(p50 ? [{ id: "p50", label: "P50", value: p50.value, tone: "percentile" as const }] : []),
    ...(p95 ? [{ id: "p95", label: "P95", value: p95.value, tone: "percentile" as const }] : []),
    { id: "base", label: "As executed", value: results.base, tone: "base" },
    ...(summary.threshold
      ? [
          {
            id: "threshold",
            label: "Threshold",
            value: summary.threshold,
            tone: "threshold" as const,
          },
        ]
      : []),
  ];
  const unit = results.metric_kind === "line_change" ? `${currency}, change over the horizon` : "";
  const interval = (item: typeof p5) =>
    item?.interval
      ? `Between ${format(item.interval.lower)} and ${format(item.interval.upper)} (${formatShare(item.interval.coverage)} coverage)`
      : undefined;

  return (
    <article className={styles.section} aria-label="Monte Carlo result">
      <h4 className={lab.sectionTitle}>
        {results.metric_label}
        {results.metric_kind === "line_change" ? ", change over the horizon" : ""} ·{" "}
        {results.accepted.toLocaleString("en")} of {results.draws.toLocaleString("en")} draws
      </h4>
      <div className={styles.figures}>
        <Figure
          label="Mean"
          value={format(summary.mean)}
          note={`Standard error ${format(summary.standard_error)}`}
        />
        {p5 && <Figure label="P5" value={format(p5.value)} note={interval(p5)} />}
        {p50 && <Figure label="Median (P50)" value={format(p50.value)} note={interval(p50)} />}
        {p95 && <Figure label="P95" value={format(p95.value)} note={interval(p95)} />}
        <Figure label="As executed" value={format(results.base)} note="The execution's own value" />
      </div>
      <p className={lab.caption}>
        {summary.share_below_zero !== null &&
          `In ${formatShare(summary.share_below_zero)} of the accepted draws the change is below zero. `}
        {summary.share_at_or_below_threshold !== null &&
          summary.threshold !== null &&
          `${formatShare(summary.share_at_or_below_threshold)} of them are at or below ${format(summary.threshold)}. `}
        Shares of draws under the distributions you stated — not probabilities of what will happen.
      </p>
      <DistributionChart
        bins={results.histogram}
        accepted={results.accepted}
        markers={markers}
        format={format}
        axisLabel={unit ? `${results.metric_label} (${unit})` : results.metric_label}
      />

      <section className={styles.section}>
        <h4 className={lab.sectionTitle}>Percentiles</h4>
        <div className={lab.tableScroll}>
          <table className={lab.table}>
            <thead>
              <tr>
                <th scope="col">Percentile</th>
                <th scope="col" className={lab.numeric}>
                  Value
                </th>
                <th scope="col">What the draws support</th>
              </tr>
            </thead>
            <tbody>
              {summary.percentiles.map((item) => (
                <tr key={item.p}>
                  <th scope="row">P{item.p}</th>
                  <td className={lab.numeric}>{format(item.value)}</td>
                  <td>
                    {item.interval
                      ? `${format(item.interval.lower)} to ${format(item.interval.upper)} — order statistics ${item.interval.lower_rank} and ${item.interval.upper_rank}, exact coverage ${formatShare(item.interval.coverage)}`
                      : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className={styles.section}>
        <h4 className={lab.sectionTitle}>The quantities drawn</h4>
        <div className={lab.tableScroll}>
          <table className={lab.table}>
            <thead>
              <tr>
                <th scope="col">Quantity</th>
                <th scope="col">Distribution</th>
                <th scope="col" className={lab.numeric}>
                  Mean of accepted draws
                </th>
                <th scope="col">Rank correlation with the result</th>
              </tr>
            </thead>
            <tbody>
              {results.quantities.map((item) => {
                const shape = item.distribution;
                const target = byId.get(item.target) ?? {
                  unit: item.unit,
                  unit_label: item.unit ?? "",
                  max_decimals: 4,
                };
                const q = (value: string | null | undefined) =>
                  value ? formatQuantity(value, target) : "—";
                const text =
                  shape.kind === "discrete"
                    ? `Discrete: ${(shape.values ?? []).map(q).join(", ")}${shape.weights ? ` (weights ${shape.weights.join(" : ")})` : ""}`
                    : shape.kind === "triangular"
                      ? `Triangular: ${q(shape.low)}, most likely ${q(shape.mode)}, ${q(shape.high)}`
                      : `Uniform: ${q(shape.low)} to ${q(shape.high)}`;
                return (
                  <tr key={item.target}>
                    <th scope="row">
                      {item.label}
                      <span className={lab.rowNote}>As executed {q(item.base_value)}</span>
                    </th>
                    <td>{text}</td>
                    <td className={lab.numeric}>{q(item.accepted_mean)}</td>
                    <td>{correlationBar(item.rank_correlation)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <p className={lab.caption}>
          Spearman's rank correlation: how consistently the result rises (+) or falls (−) with each
          quantity across the draws. Association within the sample — not causation, and not a share
          of the spread.
        </p>
      </section>

      <section className={styles.section}>
        <h4 className={lab.sectionTitle}>Every line and metric</h4>
        <div className={lab.tableScroll}>
          <table className={lab.table}>
            <thead>
              <tr>
                <th scope="col">Line or metric</th>
                <th scope="col" className={lab.numeric}>
                  As executed
                </th>
                <th scope="col" className={lab.numeric}>
                  Mean
                </th>
                <th scope="col" className={lab.numeric}>
                  P5
                </th>
                <th scope="col" className={lab.numeric}>
                  P50
                </th>
                <th scope="col" className={lab.numeric}>
                  P95
                </th>
              </tr>
            </thead>
            <tbody>
              {results.outputs.map((item) => (
                <tr key={item.id} data-emphasis={item.id === metric ? "true" : undefined}>
                  <th scope="row">
                    {item.label}
                    {item.kind === "line_change" && (
                      <span className={lab.rowNote}>Change over the horizon</span>
                    )}
                  </th>
                  {[item.base, item.mean, item.p5, item.p50, item.p95].map((value, index) => (
                    // biome-ignore lint/suspicious/noArrayIndexKey: columns are positional
                    <td key={index} className={lab.numeric}>
                      {formatMetric(value, item.id)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <details className={styles.details}>
        <summary>How reliable is this estimate?</summary>
        <div className={styles.section}>
          <p className={lab.caption}>
            Standard error of the mean {format(summary.standard_error)}
            {summary.relative_standard_error !== null &&
              ` (${formatShare(summary.relative_standard_error)} of the mean)`}
            . First half of the draws: mean {format(results.convergence.first_half_mean)}; second
            half: {format(results.convergence.second_half_mean)}
            {results.convergence.halves_z !== null &&
              ` — ${formatRounded(results.convergence.halves_z, 2)} standard errors apart`}
            .{results.convergence.halves_flagged && " The halves disagree: use more draws."}
          </p>
          <ConvergenceChart checkpoints={results.convergence.checkpoints} format={format} />
          {results.rejections.length > 0 && (
            <>
              <h4 className={lab.sectionTitle}>Rejected draws</h4>
              <ul className={styles.notes}>
                {results.rejections.map((item) => (
                  <li key={item.code}>
                    {item.count} × {item.example}
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      </details>

      <ul className={styles.notes}>
        {results.notes.map((note) => (
          <li key={note}>{note}</li>
        ))}
      </ul>
      <Reproduce executionId={executionId} analysis={analysis} />
    </article>
  );
}

// --- The tab --------------------------------------------------------------------------------

export function UncertaintyView({
  executionId,
  currency,
}: {
  executionId: string | null;
  currency: string;
}) {
  const id = executionId ?? "";
  const targets = useApiResource(`lab:analysis-targets:${id}`, () =>
    executionId ? labApi.analyses.targets(executionId) : Promise.reject(new Error("No execution.")),
  );
  const listKey = `lab:analyses:${id}`;
  const analyses = useApiResource(listKey, () =>
    executionId ? labApi.analyses.list(executionId) : Promise.resolve({ items: [] }),
  );
  const [selected, setSelected] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);
  const history =
    analyses.status === "success"
      ? analyses.data.items.filter((item) => item.kind === "monte_carlo")
      : [];
  const shownId = selected ?? history[0]?.id ?? null;
  const analysis = useApiResource(`lab:analysis:${id}:${shownId ?? "none"}`, () =>
    executionId && shownId
      ? labApi.analyses.get(executionId, shownId)
      : Promise.resolve(null as ScenarioAnalysis | null),
  );

  if (!executionId) {
    return (
      <EmptyState title="Stochastic analysis needs a stored execution">
        Execute the scenario first: each draw re-evaluates its stored model runs.
      </EmptyState>
    );
  }

  const run = async (draft: MonteCarloDraft) => {
    if (targets.status !== "success") return;
    const labels = new Map(targets.data.targets.map((target) => [target.id, target.label]));
    const built = monteCarloRequest(draft, labels);
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

  return (
    <div className={lab.sensitivityView}>
      <AnalysisTypes current="stochastic" />
      {targets.status === "loading" && (
        <LoadingState label="Reading what this execution can vary" />
      )}
      {targets.status === "error" && <ErrorState error={targets.error} onRetry={targets.reload} />}
      {targets.status === "success" && (
        <MonteCarloForm
          targets={targets.data}
          running={running}
          errors={errors}
          onRun={(draft) => void run(draft)}
        />
      )}
      {history.length > 0 && (
        <section className={styles.section} aria-label="Stored Monte Carlo analyses">
          <h4 className={lab.sectionTitle}>Stored analyses of this execution</h4>
          <div className={styles.history}>
            {history.map((item) => (
              <button
                key={item.id}
                type="button"
                className={styles.historyItem}
                aria-current={item.id === shownId ? "true" : undefined}
                onClick={() => setSelected(item.id)}
              >
                <span>
                  {item.metric_label} · {item.quantities.join(", ")}
                  <span className={lab.rowNote}>
                    {item.draws} draws · seed {item.seed} · {formatDateTime(item.created_at)}
                  </span>
                </span>
                <span className="tabular">mean {formatMetric(item.mean, item.metric)}</span>
              </button>
            ))}
          </div>
        </section>
      )}
      {analysis.status === "error" && (
        <ErrorState error={analysis.error} onRetry={analysis.reload} />
      )}
      {analysis.status === "success" && analysis.data?.monte_carlo && (
        <MonteCarloResult
          executionId={executionId}
          analysis={analysis.data}
          results={analysis.data.monte_carlo}
          currency={currency}
          targets={targets.status === "success" ? targets.data.targets : []}
        />
      )}
      {analyses.status === "success" && history.length === 0 && (
        <p className={lab.caption}>No Monte Carlo analysis of this execution yet.</p>
      )}
    </div>
  );
}
