"""Entity resolution: which records describe the same entity — decided conservatively.

1. **Record keys.** A record that exists in its own right (a country, a company, a series)
   always maps to the same node, keyed by its own ID.
2. **Exact identifiers.** Currency, sector and market nodes exist only as codes named by
   other records; every record naming the same code links to the same node.
3. **Provider identifiers.** A World Bank series names its country by ISO 3166-1 alpha-3
   and its catalogue entry links it to a reference country, so the code becomes an
   identifier of that country — unless another country claims it too.
4. **Normalised names** (``app.graph.names``) generate *candidates* only.
5. **Candidates**: equal normalised names (strong) or contained names (weak).
6. **Decision**: merges happen only through identifiers and explicit links. Two records of
   a kind RUMIN never merges automatically (e.g. two industries with one ISIC code) are
   kept apart and flagged; a name match is flagged or noted, never merged; fiction and
   fact are never matched.
7. **Audit log**: every decision beyond a record's own key is kept with the original
   values and the reason.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field

from app.domain.enums import (
    GraphNodeType,
    IdentifierScheme,
    NodeNature,
    ResolutionMethod,
    ResolutionOutcome,
)
from app.domain.graph_types import IDENTIFIER_LABELS, NODE_TYPES
from app.graph import isic
from app.graph.drafts import (
    DecisionDraft,
    IdentifierClaim,
    IssueDraft,
    NodeDraft,
    SourceRef,
    node_key,
)
from app.graph.names import (
    MatchStrength,
    NameMatch,
    compare_normalized,
    currency_is_valid,
    isin_is_valid,
    iso_alpha2_is_valid,
    iso_alpha3_is_valid,
    mic_is_valid,
    name_words,
    normalize_name,
)
from app.graph.rules import CodeClaim
from app.graph.sources import SourceSnapshot
from app.graph.validation import issue

_FORMAT_CHECKS: dict[IdentifierScheme, Callable[[str], bool]] = {
    IdentifierScheme.ISO3166_ALPHA2: iso_alpha2_is_valid,
    IdentifierScheme.ISO3166_ALPHA3: iso_alpha3_is_valid,
    IdentifierScheme.ISO4217: currency_is_valid,
    IdentifierScheme.MIC: mic_is_valid,
    IdentifierScheme.ISIN: isin_is_valid,
    IdentifierScheme.ISIC_REV4_DIVISION: lambda code: len(code) == 2 and code.isdigit(),
    IdentifierScheme.ISIC_REV4_SECTION: lambda code: code in isic.SECTIONS_BY_CODE,
    IdentifierScheme.PROVIDER_SERIES: lambda value: ":" in value and len(value) <= 128,
    IdentifierScheme.LISTING: lambda value: ":" in value and mic_is_valid(value.split(":")[0]),
}

_CODE_SCHEME = {
    GraphNodeType.CURRENCY: IdentifierScheme.ISO4217,
    GraphNodeType.SECTOR: IdentifierScheme.ISIC_REV4_SECTION,
    GraphNodeType.MARKET: IdentifierScheme.MIC,
}

# Kinds whose records are compared by name for possible duplicates.
_DUPLICATE_CHECKED = (GraphNodeType.COMPANY, GraphNodeType.ECONOMIC_VARIABLE)


@dataclass
class Resolution:
    nodes: dict[str, NodeDraft]
    # ISO 3166-1 alpha-3 code → the one country node it identifies.
    alpha3_index: dict[str, str]
    issues: list[IssueDraft] = field(default_factory=list)
    decisions: list[DecisionDraft] = field(default_factory=list)
    rejected: int = 0


def resolve(
    snapshot: SourceSnapshot, record_nodes: list[NodeDraft], claims: list[CodeClaim]
) -> Resolution:
    result = Resolution(nodes={}, alpha3_index={})
    for node in record_nodes:
        if node.key in result.nodes:
            first = result.nodes[node.key]
            result.issues.append(
                issue(
                    "unsupported_merge",
                    node.key,
                    f"Records {first.sources[0].label} and {node.sources[0].label} would share "
                    f"the key '{node.key}'. The second was not added.",
                    node_key=node.key,
                )
            )
            result.rejected += 1
            continue
        result.nodes[node.key] = node
    _derived_nodes(claims, result)
    extra = _alpha3_claims(snapshot, result.nodes)
    _attach_identifiers(result, extra)
    _name_candidates(result)
    return result


# --- Stage 2: one node per code ----------------------------------------------------------------


def _derived_nodes(claims: list[CodeClaim], result: Resolution) -> None:
    grouped: dict[tuple[GraphNodeType, str], list[CodeClaim]] = defaultdict(list)
    for claim in claims:
        grouped[(claim.node_type, claim.code.strip().upper())].append(claim)

    for (node_type, code), group in sorted(grouped.items()):
        scheme = _CODE_SCHEME[node_type]
        label = IDENTIFIER_LABELS[scheme]
        type_label = NODE_TYPES[node_type].label.lower()
        if not _FORMAT_CHECKS[scheme](code):
            result.issues.append(
                issue(
                    "invalid_code",
                    ", ".join(claim.source.label for claim in group),
                    f"'{code}' is not a valid {label} code, so no {type_label} node was made "
                    "for it.",
                    details={"code": code, "records": [claim.source.label for claim in group]},
                )
            )
            result.rejected += 1
            continue
        natures = {claim.nature for claim in group}
        nature = (
            NodeNature.REAL
            if NodeNature.REAL in natures
            else NodeNature.SAMPLE
            if NodeNature.SAMPLE in natures
            else NodeNature.FICTIONAL
        )
        sources = _unique_sources(claim.source for claim in group)
        key, name, description, attributes = _describe_code(node_type, code)
        if node_type is GraphNodeType.SECTOR:
            sources.append(
                SourceRef("isic_rev4_sections", code, None, "ISIC Rev. 4", ("code", "title"))
            )
        result.nodes[key] = NodeDraft(
            key=key,
            node_type=node_type,
            display_name=name,
            description=description,
            nature=nature,
            attributes=attributes,
            sources=sources,
            identifiers=[IdentifierClaim(scheme, code, group[0].source)],
            derived=True,
        )
        for claim in group:
            result.decisions.append(
                DecisionDraft(
                    source=claim.source,
                    source_values={"code": claim.code},
                    node_key=key,
                    method=ResolutionMethod.IDENTIFIER,
                    outcome=ResolutionOutcome.LINKED,
                    identifier=f"{scheme.value}:{code}",
                    rationale=_link_rationale(node_type, code, claim),
                )
            )


def _describe_code(node_type: GraphNodeType, code: str) -> tuple[str, str, str, dict[str, object]]:
    if node_type is GraphNodeType.CURRENCY:
        return (
            node_key(node_type, code),
            code,
            f"The currency with ISO 4217 code {code}. RUMIN records the code only; it holds "
            "no exchange rates.",
            {"code": code},
        )
    if node_type is GraphNodeType.SECTOR:
        section = isic.SECTIONS_BY_CODE[code]
        return (
            node_key(node_type, f"isic4-{code}"),
            section.title,
            f"Section {code} of ISIC Rev. 4, covering divisions "
            f"{section.first_division:02d} to {section.last_division:02d}.",
            {
                "code": code,
                "classification": isic.CLASSIFICATION_SYSTEM,
                "first_division": f"{section.first_division:02d}",
                "last_division": f"{section.last_division:02d}",
            },
        )
    return (
        node_key(node_type, code),
        code,
        f"The trading venue with ISO 10383 MIC {code}, as declared in price-file manifests. "
        "RUMIN holds no other details about it.",
        {"mic": code},
    )


def _link_rationale(node_type: GraphNodeType, code: str, claim: CodeClaim) -> str:
    if node_type is GraphNodeType.SECTOR:
        return (
            f"{claim.source.label} has an ISIC Rev. 4 division in section {code}; every "
            f"industry in that section links to the same sector node."
        )
    label = IDENTIFIER_LABELS[_CODE_SCHEME[node_type]]
    return (
        f"{claim.source.label} names {label} {code}; every record naming that code refers to "
        f"the same {NODE_TYPES[node_type].label.lower()}."
    )


def _unique_sources(sources: Iterable[SourceRef]) -> list[SourceRef]:
    seen: dict[str, SourceRef] = {}
    for source in sources:
        seen.setdefault(source.label, source)
    return list(seen.values())


# --- Stage 3: provider identifiers --------------------------------------------------------------


def _alpha3_claims(
    snapshot: SourceSnapshot, nodes: dict[str, NodeDraft]
) -> list[tuple[str, IdentifierClaim]]:
    """ISO alpha-3 codes stated by series whose catalogue entry links a reference country."""
    claims: list[tuple[str, IdentifierClaim]] = []
    for series in snapshot.series:
        if not (series.country_id and series.country_iso3):
            continue
        key = node_key(GraphNodeType.COUNTRY, series.country_id)
        if key not in nodes:
            continue
        dataset = snapshot.datasets.get(series.dataset_id)
        source = SourceRef(
            "economic_series",
            series.id,
            series.dataset_id,
            dataset.version if dataset else None,
            ("country_iso3", "country_id"),
        )
        claims.append(
            (key, IdentifierClaim(IdentifierScheme.ISO3166_ALPHA3, series.country_iso3, source))
        )
    return claims


# --- Identifier index: attach, or flag conflicts -----------------------------------------------


def _attach_identifiers(result: Resolution, extra: list[tuple[str, IdentifierClaim]]) -> None:
    claims: list[tuple[str, IdentifierClaim, bool]] = [
        (node.key, claim, True) for node in result.nodes.values() for claim in node.identifiers
    ]
    claims.extend((key, claim, False) for key, claim in extra)
    for node in result.nodes.values():
        node.identifiers = []

    index: dict[tuple[IdentifierScheme, str], dict[str, list[tuple[IdentifierClaim, bool]]]] = (
        defaultdict(lambda: defaultdict(list))
    )
    for key, claim, own in claims:
        if not _FORMAT_CHECKS[claim.scheme](claim.value):
            result.issues.append(
                issue(
                    "invalid_identifier",
                    claim.source.label,
                    f"'{claim.value}' is not a valid {IDENTIFIER_LABELS[claim.scheme]}; it was "
                    f"not attached to {key}.",
                    node_key=key,
                    details={"scheme": claim.scheme.value, "value": claim.value},
                )
            )
            continue
        index[(claim.scheme, claim.value)][key].append((claim, own))

    for (scheme, value), by_node in sorted(index.items()):
        label = f"{scheme.value}:{value}"
        if len(by_node) == 1:
            ((key, group),) = by_node.items()
            node = result.nodes[key]
            node.identifiers.append(group[0][0])
            for claim, own in group:
                if own:
                    continue
                result.decisions.append(
                    DecisionDraft(
                        source=claim.source,
                        source_values={"code": value},
                        node_key=key,
                        method=ResolutionMethod.EXPLICIT_LINK,
                        outcome=ResolutionOutcome.IDENTIFIER_ATTACHED,
                        identifier=label,
                        rationale=f"{claim.source.label} names the country {value} and its "
                        f"catalogue entry links it to {key}, so {value} is recorded as that "
                        f"country's {IDENTIFIER_LABELS[scheme]} code.",
                    )
                )
            if scheme is IdentifierScheme.ISO3166_ALPHA3:
                result.alpha3_index[value] = key
            continue
        _identifier_clash(result, scheme, value, by_node)


def _identifier_clash(
    result: Resolution,
    scheme: IdentifierScheme,
    value: str,
    by_node: dict[str, list[tuple[IdentifierClaim, bool]]],
) -> None:
    keys = tuple(sorted(by_node))
    types = {result.nodes[key].node_type for key in keys}
    same_kind_primary = len(types) == 1 and NODE_TYPES[next(iter(types))].primary_scheme is scheme
    label = f"{scheme.value}:{value}"
    code = "unsupported_merge" if same_kind_primary else "identifier_conflict"
    message = (
        f"{', '.join(keys)} share {IDENTIFIER_LABELS[scheme]} {value}. They were not merged: "
        "records of this kind are never merged automatically. Review which is correct."
        if same_kind_primary
        else f"{IDENTIFIER_LABELS[scheme]} {value} is claimed for {', '.join(keys)}; it was "
        "attached to none of them."
    )
    for key in keys:
        result.issues.append(
            issue(
                code,
                key,
                message,
                node_key=key,
                details={"identifier": label, "nodes": list(keys)},
            )
        )
        for claim, _own in by_node[key]:
            result.decisions.append(
                DecisionDraft(
                    source=claim.source,
                    source_values={"identifier": value},
                    node_key=None,
                    method=ResolutionMethod.IDENTIFIER,
                    outcome=ResolutionOutcome.CANDIDATE_FLAGGED
                    if same_kind_primary
                    else ResolutionOutcome.CONFLICT,
                    identifier=label,
                    candidate_node_keys=keys,
                    rationale=message,
                )
            )


# --- Stages 4 to 6: names suggest, never merge -------------------------------------------------


# A word shared by more names than this identifies nothing on its own ("company", "india",
# or "synthetic" in a generated dataset), so it is not used to find candidate pairs.
# Pairs with the same normalised name, or the same words in another order, are always
# compared; what can be missed is a partial match made only of such common words.
MAX_BLOCK_SIZE = 100


@dataclass(frozen=True)
class _Named:
    node: NodeDraft
    normalized: str
    words: frozenset[str]


def _named(nodes: Iterable[NodeDraft]) -> list[_Named]:
    """Each name normalised once, however many names it is compared with."""
    named = []
    for node in nodes:
        normalized = normalize_name(node.display_name)
        if normalized:
            named.append(_Named(node, normalized, name_words(normalized)))
    return named


def _candidate_pairs(
    left: list[_Named], right: list[_Named] | None = None
) -> Iterator[tuple[_Named, _Named]]:
    """Pairs worth comparing ("blocking"): the same normalised name, the same words, or a
    shared word used by at most ``MAX_BLOCK_SIZE`` names. Unrelated pairs are never
    compared, so the cost follows the number of plausible pairs rather than n². With one
    list, each pair is returned once.
    """
    same = right is None
    pool = left if right is None else right
    by_name: dict[str, list[_Named]] = defaultdict(list)
    by_words: dict[frozenset[str], list[_Named]] = defaultdict(list)
    by_word: dict[str, list[_Named]] = defaultdict(list)
    for item in pool:
        by_name[item.normalized].append(item)
        by_words[item.words].append(item)
        for word in item.words:
            by_word[word].append(item)
    seen: set[tuple[str, str]] = set()
    for item in left:
        others = [*by_name.get(item.normalized, ()), *by_words.get(item.words, ())]
        for word in item.words:
            block = by_word.get(word, ())
            if len(block) <= MAX_BLOCK_SIZE:
                others.extend(block)
        for other in others:
            if other.node.key == item.node.key:
                continue
            first, second = (
                (other, item) if same and other.node.key < item.node.key else (item, other)
            )
            if (first.node.key, second.node.key) not in seen:
                seen.add((first.node.key, second.node.key))
                yield first, second


def _compare(first: _Named, second: _Named) -> NameMatch | None:
    return compare_normalized(first.normalized, first.words, second.normalized, second.words)


def _name_candidates(result: Resolution) -> None:
    by_type: dict[GraphNodeType, list[NodeDraft]] = defaultdict(list)
    for node in sorted(result.nodes.values(), key=lambda item: item.key):
        by_type[node.node_type].append(node)

    for node_type in _DUPLICATE_CHECKED:
        for first, second in _candidate_pairs(_named(by_type[node_type])):
            match = _compare(first, second)
            if match is None:
                continue
            if first.node.nature is not second.node.nature:
                _ruled_out(result, first.node, second.node, match.reason)
            elif match.strength is MatchStrength.STRONG:
                _flag(result, "possible_duplicate", first.node, second.node, match.reason)
            else:
                _flag(result, "similar_name", first.node, second.node, match.reason)

    companies = _named(by_type[GraphNodeType.COMPANY])
    for instrument, company in _candidate_pairs(
        _named(by_type[GraphNodeType.INSTRUMENT]), companies
    ):
        match = _compare(instrument, company)
        if match is None:
            continue
        compatible = (instrument.node.nature is NodeNature.REAL) == (
            company.node.nature is NodeNature.REAL
        )
        if compatible:
            _flag(result, "possible_issuer", instrument.node, company.node, match.reason)
        else:
            _ruled_out(result, instrument.node, company.node, match.reason)


def _flag(result: Resolution, code: str, first: NodeDraft, second: NodeDraft, reason: str) -> None:
    keys = (first.key, second.key)
    consequence = {
        "possible_duplicate": "Both are kept and flagged for review; a name alone never merges "
        "entities.",
        "similar_name": "Often a parent and a subsidiary, which are different entities. Noted; "
        "nothing was merged.",
        "possible_issuer": "They were not linked: a similar name is not evidence that the "
        "company issued the instrument.",
    }[code]
    message = f'"{first.display_name}" and "{second.display_name}": {reason} {consequence}'
    for key in keys if code == "possible_duplicate" else keys[:1]:
        result.issues.append(
            issue(code, key, message, node_key=key, details={"candidates": list(keys)})
        )
    result.decisions.append(
        DecisionDraft(
            source=first.sources[0],
            source_values={"name": first.display_name, "compared_with": second.display_name},
            node_key=None,
            method=ResolutionMethod.NAME_COMPARISON,
            outcome=ResolutionOutcome.CANDIDATE_FLAGGED,
            candidate_node_keys=keys,
            rationale=message,
        )
    )


def _ruled_out(result: Resolution, first: NodeDraft, second: NodeDraft, reason: str) -> None:
    keys = (first.key, second.key)
    message = (
        f'"{first.display_name}" ({first.nature.value}) and "{second.display_name}" '
        f"({second.nature.value}): {reason} Ruled out: fiction or sample data is never matched "
        "with real-world records."
    )
    result.issues.append(
        issue(
            "match_ruled_out", first.key, message, node_key=first.key, details={"nodes": list(keys)}
        )
    )
    result.decisions.append(
        DecisionDraft(
            source=first.sources[0],
            source_values={"name": first.display_name, "compared_with": second.display_name},
            node_key=None,
            method=ResolutionMethod.NAME_COMPARISON,
            outcome=ResolutionOutcome.REJECTED,
            candidate_node_keys=keys,
            rationale=message,
        )
    )
