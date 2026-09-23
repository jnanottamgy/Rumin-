/**
 * Simulation preview (Phase 4): choose a model, enter its inputs, check them, run it, and
 * read the stored run — its pathway, months, contributions, sensitivity, calculation and
 * provenance. Every calculation happens on the server; this page collects inputs and
 * shows what the engine returned.
 *
 * Routes: /simulation (a new run) and /simulation/runs/:runId (a stored run, with its
 * inputs loaded into the form so it can be varied and run again).
 */
import { useEffect, useId, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router";
import { PageHeader } from "@/components/PageHeader";
import { Panel } from "@/components/Panel";
import { ErrorState, LoadingState } from "@/components/States";
import { StatusIndicator } from "@/components/StatusIndicator";
import { exampleSummary, withExample } from "@/features/simulation/examples";
import {
  emptyForm,
  type FieldIssue,
  type FieldState,
  type FormState,
  formFromRun,
  issuesFromDetails,
  issuesFromReport,
  toRequestInputs,
} from "@/features/simulation/form";
import { ModelOverview } from "@/features/simulation/ModelOverview";
import { RUNS_KEY, RunHistory } from "@/features/simulation/RunHistory";
import { RunResults } from "@/features/simulation/RunResults";
import styles from "@/features/simulation/Simulation.module.css";
import { SimulationForm } from "@/features/simulation/SimulationForm";
import { invalidateResource, setResourceData, useApiResource } from "@/hooks/useApiResource";
import { ApiError, describeError } from "@/lib/apiClient";
import { graphApi, simulationApi } from "@/services/api";
import type {
  SimulationIssue,
  SimulationModelDetail,
  SimulationModelSummary,
  SimulationRun,
} from "@/types/api";

type Check =
  | { state: "none" }
  | { state: "valid"; warnings: SimulationIssue[] }
  | { state: "invalid"; issues: FieldIssue[] }
  | { state: "failed"; message: string };

/** The node every airline must be connected to, from the model's own relationships. */
function entityAnchor(model: SimulationModelDetail): string | null {
  const required = model.supporting_relationships.find((item) => item.required_with_entity);
  if (!required) return null;
  return required.source === "{entity}" ? required.target : required.source;
}

function Workspace({
  modelId,
  models,
  run,
  onModelChange,
}: {
  modelId: string;
  models: SimulationModelSummary[];
  run: SimulationRun | null;
  onModelChange: (id: string) => void;
}) {
  const navigate = useNavigate();
  const location = useLocation();
  const model = useApiResource(`simulation:model:${modelId}`, () => simulationApi.model(modelId));
  const anchor = model.status === "success" ? entityAnchor(model.data) : null;
  const airlines = useApiResource(`simulation:entities:${anchor ?? "-"}`, () =>
    anchor
      ? graphApi.search({ types: ["company"], relatedTo: anchor, limit: 50 })
      : Promise.resolve(null),
  );
  const [form, setForm] = useState<FormState | null>(null);
  const [label, setLabel] = useState("");
  const [check, setCheck] = useState<Check>({ state: "none" });
  const [busy, setBusy] = useState<"validating" | "running" | null>(null);
  const modelSelectId = useId();
  const fresh = (location.state as { fresh?: boolean } | null)?.fresh === true;

  const detail = model.status === "success" ? model.data : null;
  const runKey = run?.id ?? null;
  // A new model or a newly opened run resets the form to match it.
  // biome-ignore lint/correctness/useExhaustiveDependencies: reset only when the run or model changes
  useEffect(() => {
    if (!detail) return;
    setForm(run && run.model_id === detail.id ? formFromRun(detail, run) : emptyForm(detail));
    setLabel("");
    setCheck({ state: "none" });
  }, [detail?.id, runKey]);

  if (model.status === "loading" || (detail && !form)) {
    return <LoadingState label="Loading the model…" lines={6} />;
  }
  if (model.status === "error" || !detail || !form) {
    return <ErrorState error={model.error} onRetry={model.reload} />;
  }

  const request = () => ({ model_id: detail.id, inputs: toRequestInputs(detail, form) });
  const issues = check.state === "invalid" ? check.issues : [];

  function update(id: string, next: FieldState) {
    setForm((previous) => (previous ? { ...previous, [id]: next } : previous));
    if (check.state !== "none") setCheck({ state: "none" });
  }

  async function validate() {
    setBusy("validating");
    try {
      const report = await simulationApi.validate(request());
      setCheck(
        report.valid
          ? { state: "valid", warnings: report.warnings }
          : { state: "invalid", issues: issuesFromReport(report.errors) },
      );
    } catch (error) {
      setCheck({ state: "failed", message: describeError(error) });
    } finally {
      setBusy(null);
    }
  }

  async function runModel() {
    setBusy("running");
    try {
      const created = await simulationApi.run({ ...request(), label: label.trim() || null });
      setResourceData(`simulation:run:${created.id}`, created);
      invalidateResource(RUNS_KEY(detail?.id ?? ""));
      invalidateResource("simulation:models");
      navigate(`/simulation/runs/${created.id}`, { state: { fresh: true } });
    } catch (error) {
      if (error instanceof ApiError && error.status === 422 && error.details.length > 0) {
        setCheck({ state: "invalid", issues: issuesFromDetails(error.details) });
      } else {
        setCheck({ state: "failed", message: describeError(error) });
      }
    } finally {
      setBusy(null);
    }
  }

  const example = withExample(detail.id, form);
  const summary = exampleSummary(detail.id);

  return (
    <div className={styles.workspace} data-has-run={run ? "true" : undefined}>
      <aside className={styles.formColumn} aria-label="Inputs">
        <Panel
          title="Inputs"
          description="Every calculation runs on the server. Nothing you enter is changed or filled in."
        >
          <div className={styles.modelChoice}>
            <label htmlFor={modelSelectId}>Model</label>
            <select
              id={modelSelectId}
              value={detail.id}
              onChange={(event) => onModelChange(event.target.value)}
            >
              {models.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name} {item.version}
                </option>
              ))}
            </select>
            <p className={styles.fieldMeta}>{detail.summary}</p>
          </div>
          <SimulationForm
            model={detail}
            form={form}
            label={label}
            issues={issues}
            busy={busy}
            airlines={airlines.status === "success" ? (airlines.data?.items ?? []) : null}
            onChange={update}
            onLabelChange={setLabel}
            onValidate={validate}
            onRun={runModel}
            onExample={
              example
                ? () => {
                    setForm(example);
                    setCheck({ state: "none" });
                  }
                : null
            }
            onClear={() => {
              setForm(emptyForm(detail));
              setCheck({ state: "none" });
            }}
          />
          {summary && (
            <p className={styles.exampleNote}>
              The example: {summary} Hypothetical figures, not data.
            </p>
          )}
          <div aria-live="polite" className={styles.checkResult}>
            {check.state === "valid" && (
              <div>
                <StatusIndicator tone="good" label="The inputs are valid" />
                {check.warnings.length > 0 && (
                  <ul className={styles.warnings}>
                    {check.warnings.map((warning) => (
                      <li key={`${warning.code}-${warning.message}`}>{warning.message}</li>
                    ))}
                  </ul>
                )}
              </div>
            )}
            {check.state === "failed" && (
              <p className={styles.errorText} role="alert">
                {check.message}
              </p>
            )}
          </div>
        </Panel>
      </aside>

      <div className={styles.resultColumn}>
        {run ? (
          <RunResults key={run.id} run={run} model={detail} animate={fresh} />
        ) : (
          <ModelOverview model={detail} />
        )}
      </div>
    </div>
  );
}

export function SimulationPage() {
  const { runId } = useParams();
  const navigate = useNavigate();
  const models = useApiResource("simulation:models", () => simulationApi.models());
  const run = useApiResource(`simulation:run:${runId ?? "-"}`, () =>
    runId ? simulationApi.get(runId) : Promise.resolve(null),
  );
  const [chosen, setChosen] = useState<string | null>(null);

  useEffect(() => {
    document.title = run.data?.label
      ? `${run.data.label} — Simulation — RUMIN`
      : "Simulation — RUMIN";
  }, [run.data?.label]);

  const header = (
    <PageHeader
      title="Simulation"
      description="Deterministic calculations from the inputs and assumptions you can see: how a shock travels through one airline's costs, month by month. Results are not forecasts and not investment advice."
    />
  );

  if (models.status === "loading" || run.status === "loading") {
    return (
      <div className={styles.page}>
        {header}
        <LoadingState label="Loading simulation models…" lines={6} />
      </div>
    );
  }
  if (models.status === "error") {
    return (
      <div className={styles.page}>
        {header}
        <ErrorState error={models.error} onRetry={models.reload} />
      </div>
    );
  }
  if (run.status === "error") {
    return (
      <div className={styles.page}>
        {header}
        <ErrorState title="This run could not be opened" error={run.error} onRetry={run.reload} />
      </div>
    );
  }

  const stored = run.data ?? null;
  const modelId = stored?.model_id ?? chosen ?? models.data[0]?.id ?? null;
  if (!modelId) {
    return (
      <div className={styles.page}>
        {header}
        <ErrorState error={new Error("No simulation model is registered.")} />
      </div>
    );
  }

  return (
    <div className={styles.page}>
      {header}
      <Workspace
        modelId={modelId}
        models={models.data}
        run={stored}
        onModelChange={(id) => {
          setChosen(id);
          if (runId) navigate("/simulation");
        }}
      />
      <Panel
        title="Stored runs"
        description="Every run is kept as calculated. Open one to see how it was reached, or to vary it."
      >
        <RunHistory modelId={modelId} currentRunId={stored?.id ?? null} />
      </Panel>
    </div>
  );
}
