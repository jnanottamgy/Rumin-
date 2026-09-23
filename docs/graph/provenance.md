# Provenance

Every edge in the graph can answer **"why does this connection exist?"** — from records
stored in the database, not from text written afterwards. An edge without evidence is
rejected (`missing_evidence`); an edge whose evidence is incomplete says what is missing
instead of filling the gap.

## What an evidence record holds

Each edge has at least one row in `graph_edge_evidence` (more when several records state
the same relationship):

| Field | Meaning | Example (`in_sector`: Air transport → Transportation and storage) |
|---|---|---|
| `rule` | The construction rule that made the edge | `R05 industry_sector` |
| `source_kind` | What kind of source it is: `reference_dataset`, `series_catalogue`, `price_file_manifest` or `classification_standard` | `classification_standard` |
| `source_table`, `source_record_id` | The record the edge came from | `industries` / `ind_air_transport` |
| `dataset_id`, `dataset_version` | The dataset and version that record belongs to | `rumin-sample` 1.0.0 |
| `statement` | What the source says, in words | "industries.classification_code = 51 (ISIC Rev. 4)." |
| `transformation` | How the rule turned the statement into this edge | "ISIC Rev. 4 places divisions 49 to 53 in section H; division 51 is in that range." |
| `derivation` | `direct` (the record states the relationship) or `derived` (computed from it) | `derived` |
| `derived_from` | For derived edges, what they were computed from | the record's classification code and the ISIC Rev. 4 section table in `app/graph/isic.py` |
| `citation`, `citation_url` | The external source the record cites, when it cites one. URLs are shown only if they are web links | the UN Statistics Division's ISIC Rev. 4 publication |
| `retrieved_at` | For provider data: when the provider last delivered the source. Empty otherwise | — |
| `recorded_at` | When the source record was loaded into RUMIN | 2026-09-23 14:38 UTC |

The API adds the evidence status's definition, the edge type's meaning and its caveat,
and composes one paragraph that answers the question directly:

> *Air transport — belongs to → Transportation and storage. Rule R05 industry_sector built
> it from industries/ind_air_transport (dataset rumin-sample, 1.0.0): industries.
> classification_code = 51 (ISIC Rev. 4). Evidence status: Evidence-backed. …*

## Where each kind of edge gets its evidence

| Edges | Source | Direct or derived | Cited source |
|---|---|---|---|
| Curated relationships (R01) | a `relationships` record in the reference dataset: type, endpoints, rationale, assumed polarity, illustrative strength | direct | the record's reference, if any (none of the 41 sample relationships cites one) |
| Company industry and domicile, variable economy (R02–R04) | the entity record's field | direct | — |
| Industry → sector (R05) | the industry's ISIC code and the ISIC Rev. 4 section table | **derived** (8 edges) | ISIC Rev. 4 (UN Statistics Division) |
| Country → currency (R06) | the country record's ISO 4217 code | direct | the record's ISO reference |
| Series → country, variable, currency (R07–R09) | the series catalogue entry | direct (a series without a catalogue link to a country is matched by its ISO alpha-3 code only when exactly one country carries that code, and the match is logged as a resolution decision) | World Development Indicators, with the original source named on each series |
| Instrument → market, currency, country (R10–R12) | the price-file manifest | direct | the manifest's dataset; status **unverified** |

In the sample graph all 97 edges have evidence, 32 cite an external source, and 8 are
derived. These figures are computed by each build (`provenance` in the build metrics).

## Rules

- **No fabricated evidence.** Statements are generated from stored field values; a
  citation appears only when the source record carries one. RUMIN never writes a
  source it did not receive, and never invents a URL.
- **No hidden gaps.** When a record cites nothing, the panel says "None — the record does
  not cite an outside source". For a catalogued series whose values were never retrieved,
  retrieval reads "Not yet — no values have been retrieved", and its node says "Definition
  only — no values stored". For reference data, retrieval reads "Not applicable (not
  provider data)".
- **Two times, kept apart.** `recorded_at` (when RUMIN loaded the record) and
  `retrieved_at` (when a provider delivered data) answer different questions and are never
  merged into a single "freshness".
- **Evidence changes with its edge.** When an edge's content changes, its evidence is
  rewritten in the same build; a retired edge keeps its last evidence as history.
- **Node provenance too.** Each node lists the source records it was built from (table,
  record ID, dataset, version and fields used), and derived nodes (currencies, sectors,
  markets) list every record that named their code.

## Where to see it

- **Explorer:** select a line (or a relationship in a node's panel) — the panel shows
  "Why this connection exists", every evidence record, the status definition and "What it
  does not mean".
- **API:** `GET /api/v1/graph/edges/{id}`.
- **Database:** `graph_edge_evidence`, joined on `edge_id`; `graph_resolution_decisions`
  for identity decisions.
