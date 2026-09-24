import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router";
import { APP_MODULES, STATUS_LABEL } from "@/app/modules";
import { Badge } from "@/components/Badge";
import { ButtonLink } from "@/components/Button";
import { Icon } from "@/components/Icon";
import { PageHeader } from "@/components/PageHeader";
import { Panel } from "@/components/Panel";
import { EmptyState, ErrorState, LoadingState } from "@/components/States";
import { StatGrid, StatTile } from "@/components/StatTile";
import { StatusIndicator } from "@/components/StatusIndicator";
import { JOB_STATUS } from "@/features/data/labels";
import { KIND_ENCODING } from "@/features/network/encoding";
import { KindGlyph } from "@/features/network/KindGlyph";
import { defaultFilters, KIND_ORDER, visibleSubgraph } from "@/features/network/model";
import { NetworkCanvas } from "@/features/network/NetworkCanvas";
import { NetworkLegend } from "@/features/network/NetworkLegend";
import { useNetworkGraph } from "@/features/network/useNetworkGraph";
import { STATUS_LABEL as EXECUTION_STATUS } from "@/features/scenarioLab/format";
import { useApiResource } from "@/hooks/useApiResource";
import { useMediaQuery } from "@/hooks/useMediaQuery";
import { formatCount, formatDate, plural } from "@/lib/format";
import { api } from "@/services/api";
import type { ScenarioExecutionSummary, SystemStatus } from "@/types/api";
import styles from "./DashboardPage.module.css";

const UNAVAILABLE = "—";

function NetworkPreview() {
  const network = useNetworkGraph();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const portrait = useMediaQuery("(max-width: 40rem)");
  // Stable identity, so the canvas's memoised layer only re-renders when it must.
  const visible = useMemo(
    () =>
      network.graph
        ? visibleSubgraph(network.graph.model, defaultFilters(network.graph.model))
        : null,
    [network.graph],
  );

  if (network.status === "loading") return <LoadingState label="Loading the network…" />;
  if (network.status === "error") {
    return <ErrorState error={network.error} onRetry={network.reload} />;
  }
  const graph = network.graph;
  if (!graph || !visible || graph.model.nodes.length === 0) {
    return <EmptyState title="No dataset is loaded" />;
  }
  const selected = selectedId ? graph.model.nodeById.get(selectedId) : undefined;

  return (
    <div className={styles.preview}>
      <div className={styles.previewCanvas}>
        <NetworkCanvas
          model={graph.model}
          layout={portrait ? graph.portraitLayout : graph.layout}
          visible={visible}
          selectedId={selectedId}
          onSelect={setSelectedId}
          mode="preview"
          labels={portrait ? "selected" : "structure"}
          ariaLabel={`Preview of the financial network: ${graph.model.nodes.length} entities. Select an entity to see its connections.`}
        />
      </div>
      <NetworkLegend compact />
      <p className={styles.previewStatus} aria-live="polite">
        {selected ? (
          <>
            <KindGlyph kind={selected.kind} /> <strong>{selected.label}</strong> ·{" "}
            {plural(selected.degree, "connection")} ·{" "}
            <Link to={`/universe?focus=${selected.id}`}>Open in the Universe</Link>
          </>
        ) : (
          "Select an entity to highlight its direct connections."
        )}
      </p>
    </div>
  );
}

function RecentScenarios() {
  const scenarios = useApiResource("scenarios", () => api.scenarios.list());
  if (scenarios.status === "loading") return <LoadingState lines={2} />;
  if (scenarios.status === "error") {
    return <ErrorState error={scenarios.error} onRetry={scenarios.reload} />;
  }
  const items = scenarios.data.items.slice(0, 4);
  if (items.length === 0) {
    return (
      <EmptyState
        title="No scenarios yet"
        action={
          <ButtonLink to="/scenarios" size="sm" icon={<Icon name="plus" size={14} />}>
            Define a scenario
          </ButtonLink>
        }
      >
        Build one in the Scenario Lab from a template or from scratch.
      </EmptyState>
    );
  }
  return (
    <ul className={styles.scenarios}>
      {items.map((scenario) => (
        <li key={scenario.id}>
          <Link to={`/scenarios/${scenario.id}`} className={styles.scenario}>
            <span className={styles.scenarioName}>{scenario.name}</span>
            <span className={styles.scenarioMeta}>
              {plural(scenario.shocks.length, "change")} · v{scenario.current_version} ·{" "}
              {scenario.latest_execution
                ? `executed ${formatDate(scenario.latest_execution.requested_at)}`
                : `updated ${formatDate(scenario.updated_at)}`}
            </span>
            <ExecutionBadge execution={scenario.latest_execution} />
          </Link>
        </li>
      ))}
    </ul>
  );
}

/** The latest execution's state, in words (a scenario that was never executed says so). */
function ExecutionBadge({ execution }: { execution: ScenarioExecutionSummary | null }) {
  if (!execution) return <Badge tone="neutral">Not executed</Badge>;
  if (execution.status === "completed") return <Badge tone="outline">Executed</Badge>;
  if (execution.status === "failed") return <Badge tone="critical">Execution failed</Badge>;
  return <Badge tone="neutral">{EXECUTION_STATUS[execution.status] ?? execution.status}</Badge>;
}

function SystemSummary({ system }: { system: ReturnType<typeof useSystem> }) {
  if (system.status === "loading") return <LoadingState lines={4} />;
  if (system.status === "error") {
    return (
      <ul className={styles.statusList}>
        <li>
          <StatusIndicator tone="critical" label="API" detail="Unreachable" />
        </li>
        <li className={styles.statusHint}>
          The RUMIN API is not responding. Start the backend and{" "}
          <button type="button" className={styles.linkButton} onClick={system.reload}>
            try again
          </button>
          .
        </li>
      </ul>
    );
  }
  const { database, dataset, data, capabilities, environment } = system.data;
  const missing = capabilities.filter((capability) => !capability.available);
  return (
    <ul className={styles.statusList}>
      <li>
        <StatusIndicator tone="good" label="API" detail={`Responding · ${environment}`} />
      </li>
      <li>
        <StatusIndicator
          tone={database.schema_up_to_date ? "good" : "warning"}
          label="Database"
          detail={`${database.backend} · migration ${database.migration_revision ?? "none"}${
            database.schema_up_to_date ? " (current)" : " (not current)"
          }`}
        />
      </li>
      <li>
        <StatusIndicator
          tone={dataset.loaded ? "good" : "warning"}
          label="Dataset"
          detail={
            dataset.summary
              ? `${dataset.summary.is_illustrative ? "Illustrative sample" : dataset.summary.name} loaded`
              : "Not loaded"
          }
        />
      </li>
      <li>
        <StatusIndicator
          tone={data.series_with_data > 0 ? "good" : "warning"}
          label="Provider data"
          detail={`${data.series_with_data} of ${data.series_total} series with values${
            data.last_job
              ? ` · last run ${JOB_STATUS[data.last_job.status].label.toLowerCase()}`
              : ""
          }`}
        />
      </li>
      {missing.map((capability) => (
        <li key={capability.id}>
          <StatusIndicator
            tone="planned"
            label={capability.label}
            detail={
              capability.planned_phase
                ? `Not available · Phase ${capability.planned_phase}`
                : "Not connected"
            }
          />
        </li>
      ))}
    </ul>
  );
}

function useSystem() {
  return useApiResource<SystemStatus>("system", () => api.system());
}

export function DashboardPage() {
  const system = useSystem();
  const network = useNetworkGraph();
  const scenarios = useApiResource("scenarios", () => api.scenarios.list());

  useEffect(() => {
    document.title = "Overview — RUMIN";
  }, []);

  const model = network.graph?.model;
  const counts = system.data?.dataset.entity_counts ?? {};
  const dataset = system.data?.dataset.summary ?? null;
  const economicLinks = model?.edges.filter((edge) => edge.category === "economic").length ?? 0;
  const structuralLinks = (model?.edges.length ?? 0) - economicLinks;

  return (
    <div className={styles.page}>
      <PageHeader
        eyebrow="Workspace · Local"
        title="Overview"
        description="The state of this workspace, read from the running API: what is loaded, what the network contains, and what this build can and cannot do yet."
        actions={
          <ButtonLink to="/universe" variant="primary" iconAfter={<Icon name="arrowRight" />}>
            Explore the Universe
          </ButtonLink>
        }
      />

      <StatGrid label="Workspace at a glance">
        <StatTile
          label="Entities"
          value={model ? formatCount(model.nodes.length) : UNAVAILABLE}
          detail={
            model
              ? KIND_ORDER.map(
                  (kind) => `${counts[kind] ?? 0} ${KIND_ENCODING[kind].plural.toLowerCase()}`,
                ).join(" · ")
              : "Waiting for the API"
          }
          source="Loaded sample dataset"
        />
        <StatTile
          label="Relationships"
          value={model ? formatCount(economicLinks) : UNAVAILABLE}
          detail={model ? `+ ${structuralLinks} structural links derived from records` : ""}
          source="All illustrative assumptions"
        />
        <StatTile
          label="Scenarios"
          value={scenarios.status === "success" ? formatCount(scenarios.data.total) : UNAVAILABLE}
          detail="Versioned; executed through the model registry in the Scenario Lab"
          source="Scenario Lab"
        />
        <StatTile
          label="Dataset"
          value={dataset ? `v${dataset.version}` : UNAVAILABLE}
          detail={
            dataset
              ? `${dataset.is_illustrative ? "Illustrative sample" : dataset.name} · loaded ${formatDate(dataset.loaded_at)}`
              : system.status === "error"
                ? "API unreachable"
                : "Not loaded"
          }
          source={dataset ? `SHA-256 ${dataset.checksum_sha256.slice(0, 12)}…` : undefined}
        />
      </StatGrid>

      <div className={styles.grid}>
        <Panel
          className={styles.networkPanel}
          eyebrow="Financial network"
          title="The sample economy at a glance"
          actions={
            <ButtonLink to="/universe" size="sm">
              Open Universe
            </ButtonLink>
          }
          flush
        >
          <NetworkPreview />
        </Panel>

        <div className={styles.side}>
          <Panel
            eyebrow="Scenario Lab"
            title="Recent scenarios"
            actions={
              <ButtonLink to="/scenarios" size="sm" icon={<Icon name="plus" size={14} />}>
                New
              </ButtonLink>
            }
          >
            <RecentScenarios />
          </Panel>
          <Panel eyebrow="System" title="Status" actions={<Link to="/system">Details</Link>}>
            <SystemSummary system={system} />
          </Panel>
        </div>
      </div>

      <Panel eyebrow="Modules" title="What this build contains">
        <ul className={styles.modules}>
          {APP_MODULES.filter((module) => module.id !== "overview").map((module) => (
            <li key={module.id}>
              <Link to={module.path} className={styles.module}>
                <span className={styles.moduleHead}>
                  <span className={styles.moduleTitle}>{module.title}</span>
                  <Badge
                    tone={
                      module.status === "available"
                        ? "accent"
                        : module.status === "foundation"
                          ? "outline"
                          : "neutral"
                    }
                  >
                    {STATUS_LABEL[module.status]}
                  </Badge>
                </span>
                <span className={styles.moduleSummary}>{module.summary}</span>
                <span className={styles.moduleNote}>{module.statusNote}</span>
              </Link>
            </li>
          ))}
        </ul>
      </Panel>
    </div>
  );
}
