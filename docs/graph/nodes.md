# Node model

A node is one entity RUMIN holds a record for. Only types the stored data supports
exist: there is no commodity, bank or government node, because no structured source for
them is loaded.

## Node types

| Type | Label | Built from | Key | Primary identifier | Nature today |
|---|---|---|---|---|---|
| `country` | Country | `countries` (Phase 1) | `country:<record id>` | ISO 3166-1 alpha-2 (alpha-3 attached from the series catalogue) | real |
| `currency` | Currency | every ISO 4217 code a record names (country, series, instrument) | `currency:<code>` | ISO 4217 | real |
| `sector` | Sector | the ISIC Rev. 4 section containing an industry's division | `sector:isic4-<letter>` | ISIC Rev. 4 section | real |
| `industry` | Industry | `industries` (Phase 1) | `industry:<record id>` | ISIC Rev. 4 division | real |
| `company` | Company | `companies` (Phase 1) | `company:<record id>` | none (RUMIN key only) | fictional |
| `economic_variable` | Economic variable | `economic_variables` (Phase 1) — definitions, no values | `variable:<record id>` | none | real (definitions) |
| `data_series` | Data series | `economic_series` (Phase 2 catalogue) | `series:<record id>` | provider series key, e.g. `worldbank-wdi:FP.CPI.TOTL.ZG\|IND` | real |
| `instrument` | Instrument | `instruments` (imported price files) | `instrument:<record id>` | ISIN, when the manifest gives one | sample or real, from its dataset |
| `market` | Market | the MIC declared in a price-file manifest | `market:<mic>` | ISO 10383 MIC | real |

Keys match `^(country|currency|sector|industry|company|variable|series|instrument|market):[a-z0-9][a-z0-9_.-]{0,95}$`;
record IDs are lower-cased. The API rejects anything else with 422.

## Fields

| Field | Meaning |
|---|---|
| `id` | The deterministic key (above). Stable across builds |
| `type` | One of the nine types |
| `name` | The display name, exactly as the source record gives it |
| `subtitle` | Words that tell similar names apart, e.g. "Fictional company · Air transport · India", "ISIC Rev. 4 division 51 · Transportation and storage", "World Development Indicators · India · annual" |
| `description` | The source record's description |
| `nature` | `real` (reference data or a provider catalogue), `fictional` (the sample network) or `sample` (built from sample data, such as a synthetic price file) |
| `quality_status` | `validated`, or `warning` when a validation rule flagged the node (see [construction](construction.md#validation)) |
| `identifiers` | External identifiers, each with its scheme and the record that stated it. One identifier belongs to at most one node — the database enforces it |
| `attributes` | Descriptive, type-specific fields: codes, units, frequency, classification. **Never financial figures** |
| `sources` | The source records the node was built from: table, record ID, dataset, dataset version and the fields used |
| `degree`, `in_degree`, `out_degree` | Current edges touching the node. Data coverage, not importance |
| `component` | The node's connected component in the latest build (1 = largest) |
| `data_status` | Series and instruments only: `values_stored` or `definition_only`. Read live from the Phase 2 tables, never assumed |
| `first_build_id`, `changed_build_id`, `retired_build_id` | The build that added the node, last changed it and retired it |
| `created_at`, `updated_at` | Timestamps of the row |

Degree, in/out degree and component are **derived** from the edges and refreshed by every
build without counting as a change to the node.

## Nature: real, fictional, sample

Nature is taken from the source records, never inferred from names:

- **Countries, industries, companies and variables** (Phase 1 records): **fictional**
  when the record is marked `is_fictional` (all 12 sample companies), otherwise **real**.
  The sample dataset as a whole is illustrative, but its countries, ISIC industries and
  variable definitions describe real things.
- **Series and instruments**: **sample** when their dataset is flagged as illustrative
  sample data (for example the smoke test's synthetic price file), otherwise **real**.
- **Currencies, sectors and markets** (derived from codes): **real** if any real record
  names the code, otherwise sample, otherwise fictional.

Fiction and fact are kept apart by rule: an evidence-backed edge may not touch a
fictional or sample node, a business relationship may not join a fictional company to a
real one, and entity resolution never matches a fictional record with a real one
(see [entity resolution](entity-resolution.md)).

## What a node does not contain

- **No financial values.** Company financial statements are not stored anywhere in
  RUMIN. A series node says whether values are stored; the values stay in the Phase 2
  tables and are shown in the Data Explorer.
- **No importance score.** Degree is shown with the note "data coverage, not importance",
  and no ranking of companies is computed.
- **No invented identifiers.** A fictional company has none; its RUMIN key is shown
  instead.

## Example

```json
{
  "id": "company:co_deltrin_refining",
  "type": "company",
  "name": "Deltrin Refining",
  "subtitle": "Fictional company · Refined petroleum products · India",
  "nature": "fictional",
  "quality_status": "validated",
  "degree": 8,
  "primary_identifier": null,
  "data_status": "not_applicable",
  "identifiers": [],
  "sources": [{ "table": "companies", "record_id": "co_deltrin_refining",
                "dataset_id": "rumin-sample", "dataset_version": "1.0.0",
                "fields": ["name", "is_fictional"] }],
  "in_degree": 3,
  "out_degree": 5,
  "component": 1,
  "first_build_id": 1,
  "changed_build_id": 1
}
```

(`GET /api/v1/graph/nodes/company:co_deltrin_refining`, abridged.)
