/**
 * Phase 2 API fixtures, captured from running backends (not hand-written):
 *
 * - `synthetic-*`: a throwaway database filled through the real ingestion pipeline with
 *   SYNTHETIC provider responses and a SYNTHETIC price file. The values come from a
 *   formula and every name says so; they are not World Bank data and not market data.
 * - `failed-*` and `empty-*`: the real series catalogue after a World Bank run that
 *   failed because the build environment could not reach the provider — no values.
 */
import type {
  DatasetPage,
  EconomicSeriesDetail,
  EconomicSeriesPage,
  IngestionJobDetail,
  IngestionJobPage,
  InstrumentDetail,
  InstrumentPage,
  ObservationPage,
  PriceBarPage,
  QualityIssuePage,
  SystemStatus,
} from "@/types/api";
import emptyInstruments from "./data/empty-instruments.json";
import failedDatasets from "./data/failed-datasets.json";
import failedJob from "./data/failed-job.json";
import failedJobs from "./data/failed-jobs.json";
import failedSeries from "./data/failed-series.json";
import failedSeriesDetail from "./data/failed-series-detail.json";
import failedSystem from "./data/failed-system.json";
import syntheticDatasets from "./data/synthetic-datasets.json";
import syntheticInstrument from "./data/synthetic-instrument.json";
import syntheticInstrumentIssues from "./data/synthetic-instrument-issues.json";
import syntheticInstruments from "./data/synthetic-instruments.json";
import syntheticJob from "./data/synthetic-job.json";
import syntheticJobs from "./data/synthetic-jobs.json";
import syntheticObservations from "./data/synthetic-observations.json";
import syntheticObservationsRevisions from "./data/synthetic-observations-revisions.json";
import syntheticPrices from "./data/synthetic-prices.json";
import syntheticSeries from "./data/synthetic-series.json";
import syntheticSeriesDetail from "./data/synthetic-series-detail.json";
import syntheticSeriesIssues from "./data/synthetic-series-issues.json";
import syntheticSystem from "./data/synthetic-system.json";

const copy = <T>(value: unknown): T => structuredClone(value) as T;

export const synthetic = {
  system: () => copy<SystemStatus>(syntheticSystem),
  series: () => copy<EconomicSeriesPage>(syntheticSeries),
  seriesDetail: () => copy<EconomicSeriesDetail>(syntheticSeriesDetail),
  observations: () => copy<ObservationPage>(syntheticObservations),
  observationsWithRevisions: () => copy<ObservationPage>(syntheticObservationsRevisions),
  seriesIssues: () => copy<QualityIssuePage>(syntheticSeriesIssues),
  datasets: () => copy<DatasetPage>(syntheticDatasets),
  instruments: () => copy<InstrumentPage>(syntheticInstruments),
  instrument: () => copy<InstrumentDetail>(syntheticInstrument),
  prices: () => copy<PriceBarPage>(syntheticPrices),
  instrumentIssues: () => copy<QualityIssuePage>(syntheticInstrumentIssues),
  jobs: () => copy<IngestionJobPage>(syntheticJobs),
  job: () => copy<IngestionJobDetail>(syntheticJob),
};

export const failed = {
  system: () => copy<SystemStatus>(failedSystem),
  series: () => copy<EconomicSeriesPage>(failedSeries),
  seriesDetail: () => copy<EconomicSeriesDetail>(failedSeriesDetail),
  jobs: () => copy<IngestionJobPage>(failedJobs),
  job: () => copy<IngestionJobDetail>(failedJob),
  datasets: () => copy<DatasetPage>(failedDatasets),
  instruments: () => copy<InstrumentPage>(emptyInstruments),
};
