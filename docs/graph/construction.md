# Construction pipeline

How `python -m app.graph build` turns stored records into the graph — repeatably, with a
validation report whose numbers come from the run itself. Code: `backend/app/graph/`
(`sources.py` → `rules.py` → `resolution.py` → `validation.py` → `assemble.py` →
`persist.py`, orchestrated by `build.py`).

## Running it

```bash
make graph                              # = python -m app.graph build (in backend/)
python -m app.graph validate            # what a build would do; writes nothing
python -m app.graph status              # latest build; are the sources unchanged since?
python -m app.graph builds [--limit N]  # recent builds with their changes
python -m app.graph report [BUILD]      # one build's full report (default: latest)
```

Exit codes: `0` success (warnings allowed); `1` the build failed, or `validate` found
something a build would reject; `2` nothing could run (another build is running, the
database is not migrated, or the requested build does not exist).

## The steps

1. **Read** every source record — countries, industries, companies, variables and
   relationships (Phase 1), the series catalogue and instruments (Phase 2), and the
   datasets with their versions — into plain records, and fingerprint them (SHA-256
   over every record and the rules version).
2. **Make nodes** with rules N01–N09, one per record, or one per code for currencies,
   sectors and markets. Records that cannot become a node (no ID, no name, an invalid
   code) are rejected with an issue.
3. **Resolve entities** ([entity resolution](entity-resolution.md)): identifiers,
   explicit links, name candidates — flag, never merge.
4. **Make edges** with rules R01–R12. Every edge carries evidence: the source record,
   what it says, and the transformation.
5. **Validate** every edge against the type registry (below). Structural problems
   reject; doubtful identity flags; information is noted.
6. **Describe** nodes (subtitles that tell similar names apart, search text) and compute
   metrics: components, degree, density, provenance coverage.
7. **Persist**: compare each node and edge with its stored row by content hash — add,
   change, retire or leave alone. Nothing is deleted.
8. **Record** the build: counts, changes, sources, fingerprint, metrics, issues and
   resolution decisions.

A build is one transaction for the graph: if anything fails, the graph is left as it was,
the build is marked `failed` with a short error summary, and the command exits 1. Only
one build runs at a time; a build still marked `running` after an hour is treated as
crashed and marked failed by the next one.

## Construction rules

**Nodes**

| Rule | Name | Reads | What it does |
|---|---|---|---|
| N01 | `country` | countries | One node per country record. |
| N02 | `currency` | countries.currency_code, economic_series.currency, instruments.currency | One node per ISO 4217 code named by any record; records naming the same code are linked to the same node. |
| N03 | `sector` | industries.classification_code + the ISIC Rev. 4 structure | One node per ISIC Rev. 4 section that contains an industry's division. |
| N04 | `industry` | industries | One node per industry record. |
| N05 | `company` | companies | One node per company record. |
| N06 | `economic_variable` | economic_variables | One node per variable definition. |
| N07 | `data_series` | economic_series | One node per catalogued series, whether or not values have been retrieved. |
| N08 | `instrument` | instruments | One node per imported instrument. |
| N09 | `market` | instruments.exchange_mic | One node per ISO 10383 MIC declared in a price-file manifest. |

**Edges**

| Rule | Name | Reads | Produces | Evidence status | What it does |
|---|---|---|---|---|---|
| R01 | `curated_relationship` | relationships | an edge of the relationship's own type | model_assumption | Each curated relationship becomes an edge of the same type, keeping its description, rationale, assumed polarity and illustrative strength. |
| R02 | `company_industry` | companies.industry_id | in_industry | analyst_created | A company's primary industry, as written in its record. |
| R03 | `company_country` | companies.country_id | domiciled_in | analyst_created | A company's country of domicile, as written in its record. |
| R04 | `variable_country` | economic_variables.country_id | measured_for | analyst_created | The economy a variable describes, as written in its definition. |
| R05 | `industry_sector` | industries.classification_code | in_sector | evidence_backed | An ISIC Rev. 4 division belongs to the section whose division range contains it. |
| R06 | `country_currency` | countries.currency_code | has_currency | evidence_backed | A country's ISO 4217 currency, as cited in its record. |
| R07 | `series_country` | economic_series.country_id, economic_series.country_iso3 | covers | evidence_backed | The country a series describes: its catalogue link, or else its ISO alpha-3 code when that code already identifies exactly one country node. |
| R08 | `series_variable` | economic_series.variable_id, economic_series.variable_relation | related_measure_of | analyst_created | A curator's link from a series to a variable, kept with the stated difference. |
| R09 | `series_currency` | economic_series.currency | expressed_in | evidence_backed | The currency of a series' unit. |
| R10 | `instrument_market` | instruments.exchange_mic | listed_on | unverified | The market declared for an instrument in its price-file manifest. |
| R11 | `instrument_currency` | instruments.currency | quoted_in | unverified | The currency declared for an instrument's prices in its manifest. |
| R12 | `instrument_country` | instruments.country_id | associated_with | unverified | The country a manifest links an instrument to (the manifest does not say how). |

What the rules never do: create an edge because two records share an industry, a
country or a dataset; infer a supplier, customer or lender; convert a currency; or give
a relationship a strength or confidence nobody stated.

## Validation

**Structural problems reject; doubtful identity flags; information is noted.** Rejected
items are not stored (their issues are); flagged items are stored with quality status
`warning`; noted items are stored unchanged.

| Rule | Subject | Severity | Outcome | What it checks |
|---|---|---|---|---|
| `missing_node_key` | node | error | **rejected** | The source record has no ID, so no stable node key can be made. |
| `missing_name` | node | error | **rejected** | The record has no name to display. |
| `missing_provenance` | node | error | **rejected** | The node would have no source record to explain it. |
| `invalid_code` | node | error | **rejected** | A code that would identify a currency, sector or market is not valid in its scheme, so no node is made for it (and no edge leads to it). |
| `unknown_classification` | node | warning | **flagged** | The industry's code is not a division of ISIC Rev. 4, so it is given no sector. |
| `isolated_node` | node | info | **noted** | The node has no edge to any other node. |
| `invalid_identifier` | identifier | warning | **flagged** | An identifier is not in its scheme's format; it is not attached to the node. |
| `identifier_conflict` | identifier | warning | **flagged** | The same identifier is claimed for different nodes; it is attached to none of them and the nodes are flagged for review. |
| `unsupported_merge` | resolution | warning | **flagged** | Two records of a kind RUMIN never merges automatically share an identifier. Both are kept and flagged for review. |
| `possible_duplicate` | resolution | warning | **flagged** | Two records' names are identical once normalised. Both are kept and flagged for review: a name alone never merges entities. |
| `similar_name` | resolution | info | **noted** | Every word of one name appears in another (often a parent and a subsidiary, which are different entities). Noted for review; nothing is merged. |
| `possible_issuer` | resolution | info | **noted** | An instrument's name is similar to a company's. They are not linked: a similar name is not evidence that the company issued the instrument. |
| `match_ruled_out` | resolution | info | **noted** | Similar names, but one record is fictional or sample data and the other is not, so they cannot be the same entity. |
| `unknown_edge_type` | edge | error | **rejected** | The relationship type has no definition in the graph's type registry. |
| `missing_source_node` | edge | error | **rejected** | The edge's source does not exist in the graph. |
| `missing_target_node` | edge | error | **rejected** | The edge's target does not exist in the graph. |
| `reversed_direction` | edge | error | **rejected** | The edge points the wrong way: its type is defined from the target's kind to the source's kind. |
| `endpoint_types_not_allowed` | edge | error | **rejected** | The edge's type is not defined between these kinds of node. |
| `self_loop` | edge | error | **rejected** | The edge connects a node to itself. |
| `missing_evidence` | edge | error | **rejected** | The edge has no evidence record, so nothing could explain why it exists. |
| `evidence_status_not_allowed` | edge | error | **rejected** | The edge's evidence status is not allowed for its type (e.g. an assumed variable-to-variable effect claimed as evidence-backed). |
| `invalid_validity_period` | edge | error | **rejected** | The validity period ends before it starts. |
| `future_validity` | edge | warning | **flagged** | The validity period starts in the future. |
| `reality_mismatch` | edge | error | **rejected** | The edge would mix fiction and fact: an evidence-backed edge touching a fictional or sample node, or a business relationship between a fictional and a real company. |
| `duplicate_edge` | edge | info | **noted** | More than one record states the same relationship; it is stored once, with every record as evidence. |
| `unresolved_reference` | edge | info | **noted** | A record refers to an entity that is not in the graph, so no edge was made. |

## The report

Every count comes from the run: `processed = valid + flagged + rejected`, for nodes and
for edges. The sample dataset plus the World Bank catalogue gives:

```
Graph build #1 · completed · 0.12 s · rules v1

GRAPH VALIDATION REPORT

Nodes processed: 50
Valid nodes: 50
Flagged nodes: 0
Rejected nodes: 0

Edges processed: 97
Valid edges: 97
Flagged edges: 0
Rejected edges: 0

Changes: nodes +50 added, 0 changed, 0 retired, 0 unchanged · edges +97 added, 0 changed, 0 retired, 0 unchanged
Graph: 50 nodes · 97 edges · 1 connected component(s) · evidence on 97 of 97 edges
Issues: 0 error(s) · 0 warning(s) · 0 note(s)
Entity resolution:
    11  identifier_attached by explicit link
    13  linked by identifier
```

With the smoke test's synthetic price file imported, the graph has 52 nodes and 99 edges
(an instrument and its market, with two unverified edges). On the synthetic benchmark
networks ([performance](performance.md)), the validator rejected the evidence-backed
sector links of the fictional benchmark industries (`reality_mismatch`) and noted the
sectors left isolated — the rules working as designed at scale.

The same report is available from `GET /api/v1/graph/builds/{id}` (with issue counts by
rule and resolution decisions by outcome) and each issue from `GET /api/v1/graph/issues`.

## Rebuilds and change tracking

Keys are deterministic and content is hashed, so rebuilding from unchanged sources adds,
changes and retires nothing (the smoke test checks it on every CI run). When a source
changes, the next build reports exactly what moved:

| Situation | Result |
|---|---|
| A new record | Its node and edges are **added** |
| A changed record (name, description, codes, qualifiers) | The node or edge is **changed**: new content, `changed_build_id` updated |
| A deleted record | Its node and edges are **retired** (kept, with `retired_build_id`) |
| A record that comes back | Its node or edge is **added** again |
| Only the graph around a node changed | Degree and component are refreshed, not counted as a change |

`GET /api/v1/graph/overview` compares the latest build's fingerprint with the current
sources and says whether the graph is **current** or **stale** (the answer is cached for up
to 30 seconds per API process — see [performance](performance.md)).
