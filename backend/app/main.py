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
from fastapi.routing import APIRoute

from app import API_VERSION, __version__
from app.api import health
from app.api.v1 import router as api_v1_router
from app.core.config import Settings, get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import REQUEST_ID_HEADER, BodySizeLimitMiddleware, RequestContextMiddleware
from app.db.session import create_db_engine, create_session_factory

logger = logging.getLogger(__name__)

API_DESCRIPTION = """
RUMIN is an interactive financial intelligence and economic simulation platform.
This is the **Phase 1 foundation** of its API.

### Five kinds of knowledge
RUMIN never blurs these categories; responses label them with `epistemic_category`.

| Category | Meaning | In this build |
|---|---|---|
| `observation` | Historical data from a cited source | None stored yet (Phase 2) |
| `assumption` | Rules, parameters and relationships defined by the model | Every relationship |
| `scenario_input` | Values changed by a user | Scenario shocks |
| `simulated_output` | Results computed by a simulation engine | None: no engine yet (Phase 4) |
| `uncertainty` | Limitations and ranges | Documented qualitatively |

### Sample data
The loaded dataset is **illustrative**. Companies are fictional; countries, ISIC Rev. 4
industries and economic-variable definitions are real concepts with references. The
dataset contains no prices, financial figures or time series.

### Errors
Every error response uses one envelope:
`{"error": {"code", "message", "details", "request_id"}}`.
"""

OPENAPI_TAGS = [
    {"name": "health", "description": "Liveness and readiness probes."},
    {"name": "reference data", "description": "Entities, relationships and their types."},
    {"name": "network", "description": "Graph projection for visualisation."},
    {"name": "scenarios", "description": "Draft scenario inputs. Nothing is simulated."},
    {"name": "system", "description": "Runtime status and capabilities."},
]


def _operation_id(route: APIRoute) -> str:
    return route.name


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    engine = create_db_engine(settings.database_url)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        logger.info(
            "RUMIN API %s starting (environment=%s, database=%s)",
            __version__,
            settings.environment,
            settings.database_backend,
        )
        yield
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
        # CORS headers; the request context wraps the size limit so 413s get an ID too.
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
            Middleware(RequestContextMiddleware),
            Middleware(BodySizeLimitMiddleware, max_bytes=settings.max_request_body_bytes),
        ],
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)

    register_exception_handlers(app)
    app.include_router(health.router)
    app.include_router(api_v1_router, prefix=f"/api/{API_VERSION}")
    return app


app = create_app()
