"""Response schemas for financial entities (a discriminated union on ``kind``)."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, computed_field

from app.domain.enums import ChangeType, EntityKind, Frequency, ValueKind, VariableCategory
from app.domain.scenario_rules import change_rules_for
from app.schemas.common import ApiModel, Page


class EntityBase(ApiModel):
    id: str
    name: str
    description: str
    is_fictional: bool = Field(description="True for invented entities (all sample companies).")
    reference: str | None = Field(description="Citation for the entity's definition.")
    reference_url: str | None
    attributes: dict[str, str | bool | int | float]
    dataset_id: str = Field(description="Dataset the record was loaded from (provenance).")


class CompanyRead(EntityBase):
    kind: Literal[EntityKind.COMPANY]
    industry_id: str
    country_id: str


class IndustryRead(EntityBase):
    kind: Literal[EntityKind.INDUSTRY]
    classification_system: str = Field(examples=["ISIC Rev. 4"])
    classification_code: str = Field(examples=["51"])


class CountryRead(EntityBase):
    kind: Literal[EntityKind.COUNTRY]
    iso_alpha2: str
    currency_code: str


class ChangeRuleRead(ApiModel):
    """A kind of scenario change a variable accepts, with its input limits."""

    change_type: ChangeType
    minimum: float
    maximum: float
    minimum_exclusive: bool
    unit_label: str = Field(examples=["%", "percentage points", "USD per barrel"])


class EconomicVariableRead(EntityBase):
    kind: Literal[EntityKind.ECONOMIC_VARIABLE]
    unit: str
    value_kind: ValueKind
    frequency: Frequency
    category: VariableCategory
    country_id: str | None = Field(description="Economy described; null for global benchmarks.")

    @computed_field(  # type: ignore[prop-decorator]
        description="Which scenario changes this variable accepts, and the enforced limits."
    )
    @property
    def scenario_rules(self) -> list[ChangeRuleRead]:
        return [
            ChangeRuleRead.model_validate(rule, from_attributes=True)
            for rule in change_rules_for(self.value_kind, self.unit)
        ]


EntityRead = Annotated[
    CompanyRead | IndustryRead | CountryRead | EconomicVariableRead,
    Field(discriminator="kind"),
]


class EntityPage(Page[EntityRead]):
    """A page of entities."""


class IndustryPage(Page[IndustryRead]):
    """A page of industries."""


class EconomicVariablePage(Page[EconomicVariableRead]):
    """A page of economic variables."""
