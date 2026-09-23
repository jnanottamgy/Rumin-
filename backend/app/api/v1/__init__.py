"""Version 1 of the RUMIN API, mounted at ``/api/v1``."""

from fastapi import APIRouter

from app.api.deps import ERRORS
from app.api.v1 import network, reference_data, scenarios, system

router = APIRouter(responses=ERRORS)
router.include_router(reference_data.router)
router.include_router(network.router)
router.include_router(scenarios.router)
router.include_router(system.router)
