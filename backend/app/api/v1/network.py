from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import SessionDep
from app.schemas.network import NetworkResponse
from app.services.network import build_network

router = APIRouter(tags=["network"])


@router.get(
    "/network",
    response_model=NetworkResponse,
    summary="Financial network projection",
    description="All nodes and edges for visualisation: curated economic relationships "
    "plus structural links derived from entity attributes, with degree per node and the "
    "relationship-type registry for legends.",
)
def get_network(session: SessionDep) -> NetworkResponse:
    return build_network(session)
