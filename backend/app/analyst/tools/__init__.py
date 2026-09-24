"""The Analyst's tools (see ``registry.py``): an allowlist of read-only tools over RUMIN's
services, and one compute tool (the scenario preview), which never stores anything."""

from app.analyst.tools.data import COMPARE_PERIODS, GET_FINDINGS, GET_SERIES, LIST_CHANGES
from app.analyst.tools.records import (
    FIND_PATHS,
    GET_DATA_COVERAGE,
    GET_ENTITY_DOSSIER,
    GET_EXPOSURE,
    GET_RELATIONSHIP,
    GET_VARIABLE_REACH,
    LIST_MODELS,
    LIST_TEMPLATES,
    SEARCH_RECORDS,
)
from app.analyst.tools.registry import ToolRegistry
from app.analyst.tools.scenarios import (
    EXPLAIN_LINE,
    GET_EXECUTION,
    LIST_SCENARIOS,
    PREVIEW_SCENARIO,
)

TOOLS = ToolRegistry(
    [
        SEARCH_RECORDS,
        GET_ENTITY_DOSSIER,
        GET_EXPOSURE,
        GET_VARIABLE_REACH,
        FIND_PATHS,
        GET_RELATIONSHIP,
        GET_SERIES,
        COMPARE_PERIODS,
        LIST_CHANGES,
        GET_FINDINGS,
        LIST_SCENARIOS,
        GET_EXECUTION,
        EXPLAIN_LINE,
        PREVIEW_SCENARIO,
        LIST_MODELS,
        LIST_TEMPLATES,
        GET_DATA_COVERAGE,
    ]
)

__all__ = ["TOOLS"]
