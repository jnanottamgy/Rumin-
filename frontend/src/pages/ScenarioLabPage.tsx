import { useEffect, useMemo, useReducer, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { EpistemicBadge } from "@/components/EpistemicBadge";
import { Icon } from "@/components/Icon";
import { PageHeader } from "@/components/PageHeader";
import { EmptyState, ErrorState, LoadingState } from "@/components/States";
import { useNetworkGraph } from "@/features/network/useNetworkGraph";
import { ScenarioContext } from "@/features/scenarios/ScenarioContext";
import { fieldId, ScenarioEditor } from "@/features/scenarios/ScenarioEditor";
import {
  draftFromScenario,
  editorReducer,
  emptyDraft,
  errorsFromApi,
  exampleDraft,
  initialEditorState,
  isDirty,
  toPayload,
  validateDraft,
} from "@/features/scenarios/scenarioModel";
import { invalidateResource, setResourceData, useApiResource } from "@/hooks/useApiResource";
import { ApiError, describeError } from "@/lib/apiClient";
import { cx } from "@/lib/cx";
import { formatDateTime, plural } from "@/lib/format";
import { api } from "@/services/api";
import type { EconomicVariable, Scenario } from "@/types/api";
import styles from "./ScenarioLabPage.module.css";

const SCENARIOS = "scenarios";
const scenarioKey = (id: string) => `scenario:${id}`;

function ScenarioList({ activeId }: { activeId: string | null }) {
  const scenarios = useApiResource(SCENARIOS, () => api.scenarios.list());
  return (
    <nav className={styles.list} aria-label="Saved scenarios">
      <div className={styles.listHeader}>
        <h2>Drafts</h2>
        <Link to="/scenarios" className={styles.newLink}>
          <Icon name="plus" size={14} /> New
        </Link>
      </div>
      {scenarios.status === "loading" && <LoadingState lines={3} />}
      {scenarios.status === "error" && (
        <ErrorState error={scenarios.error} onRetry={scenarios.reload} />
      )}
      {scenarios.status === "success" &&
        (scenarios.data.items.length === 0 ? (
          <p className={styles.listEmpty}>No saved scenarios yet.</p>
        ) : (
          <ul>
            {scenarios.data.items.map((scenario) => (
              <li key={scenario.id}>
                <Link
                  to={`/scenarios/${scenario.id}`}
                  className={cx(styles.listItem, scenario.id === activeId && styles.listItemActive)}
                  aria-current={scenario.id === activeId ? "page" : undefined}
                >
                  <span className={styles.listName}>{scenario.name}</span>
                  <span className={styles.listMeta}>
                    {plural(scenario.shocks.length, "input")} · Draft · not simulated
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        ))}
    </nav>
  );
}

function Workspace({
  variables,
  scenario,
}: {
  variables: EconomicVariable[];
  scenario: Scenario | null;
}) {
  const navigate = useNavigate();
  const location = useLocation();
  const network = useNetworkGraph();
  const [state, dispatch] = useReducer(editorReducer, scenario, (initial) =>
    initialEditorState(initial ? draftFromScenario(initial) : emptyDraft()),
  );
  const [saving, setSaving] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  // A confirmation carried across the redirect that follows the first save.
  const [status, setStatus] = useState<string | null>(
    (location.state as { status?: string } | null)?.status ?? null,
  );
  const variablesById = useMemo(
    () => new Map(variables.map((variable) => [variable.id, variable])),
    [variables],
  );
  const dirty = isDirty(state);
  const errorEntries = Object.entries(state.errors);
  const selectedVariables = [
    ...new Set(state.draft.shocks.map((shock) => shock.variableId).filter(Boolean)),
  ];

  const focusField = (key: string) => document.getElementById(fieldId(key))?.focus();

  const save = async () => {
    setStatus(null);
    const errors = validateDraft(state.draft, variablesById);
    if (Object.keys(errors).length > 0) {
      dispatch({ type: "setErrors", errors });
      return;
    }
    setSaving(true);
    try {
      const payload = toPayload(state.draft);
      const saved = state.draft.id
        ? await api.scenarios.replace(state.draft.id, payload)
        : await api.scenarios.create(payload);
      setResourceData(scenarioKey(saved.id), saved);
      invalidateResource(SCENARIOS);
      dispatch({ type: "saved", draft: draftFromScenario(saved) });
      const message = `Saved at ${formatDateTime(saved.updated_at)}. Nothing was simulated.`;
      setStatus(message);
      if (!state.draft.id) {
        navigate(`/scenarios/${saved.id}`, { replace: true, state: { status: message } });
      }
    } catch (error) {
      if (error instanceof ApiError && error.status === 422) {
        dispatch({ type: "setErrors", errors: errorsFromApi(error, state.draft) });
      } else {
        dispatch({ type: "setErrors", errors: { form: describeError(error) } });
      }
    } finally {
      setSaving(false);
    }
  };

  const remove = async () => {
    if (!state.draft.id) return;
    setSaving(true);
    try {
      await api.scenarios.remove(state.draft.id);
      invalidateResource(SCENARIOS);
      navigate("/scenarios", { replace: true });
    } catch (error) {
      dispatch({ type: "setErrors", errors: { form: describeError(error) } });
      setSaving(false);
    }
  };

  return (
    <div className={styles.workspace}>
      <section className={styles.editorPanel} aria-labelledby="scenario-editor-title">
        <header className={styles.editorHeader}>
          <div>
            <h2 id="scenario-editor-title" className={styles.editorTitle}>
              {state.draft.id ? "Edit scenario" : "New scenario"}
            </h2>
            <p className={styles.statusLine}>
              <Badge tone="outline">Draft</Badge>
              <Badge tone="neutral">Not simulated yet</Badge>
              {dirty && <Badge tone="warning">Unsaved changes</Badge>}
            </p>
          </div>
          {!state.draft.id && (
            <Button
              size="sm"
              variant="ghost"
              onClick={() => {
                setStatus(null);
                dispatch({ type: "load", draft: exampleDraft() });
              }}
            >
              Load the oil-shock example
            </Button>
          )}
        </header>

        {errorEntries.length > 0 && (
          <div className={styles.errorSummary} role="alert" tabIndex={-1}>
            <p className={styles.errorSummaryTitle}>
              <Icon name="alert" /> Check{" "}
              {errorEntries.length === 1 ? "this field" : "these fields"}
            </p>
            <ul>
              {errorEntries.map(([key, message]) => (
                <li key={key}>
                  {key === "form" ? (
                    message
                  ) : (
                    <button type="button" onClick={() => focusField(key)}>
                      {message}
                    </button>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}

        <form
          noValidate
          onSubmit={(event) => {
            event.preventDefault();
            void save();
          }}
        >
          <ScenarioEditor state={state} dispatch={dispatch} variables={variables} />
          <div className={styles.actions}>
            <Button type="submit" variant="primary" disabled={saving}>
              {saving ? "Saving…" : "Save draft"}
            </Button>
            {state.draft.id &&
              (confirmDelete ? (
                <>
                  <Button variant="danger" onClick={() => void remove()} disabled={saving}>
                    Delete permanently
                  </Button>
                  <Button variant="ghost" onClick={() => setConfirmDelete(false)}>
                    Keep it
                  </Button>
                </>
              ) : (
                <Button variant="ghost" onClick={() => setConfirmDelete(true)}>
                  Delete…
                </Button>
              ))}
            <p className={styles.saveNote} role="status" aria-live="polite">
              {status ?? "Saving stores the inputs only. It does not run a simulation."}
            </p>
          </div>
        </form>
      </section>

      <aside className={styles.context} aria-label="Scenario context">
        <ScenarioContext model={network.graph?.model ?? null} variableIds={selectedVariables} />
      </aside>
    </div>
  );
}

export function ScenarioLabPage() {
  const { scenarioId = null } = useParams();
  const variables = useApiResource("variables", () => api.variables());
  const scenario = useApiResource(scenarioId ? scenarioKey(scenarioId) : "scenario:new", () =>
    scenarioId ? api.scenarios.get(scenarioId) : Promise.resolve(null),
  );

  const ready = variables.status === "success" && scenario.status === "success";

  // Reset the editor whenever the route switches between scenarios.
  const workspaceKey = ready ? (scenario.data?.id ?? "new") : "loading";

  useEffect(() => {
    document.title = "Scenario Lab — RUMIN";
  }, []);

  return (
    <div className={styles.page}>
      <PageHeader
        eyebrow="Scenario Lab · Foundation"
        title="Define a scenario"
        description="Choose economic variables and how they change. RUMIN stores these inputs as a draft; simulating their effects arrives with the Phase 4 engine."
        meta={
          <>
            <EpistemicBadge category="scenario_input" suffix="what you change" />
            <Badge tone="outline">No simulation engine in this build</Badge>
          </>
        }
      />
      <div className={styles.layout}>
        <ScenarioList activeId={scenarioId} />
        <div className={styles.main}>
          {(variables.status === "loading" || scenario.status === "loading") && (
            <LoadingState label="Loading the scenario workspace…" lines={6} />
          )}
          {variables.status === "error" && (
            <ErrorState error={variables.error} onRetry={variables.reload} />
          )}
          {scenario.status === "error" &&
            (scenario.error instanceof ApiError && scenario.error.status === 404 ? (
              <EmptyState
                title="This scenario does not exist"
                action={<Link to="/scenarios">Start a new scenario</Link>}
              >
                It may have been deleted.
              </EmptyState>
            ) : (
              <ErrorState error={scenario.error} onRetry={scenario.reload} />
            ))}
          {ready &&
            (variables.data.items.length === 0 ? (
              <EmptyState title="No economic variables are loaded">
                Load the sample dataset (<span className="mono">python -m app.db.seed</span>) to
                define scenarios.
              </EmptyState>
            ) : (
              <Workspace
                key={workspaceKey}
                variables={variables.data.items}
                scenario={scenario.data}
              />
            ))}
        </div>
      </div>
    </div>
  );
}
