"""Schemas shared across the API: error envelope, pagination, reusable field types."""

from __future__ import annotations

import re
from typing import Annotated, Generic, Literal, TypeVar

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints

# --- Reusable field types ------------------------------------------------------

ENTITY_ID_PATTERN = r"^[a-z]{2,4}_[a-z0-9_]{2,59}$"
EntityId = Annotated[
    str,
    StringConstraints(pattern=ENTITY_ID_PATTERN, max_length=64),
]

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _reject_control_characters(value: str) -> str:
    # PostgreSQL rejects NUL bytes outright and other control characters are never
    # meaningful in names or notes, so they are refused at the API boundary.
    if _CONTROL_CHARS.search(value):
        raise ValueError("Text must not contain control characters.")
    return value


SafeText = Annotated[str, AfterValidator(_reject_control_characters)]


class ApiModel(BaseModel):
    """Base class for response models."""

    model_config = ConfigDict(from_attributes=True)


class InputModel(BaseModel):
    """Base class for request bodies: unknown fields are rejected, strings are trimmed."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


# --- Error envelope -------------------------------------------------------------

ErrorLocation = Literal["body", "query", "path", "header", "cookie"]


class ErrorDetail(BaseModel):
    location: ErrorLocation | None = Field(
        default=None, description="Part of the request the problem was found in."
    )
    field: str | None = Field(
        default=None,
        description="Path of the offending field, e.g. `shocks[0].value`.",
        examples=["shocks[0].value"],
    )
    message: str
    type: str | None = Field(default=None, description="Machine-readable error type.")


class ErrorBody(BaseModel):
    code: str = Field(description="Stable machine-readable error code.", examples=["not_found"])
    message: str = Field(description="Human-readable summary, safe to display.")
    details: list[ErrorDetail] = Field(default_factory=list)
    request_id: str | None = Field(
        default=None, description="Correlates the error with server logs (X-Request-ID)."
    )


class ErrorResponse(BaseModel):
    """Every non-2xx response from the API uses this envelope."""

    error: ErrorBody


# --- Pagination -----------------------------------------------------------------

DEFAULT_PAGE_LIMIT = 100
MAX_PAGE_LIMIT = 500


ItemT = TypeVar("ItemT")


class Page(BaseModel, Generic[ItemT]):
    items: list[ItemT]
    total: int = Field(ge=0, description="Total number of items matching the query.")
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
