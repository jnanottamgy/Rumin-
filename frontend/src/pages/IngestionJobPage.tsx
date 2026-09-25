/** One ingestion run: what was asked, what each target did, and what was stored. */
import { useEffect } from "react";
import { Link, useParams } from "react-router";
import { PageHeader } from "@/components/PageHeader";
import { Panel } from "@/components/Panel";
import { ScrollRegion } from "@/components/ScrollRegion";
import { ErrorState, LoadingState } from "@/components/States";
import { StatGrid, StatTile } from "@/components/StatTile";
import { Fact, ItemStatusIndicator, JobStatusIndicator, Notice } from "@/features/data/DataNature";
import styles from "@/features/data/DataViews.module.css";
import { OUTCOME, ruleLabel } from "@/features/data/labels";
import { useApiResource } from "@/hooks/useApiResource";
import { ApiError } from "@/lib/apiClient";
import { formatBytes, formatCount, formatDateTime } from "@/lib/format";
import { dataApi } from "@/services/api";
import type { IngestionJobDetail, IngestionJobItem } from "@/types/api";
import page from "./DataDetailPage.module.css";

function targetLink(item: IngestionJobItem) {
  if (item.series_id) return <Link to={`/data/series/${item.series_id}`}>{item.target_label}</Link>;
  if (item.instrument_id) {
    return <Link to={`/data/instruments/${item.instrument_id}`}>{item.target_label}</Link>;
  }
  return item.target_label;
}

function duration(job: IngestionJobDetail): string {
  if (!job.started_at || !job.finished_at) return "—";
  const seconds = (Date.parse(job.finished_at) - Date.parse(job.started_at)) / 1000;
  return seconds < 60 ? `${seconds.toFixed(1)} s` : `${(seconds / 60).toFixed(1)} min`;
}

function Summary({ job }: { job: IngestionJobDetail }) {
  if (!job.error_summary) return null;
  const tone =
    job.status === "failed" ? "critical" : job.status === "cancelled" ? "neutral" : "warning";
  return (
    <Notice tone={tone} title="What went wrong">
      <p>{job.error_summary}</p>
    </Notice>
  );
}

function Items({ job }: { job: IngestionJobDetail }) {
  return (
    <ScrollRegion className={styles.tableScroll}>
      <table className={styles.table}>
        <caption>
          Received = new + revised + unchanged + rejected. Missing counts accepted periods that had
          no value.
        </caption>
        <thead>
          <tr>
            <th scope="col">Target</th>
            <th scope="col">Outcome</th>
            <th scope="col" className={styles.number}>
              Received
            </th>
            <th scope="col" className={styles.number}>
              New
            </th>
            <th scope="col" className={styles.number}>
              Revised
            </th>
            <th scope="col" className={styles.number}>
              Unchanged
            </th>
            <th scope="col" className={styles.number}>
              Missing
            </th>
            <th scope="col" className={styles.number}>
              Rejected
            </th>
          </tr>
        </thead>
        <tbody>
          {job.items.map((item) => (
            <tr key={item.id}>
              <th scope="row">
                {targetLink(item)}
                {item.error_message && item.status === "failed" && (
                  <span className={styles.secondary}>{item.error_message}</span>
                )}
              </th>
              <td>
                <ItemStatusIndicator status={item.status} errorCode={item.error_code} />
              </td>
              <td className={styles.number}>{formatCount(item.records_received)}</td>
              <td className={styles.number}>{formatCount(item.records_new)}</td>
              <td className={styles.number}>{formatCount(item.records_revised)}</td>
              <td className={styles.number}>{formatCount(item.records_unchanged)}</td>
              <td className={styles.number}>{formatCount(item.records_missing)}</td>
              <td className={styles.number}>{formatCount(item.records_rejected)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </ScrollRegion>
  );
}

function Issues({ job }: { job: IngestionJobDetail }) {
  if (job.issue_counts.length === 0) {
    return <p className={styles.muted}>No quality issues were recorded by this run.</p>;
  }
  return (
    <ScrollRegion className={styles.tableScroll}>
      <table className={styles.table} aria-label="Quality issues by rule">
        <thead>
          <tr>
            <th scope="col">Rule</th>
            <th scope="col">Outcome</th>
            <th scope="col" className={styles.number}>
              Count
            </th>
          </tr>
        </thead>
        <tbody>
          {job.issue_counts.map((issue) => (
            <tr key={`${issue.rule}-${issue.outcome}`}>
              <th scope="row">{ruleLabel(issue.rule)}</th>
              <td title={OUTCOME[issue.outcome].description}>{OUTCOME[issue.outcome].label}</td>
              <td className={styles.number}>{formatCount(issue.count)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </ScrollRegion>
  );
}

function Captures({ job }: { job: IngestionJobDetail }) {
  if (job.captures.length === 0) {
    return <p className={styles.muted}>Nothing was received, so nothing was stored.</p>;
  }
  return (
    <ScrollRegion className={styles.tableScroll}>
      <table className={styles.table}>
        <caption>
          The exact bytes received are stored (compressed) with their SHA-256, so every value can be
          traced to its response. Credentials are removed from addresses before storage.
        </caption>
        <thead>
          <tr>
            <th scope="col">Received</th>
            <th scope="col">Source</th>
            <th scope="col" className={styles.number}>
              HTTP
            </th>
            <th scope="col" className={styles.number}>
              Size
            </th>
            <th scope="col">SHA-256</th>
          </tr>
        </thead>
        <tbody>
          {job.captures.map((capture) => (
            <tr key={capture.id}>
              <td className={styles.nowrap}>{formatDateTime(capture.received_at)}</td>
              <td className={`${styles.mono} ${page.locator}`}>{capture.locator}</td>
              <td className={styles.number}>{capture.http_status ?? "—"}</td>
              <td className={styles.number}>{formatBytes(capture.size_bytes)}</td>
              <td className={styles.mono} title={capture.sha256}>
                {capture.sha256.slice(0, 12)}…
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </ScrollRegion>
  );
}

export function IngestionJobPage() {
  const { jobId = "" } = useParams();
  const job = useApiResource(`data:job:${jobId}`, () => dataApi.job(jobId));

  useEffect(() => {
    document.title = "Ingestion run — RUMIN";
  }, []);

  if (job.status === "loading") return <LoadingState label="Loading the run…" />;
  if (job.status === "error") {
    const missing = job.error instanceof ApiError && [404, 422].includes(job.error.status ?? 0);
    return (
      <div className={page.page}>
        <Link to="/data" className={page.back}>
          ← Data Explorer
        </Link>
        <ErrorState
          error={job.error}
          title={missing ? "This ingestion run does not exist" : "The run could not be loaded"}
          onRetry={missing ? undefined : job.reload}
        />
      </div>
    );
  }

  const data = job.data;
  return (
    <div className={page.page}>
      <Link to="/data" className={page.back}>
        ← Data Explorer
      </Link>
      <PageHeader
        eyebrow={`Ingestion run · ${data.provider_id}`}
        title={`${data.dataset_id} · ${formatDateTime(data.created_at)}`}
        meta={<JobStatusIndicator status={data.status} />}
      />
      <Summary job={data} />
      <StatGrid label="What the run did">
        <StatTile
          label="Targets succeeded"
          value={`${formatCount(data.items_succeeded)} of ${formatCount(data.items_total)}`}
          detail={`${formatCount(data.items_failed)} failed · ${formatCount(data.items_skipped)} skipped`}
        />
        <StatTile
          label="Records received"
          value={formatCount(data.records_received)}
          detail={`${formatCount(data.records_new)} new · ${formatCount(data.records_revised)} revised · ${formatCount(data.records_rejected)} rejected`}
        />
        <StatTile
          label="Warnings"
          value={formatCount(data.warning_count)}
          detail={`${formatCount(data.error_count)} record errors`}
        />
        <StatTile
          label="Requests"
          value={formatCount(data.request_count)}
          detail={`${formatBytes(data.bytes_received)} received in ${duration(data)}`}
        />
      </StatGrid>
      <Panel title="Targets">
        <Items job={data} />
      </Panel>
      <Panel title="Stored responses and files">
        <Captures job={data} />
      </Panel>
      <div className={page.columns}>
        <Panel title="Quality issues">
          <Issues job={data} />
        </Panel>
        <Panel title="Run details">
          <dl className={styles.facts}>
            <Fact label="Trigger">Command line</Fact>
            <Fact label="Requested">
              <span className={styles.mono}>{JSON.stringify(data.parameters)}</span>
            </Fact>
            <Fact label="Started">{data.started_at ? formatDateTime(data.started_at) : "—"}</Fact>
            <Fact label="Finished">
              {data.finished_at ? formatDateTime(data.finished_at) : "Not finished"}
            </Fact>
          </dl>
        </Panel>
      </div>
    </div>
  );
}
