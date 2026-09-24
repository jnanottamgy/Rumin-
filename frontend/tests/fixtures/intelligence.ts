/**
 * Phase 6 Financial Intelligence fixtures, captured from a running backend by
 * `backend/scripts/capture_intelligence_fixtures.py` (not hand-written): the sample network
 * built into a knowledge graph with the series catalogue (definitions only), and the
 * backend tests' REFERENCE scenario on the fictional Aerisca Airways, with HYPOTHETICAL round
 * figures (profit before tax −6,700,000 INR over 12 months), executed.
 *
 * `synthetic-*` fixtures also read SYNTHETIC exchange-rate and inflation values stored
 * through the ingestion pipeline from a scripted response
 * (`backend/tests/intelligence_support.py`): test values, not World Bank data.
 */
import type {
  EntityAnalysis,
  IntelligenceBrief,
  IntelligenceEntityList,
  IntelligenceMethods,
  IntelligenceOverview,
  SeriesIntelligence,
  StoredAnalysis,
  StoredAnalysisPage,
} from "@/types/api";
import analyses from "./intelligence/analyses.json";
import analysis from "./intelligence/analysis.json";
import brief from "./intelligence/brief.json";
import entities from "./intelligence/entities.json";
import entity from "./intelligence/entity.json";
import industry from "./intelligence/industry.json";
import methods from "./intelligence/methods.json";
import overview from "./intelligence/overview.json";
import overviewUnsimulated from "./intelligence/overview-unsimulated.json";
import syntheticStale from "./intelligence/synthetic-analysis-stale.json";
import syntheticEntity from "./intelligence/synthetic-entity.json";
import syntheticOverview from "./intelligence/synthetic-overview.json";
import syntheticSeries from "./intelligence/synthetic-series.json";
import thresholdError from "./intelligence/threshold-error.json";

const copy = <T>(value: unknown): T => structuredClone(value) as T;

export const AERISCA = "company:co_aerisca_airways";
export const AIR_TRANSPORT = "industry:ind_air_transport";
export const STORED_ID = analysis.id;

export const intelligenceFixtures = {
  methods: () => copy<IntelligenceMethods>(methods),
  overview: () => copy<IntelligenceOverview>(overview),
  overviewUnsimulated: () => copy<IntelligenceOverview>(overviewUnsimulated),
  entities: () => copy<IntelligenceEntityList>(entities),
  entity: () => copy<EntityAnalysis>(entity),
  industry: () => copy<EntityAnalysis>(industry),
  brief: () => copy<IntelligenceBrief>(brief),
  analysis: () => copy<StoredAnalysis>(analysis),
  analyses: () => copy<StoredAnalysisPage>(analyses),
  thresholdError: () => copy<unknown>(thresholdError),
  syntheticOverview: () => copy<IntelligenceOverview>(syntheticOverview),
  syntheticEntity: () => copy<EntityAnalysis>(syntheticEntity),
  syntheticSeries: () => copy<SeriesIntelligence>(syntheticSeries),
  syntheticStale: () => copy<StoredAnalysis>(syntheticStale),
};
