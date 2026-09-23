"""Graph construction without a database: rules, entity resolution and validation."""

from __future__ import annotations

from dataclasses import replace
from datetime import date

from app.domain.enums import (
    EvidenceSourceKind,
    EvidenceStatus,
    GraphEdgeType,
    GraphNodeType,
    IssueOutcome,
    NodeNature,
    QualityStatus,
    RelationshipType,
    ResolutionOutcome,
)
from app.graph.assemble import assemble
from app.graph.drafts import EdgeDraft, EvidenceDraft, GraphDraft, SourceRef, content_hash, edge_key
from app.graph.validation import GRAPH_RULES, check_edge
from tests.graph_factories import (
    AERISCA,
    AIR,
    CPI_SERIES,
    DELTRIN,
    INDIA,
    REAL_PRICES,
    USA,
    company,
    country,
    industry,
    instrument,
    relationship,
    series,
    snapshot,
)

TODAY = date(2026, 9, 23)


def build(**changes: object) -> GraphDraft:
    return assemble(snapshot(**changes), today=TODAY)


def rules_found(draft: GraphDraft) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in draft.issues:
        counts[item.rule] = counts.get(item.rule, 0) + 1
    return counts


def edges_of(draft: GraphDraft, edge_type: GraphEdgeType) -> list[EdgeDraft]:
    return [edge for edge in draft.edges.values() if edge.edge_type is edge_type]


# --- The baseline ------------------------------------------------------------------------------


def test_a_clean_world_builds_without_issues() -> None:
    draft = build()
    assert draft.issues == []
    types = sorted(node.node_type.value for node in draft.nodes.values())
    assert types.count("country") == 2 and types.count("currency") == 2
    assert types.count("sector") == 2  # ISIC H (divisions 49, 51) and C (division 19)
    assert len(draft.nodes) == 15 and len(draft.edges) == 16
    for edge in draft.edges.values():
        assert edge.evidence, f"{edge.key} has no evidence"
    tally_n, tally_e = draft.node_tally, draft.edge_tally
    assert (tally_n.processed, tally_n.valid, tally_n.flagged, tally_n.rejected) == (15, 15, 0, 0)
    assert (tally_e.processed, tally_e.valid, tally_e.flagged, tally_e.rejected) == (16, 16, 0, 0)


def test_evidence_statuses_follow_the_rules() -> None:
    draft = build()
    status = {edge.edge_type: edge.evidence_status for edge in draft.edges.values()}
    assert status[GraphEdgeType.AFFECTS_COSTS] is EvidenceStatus.MODEL_ASSUMPTION
    assert status[GraphEdgeType.IN_INDUSTRY] is EvidenceStatus.ANALYST_CREATED
    assert status[GraphEdgeType.IN_SECTOR] is EvidenceStatus.EVIDENCE_BACKED
    assert status[GraphEdgeType.HAS_CURRENCY] is EvidenceStatus.EVIDENCE_BACKED
    assert status[GraphEdgeType.COVERS] is EvidenceStatus.EVIDENCE_BACKED
    assert status[GraphEdgeType.RELATED_MEASURE_OF] is EvidenceStatus.ANALYST_CREATED


def test_illustrative_flags() -> None:
    draft = build()
    for edge in draft.edges.values():
        touches_fiction = any(
            draft.nodes[key].nature is not NodeNature.REAL
            for key in (edge.source_key, edge.target_key)
        )
        if touches_fiction or edge.edge_type is GraphEdgeType.AFFECTS_COSTS:
            assert edge.is_illustrative, edge.description
    sector_edges = edges_of(draft, GraphEdgeType.IN_SECTOR)
    assert sector_edges and not any(edge.is_illustrative for edge in sector_edges)


def test_the_same_sources_always_give_the_same_graph() -> None:
    first, second = build(), build()
    assert list(first.nodes) == list(second.nodes)
    assert [content_hash(edge.hash_payload()) for edge in first.edges.values()] == [
        content_hash(edge.hash_payload()) for edge in second.edges.values()
    ]


def test_derived_edges_record_how_they_were_derived() -> None:
    (edge,) = [
        e for e in edges_of(build(), GraphEdgeType.IN_SECTOR) if e.source_key == "industry:ind_air"
    ]
    assert edge.target_key == "sector:isic4-h"
    evidence = edge.evidence[0]
    assert evidence.derivation.value == "derived"
    assert "51" in evidence.statement and "49 to 53" in evidence.transformation
    assert "ISIC" in (evidence.citation or "")


# --- Entity resolution: identifiers --------------------------------------------------------------


def test_records_naming_one_currency_code_share_one_node() -> None:
    draft = build(series=(CPI_SERIES, series("wb-fx", "IND", INDIA.id, currency="INR")))
    inr = draft.nodes["currency:inr"]
    assert {source.label for source in inr.sources} == {"countries/cty_in", "economic_series/wb-fx"}
    linked = [d for d in draft.decisions if d.node_key == "currency:inr"]
    assert {d.outcome for d in linked} == {ResolutionOutcome.LINKED} and len(linked) == 2


def test_provider_alpha3_code_is_attached_through_the_catalogue_link() -> None:
    draft = build()
    india = draft.nodes["country:cty_in"]
    assert {claim.label for claim in india.identifiers} == {
        "iso3166_alpha2:IN",
        "iso3166_alpha3:IND",
    }
    attached = [d for d in draft.decisions if d.outcome is ResolutionOutcome.IDENTIFIER_ATTACHED]
    assert attached and all(d.node_key == "country:cty_in" for d in attached)


def test_a_series_without_a_link_is_resolved_by_its_alpha3_code() -> None:
    unlinked = series("wb-unlinked", "IND", None)
    draft = build(series=(CPI_SERIES, unlinked))
    covers = [
        e for e in edges_of(draft, GraphEdgeType.COVERS) if e.source_key == "series:wb-unlinked"
    ]
    assert [edge.target_key for edge in covers] == ["country:cty_in"]
    assert "identifies exactly one country node" in covers[0].evidence[0].transformation


def test_an_unknown_country_code_creates_nothing() -> None:
    draft = build(series=(CPI_SERIES, series("wb-chn", "CHN", None)))
    assert rules_found(draft).get("unresolved_reference") == 1
    assert not any(key.startswith("country:") and "chn" in key for key in draft.nodes)
    assert not [e for e in edges_of(draft, GraphEdgeType.COVERS) if e.source_key == "series:wb-chn"]


def test_a_conflicting_code_is_attached_to_no_one() -> None:
    wrong = series("wb-wrong", "IND", USA.id)  # claims IND for the United States
    draft = build(series=(CPI_SERIES, wrong))
    assert rules_found(draft).get("identifier_conflict") == 2
    for key in ("country:cty_in", "country:cty_us"):
        node = draft.nodes[key]
        assert "iso3166_alpha3:IND" not in {claim.label for claim in node.identifiers}
        assert node.quality_status is QualityStatus.WARNING
    assert any(d.outcome is ResolutionOutcome.CONFLICT for d in draft.decisions)


def test_two_industries_with_one_code_are_kept_apart() -> None:
    twin = industry("ind_airlines", "Airlines", "51")
    draft = build(industries=(AIR, twin))
    assert rules_found(draft).get("unsupported_merge") == 2
    assert {"industry:ind_air", "industry:ind_airlines"} <= set(draft.nodes)
    for key in ("industry:ind_air", "industry:ind_airlines"):
        assert draft.nodes[key].quality_status is QualityStatus.WARNING
        assert not [c for c in draft.nodes[key].identifiers if c.value == "51"]


# --- Entity resolution: names suggest, never merge -----------------------------------------------


def test_identical_normalised_names_are_flagged_not_merged() -> None:
    twin = company("co_anvaya_2", "ANVAYA BANK LTD.", AIR.id, INDIA.id)
    first = company("co_anvaya", "Anvaya Bank", AIR.id, INDIA.id)
    draft = build(companies=(first, twin), relationships=())
    assert {"company:co_anvaya", "company:co_anvaya_2"} <= set(draft.nodes)
    assert rules_found(draft).get("possible_duplicate") == 2
    assert draft.nodes["company:co_anvaya"].quality_status is QualityStatus.WARNING
    (decision,) = [d for d in draft.decisions if d.outcome is ResolutionOutcome.CANDIDATE_FLAGGED]
    assert decision.node_key is None  # nothing was linked
    assert set(decision.candidate_node_keys) == {"company:co_anvaya", "company:co_anvaya_2"}


def test_same_name_in_different_countries_is_still_two_entities() -> None:
    indian = company("co_abc_in", "ABC Holdings Ltd", AIR.id, INDIA.id)
    american = company("co_abc_us", "ABC Holdings Limited", AIR.id, USA.id)
    draft = build(companies=(indian, american), relationships=())
    assert {"company:co_abc_in", "company:co_abc_us"} <= set(draft.nodes)
    domiciles = {e.source_key: e.target_key for e in edges_of(draft, GraphEdgeType.DOMICILED_IN)}
    assert domiciles == {
        "company:co_abc_in": "country:cty_in",
        "company:co_abc_us": "country:cty_us",
    }


def test_a_contained_name_is_only_noted() -> None:
    parent = company("co_tata", "Tata Steel", AIR.id, INDIA.id)
    subsidiary = company("co_tata_eu", "Tata Steel Europe", AIR.id, USA.id)
    draft = build(companies=(parent, subsidiary), relationships=())
    found = rules_found(draft)
    assert found["similar_name"] == 1
    assert not {"possible_duplicate", "unsupported_merge"} & set(found)
    assert all(node.quality_status is QualityStatus.VALIDATED for node in draft.nodes.values())


def test_fiction_is_never_matched_with_a_real_instrument() -> None:
    real = instrument("xtst-deltrin", "Deltrin Refining Ltd", dataset=REAL_PRICES)
    draft = build(instruments=(real,))
    assert rules_found(draft).get("match_ruled_out") == 1
    ruled_out = [d for d in draft.decisions if d.outcome is ResolutionOutcome.REJECTED]
    assert ruled_out and set(ruled_out[0].candidate_node_keys) == {
        "instrument:xtst-deltrin",
        f"company:{DELTRIN.id}",
    }


def test_a_similar_name_never_links_an_instrument_to_a_company() -> None:
    sample = instrument("xtst-aerisca", "Aerisca Airways", mic="XTST")
    draft = build(instruments=(sample,))
    assert rules_found(draft).get("possible_issuer") == 1
    touching = {
        (edge.source_key, edge.target_key)
        for edge in draft.edges.values()
        if "instrument:xtst-aerisca" in (edge.source_key, edge.target_key)
    }
    assert all(f"company:{AERISCA.id}" not in pair for pair in touching)


def test_instrument_links_are_unverified_and_sample_data_is_illustrative() -> None:
    sample = instrument("xnse-test", "Test Equity", mic="XNSE", currency="INR", country_id=INDIA.id)
    draft = build(instruments=(sample,))
    market = draft.nodes["market:xnse"]
    assert market.nature is NodeNature.SAMPLE  # only a sample file names it
    assert draft.nodes["currency:inr"].nature is NodeNature.REAL  # India names it too
    for edge_type in (
        GraphEdgeType.LISTED_ON,
        GraphEdgeType.QUOTED_IN,
        GraphEdgeType.ASSOCIATED_WITH,
    ):
        (edge,) = edges_of(draft, edge_type)
        assert edge.evidence_status is EvidenceStatus.UNVERIFIED and edge.is_illustrative


# --- Validation ----------------------------------------------------------------------------------


def test_an_invalid_currency_code_makes_no_node_and_no_edge() -> None:
    odd = country("cty_xx", "Oddland", "XX", "US$")
    draft = build(countries=(INDIA, USA, odd))
    assert rules_found(draft).get("invalid_code") == 1
    assert "currency:us$" not in draft.nodes
    assert rules_found(draft).get("missing_target_node") == 1
    assert draft.node_tally.rejected == 1 and draft.edge_tally.rejected == 1


def test_an_unknown_isic_division_flags_the_industry() -> None:
    draft = build(industries=(AIR, industry("ind_bad", "Bad code", "04")))
    assert rules_found(draft).get("unknown_classification") == 1
    assert draft.nodes["industry:ind_bad"].quality_status is QualityStatus.WARNING
    assert not [
        e for e in edges_of(draft, GraphEdgeType.IN_SECTOR) if e.source_key == "industry:ind_bad"
    ]


def test_another_classification_system_is_not_an_error() -> None:
    nic = industry("ind_nic", "Something (NIC)", "51", system="NIC 2008")
    draft = build(industries=(AIR, nic))
    assert "unknown_classification" not in rules_found(draft)
    assert rules_found(draft).get("isolated_node") == 1  # no sector, no company: noted


def test_structural_problems_reject_edges() -> None:
    bad = (
        relationship("rel_missing", RelationshipType.SUPPLIES_TO, DELTRIN.id, "co_ghost"),
        relationship("rel_self", RelationshipType.SUPPLIES_TO, DELTRIN.id, DELTRIN.id),
        relationship("rel_types", RelationshipType.LENDS_TO, DELTRIN.id, INDIA.id),
        relationship("rel_reversed", RelationshipType.AFFECTS_COSTS, AIR.id, "var_fuel"),
    )
    draft = build(relationships=bad)
    found = rules_found(draft)
    assert found["missing_target_node"] == 1
    assert found["self_loop"] == 1
    assert found["endpoint_types_not_allowed"] == 1
    assert found["reversed_direction"] == 1
    assert not edges_of(draft, GraphEdgeType.SUPPLIES_TO) and not edges_of(
        draft, GraphEdgeType.LENDS_TO
    )


def test_fiction_and_fact_are_never_connected() -> None:
    real_company = company("co_real", "Real Co", AIR.id, INDIA.id, fictional=False)
    supply = relationship("rel_mixed", RelationshipType.SUPPLIES_TO, DELTRIN.id, real_company.id)
    draft = build(companies=(AERISCA, DELTRIN, real_company), relationships=(supply,))
    assert rules_found(draft).get("reality_mismatch") == 1
    assert not edges_of(draft, GraphEdgeType.SUPPLIES_TO)


def test_an_evidence_backed_edge_cannot_touch_fiction() -> None:
    utopia = replace(country("cty_zz", "Utopia", "ZZ", "ZZD"), is_fictional=True)
    draft = build(countries=(INDIA, USA, utopia))
    assert draft.nodes["currency:zzd"].nature is NodeNature.FICTIONAL
    assert rules_found(draft).get("reality_mismatch") == 1  # its has_currency edge


def test_duplicate_and_undirected_edges_are_stored_once() -> None:
    again = replace(relationship("rel_again", RelationshipType.SUPPLIES_TO, DELTRIN.id, AERISCA.id))
    ab = relationship("rel_ab", RelationshipType.COMPETES_WITH, AERISCA.id, DELTRIN.id)
    ba = relationship("rel_ba", RelationshipType.COMPETES_WITH, DELTRIN.id, AERISCA.id)
    draft = build(
        relationships=(
            relationship("rel_supply", RelationshipType.SUPPLIES_TO, DELTRIN.id, AERISCA.id),
            again,
            ab,
            ba,
        )
    )
    assert rules_found(draft).get("duplicate_edge") == 2
    (supply,) = edges_of(draft, GraphEdgeType.SUPPLIES_TO)
    assert len(supply.evidence) == 2
    (compete,) = edges_of(draft, GraphEdgeType.COMPETES_WITH)
    assert compete.source_key < compete.target_key and not compete.directed
    assert draft.duplicates_merged == 2


def test_records_without_id_or_name_are_rejected() -> None:
    nameless = replace(company("co_nameless", "x", AIR.id, INDIA.id), name="  ")
    keyless = replace(company("co_keyless", "Keyless", AIR.id, INDIA.id), id="")
    draft = build(companies=(AERISCA, nameless, keyless))
    found = rules_found(draft)
    assert found["missing_name"] == 1 and found["missing_node_key"] == 1
    assert "company:co_nameless" not in draft.nodes
    assert draft.node_tally.rejected == 2


def test_tallies_always_add_up() -> None:
    draft = build(
        countries=(INDIA, USA, country("cty_xx", "Oddland", "XX", "US$")),
        industries=(AIR, industry("ind_bad", "Bad", "04"), industry("ind_twin", "Twin", "51")),
        relationships=(
            relationship("rel_x", RelationshipType.SUPPLIES_TO, DELTRIN.id, "co_ghost"),
        ),
    )
    for tally in (draft.node_tally, draft.edge_tally):
        assert tally.processed == tally.valid + tally.flagged + tally.rejected
    assert draft.node_tally.flagged >= 3 and draft.edge_tally.rejected >= 2


def _evidence() -> EvidenceDraft:
    return EvidenceDraft(
        "test",
        EvidenceSourceKind.REFERENCE_DATASET,
        SourceRef("relationships", "rel"),
        "statement",
        "transformation",
    )


def test_validity_and_status_rules() -> None:
    draft = build()
    nodes = draft.nodes

    def check(
        *,
        valid_from: date | None = None,
        valid_to: date | None = None,
        status: EvidenceStatus = EvidenceStatus.MODEL_ASSUMPTION,
        evidence: list[EvidenceDraft] | None = None,
    ) -> set[str]:
        edge = EdgeDraft(
            edge_type=GraphEdgeType.INFLUENCES,
            source_key="variable:var_fuel",
            target_key="variable:var_cpi",
            description="test",
            evidence_status=status,
            evidence=[_evidence()] if evidence is None else evidence,
            valid_from=valid_from,
            valid_to=valid_to,
        )
        return {item.rule for item in check_edge(edge, nodes, TODAY)}

    assert check() == set()
    assert check(valid_from=date(2020, 1, 1), valid_to=date(2019, 1, 1)) == {
        "invalid_validity_period"
    }
    assert check(valid_from=date(2030, 1, 1)) == {"future_validity"}
    assert check(status=EvidenceStatus.EVIDENCE_BACKED) == {"evidence_status_not_allowed"}
    assert check(evidence=[]) == {"missing_evidence"}


def test_every_rule_has_a_description() -> None:
    for rule in GRAPH_RULES.values():
        assert rule.description.endswith(".")
        assert (rule.outcome is IssueOutcome.REJECTED) == (rule.severity.value == "error")


def test_edge_keys_are_stable() -> None:
    assert edge_key(GraphEdgeType.COVERS, "series:a", "country:b") == edge_key(
        GraphEdgeType.COVERS, "series:a", "country:b"
    )
    assert edge_key(GraphEdgeType.COVERS, "series:a", "country:b") != edge_key(
        GraphEdgeType.COVERS, "country:b", "series:a"
    )
    assert GraphNodeType.SECTOR.value == "sector"
