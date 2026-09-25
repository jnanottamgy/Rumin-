/**
 * Stored runs of a model, newest first. Runs are never changed or deleted, so any of them
 * can be reopened, explained and checked again.
 */
import { Link } from "react-router";
import { ScrollRegion } from "@/components/ScrollRegion";
import { EmptyState, ErrorState, LoadingState } from "@/components/States";
import { useApiResource } from "@/hooks/useApiResource";
import { formatDateTime } from "@/lib/format";
import { simulationApi } from "@/services/api";
import { formatUnitValue, shortHash } from "./format";
import styles from "./Simulation.module.css";

export const RUNS_KEY = (modelId: string) => `simulation:runs:${modelId}`;

export function RunHistory({
  modelId,
  currentRunId,
}: {
  modelId: string;
  currentRunId: string | null;
}) {
  const runs = useApiResource(RUNS_KEY(modelId), () => simulationApi.runs({ modelId, limit: 10 }));
  if (runs.status === "loading") return <LoadingState label="Loading stored runs…" />;
  if (runs.status === "error") return <ErrorState error={runs.error} onRetry={runs.reload} />;
  if (runs.data.items.length === 0) {
    return (
      <EmptyState title="No stored runs yet">
        Runs appear here once calculated, newest first. They are kept exactly as calculated.
      </EmptyState>
    );
  }
  const columns = runs.data.items[0]?.headline.slice(0, 2) ?? [];
  return (
    <ScrollRegion className={styles.tableScroll}>
      <table className={styles.table}>
        <caption className="visually-hidden">Stored runs, newest first</caption>
        <thead>
          <tr>
            <th scope="col">Run</th>
            <th scope="col">Calculated</th>
            {columns.map((output) => (
              <th key={output.id} scope="col">
                {output.label}
              </th>
            ))}
            <th scope="col">Result hash</th>
          </tr>
        </thead>
        <tbody>
          {runs.data.items.map((run) => (
            <tr key={run.id} aria-current={run.id === currentRunId ? "true" : undefined}>
              <th scope="row">
                <Link to={`/simulation/runs/${run.id}`}>{run.label ?? "Untitled run"}</Link>
                {run.entity && <span className={styles.barSub}>{run.entity.name}</span>}
              </th>
              <td>{formatDateTime(run.created_at)}</td>
              {columns.map((column) => {
                const output = run.headline.find((item) => item.id === column.id);
                return (
                  <td key={column.id} className="tabular">
                    {output ? formatUnitValue(output.value, output.unit, { signed: true }) : "—"}
                  </td>
                );
              })}
              <td className="mono">{shortHash(run.result_hash)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {runs.data.total > runs.data.items.length && (
        <p className={styles.note}>
          Showing the latest {runs.data.items.length} of {runs.data.total} stored runs.
        </p>
      )}
    </ScrollRegion>
  );
}
