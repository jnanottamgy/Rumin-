/** One instrument's daily prices, from one imported dataset at a time (never blended). */
import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router";
import { PageHeader } from "@/components/PageHeader";
import { Panel } from "@/components/Panel";
import { ScrollRegion } from "@/components/ScrollRegion";
import { EmptyState, ErrorState, LoadingState } from "@/components/States";
import { type ChartPoint, dateTime, withinDays } from "@/features/data/chartMath";
import { DataNatureBadges, Fact, FreshnessFacts } from "@/features/data/DataNature";
import styles from "@/features/data/DataViews.module.css";
import { describeValue, QUALITY } from "@/features/data/labels";
import { ChartKey, FlagGlyph } from "@/features/data/ObservationViews";
import { ProvenanceFacts, QualityIssueList } from "@/features/data/Provenance";
import { TimeSeriesChart } from "@/features/data/TimeSeriesChart";
import { graphHref } from "@/features/graph/encoding";
import { useApiResource } from "@/hooks/useApiResource";
import { ApiError } from "@/lib/apiClient";
import { formatExact, formatRounded, toNumber } from "@/lib/decimal";
import { formatCalendarDate, formatCount } from "@/lib/format";
import { dataApi } from "@/services/api";
import type { InstrumentDetail, PriceBar, PriceBarPage } from "@/types/api";
import page from "./DataDetailPage.module.css";

/** Prices beyond this many rows are not loaded into the page (the note says so). */
const MAX_PAGES = 20;
// The trading-gap quality rule uses the same threshold: longer gaps break the line.
const MAX_TRADING_GAP_DAYS = 7;

async function loadPrices(id: string, datasetId: string) {
  const first: PriceBarPage = await dataApi.prices(id, datasetId);
  const items: PriceBar[] = [...first.items];
  for (let pages = 1; items.length < first.total && pages < MAX_PAGES; pages += 1) {
    const next = await dataApi.prices(id, datasetId, items.length);
    if (next.items.length === 0) break;
    items.push(...next.items);
  }
  return { first, items };
}

function PriceChart({
  items,
  currency,
  label,
}: {
  items: PriceBar[];
  currency: string;
  label: string;
}) {
  const points = useMemo<ChartPoint[]>(
    () =>
      items.map((bar) => ({
        key: bar.trade_date,
        time: dateTime(bar.trade_date),
        value: toNumber(bar.close),
        flagged: bar.quality_status === "warning",
      })),
    [items],
  );
  const contiguous = useMemo(() => withinDays(MAX_TRADING_GAP_DAYS), []);
  return (
    <>
      <TimeSeriesChart
        points={points}
        label={`${label} closing price`}
        unit={`Close, ${currency}`}
        contiguous={contiguous}
        describe={(index) => {
          const bar = items[index];
          if (!bar) return { title: "", value: "", notes: [] };
          const notes = [
            `Open ${formatExact(bar.open)} · High ${formatExact(bar.high)} · Low ${formatExact(bar.low)}`,
          ];
          if (bar.volume !== null) notes.push(`Volume ${formatCount(bar.volume)}`);
          if (bar.quality_status === "warning") notes.push("Flagged for review.");
          return {
            title: `${formatCalendarDate(bar.trade_date)} · close, ${currency}`,
            value: formatExact(bar.close),
            notes,
          };
        }}
        endLabel={(index) => {
          const bar = items[index];
          return bar ? formatRounded(bar.close, 2) : "";
        }}
      />
      <ChartKey flagged={points.some((point) => point.flagged)} missing={false} />
    </>
  );
}

function PriceTable({ items }: { items: PriceBar[] }) {
  return (
    <ScrollRegion className={styles.tableScroll}>
      <table className={styles.table}>
        <caption>
          Prices exactly as they appear in the imported file. RUMIN does not adjust prices; an
          adjusted close appears only when the file supplies one.
        </caption>
        <thead>
          <tr>
            <th scope="col">Date</th>
            <th scope="col" className={styles.number}>
              Open
            </th>
            <th scope="col" className={styles.number}>
              High
            </th>
            <th scope="col" className={styles.number}>
              Low
            </th>
            <th scope="col" className={styles.number}>
              Close
            </th>
            <th scope="col" className={styles.number}>
              Adj. close
            </th>
            <th scope="col" className={styles.number}>
              Volume
            </th>
            <th scope="col">Quality</th>
            <th scope="col" className={styles.number}>
              File line
            </th>
          </tr>
        </thead>
        <tbody>
          {[...items].reverse().map((bar) => (
            <tr key={bar.id}>
              <th scope="row" className={styles.nowrap}>
                {formatCalendarDate(bar.trade_date)}
              </th>
              <td className={styles.number}>{formatExact(bar.open)}</td>
              <td className={styles.number}>{formatExact(bar.high)}</td>
              <td className={styles.number}>{formatExact(bar.low)}</td>
              <td className={styles.number}>{formatExact(bar.close)}</td>
              <td className={styles.number}>
                {bar.adjusted_close ? formatExact(bar.adjusted_close) : "—"}
              </td>
              <td className={styles.number}>
                {bar.volume === null ? "—" : formatCount(bar.volume)}
              </td>
              <td>
                {bar.quality_status === "warning" ? (
                  <span className={styles.flagMark}>
                    <FlagGlyph /> {QUALITY.warning}
                  </span>
                ) : (
                  QUALITY.validated
                )}
              </td>
              <td className={styles.number}>{bar.source_row ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </ScrollRegion>
  );
}

function Prices({ instrument, datasetId }: { instrument: InstrumentDetail; datasetId: string }) {
  const [view, setView] = useState<"chart" | "table">("chart");
  const prices = useApiResource(`data:prices:${instrument.id}:${datasetId}`, () =>
    loadPrices(instrument.id, datasetId),
  );
  const issues = useApiResource(`data:issues:instrument:${instrument.id}`, () =>
    dataApi.issues({ instrumentId: instrument.id, limit: 50 }),
  );

  if (prices.status === "loading") return <LoadingState label="Loading prices…" />;
  if (prices.status === "error") return <ErrorState error={prices.error} onRetry={prices.reload} />;
  const { first, items } = prices.data;
  const dataset = first.dataset;
  const latest = items[items.length - 1];
  const flagged = items.filter((bar) => bar.quality_status === "warning").length;

  return (
    <>
      {flagged > 0 && (
        <p className={styles.caption}>
          {formatCount(flagged)} trading day(s) from this source are flagged for review. They are
          stored exactly as imported.
        </p>
      )}
      <FreshnessFacts
        latestPeriod={latest ? formatCalendarDate(latest.trade_date) : "None"}
        latestLabel="Latest trading day"
        retrievedAt={latest?.retrieved_at}
        retrievedLabel="Imported into RUMIN"
        providerLastUpdated={dataset.provider_last_updated}
      />
      <Panel
        title="Daily prices"
        description={`${instrument.currency} · ${describeValue(items[0]?.adjustment ?? "unadjusted")}`}
        actions={
          <fieldset className={styles.switch}>
            <legend className="visually-hidden">Show prices as</legend>
            {(["chart", "table"] as const).map((option) => (
              <button
                key={option}
                type="button"
                aria-pressed={view === option}
                onClick={() => setView(option)}
              >
                {option === "chart" ? "Chart" : "Table"}
              </button>
            ))}
          </fieldset>
        }
      >
        {items.length === 0 ? (
          <EmptyState title="No prices stored from this dataset" />
        ) : view === "chart" ? (
          <PriceChart items={items} currency={instrument.currency} label={instrument.name} />
        ) : (
          <PriceTable items={items} />
        )}
        {items.length < first.total && (
          <p className={styles.caption}>
            Showing the first {formatCount(items.length)} of {formatCount(first.total)} trading
            days.
          </p>
        )}
        <p className={styles.caption}>
          The chart shows closing prices. Gaps longer than {MAX_TRADING_GAP_DAYS} days are left as
          gaps; nothing is interpolated.
        </p>
      </Panel>
      <div className={page.columns}>
        <Panel title="Source and licence">
          <ProvenanceFacts dataset={dataset}>
            <Fact label="Listing">
              <span className={styles.mono}>
                {instrument.exchange_mic}:{instrument.symbol}
              </span>
            </Fact>
            {instrument.isin && (
              <Fact label="ISIN">
                <span className={styles.mono}>{instrument.isin}</span>
              </Fact>
            )}
            <Fact label="Type">{describeValue(instrument.instrument_type)}</Fact>
            <Fact label="Currency">{instrument.currency}</Fact>
            {graphHref("instrument", instrument.id) && (
              <Fact label="Knowledge graph">
                <Link to={graphHref("instrument", instrument.id) ?? "/graph"}>
                  See what this instrument is linked to
                </Link>
              </Fact>
            )}
          </ProvenanceFacts>
        </Panel>
        <Panel
          title="Data quality"
          description="Issues found when files for this instrument were imported."
        >
          {issues.status === "loading" && <LoadingState lines={2} />}
          {issues.status === "error" && <ErrorState error={issues.error} onRetry={issues.reload} />}
          {issues.status === "success" && (
            <QualityIssueList issues={issues.data.items} empty="No issues were found." />
          )}
        </Panel>
      </div>
    </>
  );
}

export function InstrumentPage() {
  const { instrumentId = "" } = useParams();
  const instrument = useApiResource(`data:instrument:${instrumentId}`, () =>
    dataApi.instrument(instrumentId),
  );
  const [chosen, setChosen] = useState<string | null>(null);

  useEffect(() => {
    document.title = `${instrument.status === "success" ? instrument.data.name : "Instrument"} — RUMIN`;
  }, [instrument]);

  if (instrument.status === "loading") return <LoadingState label="Loading the instrument…" />;
  if (instrument.status === "error") {
    const missing = instrument.error instanceof ApiError && instrument.error.status === 404;
    return (
      <div className={page.page}>
        <Link to="/data" className={page.back}>
          ← Data Explorer
        </Link>
        <ErrorState
          error={instrument.error}
          title={missing ? "This instrument does not exist" : "The instrument could not be loaded"}
          onRetry={missing ? undefined : instrument.reload}
        />
      </div>
    );
  }

  const data = instrument.data;
  const datasets = data.price_datasets;
  const datasetId = chosen ?? datasets[0]?.id ?? data.dataset_id;

  return (
    <div className={page.page}>
      <Link to="/data" className={page.back}>
        ← Data Explorer
      </Link>
      <PageHeader
        eyebrow={`Instrument · ${data.exchange_mic}:${data.symbol}`}
        title={data.name}
        description="Daily prices imported from files the user is licensed to use. RUMIN ships no price data and connects to no market feed."
        meta={
          <DataNatureBadges
            dataset={
              datasets.find((dataset) => dataset.id === datasetId) ?? { is_illustrative: false }
            }
            hasData={data.bar_count > 0}
          />
        }
        actions={
          datasets.length > 1 ? (
            <label className={styles.check}>
              Source
              <select
                className={page.select}
                value={datasetId}
                onChange={(event) => setChosen(event.target.value)}
              >
                {datasets.map((dataset) => (
                  <option key={dataset.id} value={dataset.id}>
                    {dataset.name}
                  </option>
                ))}
              </select>
            </label>
          ) : undefined
        }
      />
      {datasets.length > 1 && (
        <p className={styles.caption}>
          Prices for this instrument come from {datasets.length} sources. They are shown one source
          at a time and never blended.
        </p>
      )}
      <Prices instrument={data} datasetId={datasetId} />
    </div>
  );
}
