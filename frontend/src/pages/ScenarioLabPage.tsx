/**
 * The Scenario Lab: "what happens if X changes?", answered by the registered models with
 * the modelled pathway, not just a number.
 *
 * Layout: the controls on the left, the impact pathway in the centre, the results on the
 * right, the execution and the simulated months along the bottom. What the centre and the
 * right show is always labelled: a *live preview* the backend computes as you edit (not
 * stored), or a *stored execution* (reproducible, with its model runs and hashes).
 */
import { useCallback, useEffect, useMemo, useReducer, useState } from "react";
import { Link, useLocation, useNavigate, useParams, useSearchParams } from "react-router";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { EpistemicBadge } from "@/components/EpistemicBadge";
import { Icon } from "@/components/Icon";
import { PageHeader } from "@/components/PageHeader";
import { EmptyState, ErrorState, LoadingState } from "@/components/States";
import { MonthsView, SensitivityView, StressView } from "@/features/scenarioLab/AnalysisViews";
import {
  Builder,
  type FieldMessages,
  fieldId,
  type MessageSeverity,
} from "@/features/scenarioLab/Builder";
import {
  draftFromInput,
  draftFromScenario,
  draftReducer,
  emptyDraft,
  type LabDraft,
  missingBasics,
  sameScenario,
  toInput,
  toUpdate,
} from "@/features/scenarioLab/draft";
import { ExecutionStrip } from "@/features/scenarioLab/ExecutionStrip";
import { ExplainView } from "@/features/scenarioLab/ExplainView";
import { CompareView, HistoryView } from "@/features/scenarioLab/HistoryViews";
import { useExecution, usePreview } from "@/features/scenarioLab/hooks";
import { LabHome } from "@/features/scenarioLab/LabHome";
import { PathwayCanvas } from "@/features/scenarioLab/PathwayCanvas";
import { PlanView } from "@/features/scenarioLab/PlanView";
import { ResultsPanel } from "@/features/scenarioLab/ResultsPanel";
import styles from "@/features/scenarioLab/ScenarioLab.module.css";
import { TimelineStrip } from "@/features/scenarioLab/TimelineStrip";
import { Tabs } from "@/features/simulation/Tabs";
import { invalidateResource, setResourceData, useApiResource } from "@/hooks/useApiResource";
import { ApiError, describeError } from "@/lib/apiClient";
import { formatDateTime } from "@/lib/format";
import { api, labApi } from "@/services/api";
import type {
  EconomicVariable,
  Scenario,
  ScenarioExecutionSummary,
  ScenarioTemplate,
} from "@/types/api";

const scenarioKey = (id: string) => `scenario:${id}`;
const REPLAY_STEP_MS = 700;

function addMessage(
  messages: FieldMessages,
  field: string | null | undefined,
  message: string,
  severity: MessageSeverity,
) {
  const key = field ?? "form";
  const list = messages[key] ?? [];
  if (!list.some((item) => item.message === message)) list.push({ message, severity });
  messages[key] = list;
}

function Workspace({
  variables,
  scenario,
  template,
  executions,
}: {
  variables: EconomicVariable[];
  scenario: Scenario | null;
  template: ScenarioTemplate | null;
  executions: ScenarioExecutionSummary[];
}) {
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const initial = useMemo(
    () =>
      scenario
        ? draftFromScenario(scenario)
        : template
          ? draftFromInput(template.scenario)
          : emptyDraft(),
    [scenario, template],
  );
  const [draft, dispatch] = useReducer(draftReducer, initial);
  const saved = useMemo(() => (scenario ? draftFromScenario(scenario) : null), [scenario]);
  const dirty = saved ? !sameScenario(draft, saved) : true;

  const [saveErrors, setSaveErrors] = useState<FieldMessages>({});
  const [attempted, setAttempted] = useState(false);
  const [busy, setBusy] = useState<"save" | "execute" | null>(null);
  const [notice, setNotice] = useState<string | null>(
    (location.state as { notice?: string } | null)?.notice ?? null,
  );
  const [tab, setTab] = useState("pathway");
  const [month, setMonth] = useState<number | null>(null);
  const [playing, setPlaying] = useState(false);

  // Which stored execution to show: the one asked for, else the latest of this version.
  const requested = searchParams.get("execution");
  const latestOfVersion = executions.find(
    (item) => item.version === scenario?.current_version && item.status !== "failed",
  );
  const executionId = requested ?? latestOfVersion?.id ?? null;
  const followed = useExecution(executionId);
  const compareIds = searchParams.getAll("compare");

  // The live preview, computed by the backend while you edit.
  const input = useMemo(
    () =>
      draft.changes.some((change) => change.variableId && change.magnitude.trim())
        ? toInput({ ...draft, name: draft.name.trim() || "Untitled scenario" } as LabDraft)
        : null,
    [draft],
  );
  const preview = usePreview(input);
  const plan = preview.data?.plan ?? followed.execution?.plan ?? null;

  const showExecution =
    followed.results !== null &&
    (requested !== null || (!dirty && followed.execution?.version === scenario?.current_version));
  const results = showExecution ? followed.results : (preview.data?.results ?? null);
  const pathway = showExecution ? followed.pathway : (preview.data?.pathway ?? null);
  /** The plan the shown results were computed from. */
  const resultsPlan = showExecution
    ? (followed.execution?.plan ?? null)
    : (preview.data?.plan ?? null);
  const changeNames = useMemo(
    () => new Map(variables.map((variable) => [variable.id, variable.name])),
    [variables],
  );

  // Replay of the simulated months: a step every REPLAY_STEP_MS, stopping at the end. The
  // replay only moves through values already computed; with reduced motion the steps
  // still advance, but nothing animates between them.
  const horizon = results?.horizon_months ?? 0;
  useEffect(() => {
    if (!playing || horizon === 0) return;
    const timer = window.setInterval(() => {
      setMonth((current) => Math.min((current ?? 0) + 1, horizon));
    }, REPLAY_STEP_MS);
    return () => window.clearInterval(timer);
  }, [playing, horizon]);
  useEffect(() => {
    if (playing && month !== null && month >= horizon) setPlaying(false);
  }, [playing, month, horizon]);

  // Messages for every field: the browser's own "required" checks after an attempt, the
  // API's validation of the last save, the preview's validation and the plan's issues.
  const messages = useMemo(() => {
    const collected: FieldMessages = {};
    if (attempted) {
      for (const [field, message] of Object.entries(missingBasics(draft)))
        addMessage(collected, field, message, "error");
    }
    for (const [field, list] of Object.entries(saveErrors)) {
      for (const item of list) addMessage(collected, field, item.message, item.severity);
    }
    if (preview.status === "invalid") {
      for (const detail of preview.error.details) {
        if (detail.field === "name") continue;
        addMessage(collected, detail.field, detail.message, "error");
      }
    }
    for (const issue of preview.data?.plan.issues ?? []) {
      if (issue.code === "unmodelled_change" || issue.code === "cross_effect") continue;
      // A value not entered yet is a note until the user tries to save or execute.
      const severity = issue.code === "required" && !attempted ? "needed" : issue.severity;
      addMessage(collected, issue.field, issue.message, severity);
    }
    return collected;
  }, [attempted, draft, saveErrors, preview]);

  const blocking = preview.data ? !preview.data.plan.executable : true;
  const executeDisabled =
    input === null
      ? "Add a change first."
      : preview.status === "invalid"
        ? "Fix the fields marked in the controls."
        : blocking && preview.data
          ? "The plan lists what is missing before the scenario can run."
          : null;

  const save = useCallback(async (): Promise<Scenario | null> => {
    setAttempted(true);
    setNotice(null);
    const missing = missingBasics(draft);
    if (Object.keys(missing).length > 0) {
      document.getElementById(fieldId(Object.keys(missing)[0] ?? "name"))?.focus();
      return null;
    }
    setBusy("save");
    try {
      const result = scenario
        ? await api.scenarios.replace(scenario.id, toUpdate(draft, scenario.current_version))
        : await api.scenarios.create(toInput(draft));
      setResourceData(scenarioKey(result.id), result);
      invalidateResource("scenarios");
      setSaveErrors({});
      const message =
        scenario && result.current_version === scenario.current_version
          ? "Nothing changed, so no new version was saved."
          : `Saved as version ${result.current_version} at ${formatDateTime(result.updated_at)}.`;
      if (!scenario) {
        navigate(`/scenarios/${result.id}`, { replace: true, state: { notice: message } });
      } else {
        setNotice(message);
        invalidateResource(scenarioKey(result.id));
      }
      return result;
    } catch (error) {
      const collected: FieldMessages = {};
      if (error instanceof ApiError && error.status === 422) {
        for (const detail of error.details)
          addMessage(collected, detail.field, detail.message, "error");
      } else {
        addMessage(collected, "form", describeError(error), "error");
      }
      setSaveErrors(collected);
      return null;
    } finally {
      setBusy(null);
    }
  }, [draft, scenario, navigate]);

  const execute = async () => {
    const target = dirty || !scenario ? await save() : scenario;
    if (!target) return;
    setBusy("execute");
    try {
      const execution = await labApi.execute(target.id, null);
      invalidateResource(`lab:executions:${target.id}`);
      invalidateResource("scenarios");
      setMonth(null);
      if (scenario) {
        setSearchParams({ execution: execution.id }, { replace: true });
      } else {
        navigate(`/scenarios/${target.id}?execution=${execution.id}`, { replace: true });
      }
    } catch (error) {
      setSaveErrors({ form: [{ message: describeError(error), severity: "error" }] });
    } finally {
      setBusy(null);
    }
  };

  const cancel = async () => {
    if (!executionId) return;
    try {
      await labApi.cancel(executionId);
    } catch (error) {
      setNotice(describeError(error));
    }
  };

  const restore = async (version: number) => {
    if (!scenario) return;
    try {
      const result = await labApi.restore(scenario.id, version);
      setResourceData(scenarioKey(result.id), result);
      invalidateResource(scenarioKey(result.id));
      setNotice(`Version ${version} restored as version ${result.current_version}.`);
    } catch (error) {
      setNotice(describeError(error));
    }
  };

  const duplicate = async () => {
    if (!scenario) return;
    try {
      const copy = await labApi.duplicate(scenario.id, null);
      invalidateResource("scenarios");
      navigate(`/scenarios/${copy.id}`, {
        state: { notice: `Duplicated from “${scenario.name}”.` },
      });
    } catch (error) {
      setNotice(describeError(error));
    }
  };

  const toggleCompare = (id: string) => {
    const next = compareIds.includes(id)
      ? compareIds.filter((item) => item !== id)
      : [...compareIds, id].slice(-6);
    const params = new URLSearchParams(searchParams);
    params.delete("compare");
    for (const item of next) params.append("compare", item);
    setSearchParams(params, { replace: true });
  };

  const formErrors = messages.form ?? [];
  const source = showExecution ? "execution" : "preview";
  const execution = followed.execution;

  const tabs = [
    {
      id: "pathway",
      label: "Pathway",
      content: () =>
        pathway && results ? (
          <PathwayCanvas pathway={pathway} month={month} currency={results.currency} />
        ) : (
          <PathwayPlaceholder previewStatus={preview.status} plan={plan !== null} />
        ),
    },
    {
      id: "plan",
      label: "Plan",
      content: () =>
        plan ? (
          <PlanView plan={plan} />
        ) : (
          <PathwayPlaceholder previewStatus={preview.status} plan={false} />
        ),
    },
    {
      id: "months",
      label: "Months",
      content: () => (results ? <MonthsView results={results} /> : <NoResults />),
    },
    {
      id: "stress",
      label: "Stress",
      content: () =>
        results ? (
          <StressView results={results} changes={resultsPlan?.changes ?? []} />
        ) : (
          <NoResults />
        ),
    },
    {
      id: "sensitivity",
      label: "Sensitivity",
      content: () => <SensitivityView executionId={showExecution ? executionId : null} />,
    },
    {
      id: "explain",
      label: "Explain",
      content: () => (
        <ExplainView
          executionId={showExecution ? executionId : null}
          results={showExecution ? results : null}
        />
      ),
    },
    ...(scenario
      ? [
          {
            id: "history",
            label: "History",
            content: () => (
              <HistoryView
                scenario={scenario}
                executions={executions}
                selectedExecution={executionId}
                compareIds={compareIds}
                onToggleCompare={toggleCompare}
                onOpenExecution={(id) => setSearchParams({ execution: id }, { replace: true })}
                onRestore={(version) => void restore(version)}
              />
            ),
          },
          {
            id: "compare",
            label: `Compare${compareIds.length ? ` (${compareIds.length})` : ""}`,
            content: () => (
              <CompareView
                ids={compareIds}
                onClear={() => {
                  const params = new URLSearchParams(searchParams);
                  params.delete("compare");
                  setSearchParams(params, { replace: true });
                }}
              />
            ),
          },
        ]
      : []),
  ];

  return (
    <div className={styles.workspace}>
      <header className={styles.workspaceHeader}>
        <div className={styles.workspaceTitleBlock}>
          <Link to="/scenarios" className={styles.backLink}>
            <Icon name="arrowLeft" size={14} /> Library
          </Link>
          <h1 className={styles.workspaceTitle}>{draft.name.trim() || "Untitled scenario"}</h1>
          <p className={styles.workspaceMeta}>
            {scenario ? (
              <Badge tone="outline">v{scenario.current_version}</Badge>
            ) : (
              <Badge tone="outline">Not saved</Badge>
            )}
            {dirty && scenario && <Badge tone="warning">Unsaved changes</Badge>}
            {template && !scenario && <Badge tone="neutral">From template: {template.title}</Badge>}
            <EpistemicBadge category="scenario_input" suffix="what you change" />
            <span className={styles.sourceTag} data-source={source}>
              {source === "execution" && execution
                ? `Showing stored execution · v${execution.version} · ${formatDateTime(execution.requested_at)}`
                : preview.updating
                  ? "Live preview · updating…"
                  : "Live preview · computed, not stored"}
            </span>
          </p>
        </div>
        <div className={styles.workspaceActions}>
          <Button
            variant="secondary"
            onClick={() => void save()}
            disabled={busy !== null || (!dirty && scenario !== null)}
          >
            {busy === "save" ? "Saving…" : scenario ? "Save new version" : "Save scenario"}
          </Button>
          {scenario && (
            <Button variant="ghost" onClick={() => void duplicate()}>
              Duplicate
            </Button>
          )}
        </div>
      </header>

      {(notice || formErrors.length > 0) && (
        <div className={styles.noticeBar} role={formErrors.length ? "alert" : "status"}>
          {formErrors.map((item) => (
            <p key={item.message} className={styles.errorText}>
              <Icon name="alert" size={14} /> {item.message}
            </p>
          ))}
          {notice && <p>{notice}</p>}
        </div>
      )}

      <div className={styles.grid}>
        <aside className={styles.controls} aria-label="Scenario controls">
          <Builder
            draft={draft}
            dispatch={dispatch}
            variables={variables}
            plan={plan}
            messages={messages}
          />
        </aside>

        <section className={styles.centre} aria-label="Impact">
          <div
            data-updating={preview.updating && source === "preview" ? "true" : undefined}
            className={styles.centreBody}
          >
            <Tabs items={tabs} active={tab} onChange={setTab} label="Scenario views" />
          </div>
        </section>

        <aside className={styles.side} aria-label="Results">
          {results ? (
            <div data-updating={preview.updating && source === "preview" ? "true" : undefined}>
              <ResultsPanel results={results} changeNames={changeNames} source={source} />
            </div>
          ) : (
            <NoResults
              detail={preview.status === "error" ? describeError(preview.error) : undefined}
            />
          )}
        </aside>

        <div className={styles.bottom}>
          <ExecutionStrip
            execution={
              execution && (showExecution || !dirty || execution.status !== "completed")
                ? execution
                : null
            }
            busy={busy !== null}
            executeLabel={dirty || !scenario ? "Save and execute" : "Execute"}
            disabledReason={executeDisabled}
            onExecute={() => void execute()}
            onCancel={() => void cancel()}
          />
          {results && (
            <TimelineStrip
              timeline={results.timeline}
              lines={results.lines}
              month={month}
              onMonth={(value) => {
                setPlaying(false);
                setMonth(value);
              }}
              playing={playing}
              onTogglePlay={() => {
                if (playing) setPlaying(false);
                else {
                  if (month === null || month >= results.horizon_months) setMonth(1);
                  setPlaying(true);
                }
              }}
            />
          )}
        </div>
      </div>
    </div>
  );
}

function NoResults({ detail }: { detail?: string }) {
  return (
    <EmptyState title="No results yet">
      {detail ??
        "Results appear when the plan can run: a change that a model simulates, and the figures the model needs. Nothing is shown that was not computed."}
    </EmptyState>
  );
}

function PathwayPlaceholder({ previewStatus, plan }: { previewStatus: string; plan: boolean }) {
  if (previewStatus === "idle") {
    return (
      <EmptyState title="Define a change to begin">
        Choose a variable and how it changes. The plan then shows which models apply and why, and
        the pathway appears as soon as the scenario can be computed.
      </EmptyState>
    );
  }
  return (
    <EmptyState title={plan ? "The pathway needs a runnable scenario" : "Planning…"}>
      {plan
        ? "See the Plan for what is still missing. Only pathways the engine computes are drawn."
        : "Asking the backend which models apply."}
    </EmptyState>
  );
}

function CompareOnly() {
  const [searchParams, setSearchParams] = useSearchParams();
  const ids = searchParams.getAll("execution");
  return (
    <div className={styles.page}>
      <PageHeader
        eyebrow="Scenario Lab"
        title="Compare executions"
        description="Stored executions side by side. Differences are shown only between executions with the same currency and horizon; nothing is ranked."
        actions={
          <Link to="/scenarios">
            <Icon name="arrowLeft" size={14} /> Library
          </Link>
        }
      />
      <CompareView ids={ids} onClear={() => setSearchParams({})} />
    </div>
  );
}

function SavedWorkspace({
  scenarioId,
  variables,
}: {
  scenarioId: string;
  variables: EconomicVariable[];
}) {
  const scenario = useApiResource(scenarioKey(scenarioId), () => api.scenarios.get(scenarioId));
  const executions = useApiResource(`lab:executions:${scenarioId}`, () =>
    labApi.executions(scenarioId),
  );
  if (scenario.status === "loading" || executions.status === "loading") {
    return <LoadingState label="Loading the scenario…" lines={6} />;
  }
  if (scenario.status === "error") {
    return scenario.error instanceof ApiError && scenario.error.status === 404 ? (
      <EmptyState
        title="This scenario does not exist"
        action={<Link to="/scenarios">Back to the library</Link>}
      >
        It may have been deleted.
      </EmptyState>
    ) : (
      <ErrorState error={scenario.error} onRetry={scenario.reload} />
    );
  }
  if (executions.status === "error")
    return <ErrorState error={executions.error} onRetry={executions.reload} />;
  return (
    <Workspace
      key={`${scenario.data.id}:${scenario.data.current_version}`}
      variables={variables}
      scenario={scenario.data}
      template={null}
      executions={executions.data.items}
    />
  );
}

function NewWorkspace({ variables }: { variables: EconomicVariable[] }) {
  const [searchParams] = useSearchParams();
  const templateId = searchParams.get("template");
  const template = useApiResource(
    templateId ? `lab:template:${templateId}` : "lab:template:none",
    () => (templateId ? labApi.template(templateId) : Promise.resolve(null)),
  );
  if (template.status === "loading")
    return <LoadingState label="Loading the template…" lines={6} />;
  if (template.status === "error")
    return <ErrorState error={template.error} onRetry={template.reload} />;
  return (
    <Workspace
      key={templateId ?? "blank"}
      variables={variables}
      scenario={null}
      template={template.data}
      executions={[]}
    />
  );
}

export function ScenarioLabPage() {
  const { scenarioId = null } = useParams();
  const location = useLocation();
  const variables = useApiResource("variables", () => api.variables());
  const isNew = location.pathname.endsWith("/new");
  const isCompare = location.pathname.endsWith("/compare");

  useEffect(() => {
    document.title = "Scenario Lab — RUMIN";
  }, []);

  if (isCompare) return <CompareOnly />;

  if (!scenarioId && !isNew) {
    return (
      <div className={styles.page}>
        <PageHeader
          eyebrow="Scenario Lab"
          title="What happens if something changes?"
          description="Build a scenario from implemented models, see which apply and why, execute it and follow the modelled pathway from each change to each line — baseline against scenario, month by month, with stress cases, sensitivity and the equations behind every figure."
          meta={
            <>
              <EpistemicBadge category="scenario_input" suffix="what you change" />
              <EpistemicBadge category="simulated_output" suffix="what the models compute" />
              <Badge tone="outline">Deterministic · not forecasts</Badge>
            </>
          }
        />
        <LabHome />
      </div>
    );
  }

  return (
    <div className={styles.labPage}>
      {variables.status === "loading" && (
        <LoadingState label="Loading the Scenario Lab…" lines={6} />
      )}
      {variables.status === "error" && (
        <ErrorState error={variables.error} onRetry={variables.reload} />
      )}
      {variables.status === "success" &&
        (scenarioId ? (
          <SavedWorkspace scenarioId={scenarioId} variables={variables.data.items} />
        ) : (
          <NewWorkspace variables={variables.data.items} />
        ))}
    </div>
  );
}
