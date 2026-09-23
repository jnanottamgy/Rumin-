/**
 * Sensitivity of a stored run: choose the result to rank by, run the model's default
 * one-at-a-time analysis on the server, and read it as a tornado. Analyses are stored
 * with the run, so they can be reopened and re-checked.
 */
import { useId, useState } from "react";
import { Button } from "@/components/Button";
import { EmptyState, ErrorState, LoadingState } from "@/components/States";
import { invalidateResource, useApiResource } from "@/hooks/useApiResource";
import { describeError } from "@/lib/apiClient";
import { formatDateTime } from "@/lib/format";
import { simulationApi } from "@/services/api";
import type { SimulationModelDetail, SimulationRun } from "@/types/api";
import styles from "./Simulation.module.css";
import { TornadoChart } from "./TornadoChart";

export function SensitivityPanel({
  run,
  model,
}: {
  run: SimulationRun;
  model: SimulationModelDetail;
}) {
  const key = `simulation:sensitivity:${run.id}`;
  const analyses = useApiResource(key, () => simulationApi.sensitivity.list(run.id));
  const metrics = run.outputs.filter((output) => output.kind === "simulated");
  const [metric, setMetric] = useState(
    model.sensitivity_metric ?? metrics[0]?.id ?? run.outputs[0]?.id ?? "",
  );
  const [running, setRunning] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const selectId = useId();
  const unitLabels = Object.fromEntries(run.inputs.map((input) => [input.id, input.unit_label]));
  const metricUnit = run.outputs.find((output) => output.id === metric)?.unit ?? "";
  const defaults = model.sensitivity_defaults
    .map((id) => run.inputs.find((input) => input.id === id)?.label ?? id)
    .join(", ");

  async function analyse() {
    setRunning(true);
    setFailure(null);
    try {
      await simulationApi.sensitivity.create(run.id, { metric, inputs: [] });
      invalidateResource(key);
      invalidateResource(`simulation:run:${run.id}`);
    } catch (error) {
      setFailure(describeError(error));
    } finally {
      setRunning(false);
    }
  }

  const current =
    analyses.status === "success"
      ? analyses.data.items.find((analysis) => analysis.metric === metric)
      : undefined;

  return (
    <div className={styles.sensitivity}>
      <p className={styles.lead}>
        Each input moves on its own — lowered and raised by a stated step — while every other input
        keeps this run's value. The spread shows how much the result depends on that input, not how
        likely any value is.
      </p>
      <div className={styles.inlineField}>
        <label htmlFor={selectId}>Rank by</label>
        <select id={selectId} value={metric} onChange={(event) => setMetric(event.target.value)}>
          {metrics.map((output) => (
            <option key={output.id} value={output.id}>
              {output.label}
            </option>
          ))}
        </select>
        <Button variant="primary" onClick={analyse} disabled={running}>
          {running ? "Analysing…" : current ? "Run the analysis again" : "Run the analysis"}
        </Button>
      </div>
      <p className={styles.note}>Inputs varied: {defaults}.</p>
      {failure && (
        <p className={styles.errorText} role="alert">
          {failure}
        </p>
      )}
      {analyses.status === "loading" && <LoadingState label="Loading analyses…" />}
      {analyses.status === "error" && (
        <ErrorState error={analyses.error} onRetry={analyses.reload} />
      )}
      {analyses.status === "success" &&
        (current ? (
          <>
            <TornadoChart analysis={current} metricUnit={metricUnit} unitLabels={unitLabels} />
            <p className={styles.note}>
              {current.evaluations} evaluations in {current.duration_ms} ms, stored{" "}
              {formatDateTime(current.created_at)}. {current.note}
            </p>
          </>
        ) : (
          <EmptyState title="No analysis for this result yet">
            Run the analysis to see which inputs move{" "}
            {metrics.find((output) => output.id === metric)?.label.toLowerCase() ?? "it"} the most.
          </EmptyState>
        ))}
    </div>
  );
}
