"""Which providers exist, and how to build them from settings."""

from __future__ import annotations

from app.core.config import Settings
from app.ingestion.http import HttpClient, RateLimiter, RetryPolicy, UrllibTransport
from app.ingestion.providers import price_file, worldbank
from app.ingestion.providers.base import ProviderProfile
from app.ingestion.providers.price_file import PriceFileProvider
from app.ingestion.providers.worldbank import WorldBankProvider

PROFILES: dict[str, ProviderProfile] = {
    profile.id: profile for profile in (worldbank.PROFILE, price_file.PROFILE)
}


def build_worldbank(settings: Settings) -> WorldBankProvider:
    client = HttpClient(
        transport=UrllibTransport(),
        limiter=RateLimiter(settings.worldbank_min_interval_seconds),
        policy=RetryPolicy(max_attempts=settings.provider_max_attempts),
        timeout=settings.provider_timeout_seconds,
        provider=worldbank.PROFILE.id,
    )
    return WorldBankProvider(client, base_url=settings.worldbank_base_url)


def build_price_file(settings: Settings) -> PriceFileProvider:
    return PriceFileProvider(max_bytes=settings.max_import_file_bytes)
