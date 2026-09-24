"""Application factory.

Run locally (from ``backend/``)::

    uvicorn app.main:app --reload --no-access-log
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware import Middleware
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.routing import APIRoute
from sqlalchemy.exc import SQLAlchemyError

from app import API_VERSION, __version__
from app.api import health
from app.api.v1 import router as api_v1_router
from app.core.config import Settings, get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import REQUEST_ID_HEADER, BodySizeLimitMiddleware, RequestContextMiddleware
from app.db.session import create_db_engine, create_session_factory
from app.scenario_lab.runner import ExecutionRunner
from app.services import scenarios

logger = logging.getLogger(__name__)

API_DESCRIPTION = """
RUMIN is an interactive financial intelligence and economic simulation platform.
This API covers the **Phase 1 foundation**, the **Phase 2 financial data
infrastructure**, the **Phase 3 knowledge graph** and the **Phase 4 simulation engine**
(one model, in preview).

### Five kinds of knowledge
RUMIN never blurs these categories; responses label them with `epistemic_category`.

| Category | Meaning | In this build |
|---|---|---|
| `observation` | Historical data from a cited source | World Bank series; licensed price files |
| `assumption` | Rules, parameters and relationships defined by the model | Relationships, ranges |
| `scenario_input` | Values changed by a user | Scenario shocks |
| `simulated_output` | Results computed by a simulation engine | Simulation runs |
| `uncertainty` | Limitations and ranges | Documented qualitatively |

### Data
* The curated **network** dataset is **illustrative**: companies are fictional; countries,
  ISIC Rev. 4 industries and variable definitions are real concepts with references.
* **Provider data** is historical, stored exactly as published and never live. Every value
  carries its period, when RUMIN retrieved it, the stored response it came from and the
  dataset's licence and attribution. Revisions are kept, not overwritten.
* **Numbers are decimal strings** (`"5.649"`) so no digit is lost to floating point.
* Ingestion is started from the command line only; these endpoints are read-only.

### Knowledge graph
* Built from the stored data by `python -m app.graph build`; the graph endpoints are
  read-only and every traversal is bounded (depth, nodes, path length, number of paths).
* Every edge carries an **evidence status** (`evidence_backed`, `analyst_created`,
  `model_assumption`, `unverified`), says whether it is **illustrative**, and lists the
  evidence records that explain why it exists.
* A connection is not evidence of causation. A path shows how records are connected; it
  is not an influence chain, and a shorter path is not a stronger relationship.

### Simulation
* Models are defined in code, **versioned** and stored with a definition hash; a changed
  equation is a new version. Runs are **deterministic** and **append-only**: identical
  inputs give an identical result hash, and `POST /simulations/{id}/verify` re-executes a
  stored run from its snapshot.
* Every input is labelled as historical data, a user input, an assumption, a scenario
  change or a setting. Nothing missing is invented and no unit is converted silently.
* A shock travels only along relationships a model rule accepts **and** the latest graph
  build confirms as validated; other graph edges are listed, never followed.
* Results are calculations under stated assumptions — **not forecasts and not investment
  advice**.

### Errors
Every error response uses one envelope:
`{"error": {"code", "message", "details", "request_id"}}`.
"""

OPENAPI_TAGS = [
    {"name": "health", "description": "Liveness and readiness probes."},
    {"name": "reference data", "description": "Entities, relationships and their types."},
    {"name": "network", "description": "Graph projection for visualisation."},
    {
        "name": "scenarios",
        "description": "Versioned scenarios: every save that changes anything is a new, "
        "immutable version. Plans say which models apply and why; previews compute without "
        "storing.",
    },
    {
        "name": "scenario lab",
        "description": "Executions of scenario versions through the model registry (queued, "
        "bounded, cancellable), their results, pathways, explanations, verification and "
        "sensitivity analyses; comparisons; templates. Executions are append-only.",
    },
    {
        "name": "providers and datasets",
        "description": "Who publishes the data, on what terms, and what is loaded.",
    },
    {"name": "economic series", "description": "Historical series and their observations."},
    {"name": "market data", "description": "Instruments and prices from licensed files."},
    {"name": "ingestion", "description": "What each retrieval or import did (read-only)."},
    {"name": "data quality", "description": "Rules, rejected records and flagged values."},
    {
        "name": "knowledge graph",
        "description": "Entities, relationships and evidence: search, neighbourhoods, "
        "provenance, paths, components, builds and validation issues (read-only, bounded).",
    },
    {
        "name": "simulation",
        "description": "Versioned models, input validation, deterministic runs with "
        "explanations and provenance, re-execution checks and one-at-a-time sensitivity "
        "analysis. Runs are append-only.",
    },
    {"name": "system", "description": "Runtime status and capabilities."},
]


def _operation_id(route: APIRoute) -> str:
    return route.name


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    engine = create_db_engine(settings.database_url)

    session_factory = create_session_factory(engine)
    runner = ExecutionRunner(
        session_factory,
        freshness=scenarios.freshness,
        mode=settings.scenario_execution_mode,
        max_concurrent=settings.scenario_max_concurrent,
        max_queued=settings.scenario_max_queued,
        timeout_seconds=settings.scenario_timeout_seconds,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        logger.info(
            "RUMIN API %s starting (environment=%s, database=%s)",
            __version__,
            settings.environment,
            settings.database_backend,
        )
        try:
            runner.start()
        except SQLAlchemyError:
            # The schema may not be migrated yet; readiness reports it. Executions cannot
            # be requested until it is.
            logger.warning("Scenario executions could not be checked at startup.")
        yield
        runner.stop()
        engine.dispose()

    docs = settings.docs_enabled
    app = FastAPI(
        title="RUMIN API",
        version=__version__,
        summary="Financial intelligence and economic simulation platform.",
        description=API_DESCRIPTION,
        openapi_tags=OPENAPI_TAGS,
        docs_url="/docs" if docs else None,
        redoc_url="/redoc" if docs else None,
        openapi_url="/openapi.json" if docs else None,
        generate_unique_id_function=_operation_id,
        lifespan=lifespan,
        # Listed outermost first: CORS wraps everything so even error responses carry
        # CORS headers; responses over 1 KiB are compressed when the client accepts gzip
        # (a Scenario Lab preview is ~115 KB of JSON); the request context wraps the size
        # limit so 413s get an ID too.
        middleware=[
            Middleware(
                CORSMiddleware,
                allow_origins=settings.cors_origins,
                allow_methods=["GET", "POST", "PUT", "DELETE"],
                allow_headers=["Content-Type", REQUEST_ID_HEADER],
                expose_headers=[REQUEST_ID_HEADER, "Location"],
                allow_credentials=False,
                max_age=600,
            ),
            Middleware(GZipMiddleware, minimum_size=1024),
            Middleware(RequestContextMiddleware),
            Middleware(BodySizeLimitMiddleware, max_bytes=settings.max_request_body_bytes),
        ],
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.scenario_runner = runner

    register_exception_handlers(app)
    app.include_router(health.router)
    app.include_router(api_v1_router, prefix=f"/api/{API_VERSION}")
    return app


app = create_app()
