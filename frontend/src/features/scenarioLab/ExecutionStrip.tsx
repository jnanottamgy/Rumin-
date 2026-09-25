/**
 * The execution's progress, exactly as the server records it.
 *
 * Each stage appears when the server reports it, with the times it stored; nothing on
 * this strip advances by itself. Executions of RUMIN's models take milliseconds, so a
 * stage often finishes before the page asks again: the strip then shows the stages that
 * were recorded, with their real durations, drawn to scale.
 */
import { Link } from "react-router";
import { Button } from "@/components/Button";
import { Icon } from "@/components/Icon";
import { cx } from "@/lib/cx";
import type { ScenarioExecution } from "@/types/api";
import { duration, elapsed, isFinal, STATUS_LABEL } from "./format";
import styles from "./ScenarioLab.module.css";

const STAGES = ["validating", "simulating", "propagating", "aggregating"] as const;
const STAGE_DETAIL: Record<(typeof STAGES)[number], string> = {
  validating: "Plan rebuilt, inputs validated, graph relationships confirmed",
  simulating: "Each model executed by the Phase 4 engine",
  propagating: "Changes followed through the models' runs",
  aggregating: "Lines, metrics, months and stress cases combined and stored",
};

export function ExecutionStrip({
  execution,
  busy,
  executeLabel,
  disabledReason,
  onExecute,
  onCancel,
}: {
  execution: ScenarioExecution | null;
  busy: boolean;
  executeLabel: string;
  disabledReason: string | null;
  onExecute: () => void;
  /** Absent when this person may not cancel (Phase 10: the scenario's owner or an admin). */
  onCancel?: () => void;
}) {
  const recorded = new Map((execution?.stages ?? []).map((stage) => [stage.stage, stage]));
  const running = execution !== null && !isFinal(execution.status);
  const durations = STAGES.map((stage) => {
    const entry = recorded.get(stage);
    return entry ? (elapsed(entry.started_at, entry.finished_at) ?? 0) : 0;
  });
  const total = durations.reduce((sum, value) => sum + value, 0);

  return (
    <section className={styles.executionStrip} aria-label="Execution">
      <div className={styles.executionActions}>
        {running ? (
          onCancel && (
            <Button
              variant="secondary"
              size="sm"
              onClick={onCancel}
              icon={<Icon name="close" size={14} />}
            >
              Cancel
            </Button>
          )
        ) : (
          <Button
            variant="primary"
            size="sm"
            onClick={onExecute}
            disabled={busy || disabledReason !== null}
            icon={<Icon name="play" size={14} />}
            title={disabledReason ?? undefined}
          >
            {busy ? "Starting…" : executeLabel}
          </Button>
        )}
        <p className={styles.executionStatus} role="status" aria-live="polite">
          {execution === null
            ? (disabledReason ?? "Not executed yet: what you see is a live preview, not stored.")
            : execution.status === "completed"
              ? `Completed in ${duration(execution.duration_ms)} · version ${execution.version} · stored and reproducible`
              : execution.status === "failed"
                ? `Failed: ${execution.error?.message ?? "see the details"}`
                : execution.status === "cancelled"
                  ? "Cancelled. Nothing was stored."
                  : `${STATUS_LABEL[execution.status]} — as reported by the server`}
        </p>
        {execution?.status === "completed" && (
          <Link
            className={styles.runLink}
            to={`/universe/3d?execution=${encodeURIComponent(execution.id)}`}
          >
            <Icon name="layers" size={12} />
            See it in the 3D universe
          </Link>
        )}
      </div>

      <ol className={styles.stages}>
        {STAGES.map((stage, index) => {
          const entry = recorded.get(stage);
          const current = execution?.status === stage;
          const state = entry ? (entry.finished_at ? "done" : "current") : "pending";
          return (
            <li
              key={stage}
              className={styles.stage}
              data-state={current ? "current" : state}
              aria-current={current ? "step" : undefined}
              title={STAGE_DETAIL[stage]}
            >
              <span className={styles.stageMarker} aria-hidden="true">
                {state === "done" ? <Icon name="check" size={11} /> : index + 1}
              </span>
              <span className={styles.stageName}>{STATUS_LABEL[stage]}</span>
              <span className={styles.stageTime}>
                {entry?.finished_at ? duration(durations[index]) : current ? "running" : ""}
              </span>
            </li>
          );
        })}
        <li
          className={cx(styles.stage, styles.stageFinal)}
          data-state={execution && isFinal(execution.status) ? execution.status : "pending"}
        >
          <span className={styles.stageMarker} aria-hidden="true">
            <Icon
              name={
                execution?.status === "failed" || execution?.status === "cancelled"
                  ? "close"
                  : "check"
              }
              size={11}
            />
          </span>
          <span className={styles.stageName}>
            {execution && isFinal(execution.status) ? STATUS_LABEL[execution.status] : "Stored"}
          </span>
        </li>
      </ol>

      {total > 0 && execution?.status === "completed" && (
        <div
          className={styles.stageScale}
          aria-hidden="true"
          title="Recorded stage durations, to scale"
        >
          {STAGES.map((stage, index) => (
            <span
              key={stage}
              data-stage={stage}
              style={{ flexGrow: Math.max(durations[index] ?? 0, total * 0.02) }}
            />
          ))}
        </div>
      )}
    </section>
  );
}
