/**
 * The Data Explorer: every series and instrument RUMIN has stored, where it came from,
 * how current it is, and what each ingestion run did. Read-only — ingestion runs from
 * the command line.
 */
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { PageHeader } from "@/components/PageHeader";
import { Panel } from "@/components/Panel";
import { ScrollRegion } from "@/components/ScrollRegion";
import { EmptyState, ErrorState, LoadingState } from "@/components/States";
import { StatGrid, StatTile } from "@/components/StatTile";
import {
  Command,
  ItemStatusIndicator,
  JobStatusIndicator,
  Notice,
} from "@/features/data/DataNature";
import styles from "@/features/data/DataViews.module.css";
import { describeValue } from "@/features/data/labels";
import { ExternalLink } from "@/features/data/Provenance";
import { useApiResource } from "@/hooks/useApiResource";
import { formatRounded } from "@/lib/decimal";
import {
  formatCalendarDate,
  formatCount,
  formatDateTime,
  formatFrequency,
  formatPeriod,
} from "@/lib/format";
import { api, dataApi } from "@/services/api";
import type { Dataset, EconomicSeries, IngestionJob, Instrument } from "@/types/api";
import page from "./DataExplorerPage.module.css";

const UNAVAILABLE = "—";

function year(date: string | null | undefined): string {
  return date ? date.slice(0, 4) : "";
}

function Stats({ system }: { system: ReturnType<typeof useSystem> }) {
  const data = system.status === "success" ? system.data.data : null;
  const last = data?.last_job;
  return (
    <StatGrid label="Stored data">
      <StatTile
        label="Series with values"
        value={data ? formatCount(data.series_with_data) : UNAVAILABLE}
        detail={data ? `of ${formatCount(data.series_total)} in the catalogue` : undefined}
      />
      <StatTile
        label="Observations stored"
        value={data ? formatCount(data.observations) : UNAVAILABLE}
        detail="Current values; revisions are kept separately"
      />
      <StatTile
        label="Flagged for review"
        value={data ? formatCount(data.flagged_values) : UNAVAILABLE}
        detail="Stored as reported, never corrected"
      />
      <StatTile
        label="Last ingestion"
        value={last ? <JobStatusIndicator status={last.status} /> : UNAVAILABLE}
        detail={last ? formatDateTime(last.created_at) : data ? "No run yet" : undefined}
      />
    </StatGrid>
  );
}

function useSystem() {
  return useApiResource("system", () => api.system());
}

function SeriesNotice({
  items,
  lastJob,
}: {
  items: EconomicSeries[];
  lastJob: IngestionJob | undefined;
}) {
  if (items.some((series) => series.observation_count > 0)) return null;
  const failed = lastJob && ["failed", "partially_failed"].includes(lastJob.status);
  return (
    <Notice
      tone={failed ? "critical" : "neutral"}
      title={
        failed ? "The last retrieval failed — no values are stored yet" : "No values retrieved yet"
      }
    >
      {failed && lastJob && (
        <p>
          {lastJob.items_succeeded} of {lastJob.items_total} series retrieved (
          {lastJob.items_failed} failed, {lastJob.items_skipped} skipped).{" "}
          <Link to={`/data/jobs/${lastJob.id}`}>See what happened</Link>
        </p>
      )}
      <p>
        Retrieve the catalogue's series from the World Bank (this needs internet access to{" "}
        <span className={styles.mono}>api.worldbank.org</span>):
      </p>
      <p>
        <Command>python -m app.ingestion run worldbank-wdi</Command>
      </p>
    </Notice>
  );
}

function SeriesCatalogue({ lastJob }: { lastJob: IngestionJob | undefined }) {
  const series = useApiResource("data:series", () => dataApi.series());
  const [query, setQuery] = useState("");
  const [country, setCountry] = useState("");
  const [withValues, setWithValues] = useState(false);

  const items = series.status === "success" ? series.data.items : [];
  const countries = useMemo(
    () => [...new Set(items.map((item) => item.country_iso3).filter(Boolean))].sort() as string[],
    [items],
  );
  const needle = query.trim().toLowerCase();
  const visible = items.filter(
    (item) =>
      (!needle ||
        item.name.toLowerCase().includes(needle) ||
        item.provider_code.toLowerCase().includes(needle)) &&
      (!country || item.country_iso3 === country) &&
      (!withValues || item.observation_count > 0),
  );

  if (series.status === "loading") return <LoadingState label="Loading series…" />;
  if (series.status === "error") return <ErrorState error={series.error} onRetry={series.reload} />;
  if (items.length === 0) {
    return (
      <EmptyState title="The series catalogue has not been loaded">
        <p>
          Load it (it lists what to retrieve, and contains no values):{" "}
          <Command>python -m app.ingestion catalog</Command>
        </p>
      </EmptyState>
    );
  }

  return (
    <div className={page.stack}>
      <SeriesNotice items={items} lastJob={lastJob} />
      <search className={page.filters} aria-label="Filter series">
        <label className={page.field}>
          <span>Search</span>
          <input
            type="search"
            value={query}
            placeholder="Name or indicator code"
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
        <label className={page.field}>
          <span>Country</span>
          <select value={country} onChange={(event) => setCountry(event.target.value)}>
            <option value="">All countries</option>
            {countries.map((code) => (
              <option key={code} value={code}>
                {code}
              </option>
            ))}
          </select>
        </label>
        <label className={styles.check}>
          <input
            type="checkbox"
            checked={withValues}
            onChange={(event) => setWithValues(event.target.checked)}
          />
          Only series with values
        </label>
        <p className={page.count} aria-live="polite">
          {visible.length === items.length
            ? `${formatCount(items.length)} series`
            : `${formatCount(visible.length)} of ${formatCount(items.length)} series`}
        </p>
      </search>
      <ScrollRegion className={styles.tableScroll}>
        <table className={styles.table}>
          <caption>
            Latest values are rounded to two decimals here; each series page shows every published
            digit. All values are historical — nothing is live.
          </caption>
          <thead>
            <tr>
              <th scope="col">Series</th>
              <th scope="col">Frequency</th>
              <th scope="col">Unit</th>
              <th scope="col">Coverage</th>
              <th scope="col" className={styles.number}>
                Latest value
              </th>
              <th scope="col">Last retrieval</th>
            </tr>
          </thead>
          <tbody>
            {visible.map((item) => (
              <tr key={item.id}>
                <td className={page.nameCell}>
                  <Link to={`/data/series/${item.id}`}>{item.name}</Link>
                  <span className={styles.secondary}>
                    <span className={styles.mono}>{item.provider_code}</span>
                    {item.country_iso3 ? ` · ${item.country_iso3}` : ""}
                  </span>
                </td>
                <td className={styles.nowrap}>{formatFrequency(item.frequency)}</td>
                <td>{item.unit}</td>
                <td className={styles.nowrap}>
                  {item.first_period ? (
                    `${year(item.first_period)}–${year(item.last_period)}`
                  ) : (
                    <span className={styles.muted}>No values</span>
                  )}
                </td>
                <td className={styles.number}>
                  {item.latest ? (
                    <>
                      {formatRounded(item.latest.value, 2)}
                      <span className={styles.secondary}>
                        {formatPeriod(item.latest.period_label)}
                        {item.latest.quality_status === "warning" ? " · flagged" : ""}
                      </span>
                    </>
                  ) : (
                    <span className={styles.muted}>{UNAVAILABLE}</span>
                  )}
                </td>
                <td>
                  {item.last_ingestion_status ? (
                    <>
                      <ItemStatusIndicator status={item.last_ingestion_status} />
                      {item.last_ingestion_at && (
                        <span className={styles.secondary}>
                          {formatDateTime(item.last_ingestion_at)}
                        </span>
                      )}
                    </>
                  ) : (
                    <span className={styles.muted}>Never retrieved</span>
                  )}
                </td>
              </tr>
            ))}
            {visible.length === 0 && (
              <tr>
                <td colSpan={6} className={styles.muted}>
                  No series match these filters.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </ScrollRegion>
    </div>
  );
}

function Instruments() {
  const instruments = useApiResource("data:instruments", () => dataApi.instruments());
  if (instruments.status === "loading") return <LoadingState lines={2} />;
  if (instruments.status === "error") {
    return <ErrorState error={instruments.error} onRetry={instruments.reload} />;
  }
  const items: Instrument[] = instruments.data.items;
  if (items.length === 0) {
    return (
      <EmptyState title="No price files imported">
        <p>
          RUMIN ships no price data. Import daily prices from a file you are licensed to use, with a
          manifest stating its licence and attribution:
        </p>
        <p>
          <Command>python -m app.ingestion manifest-template</Command>
        </p>
        <p>
          <Command>
            python -m app.ingestion import-prices --manifest manifest.json --file prices.csv
          </Command>
        </p>
      </EmptyState>
    );
  }
  return (
    <ScrollRegion className={styles.tableScroll}>
      <table className={styles.table} aria-label="Instruments">
        <thead>
          <tr>
            <th scope="col">Instrument</th>
            <th scope="col">Listing</th>
            <th scope="col">Currency</th>
            <th scope="col">Coverage</th>
            <th scope="col" className={styles.number}>
              Trading days
            </th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.id}>
              <td className={page.nameCell}>
                <Link to={`/data/instruments/${item.id}`}>{item.name}</Link>
                <span className={styles.secondary}>
                  {describeValue(item.instrument_type)}
                  {item.isin ? ` · ISIN ${item.isin}` : ""}
                </span>
              </td>
              <td className={styles.mono}>
                {item.exchange_mic}:{item.symbol}
              </td>
              <td>{item.currency}</td>
              <td className={styles.nowrap}>
                {item.first_trade_date && item.last_trade_date
                  ? `${formatCalendarDate(item.first_trade_date)} – ${formatCalendarDate(item.last_trade_date)}`
                  : UNAVAILABLE}
              </td>
              <td className={styles.number}>{formatCount(item.bar_count)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </ScrollRegion>
  );
}

const KIND_LABEL: Record<string, string> = {
  curated: "Curated reference data",
  provider: "Provider data",
};

function DatasetCard({ dataset }: { dataset: Dataset }) {
  return (
    <li className={page.dataset}>
      <div className={styles.badges}>
        <Badge tone="outline">{KIND_LABEL[dataset.kind] ?? dataset.kind}</Badge>
        {dataset.is_illustrative && <Badge tone="warning">Illustrative sample</Badge>}
      </div>
      <p className={page.datasetName}>{dataset.name}</p>
      <dl className={page.datasetFacts}>
        <div>
          <dt>Licence</dt>
          <dd>
            {dataset.license_url ? (
              <ExternalLink href={dataset.license_url}>{dataset.license}</ExternalLink>
            ) : (
              dataset.license
            )}
          </dd>
        </div>
        {dataset.attribution && (
          <div>
            <dt>Attribution</dt>
            <dd>{dataset.attribution}</dd>
          </div>
        )}
        {dataset.kind === "provider" && (
          <div>
            <dt>Provider's last update</dt>
            <dd>
              {dataset.provider_last_updated
                ? formatCalendarDate(dataset.provider_last_updated)
                : "Not reported"}
            </dd>
          </div>
        )}
        {dataset.last_job && (
          <div>
            <dt>Last ingestion</dt>
            <dd>
              <Link to={`/data/jobs/${dataset.last_job.id}`}>
                <JobStatusIndicator status={dataset.last_job.status} />
              </Link>
              <span className={styles.secondary}>
                {formatDateTime(dataset.last_job.created_at)}
              </span>
            </dd>
          </div>
        )}
      </dl>
    </li>
  );
}

function Datasets() {
  const datasets = useApiResource("data:datasets", () => dataApi.datasets());
  if (datasets.status === "loading") return <LoadingState lines={2} />;
  if (datasets.status === "error") {
    return <ErrorState error={datasets.error} onRetry={datasets.reload} />;
  }
  return (
    <ul className={page.datasets}>
      {datasets.data.items.map((dataset) => (
        <DatasetCard key={dataset.id} dataset={dataset} />
      ))}
    </ul>
  );
}

function Jobs({ jobs }: { jobs: ReturnType<typeof useJobs> }) {
  if (jobs.status === "loading") return <LoadingState lines={2} />;
  if (jobs.status === "error") return <ErrorState error={jobs.error} onRetry={jobs.reload} />;
  if (jobs.data.items.length === 0) {
    return (
      <EmptyState title="No ingestion has run yet">
        Runs started from the command line appear here with everything they did.
      </EmptyState>
    );
  }
  return (
    <ScrollRegion className={styles.tableScroll}>
      <table className={styles.table} aria-label="Recent ingestion runs">
        <thead>
          <tr>
            <th scope="col">Started</th>
            <th scope="col">Dataset</th>
            <th scope="col">Status</th>
            <th scope="col" className={styles.number}>
              Targets
            </th>
            <th scope="col" className={styles.number}>
              New · revised · rejected
            </th>
          </tr>
        </thead>
        <tbody>
          {jobs.data.items.map((job) => (
            <tr key={job.id}>
              <td className={styles.nowrap}>
                <Link to={`/data/jobs/${job.id}`}>{formatDateTime(job.created_at)}</Link>
              </td>
              <td className={`${styles.mono} ${styles.nowrap}`}>{job.dataset_id}</td>
              <td>
                <JobStatusIndicator status={job.status} />
              </td>
              <td className={styles.number}>
                {formatCount(job.items_succeeded)} of {formatCount(job.items_total)}
              </td>
              <td className={styles.number}>
                {formatCount(job.records_new)} · {formatCount(job.records_revised)} ·{" "}
                {formatCount(job.records_rejected)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </ScrollRegion>
  );
}

function useJobs() {
  return useApiResource("data:jobs", () => dataApi.jobs({ limit: 10 }));
}

export function DataExplorerPage() {
  const system = useSystem();
  const jobs = useJobs();

  useEffect(() => {
    document.title = "Data Explorer — RUMIN";
  }, []);

  const lastJob = jobs.status === "success" ? jobs.data.items[0] : undefined;

  return (
    <div className={page.page}>
      <PageHeader
        eyebrow="Data · Phase 2"
        title="Data Explorer"
        description="Historical data RUMIN has retrieved from providers or imported from licensed files — stored exactly as published, with its source, licence and every revision. Nothing here is live."
        actions={
          <Button
            size="sm"
            onClick={() => {
              system.reload();
              jobs.reload();
            }}
          >
            Refresh
          </Button>
        }
      />
      <Stats system={system} />
      <Panel
        title="Economic series"
        description="Historical series retrieved from data providers: coverage, the latest reported value and the outcome of the last retrieval."
      >
        <SeriesCatalogue lastJob={lastJob} />
      </Panel>
      <Panel
        title="Instruments and prices"
        description="Daily prices from files you are licensed to use. Each file's licence and attribution travel with its prices."
      >
        <Instruments />
      </Panel>
      <div className={page.columns}>
        <Panel title="Datasets and licences">
          <Datasets />
        </Panel>
        <Panel title="Recent ingestion runs">
          <Jobs jobs={jobs} />
        </Panel>
      </div>
    </div>
  );
}
