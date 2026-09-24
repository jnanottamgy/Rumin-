"""Financial intelligence: structured, explainable findings grounded in RUMIN's data, graph
and simulations.

Every insight comes with the chain of evidence it rests on and an evidence grade (the
weakest link of that chain, not a probability). Observed changes, graph statements,
simulated results and model interpretations are labelled as what they are. Reads compute
the analysis from the current store and write nothing; stored analyses are created by
``POST /intelligence/analyses`` and never changed afterwards.

Thresholds can be overridden per request (query parameters on reads, ``thresholds`` in the
body of a stored analysis); ``GET /intelligence/methods`` lists them with their defaults
and reasons.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Path, Query, Response, status

from app.api.deps import NOT_FOUND, PaginationDep, SessionDep
from app.api.v1.data import INSTRUMENT_ID, SERIES_ID
from app.graph.drafts import NODE_KEY_PATTERN
from app.intelligence.insights import KIND_ORDER, RULES
from app.intelligence.thresholds import Thresholds
from app.schemas.intelligence import (
    AnalysisPage,
    AnalysisRead,
    AnalysisRequest,
    BriefRead,
    ChangesRead,
    DriversRead,
    EntityAnalysisRead,
    EntityListRead,
    EvidenceFilter,
    ExposureMapRead,
    Grade,
    InsightListRead,
    InstrumentIntelligenceRead,
    MethodsRead,
    OverviewRead,
    Scope,
    SeriesIntelligenceRead,
    SignalListRead,
    VariableExposureRead,
)
from app.services import intelligence

router = APIRouter(prefix="/intelligence", tags=["intelligence"])

EntityKey = Annotated[
    str,
    Path(
        pattern=NODE_KEY_PATTERN,
        max_length=128,
        description="A company or an industry (graph key).",
        examples=["company:co_aerisca_airways"],
    ),
]
VariableKey = Annotated[
    str,
    Path(pattern=NODE_KEY_PATTERN, max_length=128, examples=["variable:var_usd_inr"]),
]
SeriesId = Annotated[str, Path(pattern=SERIES_ID, max_length=96, examples=["wb-ind-pa-nus-fcrf"])]
InstrumentId = Annotated[
    str, Path(pattern=INSTRUMENT_ID, max_length=96, examples=["xnse-reliance"])
]
Evidence = Annotated[
    EvidenceFilter,
    Query(description="`evidence_backed` keeps only relationships with a cited source."),
]
_THRESHOLD = r"^-?\d{1,6}(\.\d{1,6})?$"


def thresholds_query(
    relative_change_percent: Annotated[
        str | None,
        Query(pattern=_THRESHOLD, description="Relative change (%) that counts as a change."),
    ] = None,
    point_change: Annotated[
        str | None,
        Query(pattern=_THRESHOLD, description="Change in percentage points that counts."),
    ] = None,
    price_move_percent: Annotated[
        str | None, Query(pattern=_THRESHOLD, description="Price move (%) that counts.")
    ] = None,
    anomaly_score: Annotated[
        str | None, Query(pattern=_THRESHOLD, description="Modified z-score called unusual.")
    ] = None,
    trend_significance: Annotated[
        str | None, Query(pattern=r"^0\.\d{1,3}$", description="0.10, 0.05 or 0.01.")
    ] = None,
    volatility_high_percentile: Annotated[
        str | None, Query(pattern=_THRESHOLD, description="Percentile called high.")
    ] = None,
    dependency_share_percent: Annotated[
        str | None, Query(pattern=_THRESHOLD, description="Share of paths called concentrated.")
    ] = None,
    min_history: Annotated[
        str | None, Query(pattern=r"^\d{1,4}$", description="Earlier values a signal needs.")
    ] = None,
    window: Annotated[
        str | None,
        Query(
            pattern=r"^\d{1,4}$", description="Values in the latest window (default: by frequency)."
        ),
    ] = None,
) -> Thresholds:
    overrides: dict[str, Any] = {
        name: value
        for name, value in {
            "relative_change_percent": relative_change_percent,
            "point_change": point_change,
            "price_move_percent": price_move_percent,
            "anomaly_score": anomaly_score,
            "trend_significance": trend_significance,
            "volatility_high_percentile": volatility_high_percentile,
            "dependency_share_percent": dependency_share_percent,
            "min_history": min_history,
            "window": window,
        }.items()
        if value is not None
    }
    return intelligence.resolve_thresholds(overrides)


ThresholdsDep = Annotated[Thresholds, Depends(thresholds_query)]


# --- The workspace -----------------------------------------------------------------------------


@router.get(
    "/overview",
    response_model=OverviewRead,
    summary="The intelligence overview",
    description="Every finding about the workspace, ordered (new observations first, then "
    "simulations, relationships, exposure and coverage), with the exposure matrix "
    "(companies × variables), the observed series and their signals, relationship changes, "
    "the latest simulated headline per company, and what the stored data can support.",
)
def get_overview(session: SessionDep, thresholds: ThresholdsDep) -> OverviewRead:
    return intelligence.overview(session, thresholds)


@router.get(
    "/insights",
    response_model=InsightListRead,
    summary="List insights",
    description="The workspace's insights, or one entity's (`entity`), filtered by kind, rule "
    "or minimum evidence grade. Each carries its facts, entities, relationships, period, "
    "models, evidence chain and grade, assumptions, sources, limitations and next steps.",
    responses=NOT_FOUND,
)
def list_insights(
    session: SessionDep,
    thresholds: ThresholdsDep,
    entity: Annotated[
        str | None, Query(pattern=NODE_KEY_PATTERN, max_length=128, description="An entity.")
    ] = None,
    kind: Annotated[
        str | None, Query(pattern="^(" + "|".join(KIND_ORDER) + ")$", description="A kind.")
    ] = None,
    rule: Annotated[
        str | None,
        Query(pattern="^(" + "|".join(r.id for r in RULES) + ")$", description="A rule id."),
    ] = None,
    grade: Annotated[Grade | None, Query(description="At least this evidence grade.")] = None,
) -> InsightListRead:
    return intelligence.insight_list(
        session, thresholds, entity=entity, kind=kind, rule=rule, grade=grade
    )


@router.get(
    "/changes",
    response_model=ChangesRead,
    summary="What changed",
    description="Changes of stored values that meet their thresholds (observed), data "
    "revisions, relationships the latest graph build added, changed or retired, and the "
    "headline between two executions of the same scenario (simulated) — each labelled.",
)
def get_changes(session: SessionDep, thresholds: ThresholdsDep) -> ChangesRead:
    return intelligence.changes(session, thresholds)


@router.get(
    "/methods",
    response_model=MethodsRead,
    summary="How intelligence is computed",
    description="The modules (question, inputs, method, limitations), the signal "
    "definitions, the insight rules, the thresholds with defaults and reasons, and the "
    "evidence grades.",
)
def get_methods() -> MethodsRead:
    return intelligence.methods()


# --- Entities ----------------------------------------------------------------------------------


@router.get(
    "/entities",
    response_model=EntityListRead,
    summary="List entities",
    description="Companies and industries with their stated exposure (paths, variables, "
    "channels, weakest evidence) and each company's latest simulated headline.",
)
def list_intelligence_entities(
    session: SessionDep,
    kind: Annotated[
        Literal["company", "industry"] | None, Query(description="Only one kind.")
    ] = None,
) -> EntityListRead:
    return intelligence.entity_list(session, kind)


@router.get(
    "/entities/{entity_key}",
    response_model=EntityAnalysisRead,
    summary="Analyse an entity",
    description="The dossier: exposure map, stored executions and their drivers, related "
    "series with their signals, model interpretations of observed changes (computed on "
    "request, not stored), the entity's signals and every insight with its evidence chain.",
    responses=NOT_FOUND,
)
def get_entity_intelligence(
    session: SessionDep,
    entity_key: EntityKey,
    thresholds: ThresholdsDep,
    evidence: Evidence = "any",
) -> EntityAnalysisRead:
    return intelligence.entity(session, entity_key, thresholds, evidence)


@router.get(
    "/entities/{entity_key}/brief",
    response_model=BriefRead,
    summary="The entity brief",
    description="The structured object a future AI Analyst would receive: observations, "
    "drivers, relationships, simulation results, assumptions, evidence and limitations, with "
    "rules for narrating them. Every number is computed by RUMIN.",
    responses=NOT_FOUND,
)
def get_entity_brief(
    session: SessionDep, entity_key: EntityKey, thresholds: ThresholdsDep
) -> BriefRead:
    return intelligence.entity_brief(session, entity_key, thresholds)


@router.get(
    "/entities/{entity_key}/exposure",
    response_model=ExposureMapRead,
    summary="An entity's exposure",
    description="Direct, via-industry and upstream exposure paths over validated "
    "relationships, with the models able to simulate each; counterparties and context listed "
    "apart; flagged relationships listed but never used.",
    responses=NOT_FOUND,
)
def get_entity_exposure(
    session: SessionDep, entity_key: EntityKey, evidence: Evidence = "any"
) -> dict[str, Any]:
    return intelligence.entity_exposure_read(session, entity_key, evidence)


@router.get(
    "/entities/{entity_key}/signals",
    response_model=SignalListRead,
    summary="An entity's signals",
    description="Exposure breadth, dependency and scenario sensitivity, each with its "
    "definition, inputs, period, evidence and limitations.",
    responses=NOT_FOUND,
)
def get_entity_signals(
    session: SessionDep, entity_key: EntityKey, thresholds: ThresholdsDep
) -> SignalListRead:
    return intelligence.entity_signal_list(session, entity_key, thresholds)


@router.get(
    "/entities/{entity_key}/drivers",
    response_model=DriversRead,
    summary="What drives an entity's simulated results",
    description="The latest completed execution's stored contributions per change (amounts, "
    "shares of the change, points of the baseline, per-unit effects), its sensitivity "
    "ranking, assumptions and entered figures, and the previous execution of the same "
    "scenario.",
    responses=NOT_FOUND,
)
def get_entity_drivers(session: SessionDep, entity_key: EntityKey) -> DriversRead:
    return intelligence.entity_drivers(session, entity_key)


@router.get(
    "/variables/{variable_key}/exposure",
    response_model=VariableExposureRead,
    summary="Who a variable reaches",
    description="Every company the graph states the variable reaches, with the paths.",
    responses=NOT_FOUND,
)
def get_variable_exposure(session: SessionDep, variable_key: VariableKey) -> VariableExposureRead:
    return intelligence.variable_exposure_read(session, variable_key)


# --- Series and instruments --------------------------------------------------------------------


@router.get(
    "/series/{series_id}",
    response_model=SeriesIntelligenceRead,
    summary="Analyse a series",
    description="Its stored values, changes, detected changes, trend, volatility and unusual "
    "change, revisions, the variable it is a related measure of and the companies that "
    "variable reaches, with the resulting insights.",
    responses=NOT_FOUND,
)
def get_series_intelligence(
    session: SessionDep, series_id: SeriesId, thresholds: ThresholdsDep
) -> SeriesIntelligenceRead:
    return intelligence.series_read(session, series_id, thresholds)


@router.get(
    "/instruments/{instrument_id}",
    response_model=InstrumentIntelligenceRead,
    summary="Analyse an instrument's prices",
    description="Changes, trend, volatility and unusual moves of its stored closing prices, "
    "one analysis per price dataset (datasets are never blended).",
    responses=NOT_FOUND,
)
def get_instrument_intelligence(
    session: SessionDep, instrument_id: InstrumentId, thresholds: ThresholdsDep
) -> InstrumentIntelligenceRead:
    return intelligence.instrument_read(session, instrument_id, thresholds)


# --- Stored analyses ---------------------------------------------------------------------------


@router.post(
    "/analyses",
    response_model=AnalysisRead,
    status_code=status.HTTP_201_CREATED,
    summary="Store an analysis",
    description="Computes an entity or workspace analysis and stores it with its thresholds, "
    "a fingerprint of everything it read and hashes of both. Stored analyses are never "
    "changed or deleted.",
    responses=NOT_FOUND,
)
def create_analysis(
    session: SessionDep, payload: AnalysisRequest, response: Response
) -> AnalysisRead:
    analysis = intelligence.create_analysis(session, payload)
    response.headers["Location"] = f"/api/v1/intelligence/analyses/{analysis.id}"
    return analysis


@router.get(
    "/analyses",
    response_model=AnalysisPage,
    summary="List stored analyses",
    description="Newest first.",
)
def list_analyses(
    session: SessionDep,
    page: PaginationDep,
    scope: Annotated[Scope | None, Query(description="Only this scope.")] = None,
    entity: Annotated[
        str | None, Query(pattern=NODE_KEY_PATTERN, max_length=128, description="An entity.")
    ] = None,
) -> AnalysisPage:
    return intelligence.list_analyses(
        session, scope=scope, entity=entity, limit=page.limit, offset=page.offset
    )


@router.get(
    "/analyses/{analysis_id}",
    response_model=AnalysisRead,
    summary="Get a stored analysis",
    description="The analysis as it was stored, and whether what it read has changed since "
    "(`freshness`).",
    responses=NOT_FOUND,
)
def get_analysis(session: SessionDep, analysis_id: uuid.UUID) -> AnalysisRead:
    return intelligence.get_analysis(session, analysis_id)
