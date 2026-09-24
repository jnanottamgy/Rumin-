"""Environment-based configuration.

All settings are read from environment variables prefixed with ``RUMIN_`` (or from a
``.env`` file in the repository root). Nothing secret is hard-coded here: the only
defaults are safe local-development values.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent
MIGRATIONS_DIR = BACKEND_DIR / "migrations"
DEFAULT_SQLITE_URL = f"sqlite:///{BACKEND_DIR / 'rumin.db'}"

Environment = Literal["development", "test", "production"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="RUMIN_",
        env_file=(REPO_ROOT / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        # The shared .env file also contains VITE_* and POSTGRES_* variables.
        extra="ignore",
    )

    environment: Environment = "development"
    database_url: str = DEFAULT_SQLITE_URL
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )
    log_level: LogLevel = "INFO"
    docs_enabled: bool = True
    max_request_body_bytes: int = Field(default=64 * 1024, ge=1024, le=10 * 1024 * 1024)

    # --- Data ingestion (Phase 2) ---------------------------------------------------------
    worldbank_base_url: str = "https://api.worldbank.org/v2"
    # Seconds between consecutive requests to the World Bank (RUMIN's own politeness limit).
    worldbank_min_interval_seconds: float = Field(default=1.0, ge=0.1, le=60)
    provider_timeout_seconds: float = Field(default=20.0, ge=1, le=120)
    # Total attempts per request, including the first (so 4 = at most 3 retries).
    provider_max_attempts: int = Field(default=4, ge=1, le=6)
    max_import_file_bytes: int = Field(default=10 * 1024 * 1024, ge=1024, le=100 * 1024 * 1024)
    # Keep the exact bytes of every response and imported file (gzip-compressed).
    store_source_bodies: bool = True

    # --- Scenario Lab (Phase 5) -----------------------------------------------------------
    # "thread": executions run on a bounded pool in the API process; "inline": in the
    # request that creates them (tests).
    scenario_execution_mode: Literal["thread", "inline"] = "thread"
    scenario_max_concurrent: int = Field(default=2, ge=1, le=8)
    # Executions waiting for a worker; beyond this, requests are refused with 429.
    scenario_max_queued: int = Field(default=8, ge=0, le=64)
    scenario_timeout_seconds: float = Field(default=20.0, ge=1, le=120)

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_comma_separated(cls, value: Any) -> Any:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("cors_origins")
    @classmethod
    def _validate_origins(cls, origins: list[str]) -> list[str]:
        cleaned: list[str] = []
        for origin in origins:
            if origin == "*":
                raise ValueError("Wildcard CORS origins are not allowed; list origins explicitly.")
            if not origin.startswith(("http://", "https://")):
                raise ValueError(f"CORS origin must start with http:// or https://: {origin!r}")
            cleaned.append(origin.rstrip("/"))
        return cleaned

    @field_validator("worldbank_base_url")
    @classmethod
    def _validate_provider_url(cls, url: str) -> str:
        # Plain http is allowed only for a local test server; real providers use https.
        local = url.startswith(("http://127.0.0.1", "http://localhost"))
        if not (url.startswith("https://") or local):
            raise ValueError("Provider URLs must use https:// (http:// only for localhost).")
        return url.rstrip("/")

    @field_validator("log_level", mode="before")
    @classmethod
    def _upper_log_level(cls, value: Any) -> Any:
        return value.upper() if isinstance(value, str) else value

    @property
    def database_backend(self) -> str:
        """Short name of the database engine, e.g. ``sqlite`` or ``postgresql``."""
        return self.database_url.split(":", 1)[0].split("+", 1)[0]


@lru_cache
def get_settings() -> Settings:
    return Settings()
