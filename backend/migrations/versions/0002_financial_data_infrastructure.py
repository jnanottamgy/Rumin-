"""Financial data infrastructure: providers, provider datasets, economic series and
observations (with revisions), instruments and price bars, ingestion jobs, source captures
and data-quality issues.

``datasets`` is extended so it can describe provider datasets as well as the curated
reference dataset from Phase 1. Existing rows become ``kind = 'curated'``.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "data_providers",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(
                "api",
                "file",
                name="provider_kind",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("homepage_url", sa.String(length=500), nullable=True),
        sa.Column("documentation_url", sa.String(length=500), nullable=True),
        sa.Column("terms_url", sa.String(length=500), nullable=True),
        sa.Column(
            "authentication",
            sa.Enum(
                "none",
                "api_key",
                "not_applicable",
                name="provider_auth",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("data_categories", sa.Text(), nullable=False),
        sa.Column("coverage", sa.Text(), nullable=False),
        sa.Column("update_frequency", sa.Text(), nullable=False),
        sa.Column("rate_limit_policy", sa.Text(), nullable=False),
        sa.Column("licensing", sa.Text(), nullable=False),
        sa.Column("commercial_use", sa.Text(), nullable=False),
        sa.Column("reliability", sa.Text(), nullable=False),
        sa.Column("known_limitations", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_data_providers")),
    )
    op.create_table(
        "ingestion_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("provider_id", sa.String(length=64), nullable=False),
        sa.Column("dataset_id", sa.String(length=64), nullable=False),
        sa.Column(
            "trigger",
            sa.Enum(
                "cli", name="job_trigger", native_enum=False, create_constraint=True, length=32
            ),
            nullable=False,
        ),
        sa.Column("parameters", sa.JSON(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "running",
                "completed",
                "completed_with_warnings",
                "partially_failed",
                "failed",
                "cancelled",
                name="job_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("items_total", sa.Integer(), nullable=False),
        sa.Column("items_succeeded", sa.Integer(), nullable=False),
        sa.Column("items_failed", sa.Integer(), nullable=False),
        sa.Column("items_skipped", sa.Integer(), nullable=False),
        sa.Column("records_received", sa.Integer(), nullable=False),
        sa.Column("records_new", sa.Integer(), nullable=False),
        sa.Column("records_revised", sa.Integer(), nullable=False),
        sa.Column("records_unchanged", sa.Integer(), nullable=False),
        sa.Column("records_missing", sa.Integer(), nullable=False),
        sa.Column("records_rejected", sa.Integer(), nullable=False),
        sa.Column("warning_count", sa.Integer(), nullable=False),
        sa.Column("error_count", sa.Integer(), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False),
        sa.Column("bytes_received", sa.Integer(), nullable=False),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["datasets.id"],
            name=op.f("fk_ingestion_jobs_dataset_id_datasets"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["provider_id"],
            ["data_providers.id"],
            name=op.f("fk_ingestion_jobs_provider_id_data_providers"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ingestion_jobs")),
    )
    with op.batch_alter_table("ingestion_jobs", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_ingestion_jobs_created_at"), ["created_at"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_ingestion_jobs_dataset_id"), ["dataset_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_ingestion_jobs_provider_id"), ["provider_id"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_ingestion_jobs_status"), ["status"], unique=False)

    op.create_table(
        "source_captures",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("provider_id", sa.String(length=64), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(
                "http_response",
                "file",
                name="capture_kind",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("locator", sa.String(length=1000), nullable=False),
        sa.Column("request_params", sa.JSON(), nullable=True),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("body_gzip", sa.LargeBinary(), nullable=True),
        sa.Column("provider_last_updated", sa.Date(), nullable=True),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["ingestion_jobs.id"],
            name=op.f("fk_source_captures_job_id_ingestion_jobs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["provider_id"],
            ["data_providers.id"],
            name=op.f("fk_source_captures_provider_id_data_providers"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_source_captures")),
    )
    with op.batch_alter_table("source_captures", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_source_captures_job_id"), ["job_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_source_captures_sha256"), ["sha256"], unique=False)

    op.create_table(
        "instruments",
        sa.Column("id", sa.String(length=96), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column(
            "instrument_type",
            sa.Enum(
                "equity",
                "etf",
                "index",
                name="instrument_type",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("isin", sa.String(length=12), nullable=True),
        sa.Column("exchange_mic", sa.String(length=4), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("country_id", sa.String(length=64), nullable=True),
        sa.Column("dataset_id", sa.String(length=64), nullable=False),
        sa.Column("first_trade_date", sa.Date(), nullable=True),
        sa.Column("last_trade_date", sa.Date(), nullable=True),
        sa.Column("bar_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["country_id"],
            ["countries.id"],
            name=op.f("fk_instruments_country_id_countries"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["datasets.id"],
            name=op.f("fk_instruments_dataset_id_datasets"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_instruments")),
        sa.UniqueConstraint(
            "exchange_mic", "symbol", name=op.f("uq_instruments_exchange_mic_symbol")
        ),
        sa.UniqueConstraint("isin", name=op.f("uq_instruments_isin")),
    )
    with op.batch_alter_table("instruments", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_instruments_dataset_id"), ["dataset_id"], unique=False)

    op.create_table(
        "economic_series",
        sa.Column("id", sa.String(length=96), nullable=False),
        sa.Column("dataset_id", sa.String(length=64), nullable=False),
        sa.Column("provider_series_key", sa.String(length=128), nullable=False),
        sa.Column("provider_code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("source_organization", sa.Text(), nullable=True),
        sa.Column(
            "measure_type",
            sa.Enum(
                "level",
                "change",
                "rate",
                "ratio",
                "exchange_rate",
                name="measure_type",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("unit", sa.String(length=100), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column(
            "frequency",
            sa.Enum(
                "daily",
                "weekly",
                "monthly",
                "quarterly",
                "annual",
                "irregular",
                name="frequency",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("aggregation", sa.String(length=200), nullable=False),
        sa.Column(
            "price_basis",
            sa.Enum(
                "nominal",
                "real",
                "not_applicable",
                name="price_basis",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "seasonal_adjustment",
            sa.Enum(
                "seasonally_adjusted",
                "not_seasonally_adjusted",
                "not_applicable",
                name="seasonal_adjustment",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("country_iso3", sa.String(length=3), nullable=True),
        sa.Column("country_id", sa.String(length=64), nullable=True),
        sa.Column("variable_id", sa.String(length=64), nullable=True),
        sa.Column("variable_relation", sa.Text(), nullable=True),
        sa.Column(
            "plausible_min",
            sa.Numeric(precision=38, scale=18).with_variant(sa.String(length=64), "sqlite"),
            nullable=True,
        ),
        sa.Column(
            "plausible_max",
            sa.Numeric(precision=38, scale=18).with_variant(sa.String(length=64), "sqlite"),
            nullable=True,
        ),
        sa.Column("first_period", sa.Date(), nullable=True),
        sa.Column("last_period", sa.Date(), nullable=True),
        sa.Column("observation_count", sa.Integer(), nullable=False),
        sa.Column("missing_count", sa.Integer(), nullable=False),
        sa.Column("last_ingestion_job_id", sa.Uuid(), nullable=True),
        sa.Column(
            "last_ingestion_status",
            sa.Enum(
                "pending",
                "succeeded",
                "failed",
                "skipped",
                name="last_ingestion_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=True,
        ),
        sa.Column("last_ingestion_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_successful_ingestion_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["country_id"],
            ["countries.id"],
            name=op.f("fk_economic_series_country_id_countries"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["datasets.id"],
            name=op.f("fk_economic_series_dataset_id_datasets"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["last_ingestion_job_id"],
            ["ingestion_jobs.id"],
            name=op.f("fk_economic_series_last_ingestion_job_id_ingestion_jobs"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["variable_id"],
            ["economic_variables.id"],
            name=op.f("fk_economic_series_variable_id_economic_variables"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_economic_series")),
        sa.UniqueConstraint(
            "dataset_id",
            "provider_series_key",
            name=op.f("uq_economic_series_dataset_id_provider_series_key"),
        ),
    )
    with op.batch_alter_table("economic_series", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_economic_series_country_id"), ["country_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_economic_series_dataset_id"), ["dataset_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_economic_series_variable_id"), ["variable_id"], unique=False
        )

    op.create_table(
        "price_bars",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("instrument_id", sa.String(length=96), nullable=False),
        sa.Column("dataset_id", sa.String(length=64), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column(
            "open",
            sa.Numeric(precision=38, scale=18).with_variant(sa.String(length=64), "sqlite"),
            nullable=False,
        ),
        sa.Column(
            "high",
            sa.Numeric(precision=38, scale=18).with_variant(sa.String(length=64), "sqlite"),
            nullable=False,
        ),
        sa.Column(
            "low",
            sa.Numeric(precision=38, scale=18).with_variant(sa.String(length=64), "sqlite"),
            nullable=False,
        ),
        sa.Column(
            "close",
            sa.Numeric(precision=38, scale=18).with_variant(sa.String(length=64), "sqlite"),
            nullable=False,
        ),
        sa.Column(
            "adjusted_close",
            sa.Numeric(precision=38, scale=18).with_variant(sa.String(length=64), "sqlite"),
            nullable=True,
        ),
        sa.Column("volume", sa.BigInteger(), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column(
            "adjustment",
            sa.Enum(
                "unadjusted",
                "adjusted",
                name="price_adjustment",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "quality_status",
            sa.Enum(
                "validated",
                "warning",
                name="quality_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("source_row", sa.Integer(), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("superseded_by_job_id", sa.Uuid(), nullable=True),
        sa.Column("first_seen_job_id", sa.Uuid(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_job_id", sa.Uuid(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("capture_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["capture_id"],
            ["source_captures.id"],
            name=op.f("fk_price_bars_capture_id_source_captures"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["datasets.id"],
            name=op.f("fk_price_bars_dataset_id_datasets"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["first_seen_job_id"],
            ["ingestion_jobs.id"],
            name=op.f("fk_price_bars_first_seen_job_id_ingestion_jobs"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["instruments.id"],
            name=op.f("fk_price_bars_instrument_id_instruments"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["last_seen_job_id"],
            ["ingestion_jobs.id"],
            name=op.f("fk_price_bars_last_seen_job_id_ingestion_jobs"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["superseded_by_job_id"],
            ["ingestion_jobs.id"],
            name=op.f("fk_price_bars_superseded_by_job_id_ingestion_jobs"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_price_bars")),
    )
    with op.batch_alter_table("price_bars", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_price_bars_dataset_id"), ["dataset_id"], unique=False)
        batch_op.create_index(
            "ix_price_bars_instrument_date", ["instrument_id", "trade_date"], unique=False
        )
        batch_op.create_index(
            "uq_price_bars_current",
            ["instrument_id", "dataset_id", "trade_date"],
            unique=True,
            sqlite_where=sa.text("superseded_at IS NULL"),
            postgresql_where=sa.text("superseded_at IS NULL"),
        )

    op.create_table(
        "economic_observations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("series_id", sa.String(length=96), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_label", sa.String(length=10), nullable=False),
        sa.Column(
            "value",
            sa.Numeric(precision=38, scale=18).with_variant(sa.String(length=64), "sqlite"),
            nullable=True,
        ),
        sa.Column("raw_value", sa.String(length=64), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "reported",
                "missing",
                name="observation_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "quality_status",
            sa.Enum(
                "validated",
                "warning",
                name="quality_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("provider_flags", sa.String(length=64), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("superseded_by_job_id", sa.Uuid(), nullable=True),
        sa.Column("first_seen_job_id", sa.Uuid(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_job_id", sa.Uuid(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("capture_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["capture_id"],
            ["source_captures.id"],
            name=op.f("fk_economic_observations_capture_id_source_captures"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["first_seen_job_id"],
            ["ingestion_jobs.id"],
            name=op.f("fk_economic_observations_first_seen_job_id_ingestion_jobs"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["last_seen_job_id"],
            ["ingestion_jobs.id"],
            name=op.f("fk_economic_observations_last_seen_job_id_ingestion_jobs"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["series_id"],
            ["economic_series.id"],
            name=op.f("fk_economic_observations_series_id_economic_series"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["superseded_by_job_id"],
            ["ingestion_jobs.id"],
            name=op.f("fk_economic_observations_superseded_by_job_id_ingestion_jobs"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_economic_observations")),
    )
    with op.batch_alter_table("economic_observations", schema=None) as batch_op:
        batch_op.create_index(
            "ix_economic_observations_series_period", ["series_id", "period_start"], unique=False
        )
        batch_op.create_index(
            "uq_economic_observations_current",
            ["series_id", "period_start"],
            unique=True,
            sqlite_where=sa.text("superseded_at IS NULL"),
            postgresql_where=sa.text("superseded_at IS NULL"),
        )

    op.create_table(
        "ingestion_job_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column(
            "target_kind",
            sa.Enum(
                "economic_series",
                "instrument",
                name="job_target_kind",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("series_id", sa.String(length=96), nullable=True),
        sa.Column("instrument_id", sa.String(length=96), nullable=True),
        sa.Column("target_label", sa.String(length=300), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "succeeded",
                "failed",
                "skipped",
                name="job_item_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("records_received", sa.Integer(), nullable=False),
        sa.Column("records_new", sa.Integer(), nullable=False),
        sa.Column("records_revised", sa.Integer(), nullable=False),
        sa.Column("records_unchanged", sa.Integer(), nullable=False),
        sa.Column("records_missing", sa.Integer(), nullable=False),
        sa.Column("records_rejected", sa.Integer(), nullable=False),
        sa.Column("warning_count", sa.Integer(), nullable=False),
        sa.Column("error_count", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["instruments.id"],
            name=op.f("fk_ingestion_job_items_instrument_id_instruments"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["ingestion_jobs.id"],
            name=op.f("fk_ingestion_job_items_job_id_ingestion_jobs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["series_id"],
            ["economic_series.id"],
            name=op.f("fk_ingestion_job_items_series_id_economic_series"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ingestion_job_items")),
    )
    with op.batch_alter_table("ingestion_job_items", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_ingestion_job_items_instrument_id"), ["instrument_id"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_ingestion_job_items_job_id"), ["job_id"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_ingestion_job_items_series_id"), ["series_id"], unique=False
        )

    op.create_table(
        "data_quality_issues",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("series_id", sa.String(length=96), nullable=True),
        sa.Column("instrument_id", sa.String(length=96), nullable=True),
        sa.Column("observation_id", sa.Integer(), nullable=True),
        sa.Column("price_bar_id", sa.Integer(), nullable=True),
        sa.Column("rule", sa.String(length=64), nullable=False),
        sa.Column(
            "severity",
            sa.Enum(
                "error",
                "warning",
                "info",
                name="issue_severity",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "outcome",
            sa.Enum(
                "rejected",
                "flagged",
                "noted",
                name="issue_outcome",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("record_key", sa.String(length=32), nullable=True),
        sa.Column("raw_record", sa.JSON(), nullable=True),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "review_status",
            sa.Enum(
                "unreviewed",
                name="review_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["instruments.id"],
            name=op.f("fk_data_quality_issues_instrument_id_instruments"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["ingestion_jobs.id"],
            name=op.f("fk_data_quality_issues_job_id_ingestion_jobs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["observation_id"],
            ["economic_observations.id"],
            name=op.f("fk_data_quality_issues_observation_id_economic_observations"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["price_bar_id"],
            ["price_bars.id"],
            name=op.f("fk_data_quality_issues_price_bar_id_price_bars"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["series_id"],
            ["economic_series.id"],
            name=op.f("fk_data_quality_issues_series_id_economic_series"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_data_quality_issues")),
    )
    with op.batch_alter_table("data_quality_issues", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_data_quality_issues_instrument_id"), ["instrument_id"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_data_quality_issues_job_id"), ["job_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_data_quality_issues_rule"), ["rule"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_data_quality_issues_series_id"), ["series_id"], unique=False
        )

    with op.batch_alter_table("datasets", schema=None) as batch_op:
        # Plain VARCHAR plus explicitly named CHECK constraints (below): the implicit
        # constraint of an Enum added with add_column is not created on every database.
        batch_op.add_column(
            sa.Column("kind", sa.String(length=32), server_default="curated", nullable=False)
        )
        batch_op.add_column(sa.Column("provider_id", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("provider_dataset_code", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("homepage_url", sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column("license_url", sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column("terms_url", sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column("attribution", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("update_frequency", sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column("provider_last_updated", sa.Date(), nullable=True))
        batch_op.alter_column("checksum_sha256", existing_type=sa.VARCHAR(length=64), nullable=True)
        batch_op.create_index(batch_op.f("ix_datasets_provider_id"), ["provider_id"], unique=False)
        batch_op.create_foreign_key(
            batch_op.f("fk_datasets_provider_id_data_providers"),
            "data_providers",
            ["provider_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch_op.create_check_constraint(
            batch_op.f("ck_datasets_dataset_kind"), "kind IN ('curated', 'provider')"
        )
        batch_op.create_check_constraint(
            batch_op.f("ck_datasets_kind_requirements"),
            "(kind = 'curated' AND checksum_sha256 IS NOT NULL) OR "
            "(kind = 'provider' AND provider_id IS NOT NULL)",
        )


def downgrade() -> None:
    # Provider datasets cannot exist in the Phase 1 schema.
    op.execute("DELETE FROM datasets WHERE kind <> 'curated'")
    with op.batch_alter_table("datasets", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f("ck_datasets_kind_requirements"), type_="check")
        batch_op.drop_constraint(batch_op.f("ck_datasets_dataset_kind"), type_="check")
        batch_op.drop_constraint(
            batch_op.f("fk_datasets_provider_id_data_providers"), type_="foreignkey"
        )
        batch_op.drop_index(batch_op.f("ix_datasets_provider_id"))
        batch_op.alter_column(
            "checksum_sha256", existing_type=sa.VARCHAR(length=64), nullable=False
        )
        batch_op.drop_column("provider_last_updated")
        batch_op.drop_column("update_frequency")
        batch_op.drop_column("attribution")
        batch_op.drop_column("terms_url")
        batch_op.drop_column("license_url")
        batch_op.drop_column("homepage_url")
        batch_op.drop_column("provider_dataset_code")
        batch_op.drop_column("provider_id")
        batch_op.drop_column("kind")

    with op.batch_alter_table("data_quality_issues", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_data_quality_issues_series_id"))
        batch_op.drop_index(batch_op.f("ix_data_quality_issues_rule"))
        batch_op.drop_index(batch_op.f("ix_data_quality_issues_job_id"))
        batch_op.drop_index(batch_op.f("ix_data_quality_issues_instrument_id"))

    op.drop_table("data_quality_issues")
    with op.batch_alter_table("ingestion_job_items", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_ingestion_job_items_series_id"))
        batch_op.drop_index(batch_op.f("ix_ingestion_job_items_job_id"))
        batch_op.drop_index(batch_op.f("ix_ingestion_job_items_instrument_id"))

    op.drop_table("ingestion_job_items")
    with op.batch_alter_table("economic_observations", schema=None) as batch_op:
        batch_op.drop_index(
            "uq_economic_observations_current",
            sqlite_where=sa.text("superseded_at IS NULL"),
            postgresql_where=sa.text("superseded_at IS NULL"),
        )
        batch_op.drop_index("ix_economic_observations_series_period")

    op.drop_table("economic_observations")
    with op.batch_alter_table("price_bars", schema=None) as batch_op:
        batch_op.drop_index(
            "uq_price_bars_current",
            sqlite_where=sa.text("superseded_at IS NULL"),
            postgresql_where=sa.text("superseded_at IS NULL"),
        )
        batch_op.drop_index("ix_price_bars_instrument_date")
        batch_op.drop_index(batch_op.f("ix_price_bars_dataset_id"))

    op.drop_table("price_bars")
    with op.batch_alter_table("economic_series", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_economic_series_variable_id"))
        batch_op.drop_index(batch_op.f("ix_economic_series_dataset_id"))
        batch_op.drop_index(batch_op.f("ix_economic_series_country_id"))

    op.drop_table("economic_series")
    with op.batch_alter_table("instruments", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_instruments_dataset_id"))

    op.drop_table("instruments")
    with op.batch_alter_table("source_captures", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_source_captures_sha256"))
        batch_op.drop_index(batch_op.f("ix_source_captures_job_id"))

    op.drop_table("source_captures")
    with op.batch_alter_table("ingestion_jobs", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_ingestion_jobs_status"))
        batch_op.drop_index(batch_op.f("ix_ingestion_jobs_provider_id"))
        batch_op.drop_index(batch_op.f("ix_ingestion_jobs_dataset_id"))
        batch_op.drop_index(batch_op.f("ix_ingestion_jobs_created_at"))

    op.drop_table("ingestion_jobs")
    op.drop_table("data_providers")
