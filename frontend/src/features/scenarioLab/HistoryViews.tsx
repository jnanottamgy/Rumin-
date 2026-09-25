/**
 * The scenario's history — every version (immutable) and every execution (reproducible) —
 * and the comparison of executions side by side. Nothing is ranked: which result is
 * preferable depends on an objective only the user can state.
 */
import { useState } from "react";
import { Link } from "react-router";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { Icon } from "@/components/Icon";
import { EmptyState, ErrorState, LoadingState } from "@/components/States";
import { useApiResource } from "@/hooks/useApiResource";
import { describeError } from "@/lib/apiClient";
import { cx } from "@/lib/cx";
import { formatDateTime } from "@/lib/format";
import { labApi } from "@/services/api";
import type { ExecutionVerification, Scenario, ScenarioExecutionSummary } from "@/types/api";
import {
  changeLabel,
  compactMoney,
  duration,
  metricValue,
  percentValue,
  STATUS_LABEL,
} from "./format";
import styles from "./ScenarioLab.module.css";

export function HistoryView({
  scenario,
  executions,
  selectedExecution,
  compareIds,
  onToggleCompare,
  onOpenExecution,
  onRestore,
}: {
  scenario: Scenario;
  executions: ScenarioExecutionSummary[];
  selectedExecution: string | null;
  compareIds: string[];
  onToggleCompare: (id: string) => void;
  onOpenExecution: (id: string) => void;
  /** Absent when this person may not change the scenario (Phase 10). */
  onRestore?: (version: number) => void;
}) {
  const [verified, setVerified] = useState<Record<string, ExecutionVerification | string>>({});
  const verify = async (id: string) => {
    try {
      const result = await labApi.verify(id);
      setVerified((previous) => ({ ...previous, [id]: result }));
    } catch (error) {
      setVerified((previous) => ({ ...previous, [id]: describeError(error) }));
    }
  };
  return (
    <div className={styles.historyView}>
      <section>
        <h3 className={styles.sectionTitle}>Executions</h3>
        {executions.length === 0 ? (
          <p className={styles.caption}>
            No execution yet. Execute the scenario to store a reproducible result.
          </p>
        ) : (
          <div className={styles.tableScroll}>
            <table className={styles.table}>
              <caption className="visually-hidden">
                Every execution of this scenario, newest first, with its headline result
              </caption>
              <thead>
                <tr>
                  <th scope="col">
                    <span className="visually-hidden">Compare</span>
                  </th>
                  <th scope="col">Execution</th>
                  <th scope="col">Status</th>
                  <th scope="col" className={styles.numeric}>
                    Headline
                  </th>
                  <th scope="col">Reproducible?</th>
                </tr>
              </thead>
              <tbody>
                {executions.map((execution) => {
                  const check = verified[execution.id];
                  const headline = execution.headline[0];
                  return (
                    <tr
                      key={execution.id}
                      aria-current={execution.id === selectedExecution ? "true" : undefined}
                    >
                      <td>
                        <input
                          type="checkbox"
                          aria-label={`Compare the execution of ${formatDateTime(execution.requested_at)}`}
                          checked={compareIds.includes(execution.id)}
                          disabled={execution.status !== "completed"}
                          onChange={() => onToggleCompare(execution.id)}
                        />
                      </td>
                      <td className={styles.nowrap}>
                        <button
                          type="button"
                          className={styles.linkButton}
                          onClick={() => onOpenExecution(execution.id)}
                        >
                          {formatDateTime(execution.requested_at)}
                        </button>
                        <span className={styles.rowNote}>
                          v{execution.version}
                          {execution.duration_ms !== null &&
                            ` · ${duration(execution.duration_ms)}`}
                        </span>
                      </td>
                      <td>
                        <Badge
                          tone={
                            execution.status === "completed"
                              ? "good"
                              : execution.status === "failed"
                                ? "critical"
                                : "outline"
                          }
                        >
                          {STATUS_LABEL[execution.status]}
                        </Badge>
                        {execution.error && (
                          <span className={styles.rowNote}>{execution.error.message}</span>
                        )}
                      </td>
                      <td className={styles.numeric}>
                        {headline ? (
                          <>
                            {compactMoney(headline.change)} {headline.currency}
                            <span className={styles.rowNote}>
                              {headline.label.toLowerCase()} ·{" "}
                              {percentValue(headline.percent_change)}
                            </span>
                          </>
                        ) : (
                          "—"
                        )}
                      </td>
                      <td>
                        {execution.status !== "completed" ? (
                          "—"
                        ) : check === undefined ? (
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => void verify(execution.id)}
                          >
                            Verify
                          </Button>
                        ) : typeof check === "string" ? (
                          <span className={styles.errorText}>{check}</span>
                        ) : (
                          <span className={check.reproduced ? styles.good : styles.errorText}>
                            <Icon name={check.reproduced ? "check" : "alert"} size={12} />{" "}
                            {check.message}
                          </span>
                        )}
                        {execution.result_hash && (
                          <span
                            className={cx(styles.rowNote, "mono")}
                            title={execution.result_hash}
                          >
                            result {execution.result_hash.slice(0, 10)}
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
      <section>
        <h3 className={styles.sectionTitle}>Versions</h3>
        <ul className={styles.versionList}>
          {scenario.versions.map((version) => (
            <li key={version.version}>
              <span className={styles.versionNumber}>v{version.version}</span>
              <span>
                {version.name}
                <span className={styles.rowNote}>
                  {formatDateTime(version.created_at)} · {version.executions}{" "}
                  {version.executions === 1 ? "execution" : "executions"} · hash{" "}
                  {version.spec_hash.slice(0, 12)}
                  {version.derived_from &&
                    ` · ${version.derived_from.kind === "restore" ? "restored from" : "duplicated from"} v${version.derived_from.version}`}
                  {version.note && ` · ${version.note}`}
                </span>
              </span>
              {onRestore && version.version !== scenario.current_version && (
                <Button size="sm" variant="ghost" onClick={() => onRestore(version.version)}>
                  Restore as v{scenario.current_version + 1}
                </Button>
              )}
            </li>
          ))}
        </ul>
        <p className={styles.caption}>
          Versions are never changed: restoring saves the old content as a new version, and every
          execution keeps pointing at the version it ran.
        </p>
      </section>
    </div>
  );
}

export function CompareView({ ids, onClear }: { ids: string[]; onClear: () => void }) {
  const [reference, setReference] = useState<string | null>(null);
  const key = `lab:compare:${ids.join(",")}:${reference ?? ""}`;
  const comparison = useApiResource(key, () =>
    ids.length >= 2 ? labApi.compare(ids, reference) : Promise.resolve(null),
  );
  if (ids.length < 2) {
    return (
      <EmptyState title="Choose executions to compare">
        Tick two to six completed executions under History — of this scenario or, from the Lab's
        library, of others — and they appear here side by side.
      </EmptyState>
    );
  }
  if (comparison.status === "loading") return <LoadingState lines={4} />;
  if (comparison.status === "error")
    return <ErrorState error={comparison.error} onRetry={comparison.reload} />;
  const data = comparison.data;
  if (!data) return null;
  const columns = data.executions;
  return (
    <div className={styles.compareView}>
      <div className={styles.viewToolbar}>
        <label className={styles.inlineSelect}>
          <span>Reference</span>
          <select value={data.reference} onChange={(event) => setReference(event.target.value)}>
            {columns.map((item) => (
              <option key={item.execution_id} value={item.execution_id}>
                {item.scenario_name} v{item.version}
              </option>
            ))}
          </select>
        </label>
        <Button size="sm" variant="ghost" onClick={onClear}>
          Clear the selection
        </Button>
      </div>
      <div className={styles.tableScroll}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th scope="col">Line</th>
              {columns.map((item) => (
                <th key={item.execution_id} scope="col">
                  {item.scenario_name}
                  <span className={styles.rowNote}>
                    v{item.version} · {item.currency} · {item.horizon_months} months
                    {item.execution_id === data.reference ? " · reference" : ""}
                    {!data.comparable[item.execution_id] ? " · not differenced" : ""}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            <tr>
              <th scope="row">Changes</th>
              {columns.map((item) => (
                <td key={item.execution_id}>
                  {item.changes
                    .map((change) => `${change.name} ${changeLabel(change.value, change.unit)}`)
                    .join("; ")}
                </td>
              ))}
            </tr>
            <tr>
              <th scope="row">Models</th>
              {columns.map((item) => (
                <td key={item.execution_id}>
                  {item.models.map((model) => model.title).join(", ")}
                </td>
              ))}
            </tr>
            {data.lines.map((row) => (
              <tr key={row.id}>
                <th scope="row">{row.label}</th>
                {row.values.map((cell) => (
                  <td key={cell.execution_id} className="tabular">
                    {cell.modelled ? (
                      compactMoney(cell.change)
                    ) : (
                      <span className={styles.muted}>Not modelled</span>
                    )}
                    {cell.difference && (
                      <span className={styles.rowNote}>
                        {compactMoney(cell.difference.absolute)} vs reference
                        {cell.difference.percent
                          ? ` (${percentValue(cell.difference.percent)})`
                          : ""}
                      </span>
                    )}
                  </td>
                ))}
              </tr>
            ))}
            {data.metrics.map((row) => (
              <tr key={row.id}>
                <th scope="row">{row.label}</th>
                {row.values.map((cell) => (
                  <td key={cell.execution_id} className="tabular">
                    {cell.scenario
                      ? metricValue(
                          cell.scenario,
                          row.id === "interest_coverage" ? "times" : "ratio",
                        )
                      : "—"}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {data.inputs.length > 0 && (
        <section>
          <h3 className={styles.sectionTitle}>Inputs and assumptions that differ</h3>
          <div className={styles.tableScroll}>
            <table className={styles.table}>
              <tbody>
                {data.inputs.map((input) => (
                  <tr key={`${input.model_id}-${input.input}`}>
                    <th scope="row">
                      {input.label}
                      <span className={styles.rowNote}>
                        {input.model_id === "scenario"
                          ? "shared"
                          : input.model_id.replaceAll("_", " ")}
                      </span>
                    </th>
                    {input.values.map((value, index) => (
                      // biome-ignore lint/suspicious/noArrayIndexKey: columns are positional
                      <td key={index} className="tabular">
                        {value ? `${value.value ?? "—"} ${value.unit}` : "—"}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
      {data.pathways.length > 0 && (
        <p className={styles.caption}>
          {data.pathways.length} pathway links differ between these executions (models or changes
          that one uses and another does not).
        </p>
      )}
      <p className={styles.caption}>{data.note}</p>
      <p className={styles.caption}>
        <Link to="/scenarios">Library</Link> lists other scenarios' executions to add.
      </p>
    </div>
  );
}
