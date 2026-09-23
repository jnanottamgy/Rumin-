/** One economic series: its values, how current they are, where they came from. */
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router";
import { PageHeader } from "@/components/PageHeader";
import { Panel } from "@/components/Panel";
import { ErrorState, LoadingState } from "@/components/States";
import { StatusIndicator } from "@/components/StatusIndicator";
import {
  Command,
  DataNatureBadges,
  Fact,
  FreshnessFacts,
  Notice,
} from "@/features/data/DataNature";
import styles from "@/features/data/DataViews.module.css";
import { describeValue, ITEM_STATUS, MEASURE } from "@/features/data/labels";
import { ObservationChart, ObservationTable } from "@/features/data/ObservationViews";
import { ProvenanceFacts, QualityIssueList } from "@/features/data/Provenance";
import { useApiResource } from "@/hooks/useApiResource";
import { ApiError } from "@/lib/apiClient";
import { formatExact } from "@/lib/decimal";
import { formatDateTime, formatFrequency, formatPeriod } from "@/lib/format";
import { dataApi } from "@/services/api";
import type { EconomicSeriesDetail } from "@/types/api";
import page from "./DataDetailPage.module.css";

type View = "chart" | "table";

function ViewSwitch({ view, onChange }: { view: View; onChange: (view: View) => void }) {
  return (
    <fieldset className={styles.switch}>
      <legend className="visually-hidden">Show values as</legend>
      {(["chart", "table"] as const).map((option) => (
        <button
          key={option}
          type="button"
          aria-pressed={view === option}
          onClick={() => onChange(option)}
        >
          {option === "chart" ? "Chart" : "Table"}
        </button>
      ))}
    </fieldset>
  );
}

function RetrievalNotice({ series }: { series: EconomicSeriesDetail }) {
  const status = series.last_ingestion_status;
  if (status === "failed" || status === "skipped") {
    const reason = series.last_job ? `(${formatDateTime(series.last_job.created_at)})` : "";
    return (
      <Notice
        tone="warning"
        title={`The last retrieval ${status === "failed" ? "failed" : "was skipped"} ${reason}`}
      >
        <p>
          {series.last_successful_ingestion_at
            ? `The values below were retrieved on ${formatDateTime(series.last_successful_ingestion_at)} and may be out of date.`
            : "No values have been retrieved for this series yet."}{" "}
          {series.last_job && (
            <Link to={`/data/jobs/${series.last_job.id}`}>See what happened</Link>
          )}
        </p>
      </Notice>
    );
  }
  if (!status) {
    return (
      <Notice tone="neutral" title="Not retrieved yet">
        <p>
          Retrieve it with{" "}
          <Command>{`python -m app.ingestion run ${series.dataset_id} --series ${series.id}`}</Command>
        </p>
      </Notice>
    );
  }
  return null;
}

function Values({ series }: { series: EconomicSeriesDetail }) {
  const [view, setView] = useState<View>("chart");
  const [revisions, setRevisions] = useState(false);
  const showRevisions = view === "table" && revisions;
  const observations = useApiResource(`data:observations:${series.id}:${showRevisions}`, () =>
    dataApi.observations(series.id, showRevisions),
  );

  return (
    <Panel
      title="Values"
      description={`${series.unit} · ${formatFrequency(series.frequency)} · ${MEASURE[series.measure_type]}`}
      actions={
        <div className={styles.toolbar}>
          {view === "table" && (
            <label className={styles.check}>
              <input
                type="checkbox"
                checked={revisions}
                onChange={(event) => setRevisions(event.target.checked)}
              />
              Show revision history
            </label>
          )}
          <ViewSwitch view={view} onChange={setView} />
        </div>
      }
    >
      {observations.status === "loading" && <LoadingState label="Loading values…" />}
      {observations.status === "error" && (
        <ErrorState error={observations.error} onRetry={observations.reload} />
      )}
      {observations.status === "success" &&
        (view === "chart" ? (
          <ObservationChart
            series={observations.data.series}
            observations={observations.data.items}
          />
        ) : (
          <ObservationTable
            series={observations.data.series}
            observations={observations.data.items}
            showRevisions={showRevisions}
          />
        ))}
      {observations.status === "success" &&
        observations.data.total > observations.data.items.length && (
          <p className={styles.caption}>
            Showing the first {observations.data.items.length} of {observations.data.total} rows.
          </p>
        )}
      <p className={styles.caption}>
        Values are shown exactly as published: missing periods are gaps, and nothing is
        interpolated, adjusted or converted. Chart labels are rounded; the reading under the pointer
        and the table are exact.
      </p>
    </Panel>
  );
}

function Source({ series }: { series: EconomicSeriesDetail }) {
  return (
    <Panel title="Source and licence">
      <ProvenanceFacts dataset={series.dataset} providerName={series.provider_name}>
        <Fact label="Original source">
          {series.source_organization ?? <span className={styles.muted}>Not reported</span>}
        </Fact>
        <Fact label="Provider code">
          <span className={styles.mono}>{series.provider_series_key}</span>
        </Fact>
        <Fact label="Aggregation">{series.aggregation}</Fact>
        <Fact label="Price basis">{describeValue(series.price_basis)}</Fact>
        <Fact label="Seasonal adjustment">{describeValue(series.seasonal_adjustment)}</Fact>
        {series.currency && <Fact label="Currency">{series.currency}</Fact>}
        {series.variable_id && (
          <Fact label="Related RUMIN variable">
            <Link to={`/universe?focus=${series.variable_id}`}>{series.variable_id}</Link>
            {series.variable_relation && (
              <span className={styles.secondary}>{series.variable_relation}</span>
            )}
          </Fact>
        )}
        <Fact label="Review range">
          {series.plausible_min !== null || series.plausible_max !== null ? (
            <>
              {series.plausible_min !== null ? formatExact(series.plausible_min) : "−∞"} to{" "}
              {series.plausible_max !== null ? formatExact(series.plausible_max) : "∞"}
              <span className={styles.secondary}>
                RUMIN's assumption, not a fact: values outside it are stored as reported and flagged
                for review.
              </span>
            </>
          ) : (
            <span className={styles.muted}>None set</span>
          )}
        </Fact>
      </ProvenanceFacts>
    </Panel>
  );
}

function Quality({ series }: { series: EconomicSeriesDetail }) {
  const jobId = series.last_job?.id;
  const issues = useApiResource(`data:issues:series:${series.id}:${jobId ?? "none"}`, () =>
    jobId
      ? dataApi.issues({ seriesId: series.id, jobId })
      : Promise.resolve({ items: [], total: 0, limit: 0, offset: 0 }),
  );
  return (
    <Panel title="Data quality" description="Issues found by the latest retrieval of this series.">
      <dl className={styles.facts}>
        <Fact label="Flagged values">{series.flagged_count}</Fact>
        <Fact label="Revised periods">{series.revised_period_count}</Fact>
        <Fact label="Periods without a value">{series.missing_count}</Fact>
        <Fact label="Last retrieval">
          {series.last_ingestion_status ? (
            <StatusIndicator
              tone={ITEM_STATUS[series.last_ingestion_status].tone}
              label={ITEM_STATUS[series.last_ingestion_status].label}
              detail={
                series.last_ingestion_at ? formatDateTime(series.last_ingestion_at) : undefined
              }
            />
          ) : (
            <span className={styles.muted}>Never</span>
          )}
        </Fact>
      </dl>
      <div className={page.issues}>
        {issues.status === "loading" && <LoadingState lines={2} />}
        {issues.status === "error" && <ErrorState error={issues.error} onRetry={issues.reload} />}
        {issues.status === "success" && (
          <QualityIssueList
            issues={issues.data.items}
            empty={
              series.last_ingestion_status === "succeeded"
                ? "The latest retrieval found no issues."
                : "No values have been checked yet: no retrieval of this series has completed."
            }
          />
        )}
      </div>
    </Panel>
  );
}

export function EconomicSeriesPage() {
  const { seriesId = "" } = useParams();
  const series = useApiResource(`data:series:${seriesId}`, () => dataApi.seriesDetail(seriesId));

  useEffect(() => {
    document.title = `${series.status === "success" ? series.data.name : "Series"} — RUMIN`;
  }, [series]);

  if (series.status === "loading") return <LoadingState label="Loading the series…" />;
  if (series.status === "error") {
    const missing = series.error instanceof ApiError && series.error.status === 404;
    return (
      <div className={page.page}>
        <Link to="/data" className={page.back}>
          ← Data Explorer
        </Link>
        <ErrorState
          error={series.error}
          title={missing ? "This series does not exist" : "The series could not be loaded"}
          onRetry={missing ? undefined : series.reload}
        />
      </div>
    );
  }

  const data = series.data;
  return (
    <div className={page.page}>
      <Link to="/data" className={page.back}>
        ← Data Explorer
      </Link>
      <PageHeader
        eyebrow={`Economic series · ${data.provider_code}${data.country_iso3 ? ` · ${data.country_iso3}` : ""}`}
        title={data.name}
        description={data.description}
        meta={
          <DataNatureBadges
            dataset={data.dataset}
            hasData={data.observation_count > 0}
            flaggedCount={data.flagged_count}
          />
        }
      />
      <FreshnessFacts
        latestPeriod={
          data.latest ? (
            <>
              {formatPeriod(data.latest.period_label)}
              <span className={styles.muted}> · {formatExact(data.latest.value)}</span>
            </>
          ) : (
            <span className={styles.muted}>None</span>
          )
        }
        retrievedAt={data.last_successful_ingestion_at}
        providerLastUpdated={data.dataset.provider_last_updated}
      />
      <RetrievalNotice series={data} />
      <Values series={data} />
      <div className={page.columns}>
        <Source series={data} />
        <Quality series={data} />
      </div>
    </div>
  );
}
