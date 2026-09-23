"""Initial schema: datasets, entities (joined inheritance), relationships, scenarios.

Revision ID: 0001
Revises: (none)
Create Date: 2026-09-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "datasets",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("is_illustrative", sa.Boolean(), nullable=False),
        sa.Column("provenance_note", sa.Text(), nullable=False),
        sa.Column("license", sa.String(length=200), nullable=False),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("loaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_datasets")),
    )
    op.create_table(
        "scenarios",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "draft",
                name="scenario_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_scenarios")),
    )
    op.create_table(
        "entities",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(
                "company",
                "industry",
                "country",
                "economic_variable",
                name="entity_kind",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("is_fictional", sa.Boolean(), nullable=False),
        sa.Column("reference", sa.String(length=500), nullable=True),
        sa.Column("reference_url", sa.String(length=500), nullable=True),
        sa.Column("attributes", sa.JSON(), nullable=False),
        sa.Column("dataset_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["datasets.id"],
            name=op.f("fk_entities_dataset_id_datasets"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_entities")),
    )
    with op.batch_alter_table("entities", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_entities_dataset_id"), ["dataset_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_entities_kind"), ["kind"], unique=False)

    op.create_table(
        "countries",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("iso_alpha2", sa.String(length=2), nullable=False),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.ForeignKeyConstraint(
            ["id"], ["entities.id"], name=op.f("fk_countries_id_entities"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_countries")),
        sa.UniqueConstraint("iso_alpha2", name=op.f("uq_countries_iso_alpha2")),
    )
    op.create_table(
        "industries",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("classification_system", sa.String(length=32), nullable=False),
        sa.Column("classification_code", sa.String(length=16), nullable=False),
        sa.ForeignKeyConstraint(
            ["id"], ["entities.id"], name=op.f("fk_industries_id_entities"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_industries")),
    )
    op.create_table(
        "relationships",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column(
            "type",
            sa.Enum(
                "supplies_to",
                "lends_to",
                "competes_with",
                "affects_costs",
                "affects_revenue",
                "affects_financing",
                "influences",
                name="relationship_type",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("source_id", sa.String(length=64), nullable=False),
        sa.Column("target_id", sa.String(length=64), nullable=False),
        sa.Column(
            "polarity",
            sa.Enum(
                "positive",
                "negative",
                "mixed",
                "not_applicable",
                name="polarity",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "strength",
            sa.Enum(
                "weak",
                "moderate",
                "strong",
                name="strength",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "evidence_level",
            sa.Enum(
                "illustrative",
                "documented",
                "estimated",
                "validated",
                name="evidence_level",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("reference", sa.String(length=500), nullable=True),
        sa.Column("dataset_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("source_id <> target_id", name=op.f("ck_relationships_no_self_loop")),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["datasets.id"],
            name=op.f("fk_relationships_dataset_id_datasets"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["entities.id"],
            name=op.f("fk_relationships_source_id_entities"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["target_id"],
            ["entities.id"],
            name=op.f("fk_relationships_target_id_entities"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_relationships")),
        sa.UniqueConstraint(
            "type", "source_id", "target_id", name=op.f("uq_relationships_type_source_id_target_id")
        ),
    )
    with op.batch_alter_table("relationships", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_relationships_dataset_id"), ["dataset_id"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_relationships_source_id"), ["source_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_relationships_target_id"), ["target_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_relationships_type"), ["type"], unique=False)

    op.create_table(
        "companies",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("industry_id", sa.String(length=64), nullable=False),
        sa.Column("country_id", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(
            ["country_id"],
            ["countries.id"],
            name=op.f("fk_companies_country_id_countries"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["id"], ["entities.id"], name=op.f("fk_companies_id_entities"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["industry_id"],
            ["industries.id"],
            name=op.f("fk_companies_industry_id_industries"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_companies")),
    )
    with op.batch_alter_table("companies", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_companies_country_id"), ["country_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_companies_industry_id"), ["industry_id"], unique=False)

    op.create_table(
        "economic_variables",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("unit", sa.String(length=64), nullable=False),
        sa.Column(
            "value_kind",
            sa.Enum(
                "price",
                "rate",
                "exchange_rate",
                "index",
                name="value_kind",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
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
        sa.Column(
            "category",
            sa.Enum(
                "commodity",
                "monetary_policy",
                "exchange_rate",
                "inflation",
                name="variable_category",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("country_id", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(
            ["country_id"],
            ["countries.id"],
            name=op.f("fk_economic_variables_country_id_countries"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["id"],
            ["entities.id"],
            name=op.f("fk_economic_variables_id_entities"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_economic_variables")),
    )
    with op.batch_alter_table("economic_variables", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_economic_variables_country_id"), ["country_id"], unique=False
        )

    op.create_table(
        "scenario_shocks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("scenario_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("variable_id", sa.String(length=64), nullable=False),
        sa.Column(
            "change_type",
            sa.Enum(
                "percent_change",
                "absolute_change",
                name="change_type",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("value", sa.Numeric(precision=14, scale=4, asdecimal=False), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["scenario_id"],
            ["scenarios.id"],
            name=op.f("fk_scenario_shocks_scenario_id_scenarios"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["variable_id"],
            ["economic_variables.id"],
            name=op.f("fk_scenario_shocks_variable_id_economic_variables"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_scenario_shocks")),
        sa.UniqueConstraint(
            "scenario_id", "variable_id", name=op.f("uq_scenario_shocks_scenario_id_variable_id")
        ),
    )
    with op.batch_alter_table("scenario_shocks", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_scenario_shocks_scenario_id"), ["scenario_id"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("scenario_shocks", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_scenario_shocks_scenario_id"))

    op.drop_table("scenario_shocks")
    with op.batch_alter_table("economic_variables", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_economic_variables_country_id"))

    op.drop_table("economic_variables")
    with op.batch_alter_table("companies", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_companies_industry_id"))
        batch_op.drop_index(batch_op.f("ix_companies_country_id"))

    op.drop_table("companies")
    with op.batch_alter_table("relationships", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_relationships_type"))
        batch_op.drop_index(batch_op.f("ix_relationships_target_id"))
        batch_op.drop_index(batch_op.f("ix_relationships_source_id"))
        batch_op.drop_index(batch_op.f("ix_relationships_dataset_id"))

    op.drop_table("relationships")
    op.drop_table("industries")
    op.drop_table("countries")
    with op.batch_alter_table("entities", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_entities_kind"))
        batch_op.drop_index(batch_op.f("ix_entities_dataset_id"))

    op.drop_table("entities")
    op.drop_table("scenarios")
    op.drop_table("datasets")
