"""Construction rules: which field of which record states which node or edge.

An edge exists only because a specific field of a specific record states the
relationship. Appearing in the same dataset, table or file never creates one. Each rule
is registered below with what it reads, what it produces and the evidence status it
assigns, so the API and the documentation can show exactly why an edge exists.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime

from app.domain.enums import (
    DatasetKind,
    Derivation,
    EvidenceLevel,
    EvidenceSourceKind,
    EvidenceStatus,
    GraphEdgeType,
    GraphNodeType,
    IdentifierScheme,
    NodeNature,
)
from app.graph import isic
from app.graph.drafts import (
    EdgeDraft,
    EvidenceDraft,
    IdentifierClaim,
    IssueDraft,
    NodeDraft,
    SourceRef,
    node_key,
)
from app.graph.sources import InstrumentRecord, SeriesRecord, SourceSnapshot
from app.graph.validation import issue


@dataclass(frozen=True)
class ConstructionRule:
    code: str
    name: str
    reads: str
    produces: str
    evidence_status: EvidenceStatus | None
    description: str


_EB = EvidenceStatus.EVIDENCE_BACKED
_AC = EvidenceStatus.ANALYST_CREATED
_MA = EvidenceStatus.MODEL_ASSUMPTION
_UV = EvidenceStatus.UNVERIFIED

CONSTRUCTION_RULES: dict[str, ConstructionRule] = {
    rule.name: rule
    for rule in (
        ConstructionRule(
            "N01", "country", "countries", "country node", None, "One node per country record."
        ),
        ConstructionRule(
            "N02",
            "currency",
            "countries.currency_code, economic_series.currency, instruments.currency",
            "currency node",
            None,
            "One node per ISO 4217 code named by any record; records naming the same code "
            "are linked to the same node.",
        ),
        ConstructionRule(
            "N03",
            "sector",
            "industries.classification_code + the ISIC Rev. 4 structure",
            "sector node",
            None,
            "One node per ISIC Rev. 4 section that contains an industry's division.",
        ),
        ConstructionRule(
            "N04", "industry", "industries", "industry node", None, "One node per industry record."
        ),
        ConstructionRule(
            "N05", "company", "companies", "company node", None, "One node per company record."
        ),
        ConstructionRule(
            "N06",
            "economic_variable",
            "economic_variables",
            "economic variable node",
            None,
            "One node per variable definition.",
        ),
        ConstructionRule(
            "N07",
            "data_series",
            "economic_series",
            "data series node",
            None,
            "One node per catalogued series, whether or not values have been retrieved.",
        ),
        ConstructionRule(
            "N08",
            "instrument",
            "instruments",
            "instrument node",
            None,
            "One node per imported instrument.",
        ),
        ConstructionRule(
            "N09",
            "market",
            "instruments.exchange_mic",
            "market node",
            None,
            "One node per ISO 10383 MIC declared in a price-file manifest.",
        ),
        ConstructionRule(
            "R01",
            "curated_relationship",
            "relationships",
            "an edge of the relationship's own type",
            _MA,
            "Each curated relationship becomes an edge of the same type, keeping its "
            "description, rationale, assumed polarity and illustrative strength.",
        ),
        ConstructionRule(
            "R02",
            "company_industry",
            "companies.industry_id",
            "in_industry",
            _AC,
            "A company's primary industry, as written in its record.",
        ),
        ConstructionRule(
            "R03",
            "company_country",
            "companies.country_id",
            "domiciled_in",
            _AC,
            "A company's country of domicile, as written in its record.",
        ),
        ConstructionRule(
            "R04",
            "variable_country",
            "economic_variables.country_id",
            "measured_for",
            _AC,
            "The economy a variable describes, as written in its definition.",
        ),
        ConstructionRule(
            "R05",
            "industry_sector",
            "industries.classification_code",
            "in_sector",
            _EB,
            "An ISIC Rev. 4 division belongs to the section whose division range contains it.",
        ),
        ConstructionRule(
            "R06",
            "country_currency",
            "countries.currency_code",
            "has_currency",
            _EB,
            "A country's ISO 4217 currency, as cited in its record.",
        ),
        ConstructionRule(
            "R07",
            "series_country",
            "economic_series.country_id, economic_series.country_iso3",
            "covers",
            _EB,
            "The country a series describes: its catalogue link, or else its ISO alpha-3 "
            "code when that code already identifies exactly one country node.",
        ),
        ConstructionRule(
            "R08",
            "series_variable",
            "economic_series.variable_id, economic_series.variable_relation",
            "related_measure_of",
            _AC,
            "A curator's link from a series to a variable, kept with the stated difference.",
        ),
        ConstructionRule(
            "R09",
            "series_currency",
            "economic_series.currency",
            "expressed_in",
            _EB,
            "The currency of a series' unit.",
        ),
        ConstructionRule(
            "R10",
            "instrument_market",
            "instruments.exchange_mic",
            "listed_on",
            _UV,
            "The market declared for an instrument in its price-file manifest.",
        ),
        ConstructionRule(
            "R11",
            "instrument_currency",
            "instruments.currency",
            "quoted_in",
            _UV,
            "The currency declared for an instrument's prices in its manifest.",
        ),
        ConstructionRule(
            "R12",
            "instrument_country",
            "instruments.country_id",
            "associated_with",
            _UV,
            "The country a manifest links an instrument to (the manifest does not say how).",
        ),
    )
}


def rule_label(name: str) -> str:
    rule = CONSTRUCTION_RULES[name]
    return f"{rule.code} {rule.name}"


# --- Helpers ----------------------------------------------------------------------------------


class _Context:
    """Lookups the rules share: datasets, and which node key each Phase 1 ID has."""

    def __init__(self, snapshot: SourceSnapshot) -> None:
        self.snapshot = snapshot
        self.entity_keys: dict[str, str] = {}
        self.entity_names: dict[str, str] = {}
        for record_type, records in (
            (GraphNodeType.COUNTRY, snapshot.countries),
            (GraphNodeType.INDUSTRY, snapshot.industries),
            (GraphNodeType.COMPANY, snapshot.companies),
            (GraphNodeType.ECONOMIC_VARIABLE, snapshot.variables),
        ):
            for record in records:
                self.entity_keys[record.id] = node_key(record_type, record.id)
                self.entity_names[record.id] = record.name

    def ref(self, table: str, record_id: str, dataset_id: str | None, *fields: str) -> SourceRef:
        dataset = self.snapshot.datasets.get(dataset_id) if dataset_id else None
        return SourceRef(
            table=table,
            record_id=record_id,
            dataset_id=dataset_id,
            dataset_version=dataset.version if dataset else None,
            fields=fields,
        )

    def dataset_illustrative(self, dataset_id: str) -> bool:
        dataset = self.snapshot.datasets.get(dataset_id)
        return bool(dataset and dataset.is_illustrative)

    def loaded_at(self, dataset_id: str | None) -> datetime | None:
        dataset = self.snapshot.datasets.get(dataset_id) if dataset_id else None
        return dataset.loaded_at if dataset else None

    def name_for_key(self, key: str, fallback: str) -> str:
        return self.entity_names.get(key.split(":", 1)[-1], fallback)

    def key_for(self, entity_id: str) -> str:
        # An unknown ID gives a key no node has, so validation reports the missing node.
        return self.entity_keys.get(entity_id, f"entity:{entity_id}")


def _nature(is_fictional: bool) -> NodeNature:
    return NodeNature.FICTIONAL if is_fictional else NodeNature.REAL


@dataclass(frozen=True)
class CodeClaim:
    """A record naming a code that identifies a derived node (currency, sector, market)."""

    node_type: GraphNodeType
    code: str
    source: SourceRef
    # Real when the naming record describes the real world; sample for sample files.
    nature: NodeNature


# --- Nodes ------------------------------------------------------------------------------------


def record_nodes(snapshot: SourceSnapshot) -> tuple[list[NodeDraft], list[IssueDraft], int]:
    """Nodes for records that exist in their own right (N01 and N04 to N08).

    Returns the nodes, the issues of rejected records, and how many were rejected.
    """
    ctx = _Context(snapshot)
    nodes: list[NodeDraft] = []
    issues: list[IssueDraft] = []
    rejected = 0

    def accept(draft: NodeDraft, record_id: str) -> None:
        nonlocal rejected
        if not record_id.strip():
            issues.append(
                issue(
                    "missing_node_key",
                    draft.sources[0].label if draft.sources else "?",
                    f"A {draft.node_type.value} record has no ID.",
                )
            )
            rejected += 1
        elif not draft.display_name.strip():
            issues.append(
                issue(
                    "missing_name",
                    draft.key,
                    f"Record {draft.sources[0].label} has no name.",
                    node_key=draft.key,
                )
            )
            rejected += 1
        elif not draft.sources:
            issues.append(
                issue(
                    "missing_provenance",
                    draft.key,
                    "The node has no source record.",
                    node_key=draft.key,
                )
            )
            rejected += 1
        else:
            nodes.append(draft)

    for country in snapshot.countries:
        ref = ctx.ref("countries", country.id, country.dataset_id, "name", "iso_alpha2")
        accept(
            NodeDraft(
                key=node_key(GraphNodeType.COUNTRY, country.id),
                node_type=GraphNodeType.COUNTRY,
                display_name=country.name,
                description=country.description,
                nature=_nature(country.is_fictional),
                attributes={
                    "iso_alpha2": country.iso_alpha2,
                    "currency_code": country.currency_code,
                    "reference": country.reference,
                },
                sources=[ref],
                identifiers=[
                    IdentifierClaim(IdentifierScheme.ISO3166_ALPHA2, country.iso_alpha2, ref)
                ],
            ),
            country.id,
        )

    for industry in snapshot.industries:
        ref = ctx.ref(
            "industries",
            industry.id,
            industry.dataset_id,
            "name",
            "classification_system",
            "classification_code",
        )
        claims = []
        if industry.classification_system == isic.CLASSIFICATION_SYSTEM:
            claims.append(
                IdentifierClaim(
                    IdentifierScheme.ISIC_REV4_DIVISION, industry.classification_code, ref
                )
            )
            if isic.section_for_division(industry.classification_code) is None:
                issues.append(
                    issue(
                        "unknown_classification",
                        node_key(GraphNodeType.INDUSTRY, industry.id),
                        f"'{industry.classification_code}' is not an ISIC Rev. 4 division, so "
                        f"{industry.name} has no sector.",
                        node_key=node_key(GraphNodeType.INDUSTRY, industry.id),
                    )
                )
        accept(
            NodeDraft(
                key=node_key(GraphNodeType.INDUSTRY, industry.id),
                node_type=GraphNodeType.INDUSTRY,
                display_name=industry.name,
                description=industry.description,
                nature=_nature(industry.is_fictional),
                attributes={
                    "classification_system": industry.classification_system,
                    "classification_code": industry.classification_code,
                    "reference": industry.reference,
                },
                sources=[ref],
                identifiers=claims,
            ),
            industry.id,
        )

    for company in snapshot.companies:
        ref = ctx.ref("companies", company.id, company.dataset_id, "name", "is_fictional")
        accept(
            NodeDraft(
                key=node_key(GraphNodeType.COMPANY, company.id),
                node_type=GraphNodeType.COMPANY,
                display_name=company.name,
                description=company.description,
                nature=_nature(company.is_fictional),
                attributes={"reference": company.reference},
                sources=[ref],
            ),
            company.id,
        )

    for variable in snapshot.variables:
        ref = ctx.ref("economic_variables", variable.id, variable.dataset_id, "name", "unit")
        accept(
            NodeDraft(
                key=node_key(GraphNodeType.ECONOMIC_VARIABLE, variable.id),
                node_type=GraphNodeType.ECONOMIC_VARIABLE,
                display_name=variable.name,
                description=variable.description,
                nature=_nature(variable.is_fictional),
                attributes={
                    "unit": variable.unit,
                    "frequency": variable.frequency.value,
                    "category": variable.category.value,
                    "value_kind": variable.value_kind.value,
                    "reference": variable.reference,
                    "reference_url": variable.reference_url,
                },
                sources=[ref],
            ),
            variable.id,
        )

    for series in snapshot.series:
        ref = ctx.ref(
            "economic_series", series.id, series.dataset_id, "name", "provider_series_key"
        )
        dataset = snapshot.datasets.get(series.dataset_id)
        accept(
            NodeDraft(
                key=node_key(GraphNodeType.DATA_SERIES, series.id),
                node_type=GraphNodeType.DATA_SERIES,
                display_name=series.name,
                description=series.description,
                nature=NodeNature.SAMPLE
                if ctx.dataset_illustrative(series.dataset_id)
                else NodeNature.REAL,
                attributes={
                    "series_id": series.id,
                    "dataset_id": series.dataset_id,
                    "dataset_name": dataset.name if dataset else None,
                    "provider_code": series.provider_code,
                    "provider_series_key": series.provider_series_key,
                    "measure_type": series.measure_type.value,
                    "unit": series.unit,
                    "currency": series.currency,
                    "frequency": series.frequency.value,
                    "country_iso3": series.country_iso3,
                    "source_organization": series.source_organization,
                },
                sources=[ref],
                identifiers=[
                    IdentifierClaim(
                        IdentifierScheme.PROVIDER_SERIES,
                        f"{series.dataset_id}:{series.provider_series_key}",
                        ref,
                    )
                ],
            ),
            series.id,
        )

    for instrument in snapshot.instruments:
        ref = ctx.ref(
            "instruments",
            instrument.id,
            instrument.dataset_id,
            "name",
            "isin",
            "exchange_mic",
            "symbol",
        )
        claims = [
            IdentifierClaim(
                IdentifierScheme.LISTING, f"{instrument.exchange_mic}:{instrument.symbol}", ref
            )
        ]
        if instrument.isin:
            claims.append(IdentifierClaim(IdentifierScheme.ISIN, instrument.isin, ref))
        accept(
            NodeDraft(
                key=node_key(GraphNodeType.INSTRUMENT, instrument.id),
                node_type=GraphNodeType.INSTRUMENT,
                display_name=instrument.name,
                description=f"A {instrument.instrument_type.value} listed as "
                f"{instrument.exchange_mic}:{instrument.symbol}, from an imported price file.",
                nature=NodeNature.SAMPLE
                if ctx.dataset_illustrative(instrument.dataset_id)
                else NodeNature.REAL,
                attributes={
                    "instrument_id": instrument.id,
                    "instrument_type": instrument.instrument_type.value,
                    "isin": instrument.isin,
                    "exchange_mic": instrument.exchange_mic,
                    "symbol": instrument.symbol,
                    "currency": instrument.currency,
                    "dataset_id": instrument.dataset_id,
                },
                sources=[ref],
                identifiers=claims,
            ),
            instrument.id,
        )
    return nodes, issues, rejected


def code_claims(snapshot: SourceSnapshot) -> list[CodeClaim]:
    """Every code that names a derived node (N02 currency, N03 sector, N09 market)."""
    ctx = _Context(snapshot)
    claims: list[CodeClaim] = []
    for country in snapshot.countries:
        claims.append(
            CodeClaim(
                GraphNodeType.CURRENCY,
                country.currency_code,
                ctx.ref("countries", country.id, country.dataset_id, "currency_code"),
                _nature(country.is_fictional),
            )
        )
    for series in snapshot.series:
        if series.currency:
            claims.append(
                CodeClaim(
                    GraphNodeType.CURRENCY,
                    series.currency,
                    ctx.ref("economic_series", series.id, series.dataset_id, "currency"),
                    NodeNature.SAMPLE
                    if ctx.dataset_illustrative(series.dataset_id)
                    else NodeNature.REAL,
                )
            )
    for instrument in snapshot.instruments:
        sample = ctx.dataset_illustrative(instrument.dataset_id)
        nature = NodeNature.SAMPLE if sample else NodeNature.REAL
        claims.append(
            CodeClaim(
                GraphNodeType.CURRENCY,
                instrument.currency,
                ctx.ref("instruments", instrument.id, instrument.dataset_id, "currency"),
                nature,
            )
        )
        claims.append(
            CodeClaim(
                GraphNodeType.MARKET,
                instrument.exchange_mic,
                ctx.ref("instruments", instrument.id, instrument.dataset_id, "exchange_mic"),
                nature,
            )
        )
    for industry in snapshot.industries:
        if industry.classification_system != isic.CLASSIFICATION_SYSTEM:
            continue
        section = isic.section_for_division(industry.classification_code)
        if section is None:
            continue  # reported as unknown_classification with the industry's node
        claims.append(
            CodeClaim(
                GraphNodeType.SECTOR,
                section.code,
                ctx.ref("industries", industry.id, industry.dataset_id, "classification_code"),
                _nature(industry.is_fictional),
            )
        )
    return claims


# --- Edges ------------------------------------------------------------------------------------


def _currency_key(code: str) -> str:
    return node_key(GraphNodeType.CURRENCY, code)


def _sector_key(code: str) -> str:
    return node_key(GraphNodeType.SECTOR, f"isic4-{code}")


def _market_key(mic: str) -> str:
    return node_key(GraphNodeType.MARKET, mic)


def edge_drafts(
    snapshot: SourceSnapshot, alpha3_index: dict[str, str]
) -> tuple[list[EdgeDraft], list[IssueDraft], list[tuple[str, str, SourceRef]]]:
    """Edges stated by source records (R01 to R12).

    ``alpha3_index`` maps ISO 3166-1 alpha-3 codes to the one country node they identify
    (after entity resolution). Returns the edges, unresolved references, and the series
    whose country was found by that code (for the resolution audit log).
    """
    ctx = _Context(snapshot)
    edges: list[EdgeDraft] = []
    issues: list[IssueDraft] = []
    by_code: list[tuple[str, str, SourceRef]] = []
    edges.extend(_curated(ctx, issues))
    edges.extend(_company_links(ctx))
    edges.extend(_variable_links(ctx))
    edges.extend(_industry_links(ctx))
    edges.extend(_country_links(ctx))
    edges.extend(_series_links(ctx, alpha3_index, issues, by_code))
    edges.extend(_instrument_links(ctx))
    return edges, issues, by_code


def _curated(ctx: _Context, issues: list[IssueDraft]) -> Iterator[EdgeDraft]:
    for rel in ctx.snapshot.relationships:
        try:
            edge_type = GraphEdgeType(rel.type.value)
        except ValueError:
            issues.append(
                issue(
                    "unknown_edge_type",
                    f"relationships/{rel.id}",
                    f"Relationship type '{rel.type.value}' has no graph definition; the "
                    "relationship was not added.",
                )
            )
            continue
        illustrative = rel.evidence_level is EvidenceLevel.ILLUSTRATIVE or ctx.dataset_illustrative(
            rel.dataset_id
        )
        source_key, target_key = ctx.key_for(rel.source_id), ctx.key_for(rel.target_id)
        yield EdgeDraft(
            edge_type=edge_type,
            source_key=source_key,
            target_key=target_key,
            description=rel.description,
            evidence_status=EvidenceStatus.MODEL_ASSUMPTION,
            attributes={
                "polarity": rel.polarity.value,
                "strength": rel.strength.value,
                "evidence_level": rel.evidence_level.value,
                "rationale": rel.rationale,
            },
            source_illustrative=illustrative,
            evidence=[
                EvidenceDraft(
                    rule=rule_label("curated_relationship"),
                    source_kind=EvidenceSourceKind.REFERENCE_DATASET,
                    source=ctx.ref("relationships", rel.id, rel.dataset_id, "type"),
                    statement=f"Curated relationship {rel.id}: {rel.source_id} "
                    f"{rel.type.value} {rel.target_id}, evidence level "
                    f"'{rel.evidence_level.value}'. Rationale: {rel.rationale}",
                    transformation="Copied as an edge of the same type; the description, "
                    "rationale, assumed polarity and illustrative strength are kept unchanged.",
                    citation=rel.reference,
                    recorded_at=ctx.loaded_at(rel.dataset_id),
                )
            ],
        )


def _company_links(ctx: _Context) -> Iterator[EdgeDraft]:
    for company in ctx.snapshot.companies:
        key = node_key(GraphNodeType.COMPANY, company.id)
        industry = ctx.entity_names.get(company.industry_id, company.industry_id)
        country = ctx.entity_names.get(company.country_id, company.country_id)
        fictional = "fictional " if company.is_fictional else ""
        yield EdgeDraft(
            edge_type=GraphEdgeType.IN_INDUSTRY,
            source_key=key,
            target_key=ctx.key_for(company.industry_id),
            description=f"{company.name} operates in {industry}.",
            evidence_status=EvidenceStatus.ANALYST_CREATED,
            evidence=[
                EvidenceDraft(
                    rule=rule_label("company_industry"),
                    source_kind=EvidenceSourceKind.REFERENCE_DATASET,
                    source=ctx.ref("companies", company.id, company.dataset_id, "industry_id"),
                    statement=f"The {fictional}company record {company.id} names "
                    f"{company.industry_id} as its industry (companies.industry_id).",
                    transformation="The company's industry field becomes an 'operates in' "
                    "edge to that industry.",
                    citation=company.reference,
                    citation_url=company.reference_url,
                    recorded_at=ctx.loaded_at(company.dataset_id),
                )
            ],
        )
        yield EdgeDraft(
            edge_type=GraphEdgeType.DOMICILED_IN,
            source_key=key,
            target_key=ctx.key_for(company.country_id),
            description=f"{company.name} is domiciled in {country}.",
            evidence_status=EvidenceStatus.ANALYST_CREATED,
            evidence=[
                EvidenceDraft(
                    rule=rule_label("company_country"),
                    source_kind=EvidenceSourceKind.REFERENCE_DATASET,
                    source=ctx.ref("companies", company.id, company.dataset_id, "country_id"),
                    statement=f"The {fictional}company record {company.id} names "
                    f"{company.country_id} as its country of domicile (companies.country_id).",
                    transformation="The company's country field becomes an 'is domiciled in' "
                    "edge to that country.",
                    citation=company.reference,
                    citation_url=company.reference_url,
                    recorded_at=ctx.loaded_at(company.dataset_id),
                )
            ],
        )


def _variable_links(ctx: _Context) -> Iterator[EdgeDraft]:
    for variable in ctx.snapshot.variables:
        if variable.country_id is None:
            continue
        country = ctx.entity_names.get(variable.country_id, variable.country_id)
        yield EdgeDraft(
            edge_type=GraphEdgeType.MEASURED_FOR,
            source_key=node_key(GraphNodeType.ECONOMIC_VARIABLE, variable.id),
            target_key=ctx.key_for(variable.country_id),
            description=f"{variable.name} is measured for {country}.",
            evidence_status=EvidenceStatus.ANALYST_CREATED,
            evidence=[
                EvidenceDraft(
                    rule=rule_label("variable_country"),
                    source_kind=EvidenceSourceKind.REFERENCE_DATASET,
                    source=ctx.ref(
                        "economic_variables", variable.id, variable.dataset_id, "country_id"
                    ),
                    statement=f"The variable definition {variable.id} names "
                    f"{variable.country_id} as the economy it describes.",
                    transformation="The variable's country field becomes an 'is measured for' "
                    "edge.",
                    citation=variable.reference,
                    citation_url=variable.reference_url,
                    recorded_at=ctx.loaded_at(variable.dataset_id),
                )
            ],
        )


def _industry_links(ctx: _Context) -> Iterator[EdgeDraft]:
    for industry in ctx.snapshot.industries:
        if industry.classification_system != isic.CLASSIFICATION_SYSTEM:
            continue
        section = isic.section_for_division(industry.classification_code)
        if section is None:
            continue  # reported as unknown_classification by resolution
        code = industry.classification_code
        yield EdgeDraft(
            edge_type=GraphEdgeType.IN_SECTOR,
            source_key=node_key(GraphNodeType.INDUSTRY, industry.id),
            target_key=_sector_key(section.code),
            description=f"{industry.name} (ISIC Rev. 4 division {code}) belongs to section "
            f"{section.code}, {section.title}.",
            evidence_status=EvidenceStatus.EVIDENCE_BACKED,
            evidence=[
                EvidenceDraft(
                    rule=rule_label("industry_sector"),
                    source_kind=EvidenceSourceKind.CLASSIFICATION_STANDARD,
                    source=ctx.ref(
                        "industries", industry.id, industry.dataset_id, "classification_code"
                    ),
                    statement=f"industries.classification_code = {code} (ISIC Rev. 4).",
                    transformation=f"ISIC Rev. 4 places divisions "
                    f"{section.first_division:02d} to {section.last_division:02d} in section "
                    f"{section.code}; division {code} is in that range.",
                    derivation=Derivation.DERIVED,
                    derived_from=(
                        f"industries/{industry.id}.classification_code",
                        "ISIC Rev. 4 section table (app/graph/isic.py)",
                    ),
                    citation=isic.SOURCE,
                    recorded_at=ctx.loaded_at(industry.dataset_id),
                )
            ],
        )


def _country_links(ctx: _Context) -> Iterator[EdgeDraft]:
    for country in ctx.snapshot.countries:
        code = country.currency_code
        yield EdgeDraft(
            edge_type=GraphEdgeType.HAS_CURRENCY,
            source_key=node_key(GraphNodeType.COUNTRY, country.id),
            target_key=_currency_key(code),
            description=f"{country.name} has the currency {code} (ISO 4217).",
            evidence_status=EvidenceStatus.EVIDENCE_BACKED,
            evidence=[
                EvidenceDraft(
                    rule=rule_label("country_currency"),
                    source_kind=EvidenceSourceKind.REFERENCE_DATASET,
                    source=ctx.ref("countries", country.id, country.dataset_id, "currency_code"),
                    statement=f"countries.currency_code = {code}.",
                    transformation="The country's ISO 4217 code becomes a 'has currency' edge "
                    "to the currency node for that code.",
                    citation=country.reference,
                    citation_url=country.reference_url,
                    recorded_at=ctx.loaded_at(country.dataset_id),
                )
            ],
        )


@dataclass(frozen=True)
class _SeriesCitation:
    """Evidence for edges stated by a series' catalogue entry."""

    ctx: _Context
    series: SeriesRecord
    source_kind: EvidenceSourceKind
    attribution: str | None

    def evidence(
        self, rule: str, statement: str, transformation: str, *fields: str
    ) -> EvidenceDraft:
        series = self.series
        return EvidenceDraft(
            rule=rule_label(rule),
            source_kind=self.source_kind,
            source=self.ctx.ref("economic_series", series.id, series.dataset_id, *fields),
            statement=statement,
            transformation=transformation,
            citation=self.attribution,
            retrieved_at=series.last_successful_ingestion_at,
            recorded_at=series.created_at,
        )


def _manifest_evidence(
    ctx: _Context,
    instrument: InstrumentRecord,
    rule: str,
    field: str,
    statement: str,
    transformation: str,
) -> EvidenceDraft:
    return EvidenceDraft(
        rule=rule_label(rule),
        source_kind=EvidenceSourceKind.PRICE_FILE_MANIFEST,
        source=ctx.ref("instruments", instrument.id, instrument.dataset_id, field),
        statement=statement,
        transformation=transformation,
        recorded_at=instrument.created_at,
    )


def _series_links(
    ctx: _Context,
    alpha3_index: dict[str, str],
    issues: list[IssueDraft],
    by_code: list[tuple[str, str, SourceRef]],
) -> Iterator[EdgeDraft]:
    for series in ctx.snapshot.series:
        key = node_key(GraphNodeType.DATA_SERIES, series.id)
        dataset = ctx.snapshot.datasets.get(series.dataset_id)
        attribution = dataset.attribution if dataset else None
        provider_kind = (
            EvidenceSourceKind.SERIES_CATALOGUE
            if dataset is None or dataset.kind is DatasetKind.PROVIDER
            else EvidenceSourceKind.REFERENCE_DATASET
        )
        cite = _SeriesCitation(ctx, series, provider_kind, attribution)
        # R07: the country the series covers.
        country_key: str | None = None
        how = ""
        if series.country_id:
            country_key = ctx.key_for(series.country_id)
            how = (
                f"The series' catalogue entry links it to {series.country_id}"
                + (f" (provider code {series.country_iso3})" if series.country_iso3 else "")
                + "."
            )
        elif series.country_iso3 and series.country_iso3 in alpha3_index:
            country_key = alpha3_index[series.country_iso3]
            how = (
                f"The provider names the country {series.country_iso3}; that ISO 3166-1 "
                f"alpha-3 code identifies exactly one country node ({country_key})."
            )
            by_code.append(
                (
                    country_key,
                    series.country_iso3,
                    ctx.ref("economic_series", series.id, series.dataset_id, "country_iso3"),
                )
            )
        elif series.country_iso3:
            issues.append(
                issue(
                    "unresolved_reference",
                    f"economic_series/{series.id}",
                    f"The series names the country {series.country_iso3}, which identifies no "
                    "country in the graph; no 'covers' edge was made.",
                    node_key=key,
                )
            )
        if country_key:
            yield EdgeDraft(
                edge_type=GraphEdgeType.COVERS,
                source_key=key,
                target_key=country_key,
                description=f"{series.name} covers "
                f"{ctx.name_for_key(country_key, series.country_iso3 or country_key)}.",
                evidence_status=EvidenceStatus.EVIDENCE_BACKED,
                source_illustrative=ctx.dataset_illustrative(series.dataset_id),
                evidence=[
                    cite.evidence(
                        "series_country",
                        f"economic_series.country_iso3 = {series.country_iso3}; "
                        f"economic_series.country_id = {series.country_id}.",
                        how + " The series becomes a 'covers' edge to it.",
                        "country_id",
                        "country_iso3",
                    )
                ],
            )

        # R08: the variable the series is a related measure of.
        if series.variable_id:
            variable = ctx.entity_names.get(series.variable_id, series.variable_id)
            yield EdgeDraft(
                edge_type=GraphEdgeType.RELATED_MEASURE_OF,
                source_key=key,
                target_key=ctx.key_for(series.variable_id),
                description=f"{series.name} is a related measure of {variable}.",
                evidence_status=EvidenceStatus.ANALYST_CREATED,
                attributes={"stated_difference": series.variable_relation},
                source_illustrative=ctx.dataset_illustrative(series.dataset_id),
                evidence=[
                    cite.evidence(
                        "series_variable",
                        f"economic_series.variable_id = {series.variable_id}. "
                        f"Stated difference: {series.variable_relation}",
                        "The catalogue curator's link becomes an 'is a related measure of' "
                        "edge; the stated difference is kept with it.",
                        "variable_id",
                        "variable_relation",
                    )
                ],
            )

        # R09: the currency of the series' unit.
        if series.currency:
            yield EdgeDraft(
                edge_type=GraphEdgeType.EXPRESSED_IN,
                source_key=key,
                target_key=_currency_key(series.currency),
                description=f"{series.name} is expressed in {series.currency} "
                f"(unit: {series.unit}).",
                evidence_status=EvidenceStatus.EVIDENCE_BACKED,
                source_illustrative=ctx.dataset_illustrative(series.dataset_id),
                evidence=[
                    cite.evidence(
                        "series_currency",
                        f"economic_series.currency = {series.currency}; unit = '{series.unit}'.",
                        "The currency of the series' unit becomes an 'is expressed in' edge "
                        "to that currency.",
                        "currency",
                        "unit",
                    )
                ],
            )


def _instrument_links(ctx: _Context) -> Iterator[EdgeDraft]:
    for instrument in ctx.snapshot.instruments:
        key = node_key(GraphNodeType.INSTRUMENT, instrument.id)
        illustrative = ctx.dataset_illustrative(instrument.dataset_id)

        yield EdgeDraft(
            edge_type=GraphEdgeType.LISTED_ON,
            source_key=key,
            target_key=_market_key(instrument.exchange_mic),
            description=f"{instrument.name} is listed on {instrument.exchange_mic} "
            f"(as {instrument.symbol}), as declared in its price-file manifest.",
            evidence_status=EvidenceStatus.UNVERIFIED,
            source_illustrative=illustrative,
            evidence=[
                _manifest_evidence(
                    ctx,
                    instrument,
                    "instrument_market",
                    "exchange_mic",
                    f"The manifest declares exchange_mic = {instrument.exchange_mic}, "
                    f"symbol = {instrument.symbol}.",
                    "The declared MIC becomes an 'is listed on' edge to that market. RUMIN "
                    "checked the code's format only.",
                )
            ],
        )
        yield EdgeDraft(
            edge_type=GraphEdgeType.QUOTED_IN,
            source_key=key,
            target_key=_currency_key(instrument.currency),
            description=f"{instrument.name}'s prices are quoted in {instrument.currency}, as "
            "declared in its price-file manifest.",
            evidence_status=EvidenceStatus.UNVERIFIED,
            source_illustrative=illustrative,
            evidence=[
                _manifest_evidence(
                    ctx,
                    instrument,
                    "instrument_currency",
                    "currency",
                    f"The manifest declares currency = {instrument.currency}.",
                    "The declared currency becomes an 'is quoted in' edge. Prices are never "
                    "converted.",
                )
            ],
        )
        if instrument.country_id:
            country = ctx.entity_names.get(instrument.country_id, instrument.country_id)
            yield EdgeDraft(
                edge_type=GraphEdgeType.ASSOCIATED_WITH,
                source_key=key,
                target_key=ctx.key_for(instrument.country_id),
                description=f"The price-file manifest associates {instrument.name} with {country}.",
                evidence_status=EvidenceStatus.UNVERIFIED,
                source_illustrative=illustrative,
                evidence=[
                    _manifest_evidence(
                        ctx,
                        instrument,
                        "instrument_country",
                        "country_id",
                        f"The manifest declares country_id = {instrument.country_id}.",
                        "The declared country becomes an 'is associated with' edge. The "
                        "manifest does not say whether this is the country of listing, of the "
                        "issuer or something else.",
                    )
                ],
            )
