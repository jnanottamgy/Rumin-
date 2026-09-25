"""Version 1 of the RUMIN API, mounted at ``/api/v1``.

Since Phase 10 every route needs a signed-in session whose password is the person's own,
except signing in and out and the session routes in ``auth``. Roles and ownership are checked
by each route on top of that.
"""

from fastapi import APIRouter, Depends

from app.api.deps import ERRORS, SIGNED_IN, active_principal
from app.api.v1 import (
    analyst,
    auth,
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
    users,
)

router = APIRouter(responses=ERRORS)
router.include_router(auth.router)

protected = APIRouter(dependencies=[Depends(active_principal)], responses=SIGNED_IN)
protected.include_router(reference_data.router)
protected.include_router(network.router)
protected.include_router(scenarios.router)
protected.include_router(scenario_lab.executions_router)
protected.include_router(scenario_lab.comparisons_router)
protected.include_router(scenario_lab.templates_router)
protected.include_router(data.router)
protected.include_router(ingestion.router)
protected.include_router(graph.router)
protected.include_router(simulations.models_router)
protected.include_router(simulations.router)
protected.include_router(intelligence.router)
protected.include_router(analyst.router)
protected.include_router(system.router)
protected.include_router(users.router)
router.include_router(protected)
