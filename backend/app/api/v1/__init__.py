"""Version 1 of the RUMIN API, mounted at ``/api/v1``."""

from fastapi import APIRouter

from app.api.deps import ERRORS
from app.api.v1 import (
    analyst,
    data,
    graph,
    ingestion,
    intelligence,
    network,
    reference_data,
    scenario_lab,
    scenarios,
    simulations,
    system,
)

router = APIRouter(responses=ERRORS)
router.include_router(reference_data.router)
router.include_router(network.router)
router.include_router(scenarios.router)
router.include_router(scenario_lab.executions_router)
router.include_router(scenario_lab.comparisons_router)
router.include_router(scenario_lab.templates_router)
router.include_router(data.router)
router.include_router(ingestion.router)
router.include_router(graph.router)
router.include_router(simulations.models_router)
router.include_router(simulations.router)
router.include_router(intelligence.router)
router.include_router(analyst.router)
router.include_router(system.router)
