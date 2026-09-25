"""Environment-based configuration.

All settings are read from environment variables prefixed with ``RUMIN_`` (or from a
``.env`` file in the repository root). Nothing secret is hard-coded here: the only
defaults are safe local-development values.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent
MIGRATIONS_DIR = BACKEND_DIR / "migrations"
DEFAULT_SQLITE_URL = f"sqlite:///{BACKEND_DIR / 'rumin.db'}"

Environment = Literal["development", "test", "production"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]


LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


def secure_url(url: str) -> bool:
    """Whether ``url`` is an https URL, or plain http to this machine only (a local test
    server): the host is parsed, so ``http://localhost.example.com`` or
    ``http://localhost@example.com`` are not local."""
    try:
        parts = urlsplit(url)
        host = parts.hostname
        parts.port  # noqa: B018 - raises on a malformed port
    except ValueError:
        return False
    if not host or parts.username is not None or parts.password is not None:
        return False
    if parts.scheme == "https":
        return True
    return parts.scheme == "http" and host in LOCAL_HOSTS


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

    # --- AI Analyst (Phase 7) -------------------------------------------------------------
    # "grounded": RUMIN's own composer, no language model (the default, and the fallback).
    # "anthropic": a Claude model through the official SDK; needs a key and a model.
    analyst_provider: Literal["grounded", "anthropic"] = "grounded"
    # Read only from RUMIN_ settings: the SDK is never left to find ANTHROPIC_* variables.
    anthropic_api_key: SecretStr | None = None
    anthropic_base_url: str = "https://api.anthropic.com"
    # The model is configuration: no model identifier is written in the code.
    analyst_model: str | None = Field(default=None, max_length=100)
    analyst_thinking: Literal["adaptive", "off"] = "adaptive"
    analyst_max_tokens: int = Field(default=4096, ge=512, le=32000)
    analyst_request_timeout_seconds: float = Field(default=60.0, ge=5, le=300)
    analyst_max_retries: int = Field(default=2, ge=0, le=5)
    analyst_max_model_requests: int = Field(default=6, ge=1, le=12)
    # Input + output tokens a day across all turns; beyond it, the grounded composer answers.
    analyst_daily_token_budget: int = Field(default=2_000_000, ge=0)
    analyst_deadline_seconds: float = Field(default=90.0, ge=5, le=300)
    analyst_max_tool_calls: int = Field(default=12, ge=1, le=32)
    analyst_max_question_chars: int = Field(default=2000, ge=100, le=8000)
    analyst_max_turns_per_session: int = Field(default=200, ge=1, le=1000)
    analyst_execution_mode: Literal["thread", "inline"] = "thread"
    analyst_max_concurrent: int = Field(default=2, ge=1, le=8)
    analyst_max_queued: int = Field(default=8, ge=0, le=64)

    # --- Accounts and sessions (Phase 10) --------------------------------------------------
    session_cookie_name: str = Field(default="rumin_session", pattern=r"^[A-Za-z0-9_\-]{1,64}$")
    # Secure cookies travel only over https. Unset: on in production, off otherwise (local
    # http development). Production refuses an explicit false.
    session_cookie_secure: bool | None = None
    # A session ends after this long without a request, and in any case after the maximum.
    session_idle_minutes: int = Field(default=120, ge=5, le=24 * 60)
    session_max_hours: int = Field(default=12, ge=1, le=24 * 14)
    # Consecutive failed sign-ins before an account is locked; the lock starts at one
    # minute and doubles with each further failure, up to the maximum.
    login_max_failures: int = Field(default=5, ge=3, le=20)
    login_lock_max_minutes: int = Field(default=15, ge=1, le=24 * 60)
    # Failed sign-ins from one client address within the window before it must wait.
    login_client_max_failures: int = Field(default=20, ge=5, le=1000)
    login_client_window_seconds: int = Field(default=600, ge=60, le=24 * 3600)
    # Who may read GET /metrics without signing in: nobody unless listed (an internal
    # scraper's address, e.g. 127.0.0.1). Administrators can always read it.
    metrics_allowed_clients: Annotated[list[str], NoDecode] = Field(default_factory=list)
    # "text" (human-readable) or "json" (one object per line, for log collectors).
    log_format: Literal["text", "json"] = "text"

    @field_validator("cors_origins", "metrics_allowed_clients", mode="before")
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
        if not secure_url(url):
            raise ValueError("Provider URLs must use https:// (http:// only for localhost).")
        return url.rstrip("/")

    @field_validator("anthropic_base_url")
    @classmethod
    def _validate_anthropic_url(cls, url: str) -> str:
        if not secure_url(url):
            raise ValueError(
                "RUMIN_ANTHROPIC_BASE_URL must use https:// (http:// only for localhost)."
            )
        return url.rstrip("/")

    @field_validator("analyst_model")
    @classmethod
    def _blank_model_is_none(cls, value: str | None) -> str | None:
        return value.strip() or None if isinstance(value, str) else value

    @property
    def analyst_ready(self) -> tuple[bool, str | None]:
        """Whether the configured provider can run, and why not."""
        if self.analyst_provider == "grounded":
            return True, None
        missing = [
            name
            for name, value in (
                ("RUMIN_ANTHROPIC_API_KEY", self.anthropic_api_key),
                ("RUMIN_ANALYST_MODEL", self.analyst_model),
            )
            if not value
        ]
        if missing:
            return False, f"{' and '.join(missing)} {'is' if len(missing) == 1 else 'are'} not set."
        return True, None

    @field_validator("log_level", mode="before")
    @classmethod
    def _upper_log_level(cls, value: Any) -> Any:
        return value.upper() if isinstance(value, str) else value

    @model_validator(mode="after")
    def _production_is_not_development(self) -> Settings:
        """Refuse to run in production on development defaults (Phase 10)."""
        if self.environment != "production":
            return self
        if "docs_enabled" not in self.model_fields_set:
            self.docs_enabled = False
        problems = production_problems(self)
        if problems:
            raise ValueError(
                "Unsafe production configuration: "
                + " ".join(problems)
                + " See docs/operations.md."
            )
        return self

    @property
    def cookie_secure(self) -> bool:
        if self.session_cookie_secure is not None:
            return self.session_cookie_secure
        return self.environment == "production"

    @property
    def database_backend(self) -> str:
        """Short name of the database engine, e.g. ``sqlite`` or ``postgresql``."""
        return self.database_url.split(":", 1)[0].split("+", 1)[0]


def production_problems(settings: Settings) -> list[str]:
    """What stops ``settings`` from being a safe production configuration."""
    problems: list[str] = []
    if settings.database_backend != "postgresql":
        problems.append("RUMIN_DATABASE_URL must point at PostgreSQL (SQLite is for development).")
    local = [origin for origin in settings.cors_origins if urlsplit(origin).hostname in LOCAL_HOSTS]
    if local:
        problems.append(
            f"RUMIN_CORS_ORIGINS lists local development origins ({', '.join(local)}); list the "
            "origins the web app is served from, or none when it shares the API's origin."
        )
    if settings.session_cookie_secure is False:
        problems.append("RUMIN_SESSION_COOKIE_SECURE must not be false: sessions need https.")
    insecure = [origin for origin in settings.cors_origins if origin.startswith("http://")]
    if insecure:
        problems.append(f"RUMIN_CORS_ORIGINS must use https:// ({', '.join(insecure)}).")
    return problems


@lru_cache
def get_settings() -> Settings:
    return Settings()
