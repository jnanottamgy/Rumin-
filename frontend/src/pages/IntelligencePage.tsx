/**
 * Financial Intelligence: what RUMIN's data, knowledge graph and stored simulations say —
 * and what each statement rests on.
 *
 * Three views share one layout (subjects on the left, the analysis on the right):
 * - the **workspace** (`/intelligence`): every finding, the exposure matrix, observed
 *   series, simulated impacts, relationship changes, coverage and stored analyses;
 * - an **entity** (`/intelligence/:entityKey`): its findings, exposure paths, drivers,
 *   signals, history, sources and the brief a future AI Analyst would receive;
 * - a **stored analysis** (`/intelligence/analyses/:analysisId`): a snapshot exactly as it
 *   was stored, and whether what it read has changed since.
 *
 * Every finding opens into its evidence chain. Thresholds live in the URL.
 */
import { type ReactNode, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { Icon } from "@/components/Icon";
import { PageHeader } from "@/components/PageHeader";
import { ErrorState, LoadingState } from "@/components/States";
import {
  SubjectPicker,
  SubjectRail,
  THRESHOLD_NAMES,
  ThresholdsPanel,
  thresholdKey,
  thresholdProblems,
  thresholdsFrom,
} from "@/features/intelligence/Controls";
import { DriversView } from "@/features/intelligence/Drivers";
import { ExposureMatrixTable, ExposurePaths, Relations } from "@/features/intelligence/Exposure";
import { change, entityPath, money, NATURE, percent, stored } from "@/features/intelligence/format";
import { HistoryView } from "@/features/intelligence/History";
import styles from "@/features/intelligence/Intelligence.module.css";
import { Ledger } from "@/features/intelligence/Ledger";
import { BriefView, SourcesView } from "@/features/intelligence/Records";
import { SignalGrid } from "@/features/intelligence/Signals";
import { Tabs } from "@/features/simulation/Tabs";
import { invalidateResource, type Resource, useApiResource } from "@/hooks/useApiResource";
import { describeError } from "@/lib/apiClient";
import { cx } from "@/lib/cx";
import { formatCount, formatDateTime, formatPeriod, plural } from "@/lib/format";
import { type EvidenceFilter, intelligenceApi, type ThresholdOverrides } from "@/services/api";
import type {
  EntityAnalysis,
  IntelligenceBuild,
  IntelligenceDrivers,
  IntelligenceMethods,
  IntelligenceOverview,
  StoredAnalysis,
} from "@/types/api";

const ANALYSES_KEY = "intelligence:analyses";

/** Cached data is shown at once and then refreshed: intelligence follows the store. */
function useFreshResource<T>(key: string, load: () => Promise<T>): Resource<T> {
  const resource = useApiResource(key, load);
  const cached = useRef(resource.status === "success");
  const { reload } = resource;
  useEffect(() => {
    if (cached.current) reload();
  }, [reload]);
  return resource;
}

function BuildBadge({ build }: { build: IntelligenceBuild }) {
  if (build.freshness === "current") {
    return (
      <Badge tone="outline" title={build.message ?? undefined}>
        Graph build #{build.id}, up to date
      </Badge>
    );
  }
  if (build.freshness === "stale") {
    return (
      <Badge tone="warning" title={build.message ?? undefined}>
        Graph build #{build.id} is older than its sources
      </Badge>
    );
  }
  return <Badge tone="warning">No knowledge graph built</Badge>;
}

function StoreButton({
  request,
  onStored,
}: {
  request: { scope: "entity" | "workspace"; entity?: string; thresholds: ThresholdOverrides };
  onStored: (analysis: StoredAnalysis) => void;
}) {
  const [state, setState] = useState<"idle" | "saving" | "error">("idle");
  const [error, setError] = useState<unknown>(null);
  return (
    <span className={styles.storeAction}>
      <Button
        size="sm"
        disabled={state === "saving"}
        onClick={async () => {
          setState("saving");
          try {
            const analysis = await intelligenceApi.analyses.create({
              scope: request.scope,
              entity: request.entity ?? null,
              thresholds: Object.keys(request.thresholds).length ? { ...request.thresholds } : null,
              evidence: "any",
              label: null,
            });
            invalidateResource(ANALYSES_KEY);
            setState("idle");
            onStored(analysis);
          } catch (caught) {
            setError(caught);
            setState("error");
          }
        }}
      >
        {state === "saving" ? "Storing…" : "Store this analysis"}
      </Button>
      {state === "error" && (
        <span role="alert" className={styles.fieldError}>
          {describeError(error)}
        </span>
      )}
    </span>
  );
}

function StoredNotice({ analysis, onClose }: { analysis: StoredAnalysis; onClose: () => void }) {
  return (
    <p className={styles.storedNotice} role="status">
      <Icon name="check" size={14} />
      <span>
        Stored with its thresholds and a fingerprint of what it read.{" "}
        <Link to={`/intelligence/analyses/${analysis.id}`}>Open the stored analysis</Link>
      </span>
      <Button size="sm" variant="ghost" onClick={onClose} aria-label="Dismiss">
        <Icon name="close" size={12} />
      </Button>
    </p>
  );
}

// --- The workspace -----------------------------------------------------------------------------

function CoverageLine({ overview }: { overview: IntelligenceOverview }) {
  const coverage = overview.coverage;
  const companies = coverage.truncated
    ? `${coverage.companies_with_exposure} of the first ${coverage.companies_listed} (${formatCount(coverage.companies)} in the graph)`
    : `${coverage.companies_with_exposure} of ${coverage.companies}`;
  const items: [string, string][] = [
    ["Companies with a stated exposure", companies],
    ["Exposure paths", formatCount(coverage.exposure_paths)],
    ["Series with stored values", `${coverage.series_with_data} of ${coverage.series}`],
    ["Stored values", formatCount(coverage.observations)],
    ["Completed executions", formatCount(coverage.executions)],
  ];
  return (
    <dl className={styles.coverage}>
      {items.map(([label, value]) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd className="tabular">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function ObservedTable({ overview }: { overview: IntelligenceOverview }) {
  const rows = [...overview.series, ...overview.instruments];
  if (rows.length === 0) {
    return (
      <p className={styles.emptyLine}>
        No series or instrument has two or more stored values, so nothing observed can be compared
        yet. Retrieve series from the command line (see the Data Explorer).
      </p>
    );
  }
  return (
    <div className={styles.tableFrame}>
      <table className={styles.table}>
        <thead>
          <tr>
            <th scope="col">Series</th>
            <th scope="col">Latest value</th>
            <th scope="col">Latest change</th>
            <th scope="col">Trend</th>
            <th scope="col">Volatility</th>
            <th scope="col">Against earlier changes</th>
            <th scope="col">Revisions</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={`${row.subject.kind}:${row.subject.id}:${row.subject.dataset.id}`}>
              <th scope="row">
                <Link
                  to={
                    row.subject.kind === "series"
                      ? `/data/series/${encodeURIComponent(row.subject.id)}`
                      : `/data/instruments/${encodeURIComponent(row.subject.id)}`
                  }
                >
                  {row.subject.name}
                </Link>
                {row.subject.dataset.is_illustrative && (
                  <span className={styles.muted}> sample data</span>
                )}
              </th>
              <td className="tabular">
                {stored(row.latest_value)} {row.subject.unit}
                {row.last && <span className={styles.muted}>, {formatPeriod(row.last)}</span>}
              </td>
              <td className={cx("tabular", row.latest_detected && styles.cellEmphasis)}>
                {row.latest ? change(row.latest.value, row.subject.change_unit) : "—"}
                {row.latest_detected && (
                  <span className="visually-hidden"> (meets the threshold)</span>
                )}
              </td>
              <td>{row.trend?.replaceAll("_", " ") ?? "—"}</td>
              <td>{row.volatility?.replaceAll("_", " ") ?? "—"}</td>
              <td>{row.anomaly?.replaceAll("_", " ") ?? "—"}</td>
              <td className="tabular">{row.revisions}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ImpactsTable({ overview }: { overview: IntelligenceOverview }) {
  if (overview.impacts.length === 0) {
    return (
      <p className={styles.emptyLine}>
        No completed execution is stored. Run a scenario in the{" "}
        <Link to="/scenarios">Scenario Lab</Link> to size an exposure with your own figures.
      </p>
    );
  }
  return (
    <table className={styles.table}>
      <thead>
        <tr>
          <th scope="col">Company</th>
          <th scope="col">Scenario</th>
          <th scope="col">Line</th>
          <th scope="col">Simulated change</th>
        </tr>
      </thead>
      <tbody>
        {overview.impacts.map((impact) => {
          const company = overview.exposure.companies.find(
            (item) => item.key === impact.entity_key,
          );
          return (
            <tr key={impact.execution.id}>
              <th scope="row">
                {company ? (
                  <Link to={entityPath(company.key)}>{company.name}</Link>
                ) : (
                  impact.execution.scenario_name
                )}
              </th>
              <td>
                <Link
                  to={`/scenarios/${encodeURIComponent(impact.execution.scenario_id)}?execution=${encodeURIComponent(impact.execution.id)}`}
                >
                  {impact.execution.scenario_name}, version {impact.execution.version}
                </Link>
              </td>
              <td>{impact.label}</td>
              <td className="tabular">
                {money(impact.change, impact.currency, true)} ({percent(impact.percent_change)})
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function RelationshipChangesList({ overview }: { overview: IntelligenceOverview }) {
  const changes = overview.relationships;
  if (!changes.previous) {
    return <p className={styles.emptyLine}>{changes.note}</p>;
  }
  if (changes.edges.length === 0) {
    return (
      <p className={styles.emptyLine}>
        Build #{changes.build?.id} changed no relationship compared with build #
        {changes.previous.id}.
      </p>
    );
  }
  return (
    <ul className={styles.plainList}>
      {changes.edges.map((edge) => (
        <li key={`${edge.change}:${edge.edge_key}`}>
          <span className={styles.muted}>{edge.change}</span> {edge.source_name} {edge.label}{" "}
          {edge.target_name}
        </li>
      ))}
    </ul>
  );
}

function StoredAnalyses() {
  const analyses = useFreshResource(ANALYSES_KEY, () => intelligenceApi.analyses.list());
  if (analyses.status === "loading") return <LoadingState lines={2} />;
  if (analyses.status === "error")
    return <ErrorState error={analyses.error} onRetry={analyses.reload} />;
  if (analyses.data.items.length === 0) {
    return (
      <p className={styles.emptyLine}>
        None yet. Storing an analysis keeps a snapshot with its thresholds and a fingerprint of what
        it read, so it can be compared with the store later.
      </p>
    );
  }
  return (
    <table className={styles.table}>
      <thead>
        <tr>
          <th scope="col">Subject</th>
          <th scope="col">Stored</th>
          <th scope="col">Findings</th>
        </tr>
      </thead>
      <tbody>
        {analyses.data.items.map((item) => (
          <tr key={item.id}>
            <th scope="row">
              <Link to={`/intelligence/analyses/${item.id}`}>
                {item.subject_name}
                {item.label ? `: ${item.label}` : ""}
              </Link>
            </th>
            <td>{formatDateTime(item.created_at)}</td>
            <td className="tabular">{item.insight_count}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function MethodNote({ methods }: { methods: IntelligenceMethods | undefined }) {
  if (!methods) return null;
  return (
    <details className={styles.fold}>
      <summary>How findings are made</summary>
      <ul className={styles.plainList}>
        {methods.notes.map((note) => (
          <li key={note}>{note}</li>
        ))}
      </ul>
      <dl className={styles.method}>
        {methods.modules.map((module) => (
          <div key={module.id}>
            <dt>{module.title}</dt>
            <dd>
              {module.question} {module.method}
            </dd>
          </div>
        ))}
      </dl>
      <table className={styles.table}>
        <caption>
          Evidence grades, strongest first: a finding takes the grade of its weakest link
        </caption>
        <tbody>
          {methods.grades.map((grade) => (
            <tr key={grade.id}>
              <th scope="row">{grade.id}</th>
              <td>{grade.statement}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </details>
  );
}

function Section({
  id,
  title,
  description,
  children,
}: {
  id: string;
  title: string;
  description?: string;
  children: ReactNode;
}) {
  return (
    <section className={styles.section} aria-labelledby={id}>
      <header className={styles.sectionHead}>
        <h2 id={id} className={styles.sectionTitle}>
          {title}
        </h2>
        {description && <p className={styles.sectionLede}>{description}</p>}
      </header>
      {children}
    </section>
  );
}

function WorkspaceView({
  thresholds,
  methods,
  onThresholds,
}: {
  thresholds: ThresholdOverrides;
  methods: IntelligenceMethods | undefined;
  onThresholds: (next: ThresholdOverrides) => void;
}) {
  const key = `intelligence:overview:${thresholdKey(thresholds)}`;
  const overview = useFreshResource(key, () => intelligenceApi.overview(thresholds));
  const [stored, setStored] = useState<StoredAnalysis | null>(null);
  const scenarios = useMemo(
    () =>
      new Map(
        (overview.data?.impacts ?? []).map((item) => [
          item.execution.id,
          item.execution.scenario_id,
        ]),
      ),
    [overview.data],
  );
  const problems = overview.status === "error" ? thresholdProblems(overview.error) : {};

  return (
    <>
      <PageHeader
        compact
        title="Financial intelligence"
        description="What the stored data, the knowledge graph and the stored simulations say, each finding with the evidence it rests on. Nothing here is a forecast or a recommendation."
        meta={overview.data && <BuildBadge build={overview.data.build} />}
        actions={
          overview.data && (
            <StoreButton request={{ scope: "workspace", thresholds }} onStored={setStored} />
          )
        }
      />
      {stored && <StoredNotice analysis={stored} onClose={() => setStored(null)} />}
      {methods && (
        <ThresholdsPanel
          specs={methods.thresholds}
          current={thresholds}
          problems={problems}
          onApply={onThresholds}
        />
      )}
      {overview.status === "loading" && <LoadingState label="Analysing the workspace…" lines={6} />}
      {overview.status === "error" && (
        <ErrorState error={overview.error} onRetry={overview.reload} />
      )}
      {overview.data && (
        <div className={cx(styles.main, overview.isRefreshing && styles.refreshing)}>
          <CoverageLine overview={overview.data} />
          <Section
            id="findings"
            title="Findings"
            description="New observations first, then simulations, relationships and coverage. Open a finding to see what it rests on."
          >
            <Ledger insights={overview.data.insights} scenarios={scenarios} />
          </Section>
          <Section
            id="exposure"
            title="Exposure map"
            description="Which variables reach which companies through validated relationships: who is exposed, never how much."
          >
            <ExposureMatrixTable matrix={overview.data.exposure} />
          </Section>
          <Section
            id="observed"
            title="Observed series"
            description="Stored values only, compared with the thresholds shown."
          >
            <ObservedTable overview={overview.data} />
          </Section>
          <Section
            id="impacts"
            title="Simulated impacts"
            description="The latest completed execution for each company: simulated under its scenario's figures and assumptions, not a forecast."
          >
            <ImpactsTable overview={overview.data} />
          </Section>
          <Section id="relationships" title="Relationship changes">
            <RelationshipChangesList overview={overview.data} />
          </Section>
          <Section id="stored" title="Stored analyses">
            <StoredAnalyses />
          </Section>
          <MethodNote methods={methods} />
        </div>
      )}
    </>
  );
}

// --- One entity --------------------------------------------------------------------------------

const TABS = ["findings", "exposure", "drivers", "signals", "history", "sources", "brief"] as const;
type DossierTab = (typeof TABS)[number];

function driversOf(analysis: EntityAnalysis): IntelligenceDrivers {
  const entity = analysis.entity;
  const note =
    entity.node_type !== "company"
      ? "Executions are run for companies; an industry has no drivers of its own."
      : analysis.drivers
        ? "Contributions are the models' stored Shapley credits per change; they add up to each line's change."
        : `No completed execution is stored for ${entity.name}: run a scenario in the Scenario Lab to size its exposure.`;
  return {
    entity,
    executions: analysis.executions,
    drivers: analysis.drivers,
    previous: analysis.previous,
    note,
  };
}

function Brief({ entityKey, thresholds }: { entityKey: string; thresholds: ThresholdOverrides }) {
  const brief = useApiResource(`intelligence:brief:${entityKey}:${thresholdKey(thresholds)}`, () =>
    intelligenceApi.brief(entityKey, thresholds),
  );
  if (brief.status === "loading") return <LoadingState label="Preparing the brief…" />;
  if (brief.status === "error") return <ErrorState error={brief.error} onRetry={brief.reload} />;
  return <BriefView brief={brief.data} />;
}

function SummaryLine({ analysis }: { analysis: EntityAnalysis }) {
  const summary = analysis.exposure.summary;
  const headline = analysis.drivers?.lines.find((line) => line.id === analysis.drivers?.headline);
  const dependency = analysis.signals.find((signal) => signal.id === "dependency");
  return (
    <dl className={styles.coverage}>
      <div>
        <dt>Variables that reach it</dt>
        <dd className="tabular">{summary.variables}</dd>
      </div>
      <div>
        <dt>Exposure paths</dt>
        <dd className="tabular">{summary.paths}</dd>
      </div>
      <div>
        <dt>Dependency</dt>
        <dd>{dependency?.level_label ?? "—"}</dd>
      </div>
      <div>
        <dt>Latest simulated headline</dt>
        <dd className="tabular">
          {headline
            ? `${headline.label} ${money(headline.change, headline.currency, true)} (${percent(headline.percent_change)})`
            : "None stored"}
        </dd>
      </div>
    </dl>
  );
}

function describeEntity(analysis: EntityAnalysis): string {
  const entity = analysis.entity;
  const industry = analysis.exposure.context.find((link) => link.kind === "industry");
  const country = analysis.exposure.context.find((link) => link.kind === "country");
  const kind = entity.node_type === "company" ? "A company" : "An industry";
  const where = [industry && `in ${industry.node.name}`, country && `based in ${country.node.name}`]
    .filter(Boolean)
    .join(", ");
  return `${kind}${where ? ` ${where}` : ""}; ${NATURE[entity.nature] ?? entity.nature}.`;
}

function EntityView({
  entityKey,
  thresholds,
  methods,
  onThresholds,
}: {
  entityKey: string;
  thresholds: ThresholdOverrides;
  methods: IntelligenceMethods | undefined;
  onThresholds: (next: ThresholdOverrides) => void;
}) {
  const [searchParams, setSearchParams] = useSearchParams();
  const tab = (TABS as readonly string[]).includes(searchParams.get("view") ?? "")
    ? (searchParams.get("view") as DossierTab)
    : "findings";
  const evidence: EvidenceFilter =
    searchParams.get("evidence") === "evidence_backed" ? "evidence_backed" : "any";
  const key = `intelligence:entity:${entityKey}:${thresholdKey(thresholds)}:${evidence}`;
  const analysis = useFreshResource(key, () =>
    intelligenceApi.entity(entityKey, thresholds, evidence),
  );
  const [stored, setStored] = useState<StoredAnalysis | null>(null);
  const scenarios = useMemo(
    () => new Map((analysis.data?.executions ?? []).map((item) => [item.id, item.scenario_id])),
    [analysis.data],
  );
  const problems = analysis.status === "error" ? thresholdProblems(analysis.error) : {};

  const setParam = useCallback(
    (name: string, value: string | null) => {
      setSearchParams(
        (current) => {
          const next = new URLSearchParams(current);
          if (value === null) next.delete(name);
          else next.set(name, value);
          return next;
        },
        { replace: true },
      );
    },
    [setSearchParams],
  );

  const data = analysis.data;
  const entity = data?.entity;
  return (
    <>
      <PageHeader
        compact
        title={entity?.name ?? "Entity"}
        description={entity && data ? describeEntity(data) : undefined}
        meta={
          data && (
            <>
              <BuildBadge build={data.build} />
              {evidence === "evidence_backed" && (
                <Badge tone="accent">Evidence-backed relationships only</Badge>
              )}
            </>
          )
        }
        actions={
          data && (
            <>
              <StoreButton
                request={{ scope: "entity", entity: entityKey, thresholds }}
                onStored={setStored}
              />
              <Link
                className={styles.headerLink}
                to={`/graph?focus=${encodeURIComponent(entityKey)}`}
              >
                In the graph
              </Link>
            </>
          )
        }
      />
      {stored && <StoredNotice analysis={stored} onClose={() => setStored(null)} />}
      {methods && (
        <ThresholdsPanel
          specs={methods.thresholds}
          current={thresholds}
          problems={problems}
          onApply={onThresholds}
        />
      )}
      {analysis.status === "loading" && <LoadingState label="Analysing…" lines={6} />}
      {analysis.status === "error" && (
        <ErrorState error={analysis.error} onRetry={analysis.reload} />
      )}
      {data && (
        <div className={cx(styles.main, analysis.isRefreshing && styles.refreshing)}>
          <SummaryLine analysis={data} />
          <Tabs
            label="Dossier"
            active={tab}
            onChange={(id) => setParam("view", id === "findings" ? null : id)}
            items={[
              {
                id: "findings",
                label: `Findings (${data.insights.length})`,
                content: () => <Ledger insights={data.insights} scenarios={scenarios} />,
              },
              {
                id: "exposure",
                label: "Exposure",
                content: () => (
                  <div className={styles.tabBody}>
                    <label className={styles.checkbox}>
                      <input
                        type="checkbox"
                        checked={evidence === "evidence_backed"}
                        onChange={(event) =>
                          setParam("evidence", event.target.checked ? "evidence_backed" : null)
                        }
                      />
                      Only relationships backed by a cited source
                    </label>
                    <ExposurePaths exposure={data.exposure} />
                    <Relations exposure={data.exposure} />
                  </div>
                ),
              },
              {
                id: "drivers",
                label: "Drivers",
                content: () => <DriversView found={driversOf(data)} />,
              },
              {
                id: "signals",
                label: "Signals",
                content: () => (
                  <SignalGrid
                    signals={[...data.signals, ...data.series.flatMap((item) => item.signals)]}
                    specs={methods?.signals ?? []}
                  />
                ),
              },
              {
                id: "history",
                label: "History",
                content: () => (
                  <HistoryView
                    series={data.series}
                    interpretations={data.interpretations}
                    notInterpreted={data.not_interpreted}
                    executions={data.executions}
                  />
                ),
              },
              {
                id: "sources",
                label: "Sources",
                content: () => <SourcesView analysis={data} />,
              },
              {
                id: "brief",
                label: "Brief",
                content: () => <Brief entityKey={entityKey} thresholds={thresholds} />,
              },
            ]}
          />
        </div>
      )}
    </>
  );
}

// --- A stored analysis -------------------------------------------------------------------------

function StoredView({ analysisId }: { analysisId: string }) {
  const analysis = useApiResource(`intelligence:analysis:${analysisId}`, () =>
    intelligenceApi.analyses.get(analysisId),
  );
  if (analysis.status === "loading") return <LoadingState label="Loading the stored analysis…" />;
  if (analysis.status === "error") {
    return <ErrorState error={analysis.error} onRetry={analysis.reload} />;
  }
  const data = analysis.data;
  const insights = data.entity?.insights ?? data.workspace?.insights ?? [];
  const live = data.subject_key ? entityPath(data.subject_key) : "/intelligence";
  return (
    <>
      <PageHeader
        compact
        title={`${data.subject_name}, as stored`}
        description={`Stored ${formatDateTime(data.created_at)}${data.label ? `: ${data.label}` : ""}. ${plural(data.insight_count, "finding")}, engine ${data.engine_version}.`}
        actions={
          <Link className={styles.headerLink} to={live}>
            The analysis now
          </Link>
        }
      />
      <p
        className={cx(
          styles.freshness,
          data.freshness.status === "stale" ? styles.freshnessStale : styles.freshnessCurrent,
        )}
        role="status"
      >
        <strong>{data.freshness.status === "stale" ? "Stale" : "Current"}.</strong>{" "}
        {data.freshness.message}
      </p>
      <div className={styles.main}>
        <Section id="stored-findings" title="Findings, as stored">
          <Ledger insights={insights} />
        </Section>
        <details className={styles.fold}>
          <summary>Fingerprint and hashes</summary>
          <table className={styles.facts}>
            <tbody>
              <tr>
                <th scope="row">Inputs hash</th>
                <td className={styles.hash}>{data.inputs_hash}</td>
              </tr>
              <tr>
                <th scope="row">Result hash</th>
                <td className={styles.hash}>{data.result_hash}</td>
              </tr>
              <tr>
                <th scope="row">Graph build</th>
                <td>{data.graph_build_id ? `#${data.graph_build_id}` : "none"}</td>
              </tr>
              {THRESHOLD_NAMES.map((name) => (
                <tr key={name}>
                  <th scope="row">{name.replaceAll("_", " ")}</th>
                  <td className="tabular">{data.thresholds[name] ?? "by frequency"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      </div>
    </>
  );
}

// --- The page ------------------------------------------------------------------------------------

export function IntelligencePage() {
  const { entityKey, analysisId } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const thresholds = useMemo(() => thresholdsFrom(searchParams), [searchParams]);
  const entities = useFreshResource("intelligence:entities", () => intelligenceApi.entities());
  const methods = useApiResource("intelligence:methods", () => intelligenceApi.methods());

  const onThresholds = useCallback(
    (next: ThresholdOverrides) => {
      setSearchParams(
        (current) => {
          const params = new URLSearchParams(current);
          for (const name of THRESHOLD_NAMES) params.delete(name);
          for (const [name, value] of Object.entries(next)) if (value) params.set(name, value);
          return params;
        },
        { replace: true },
      );
    },
    [setSearchParams],
  );

  useEffect(() => {
    if (entityKey && entityKey !== entityKey.trim()) navigate(entityPath(entityKey.trim()));
  }, [entityKey, navigate]);

  return (
    <div className={styles.page}>
      <SubjectRail entities={entities.data} />
      <div className={styles.content}>
        <SubjectPicker entities={entities.data} current={entityKey} stored={Boolean(analysisId)} />
        {analysisId ? (
          <StoredView analysisId={analysisId} />
        ) : entityKey ? (
          <EntityView
            key={entityKey}
            entityKey={entityKey}
            thresholds={thresholds}
            methods={methods.data}
            onThresholds={onThresholds}
          />
        ) : (
          <WorkspaceView
            thresholds={thresholds}
            methods={methods.data}
            onThresholds={onThresholds}
          />
        )}
      </div>
    </div>
  );
}
