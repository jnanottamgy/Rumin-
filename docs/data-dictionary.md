# Data dictionary

Field-level definitions for everything RUMIN stores or returns, followed by a catalogue of
the illustrative sample dataset. For tables, keys and constraints see
[data-model.md](data-model.md); for the wire format see [api.md](api.md).

## What the sample data is — and is not

- **Real concepts, cited:** the 3 countries (ISO 3166-1 and ISO 4217 codes), the 8
  industries (UN ISIC Rev. 4 divisions) and the definitions of the 7 economic variables,
  each with a reference to the publisher of the underlying statistic.
- **Fictional:** all 12 companies. Names were invented; any resemblance to a real company
  is unintended. They are flagged `is_fictional: true` and labelled "Fictional" in the UI.
- **Illustrative assumptions:** all 41 relationships. Each has a written rationale, but
  none has been estimated or validated: every one has `evidence_level: illustrative`.
- **Absent from the sample:** prices, rates, exchange rates, financial statements, time
  series or any other observed value. The variables are *defined*, not *measured*.
  Observed values live separately, as **provider data** (Phase 2, [below](#provider-data)):
  World Bank series retrieved from the command line and prices imported from licensed
  files, each with its source, licence and retrieval time.

## Common entity fields

| Field | Type | Required | Meaning |
|---|---|---|---|
| `id` | string, ≤ 64 | yes | Stable slug with a kind prefix: `co_`, `ind_`, `cty_`, `var_`. Never reused. |
| `kind` | enum | yes | `company`, `industry`, `country` or `economic_variable`. |
| `name` | string, ≤ 200 | yes | Display name. |
| `description` | text | yes | One or two sentences on what the entity is. |
| `is_fictional` | boolean | yes | `true` for invented entities (all sample companies). A non-fictional entity must cite a `reference`; the seed loader enforces it. |
| `reference` | string, ≤ 500 | real entities | Citation of the authoritative definition (publisher, classification, series). |
| `reference_url` | https URL, ≤ 500 | no | Link to the reference. Must be `https`. |
| `attributes` | object | yes (may be empty) | Reserved for descriptive extras; empty in the sample. |
| `dataset_id` | string | yes | The dataset the record was loaded from. |
| `created_at`, `updated_at` | UTC timestamp | yes | Record bookkeeping, not business dates. |

## Company

| Field | Type | Meaning |
|---|---|---|
| `industry_id` | entity ID | The company's primary industry (an `ind_` entity). Drawn as the structural link "operates in". |
| `country_id` | entity ID | Country of domicile (a `cty_` entity). Drawn as "is domiciled in". |

## Industry

| Field | Type | Meaning |
|---|---|---|
| `classification_system` | string | The classification the code belongs to: `ISIC Rev. 4` for every sample industry. |
| `classification_code` | string, ≤ 16 | The division code in that system, e.g. `19` (manufacture of coke and refined petroleum products). |

## Country

| Field | Type | Meaning |
|---|---|---|
| `iso_alpha2` | 2 letters, unique | ISO 3166-1 alpha-2 code, e.g. `IN`. |
| `currency_code` | 3 letters | ISO 4217 code of the national currency, e.g. `INR`. |

## Economic variable

| Field | Type | Meaning |
|---|---|---|
| `unit` | string, ≤ 64 | Unit in which the variable is quoted, e.g. `USD per barrel`, `percent per annum`, `INR per USD`. |
| `value_kind` | enum | `price`, `rate`, `exchange_rate` or `index`. Decides which scenario changes are allowed (below). |
| `frequency` | enum | How often the source publishes it: `daily` … `annual`, or `irregular` (e.g. policy decisions). |
| `category` | enum | `commodity`, `monetary_policy`, `exchange_rate` or `inflation`; groups variables in the Scenario Lab. |
| `country_id` | entity ID or null | The economy the variable describes; null for global benchmarks (Brent crude). |
| `scenario_rules` | list (API only) | Kinds of change a scenario may apply, with limits — see [api.md](api.md#scenarios). Rates (`value_kind: rate`) accept only absolute changes in percentage points. |

## Relationship

| Field | Type | Meaning |
|---|---|---|
| `id` | string | `rel_…` slug. |
| `type` | enum | One of the seven relationship types; see the registry in [data-model.md](data-model.md#relationships). |
| `category` | `economic` (API) | Curated relationships are economic; structural links (derived) are `structural`. |
| `source_id`, `target_id` | entity IDs | The two ends. Read as a sentence: *source — type label → target*. |
| `directed` | boolean (API) | From the registry; `competes_with` is the only undirected type. |
| `polarity` | enum | Assumed direction of effect. `positive`: an **increase** in the source is assumed to **increase** the target measure (its costs, revenue, financing costs, or the target variable). `negative`: the opposite. `mixed`: either, depending on circumstances. `not_applicable`: the type has no direction of effect (supplies, lends to, competes with). |
| `strength` | enum | `weak`, `moderate` or `strong`: the modeller's judgement of how material the effect is. Ordinal, not a coefficient. Drawn as line weight. |
| `evidence_level` | enum | How well supported the assumption is: `illustrative` (written for demonstration), `documented` (described in a cited source), `estimated` (quantified from data), `validated` (tested against outcomes). Anything above `illustrative` must cite a `reference`. Every sample relationship is `illustrative`. |
| `description` | text | The relationship as one plain sentence. |
| `rationale` | text | Why the modeller assumes it — the economic mechanism. |
| `reference` | string or null | Source supporting the assumption; null for illustrative ones. |
| `epistemic_category` | `assumption` (API) | Always `assumption`: a relationship is part of the model, never an observation. |

## Scenario

A scenario is a stable identity with numbered, immutable versions (Phase 5): a save that
changes anything adds a [version](#version). `GET /api/v1/scenarios/{id}` returns the
scenario with its newest version's content; `GET /api/v1/scenarios` returns a summary of
each. Results are never part of a scenario: they belong to its [executions](#execution).

| Field | Type | Meaning |
|---|---|---|
| `id` | UUID | Assigned by the server. |
| `name` | string, 1–120 | The newest version's name. Required; no control characters. |
| `description` | string, ≤ 2,000 | The newest version's description: the question the scenario explores. Optional. |
| `status` | `draft` | Always: a scenario holds inputs only. |
| `template_id` | slug or null | The [template](#template) the newest version started from. |
| `current_version` | integer | The newest version's number (1, 2, 3 …). |
| `shocks` | list, 1–10 | The newest version's changes, in order ([below](#scenario-shock)). |
| `spec` | object | The newest version's other content ([below](#scenario-content)). Full scenario only. |
| `entity` | graph key or null | Summaries only: the newest version's company (`spec.entity`). |
| `versions` | list | Every version, newest first, as [version](#version) summaries. Full scenario only. |
| `latest_execution` | object or null | The most recent execution of any version, as an [execution](#execution) summary; `null` until the scenario is executed: RUMIN never shows results that were not computed. |
| `executions` | integer | Executions of all its versions. |
| `created_at`, `updated_at` | UTC timestamp | Bookkeeping; `updated_at` moves when a version is added. |

Two fields exist only in requests: `note` (≤ 500 characters: what this version changes,
stored with the version) and, for `PUT`, `base_version` — the version the edit started
from; if a newer version has been saved since, the save is refused (409).

### Scenario content

A version's content besides its name, description, template and changes: `spec` in
responses, and the same fields at the top level of a request body (`POST` and `PUT
/api/v1/scenarios`, the plan, the preview). Every part is optional in a request; the
defaults are shown. A draft may be incomplete — the [plan](#plan) says what an execution
still needs — but not malformed. Numbers are sent as decimal strings or JSON numbers and
returned as decimal strings.

| Field | Type | Meaning |
|---|---|---|
| `entity` | `company:…` graph key, or null | A company in the current knowledge graph. Models in `auto` mode whose exposure the graph states for it, directly or through its industry, are included by default. Refused while the graph has not been built. |
| `timing.start_month` | integer 1–36; default 1 | The month the changes take effect; at most the horizon. |
| `timing.duration_months` | integer 0–36; default 0 | How many months the changes last; 0 = to the end of the horizon. |
| `timing.horizon_months` | integer 1–36; default 12 | Months simulated. |
| `company.reporting_currency` | ISO 4217 code or null | The currency of the figures and of every result. |
| `company.annual_revenue`, `company.annual_operating_costs` | decimal or null | Per year, in the reporting currency; at least 0 and below 10¹⁵. Stated once for every model. |
| `markets.fx_rate` | value or null | The exchange rate (reporting currency per US dollar) every model that needs it uses: typed, or `source: "stored_observation"` for the latest stored World Bank annual average. |
| `models` | map, ≤ 10 entries | By model ID: `mode` — `auto` (default: included when a company is chosen and the graph states its exposure), `include` or `exclude`; the model's own `inputs` (≤ 20, values as below; figures shared by every model are stated once, above); its `assumptions` (≤ 20, decimals; omitted ones take the model's stated default). |
| `constraints.evidence` | `any` or `evidence_backed`; default `any` | `evidence_backed`: rely only on knowledge-graph relationships backed by evidence, for transmission and for exposure. |
| `constraints.stored_market_data` | boolean; default false | Market baselines must be stored observations, not typed values. |
| `stress_cases` | list, ≤ 5 | Alternative magnitudes of the same changes: a `name` (1–60 characters, unique ignoring case) and **either** `scale` (every change × a multiple above 0 and at most 10, at most 4 decimal places) **or** `changes` (explicit values for some of the scenario's own changes, by variable ID; the others keep their value). Every resulting value must satisfy the variable's change rules: an invalid case is refused, never clipped. |

A **value** (`markets.fx_rate`, a model input) has `value` (a decimal string, or a code for
text inputs), `unit` (for quantities: one of the model's units, e.g. `kilolitre`),
`source` (`user` or `stored_observation`) and `series_id` (the stored series to use).

### Scenario shock

| Field | Type | Meaning |
|---|---|---|
| `variable_id` | entity ID | The economic variable changed. At most once per version. |
| `change_type` | enum | `percent_change`: relative change, `value` in percent (30 = +30 %). `absolute_change`: `value` in the variable's unit; for rates, **percentage points** (0.25 = +25 basis points). |
| `value` | decimal string | Non-zero; within the variable's published limits; at most 4 decimal places. Sent as a decimal string or a JSON number; returned as an exact decimal string in plain notation (`"30"`, `"0.5"`), never a JSON number. Stored as `NUMERIC(14, 4)`. |
| `note` | string, ≤ 500 | Why this change. Optional. |
| `epistemic_category` | `scenario_input` | Always: a shock is a value the user chose, not data. |

## Dataset

| Field | Type | Meaning |
|---|---|---|
| `id`, `version` | strings | E.g. `rumin-sample` / `1.0.0`; `worldbank-wdi` / `catalogue 1.0.0`; a price file's dataset / `user import`. |
| `kind` | enum | `curated` (written for RUMIN, loaded from a file in the repository) or `provider` (retrieved from a provider or imported from a licensed file). |
| `is_illustrative` | boolean | `true` for sample data that is not real: the Phase 1 network, or a price file whose manifest says so. |
| `provenance_note` | text | Where the data comes from and how far it can be relied on. |
| `license` | string | Terms of the dataset (for price files: the licence the user declared). |
| `checksum_sha256` | hex string | Curated datasets: SHA-256 of the file the data was loaded from. |
| `loaded_at` | UTC timestamp | When the dataset record was created. |
| `provider_id` | string | Provider datasets: who publishes it (`worldbank`, `price-file`). |
| `provider_dataset_code` | string | The provider's own id for the dataset (World Bank source `2` = WDI). |
| `license_url`, `terms_url`, `homepage_url` | https URLs | Where the licence, terms and dataset are published. |
| `attribution` | text | The attribution the licence requires; shown wherever the data is shown. |
| `update_frequency` | string | How often the provider updates it, in words. |
| `provider_last_updated` | date | When the provider last updated the dataset, **as the provider reports it** (World Bank `lastupdated`). Not the retrieval time. |

## Provider data

### Data provider

| Field | Meaning |
|---|---|
| `id`, `name`, `kind` | `worldbank` (`api`), `price-file` (`file`). |
| `authentication` | `none`, `api_key` or `not_applicable`. |
| `data_categories`, `coverage`, `update_frequency`, `reliability`, `known_limitations` | From the provider's documentation, in words. |
| `rate_limit_policy` | The provider's published limit (if any) and what RUMIN does to respect it. |
| `licensing`, `commercial_use` | The terms as understood from the provider's documentation. Not legal advice. |
| `homepage_url`, `documentation_url`, `terms_url` | Where to read more. |

### Economic series

| Field | Type | Meaning |
|---|---|---|
| `id` | slug | RUMIN's id, e.g. `wb-ind-fp-cpi-totl-zg`. |
| `provider_code`, `provider_series_key` | strings | The provider's indicator (`FP.CPI.TOTL.ZG`) and the series key within the dataset (`FP.CPI.TOTL.ZG\|IND`). |
| `name`, `description` | text | Name from the catalogue; the description is replaced by the provider's own definition at the first successful retrieval. |
| `source_organization` | text | Who originally produced the statistic, as the provider reports it. |
| `measure_type` | enum | `level`, `change` (a rate of change), `rate`, `ratio` or `exchange_rate`. |
| `unit` | string | E.g. `% change on previous year`, `INR per USD`, `US$ (current prices)`. Every value is shown with it. |
| `currency` | ISO 4217 | For monetary values; `null` otherwise. |
| `frequency` | enum | `annual`, `quarterly` or `monthly` for provider series. |
| `aggregation` | text | How the value is formed (annual average, end of period, total, …). |
| `price_basis`, `seasonal_adjustment` | enums | `nominal`/`real`/`not_applicable`; `seasonally_adjusted`/`not_seasonally_adjusted`/`not_applicable`. |
| `country_iso3`, `country_id` | code, entity ID | Geography as the provider identifies it, and the linked Phase 1 country. |
| `variable_id`, `variable_relation` | entity ID, text | A related Phase 1 variable, and **how the two measures differ** (required with a link). |
| `plausible_min`, `plausible_max` | decimals | RUMIN's review range — an assumption. Values outside it are stored and flagged. |
| `first_period`, `last_period` | dates | First and latest period with a reported value. |
| `observation_count`, `missing_count` | integers | Current periods with a value / listed without one. |
| `last_ingestion_status`, `last_ingestion_at`, `last_successful_ingestion_at` | enum, timestamps | The latest retrieval attempt, its outcome, and the last successful one. |

### Economic observation

| Field | Type | Meaning |
|---|---|---|
| `period_start`, `period_label`, `period_end` | date, string, date | The period the value describes: `2023` = 1 Jan–31 Dec 2023; `2023-Q1`; `2023-03`. |
| `value` | decimal or `null` | The value as published; `null` when the provider listed the period without a value. Never filled in. |
| `raw_value` | string | The value exactly as the provider sent it (the JSON number's literal digits). |
| `status` | enum | `reported` or `missing`. |
| `quality_status` | enum | `validated` or `warning` (flagged for review). |
| `provider_flags` | string | Flags the provider attached (World Bank `obs_status`). |
| `revision`, `is_current`, `superseded_at` | integer, boolean, timestamp | Revision number; whether this is the current value; when a later retrieval replaced it. |
| `retrieved_at` (`first_seen_at`), `last_confirmed_at` (`last_seen_at`) | timestamps | When RUMIN first received this value, and when a retrieval last returned it. |
| `retrieved_by_job_id`, `capture_id` | UUID, integer | The job that first received it and the stored response it came from. |
| `epistemic_category` | `observation` | Always, on the series. |

### Instrument and price bar

| Field | Meaning |
|---|---|
| `isin` | ISO 6166 identifier (check digit verified), optional. |
| `exchange_mic`, `symbol` | ISO 10383 market code (`XNSE` = NSE, `XBOM` = BSE) and the ticker on that exchange. A ticker is only unique on its exchange. |
| `currency` | The instrument's single currency; prices are never converted. |
| `first_trade_date`, `last_trade_date`, `bar_count` | Coverage of current prices (distinct trading days). |
| `trade_date` | The trading day (calendar date, no time zone). |
| `open`, `high`, `low`, `close` | Decimals exactly as in the imported file. |
| `adjusted_close` | Only when the file supplied one. RUMIN never computes adjustments. |
| `volume` | Whole number of units traded, when supplied. |
| `adjustment` | `unadjusted` (as traded) or `adjusted` (as supplied), declared in the manifest. |
| `source_row` | Line of the file the prices came from (1 = header). |
| `dataset_id`, revision fields | As for observations: one dataset per price, revisions kept. |

### Ingestion job and job item

| Field | Meaning |
|---|---|
| `status` | Derived from the items: `completed`, `completed_with_warnings`, `partially_failed`, `failed`, `cancelled` (or `pending`/`running`). See [ingestion](data/ingestion.md). |
| `trigger`, `parameters` | `cli`; what was requested (series, period range, file name). Never secrets. |
| `created_at`, `started_at`, `finished_at`, `heartbeat_at` | Timing; the heartbeat shows a running job is alive. |
| `items_total`, `items_succeeded`, `items_failed`, `items_skipped` | Targets and their outcomes. |
| `records_received`, `records_new`, `records_revised`, `records_unchanged`, `records_rejected` | received = new + revised + unchanged + rejected. |
| `records_missing` | Accepted periods without a value (a subset of the above). |
| `warning_count`, `error_count` | Warning-severity issues; error-severity issues (rejected records). |
| `request_count`, `bytes_received` | HTTP requests sent (including retries) and bytes received. |
| `error_summary` | A short, safe explanation of what failed. |
| Item `error_code`, `error_message` | E.g. `provider_unavailable`, `rate_limited`, `authentication_failed`, `invalid_request`, `malformed_response`, `invalid_file`, `all_records_rejected`, `storage_error`, `internal_error`, `circuit_open`, `cancelled`, `interrupted`. |

### Source capture

| Field | Meaning |
|---|---|
| `kind` | `http_response` or `file`. |
| `locator` | The request URL with credentials removed, or the imported file's name (never a local path). |
| `request_params` | The query parameters, credentials removed. |
| `http_status`, `content_type`, `received_at` | As received. |
| `size_bytes`, `sha256` | Size and SHA-256 of the exact bytes. |
| `body_gzip` | The bytes, gzip-compressed (`RUMIN_STORE_SOURCE_BODIES`). Not served by the API. |
| `provider_last_updated` | The provider's last-update date reported in that response. |

### Data-quality issue

| Field | Meaning |
|---|---|
| `rule` | One of the [quality rules](data/quality.md). |
| `severity`, `outcome` | `error`/`warning`/`info`; `rejected`/`flagged`/`noted`. |
| `message` | What was found, in words. |
| `record_key` | The period or trade date concerned. |
| `raw_record` | For rejected records: what the source sent (the only copy RUMIN keeps). |
| `observation_id`, `price_bar_id` | The stored value a flag or note is about. |
| `review_status` | `unreviewed` (no review workflow yet). |

## Knowledge graph

The graph's fields are defined in full in [`docs/graph/nodes.md`](graph/nodes.md),
[`docs/graph/edges.md`](graph/edges.md) and [`docs/graph/provenance.md`](graph/provenance.md).
The graph is derived from the records above: it adds no data of its own beyond codes those
records name (currencies, ISIC sections, markets) and the links between them.

### Graph node

| Field | Meaning |
|---|---|
| `id` | Deterministic key, `type:record-id` (`company:co_deltrin_refining`, `currency:inr`, `sector:isic4-c`). Stable across builds. |
| `type` | `country`, `currency`, `sector`, `industry`, `company`, `economic_variable`, `data_series`, `instrument` or `market`. |
| `name`, `subtitle` | The source record's name, and words that tell similar names apart. |
| `nature` | `real`, `fictional` or `sample`, taken from the source records, never from names. |
| `quality_status` | `validated`, or `warning` when a validation rule flagged it. |
| `identifiers` | External identifiers (scheme, value, the record that stated it). One identifier belongs to at most one node. |
| `sources` | The source records it was built from: table, record ID, dataset, version, fields used. |
| `degree`, `in_degree`, `out_degree` | Current edges touching it. Data coverage, not importance. |
| `component` | Its connected component in the latest build (1 = largest). |
| `data_status` | Series and instruments: `values_stored` or `definition_only`, read live. Others: `not_applicable`. |

### Graph edge

| Field | Meaning |
|---|---|
| `id` | `e-` + 16 hex characters of SHA-256 over (type, source key, target key). |
| `type`, `category` | One of the 18 [relationship types](graph/relationship-types.md); `economic` or `structural`. |
| `source`, `target`, `directed` | Node keys and whether direction matters (not for `competes_with`). |
| `evidence_status` | `evidence_backed`, `analyst_created`, `model_assumption` or `unverified`. |
| `is_illustrative` | True when it touches fictional or sample data. |
| `valid_from`, `valid_to`, `historical` | The validity period, only if a source states one; `historical` when it has ended. |
| `qualifiers` | What the source states: assumed `polarity`, illustrative `strength`, `evidence_level`, `rationale`, `stated_difference`. No confidence score. |

### Edge evidence

| Field | Meaning |
|---|---|
| `rule` | The construction rule (`R01`–`R12`) that made the edge. |
| `source_kind` | `reference_dataset`, `series_catalogue`, `price_file_manifest` or `classification_standard`. |
| `source_table`, `source_record_id`, `dataset_id`, `dataset_version` | The record the edge came from. |
| `statement`, `transformation` | What the source says, and how the rule turned it into the edge. |
| `derivation`, `derived_from` | `direct`, or `derived` with what it was derived from. |
| `citation`, `citation_url` | The outside source the record cites, if any. |
| `retrieved_at`, `recorded_at` | When a provider delivered the data (provider data only); when RUMIN loaded the record. |

### Graph build

| Field | Meaning |
|---|---|
| `status` | `running`, `completed`, `completed_with_warnings` or `failed`. |
| `rules_version`, `source_fingerprint` | The construction rules' version and a SHA-256 over every source record, used to tell whether the graph is current. |
| `sources` | The datasets and versions read. |
| `nodes`, `edges` | Processed, valid, flagged and rejected counts, from the run itself. |
| `node_changes`, `edge_changes` | Added, changed, retired and unchanged. |
| `metrics` | Node and edge counts, components, degree, density and provenance coverage, each defined in [algorithms](graph/algorithms.md#graph-metrics). |

## Simulation

The engine, its first model and what a run stores are described in
[`docs/simulation/`](simulation/README.md); the tables are in
[data-model.md](data-model.md#phase-4-simulation-runs). Numbers are exact decimal strings in
plain notation; outputs carry 10 decimal places.

### Model version

`simulation_model_versions`: one row per (model, version), written the first time that
version runs.

| Field | Meaning |
|---|---|
| `model_id`, `version` | The model's ID (`airline_fuel_cost`) and its version (MAJOR.MINOR.PATCH). Unique together. |
| `name`, `status` | Display name; `preview`, `active` or `deprecated` (a deprecated version stays readable and explainable but no longer runs). |
| `definition` | The whole model definition as canonical JSON: inputs, equations, outputs, graph rules, assumptions, limitations, validation rules, references. Old runs are explained from this copy, not from current code. |
| `definition_hash` | SHA-256 over `definition`. A later run whose code has a different hash is refused (409). |
| `registered_at` | When the version first ran. |

### Model input (in a definition)

| Field | Meaning |
|---|---|
| `id`, `label`, `description` | Identity and plain-language meaning. |
| `category` | `scenario_input` (the change explored), `market_baseline` (a market level: stored data or the user's figure), `company_input` (the user's figures about the company), `assumption` (a parameter with a neutral default and a written rationale) or `setting` (how the run is carried out). |
| `kind` | `decimal`, `integer`, `quantity` (a unit chosen from `units`), `currency` (an ISO 4217 code) or `graph_node` (a node key in the knowledge graph). |
| `unit`, `unit_label`, `units` | The unit, its label, and for quantities the units accepted. Nothing converts between units the model does not list. |
| `minimum`, `maximum`, `minimum_exclusive`, `maximum_exclusive` | The allowed range, inclusive unless marked exclusive. A value outside it is refused, never clipped. |
| `max_decimals` | The decimal places accepted; more are refused, never rounded. |
| `required`, `default`, `rationale` | Whether a value must be given; the default for optional inputs and why it was chosen. |
| `variable` | The knowledge-graph variable a scenario input changes. |
| `sources` | Stored series the value may be taken from, with whether a value is stored now. |
| `sensitivity` | The default variation for sensitivity analysis (`absolute` or `relative`, and its step). |

### Run

`simulation_runs`: one completed run. Nothing updates or deletes a run.

| Field | Meaning |
|---|---|
| `id` | UUID. |
| `model_version_id`, `model_id`, `model_version` | The stored model version the run used. |
| `status` | `completed`. Invalid inputs are refused with their reasons (422) and never stored as runs. |
| `label` | An optional name, ≤ 120 characters. |
| `entity_id` | The knowledge-graph company the run is about, if one was chosen. |
| `horizon_months` | 1–36 for the airline model. |
| `inputs` | Every input, including those left on their defaults ([resolved input](#resolved-input)). |
| `inputs_hash` | SHA-256 over the model ID, version, definition hash, engine version and every input's value, unit and source. Equal numbers written differently hash the same. |
| `assumptions`, `limitations` | The model's statements as they were at run time. |
| `graph_snapshot` | The graph build (ID, finish time, source fingerprint, freshness), the confirming edge for each transmission rule and supporting relationship (or `null` where the graph does not state it), the entity, and the relationships around the model's variables that were listed but not followed. |
| `data_snapshot` | Each stored observation used ([below](#resolved-input)). |
| `outputs` | Every output: value, unit, `derived` (from the inputs alone) or `simulated` (under the scenario). |
| `monthly` | Each monthly series, one value per month. |
| `contributions` | For each attributable output, each change's Shapley credit. |
| `bridge` | The accounting bridge: its signed steps and total, checked to add up before storage. |
| `transmission` | Every propagation path: its nodes, rules, edge keys, coefficient, lag, first month and log change. |
| `warnings` | Notes raised for the run: code, message and field. |
| `result_hash` | SHA-256 over every output, monthly value and contribution, as stored. |
| `engine_version` | The engine's version, also part of the inputs hash. |
| `random_seed` | `null`: the calculation is deterministic. Reserved for a future probabilistic run. |
| `started_at`, `finished_at`, `duration_ms`, `created_at` | Timing and bookkeeping. |

### Resolved input

One entry of a run's `inputs`.

| Field | Meaning |
|---|---|
| `id`, `label`, `category`, `variable` | From the definition. |
| `knowledge` | What the value **is**: `scenario_input`, `historical_data` (a stored observation), `user_input` (a figure the user entered), `assumption` or `setting`. |
| `source` | Who chose it: `user`, `default` or `stored_observation`. |
| `value`, `unit`, `unit_label` | The value used and its unit. |
| `default`, `rationale` | The definition's default and its rationale, kept beside the value used. |
| `observation` | For a stored observation: series, frequency, period, value as stored and as published (`raw_value`), quality status, revision, last confirmed, source capture, ingestion job, dataset and version, licence and attribution. `null` otherwise. |

### Run step

`simulation_run_steps`: every evaluated equation of a run, in order.

| Field | Meaning |
|---|---|
| `sequence` | Order of evaluation from 1, unique within the run. |
| `equation_id`, `label` | The equation (`E1`–`E19` for the airline model) and what the step calculates. |
| `month` | The month, from 1 (scenario changes start in month 1), or `null` for annual, horizon and steady-state steps. |
| `output_symbol`, `output_value`, `output_unit` | What was calculated: exact to 18 decimal places (`NUMERIC(38, 18)`), with its unit. |
| `inputs` | Each term the equation read: symbol, value and unit. |

### Sensitivity analysis

`simulation_sensitivity_analyses`: one analysis of a run. Nothing updates or deletes one.

| Field | Meaning |
|---|---|
| `id`, `run_id` | UUID; the run analysed (a run with analyses cannot be deleted). |
| `metric` | The output the inputs are ranked by. |
| `request` | Each input varied, with its mode (`default`, `absolute`, `relative` or `values`) and step or values, as resolved. |
| `results` | Per input: label, category, unit, the run's value, mode and step; each point's value with every output and its difference from the run, or the reason it was skipped; the metric's lowest, highest and spread. Then the ranking, largest spread first. |
| `evaluations`, `duration_ms` | Model evaluations performed (≤ 60) and time taken. |
| `result_hash` | SHA-256 over the results, timing excluded. |
| `created_at` | Bookkeeping. |

## Scenario Lab

Versions of [scenarios](#scenario), plans, executions and what is read from them (Phase 5).
The tables are in [data-model.md](data-model.md#phase-5-scenario-lab), the endpoints in
[api.md](api.md#scenario-lab), and how the Lab works in
[`docs/scenario-lab/`](scenario-lab/README.md). Numbers are exact decimal strings in plain
notation; results are rounded half to even to 10 decimal places. Every value in results,
pathways and stress cases is simulated from stated inputs: none is a forecast.

### Version

`scenario_versions`: one saved state of a scenario, never updated. `GET
/api/v1/scenarios/{id}/versions` lists summaries, newest first; `…/versions/{n}` returns
one version in full.

| Field | Type | Meaning |
|---|---|---|
| `version` | integer | 1, 2, 3 … within the scenario. |
| `name` | string | The version's name. |
| `spec_hash` | hex string | SHA-256 over the whole version in canonical form — name, description, template, changes and content, keys sorted, decimals in plain form — so equal content hashes the same however its numbers were typed. The note is not part of it. |
| `note` | string | What this version changes, as the request said; for a restored or duplicated version, where it came from (`Restored from version 1.`). |
| `derived_from` | object or null | The version this one copies: `kind` (`restore` or `duplicate`), `scenario_id`, `version`. |
| `created_at` | UTC timestamp | When it was saved. |
| `executions` | integer (API) | Executions of this version. |
| `scenario_id`, `description`, `template_id`, `shocks`, `spec` | | Full version only: its scenario and its content ([scenario](#scenario), [content](#scenario-content)). |

### Plan

What `POST /api/v1/scenarios/plan`, `GET /api/v1/scenarios/{id}/plan` and a preview
return, and what an execution stores as `plan`: which models apply to the scenario and why,
and whether it can be executed. A plan fills nothing in; it lists what is missing.

| Field | Type | Meaning |
|---|---|---|
| `spec_hash` | hex string | The planned content's hash ([version](#version)). |
| `executable` | boolean | True when at least one model is included and there is no error: every change is simulated by an included model, no model is blocked, no two included models claim the same item of the same line, and every stress case is valid. |
| `errors` | integer | Issues of severity `error`. |
| `issues` | list | Every problem and caution: `code` (e.g. `required`, `unmodelled_change`, `double_counting`, `stress_case_invalid`, `cross_effect`, `graph_stale`, `fictional_entity`), `message`, `severity` (`error` or `warning`), `field` (its path in the scenario body, e.g. `company.annual_revenue`) and `model_id`. |
| `graph` | object | The knowledge graph used: `build_id` and `freshness` (`current`, `stale` or `not_built`). |
| `entity` | object or null | The chosen company: `key`, `name`, `nature` and its `industries`. |
| `changes` | list | Per change: `index`, `variable_id`, `name`, `change_type`, `value`, `unit` (`%`, `percentage points` or the variable's unit), `modelled`, the included `models` that simulate it and, when none does, the `reason`. |
| `models` | list | Every Scenario Lab model ([model plan](#model-plan)); empty when the scenario is malformed (an unknown variable, a change outside its limits …), whose problems are then the `issues`. |
| `stress_cases` | list | Per case: `index`, `name`, the resulting `changes` by variable, `valid` and its `issues`. |
| `ties` | list | The graph's relationships from the changed variables (`influences`, `affects_costs`, `affects_revenue`, `affects_financing`): `edge_key`, `edge_type`, `source`, `target`, `evidence_status`, `is_illustrative`. |
| `names` | map | Display names of the graph nodes the plan mentions, by key. |
| `affected` | object or null | Companies the graph ties to the changed variables — through up to two `influences` hops, then an exposure of the company or its industry. `entities`: each company (`key`, `name`, `type`, `nature`) with its `exposures`, each giving the `changed_variable`, the variables it passes `via`, the `relationship` and the `exposed_variable`, the `industry` it goes through (if any), the `edges` and the `models` that simulate it (empty: none does). Also `variables` (their names), `limit` (200 companies), `truncated` (whether more were found) and a `note` that ties are not measured effects. `null` when the graph is not built or the scenario is malformed. |

### Model plan

One entry of a plan's `models`.

| Field | Type | Meaning |
|---|---|---|
| `model_id`, `version`, `name`, `title`, `covers` | strings | The model version the Lab runs (the latest runnable one), its names and what it covers. |
| `definition_hash`, `profile_hash` | hex strings | The model definition's hash, and the hash of its scenario profile: what it declares about scenarios (the changes it responds to, the line items it contributes, the exposure it needs). |
| `mode` | enum | `auto`, `include` or `exclude`, as the scenario sets it. |
| `status` | enum | `included` (it will run), `blocked` (it would run, but an input is missing or invalid, a relationship is not confirmed or a constraint is not met), `available` (a change reaches it but it is not included by default: no company is chosen, or the graph does not state the company's exposure), `excluded` (by the user) or `not_applicable` (no change reaches it, or the graph does not state the exposure the model requires). |
| `reasons` | list of strings | Why it has that status. |
| `changes` | list | The scenario's changes (variable IDs) it responds to. |
| `responds_to` | list | Every change it accepts: `variable_id`, `change_type` and the model `input` it sets. A change of another type is never converted. |
| `lines` | list | The line items it contributes to: `line`, `item`, `label`, `output`. |
| `exposure` | object | `checked` (a company is chosen, so the graph was consulted), `required` (the model only simulates companies with this exposure), `stated`, and the `chains` of graph edges that state it. |
| `issues` | list | Its own issues, as in the plan. |
| `inputs` | list | Its inputs, resolved and labelled as for a simulation run ([resolved input](#resolved-input)); empty when the model was not prepared for running. |
| `graph` | object or null | The graph snapshot of its preparation, as a run records it. |

### Execution

`scenario_executions`: one execution of one version, updated while it runs and never again
once final. `GET /api/v1/scenario-executions/{id}` returns every field; a scenario's list
of executions and its `latest_execution` return the summary (the fields down to `error`).

| Field | Type | Meaning |
|---|---|---|
| `id` | UUID | Assigned when the execution is accepted. |
| `scenario_id`, `version` | UUID, integer | The scenario and the version executed. |
| `status` | enum | `queued` (accepted, waiting for a worker); then the stage in progress: `validating`, `simulating`, `propagating`, `aggregating`; finally `completed`, `failed` or `cancelled`. |
| `requested_at`, `started_at`, `finished_at` | UTC timestamps | Accepted; picked up by a worker; final. |
| `duration_ms` | integer or null | From start to finish. |
| `inputs_hash` | hex string or null | SHA-256 over the Lab version, the version's `spec_hash` and, per model, its version, definition hash, profile hash and its run's inputs hash. Set on completion. |
| `result_hash` | hex string or null | SHA-256 over every line (baseline, change, months), every metric (baseline, scenario), every stress case and each model run's result hash. Set on completion. |
| `headline` | list | Up to two lines of the results, the first that exist of profit before tax, operating profit, operating costs, interest expense and revenue: `id`, `label`, `change`, `percent_change`, `currency`. Empty until completed. |
| `models` | list | The models whose runs it stored, in order. Empty until completed. |
| `error` | object or null | Why it did not complete: `code`, `message`, `details`. Codes: `plan_blocked` (`details` holds the plan's errors), `timeout`, `cancelled`, `interrupted` (the server stopped before it finished), `model_version_conflict`, `internal_error`, or a numerical code (`numerical_limit`, `transmission_limit`, `aggregation_inconsistent`). |
| `scenario_name` | string | The scenario's current name. |
| `lab_version` | string | The Lab's version (`1.0.0`), part of the inputs hash. |
| `cancel_requested` | boolean | Cancellation was requested; the execution stops at its next checkpoint. |
| `stages` | list | Each stage entered, in order: `stage`, `started_at`, `finished_at` (`null` while it runs) and `detail` (e.g. "Executing 3 models and 2 stress cases"). |
| `plan` | object or null | The [plan](#plan) rebuilt at `validating`; `null` before. |
| `runs` | list | The Phase 4 [run](#run) of each model: `position`, `model_id`, `model_version`, `run_id`. Empty until completed. |
| `results_available` | boolean | True once completed with results. |
| `poll_after_ms` | integer or null | While not final: when to ask again, in milliseconds (400). `null` once final. |

### Results

`GET /api/v1/scenario-executions/{id}/results`, and `results` in a preview. Stored in the
execution's `results` together with its [pathway](#pathway), which is served separately.

| Field | Type | Meaning |
|---|---|---|
| `execution_id` | UUID or null | `null` in a preview, which is not stored. |
| `lab_version`, `engine_version` | strings | The Lab's and the Phase 4 engine's versions. |
| `currency` | ISO 4217 code | The reporting currency of every amount. |
| `horizon_months` | integer | Months simulated. |
| `timing` | object | `start_month`, `end_month` (the last month the changes last, within the horizon) and `duration_months`. |
| `entity` | object or null | The company, as in the plan. |
| `lines` | list | The [lines](#line) the included models reach, in the order revenue, operating costs, operating profit, interest expense, profit before tax. Revenue and operating costs come together: a side no model changes carries a `note`. |
| `metrics` | list | [Metrics](#metric): `operating_margin` when the revenue and operating-cost lines are present and revenue is positive; `interest_coverage` when an interest model is included and interest expense is positive. |
| `not_modelled` | list | The lines the results do not cover, each with `id`, `label` and `reason` (not modelled is not the same as unchanged), and always `cash_flow`: no model covers working capital, tax or investment. |
| `models` | list | Per model: `model_id`, `version`, `name`, `title`, `definition_hash`, `profile_hash`, `run_id` (`null` in a preview), its run's `inputs_hash` and `result_hash`, `key_outputs` (`id`, `label`, `value`, `unit`, `kind`: `derived` or `simulated`), its accounting `bridge` and `warnings`. |
| `timeline` | object | `months`, `start_month`, `end_month`, each line's monthly `values`, and `events` (`month`, `label`, `model_id` — `scenario` for the changes themselves): the changes taking effect and ending, lags elapsing, hedges expiring, fares, selling prices and loans starting to move. Months of the simulation, not calendar dates. |
| `stress_cases` | list | Per case: `name`, `scale`, the `changes` used, and its `lines` and `metrics` (fields as below; `by_change` is empty: changes are attributed for the scenario only). |
| `steps` | list | The Lab's own calculation steps, in order: `sequence`, `equation` (AG1–AG7), `label`, `output` and `inputs` (each a `symbol`, `value` and `unit`). |
| `equations` | list | The Lab's equations AG0–AG7: `id`, `name`, `formula`, `explanation`. |
| `configuration` | map | The Lab and engine versions, the time step (`month`), the horizon, the rounding (34 significant digits; results rounded half to even to 10 decimal places) and how changes are attributed. |
| `note` | string | What the values are: simulated, not forecasts, not investment advice. |

### Line

One entry of `lines` in results and in stress cases. Amounts are over the horizon, in the
reporting currency.

| Field | Type | Meaning |
|---|---|---|
| `id`, `label`, `equation` | strings | `revenue` (AG1), `operating_costs` (AG2), `operating_profit` (AG3), `interest_expense` (AG4) or `profit_before_tax` (AG5). |
| `unit`, `currency` | strings | `currency`, and the reporting currency. |
| `baseline` | decimal | The line over the horizon from the user's annual figures (× horizon ÷ 12), held constant: an input, not a forecast. |
| `change` | decimal | The simulated change over the horizon. |
| `scenario` | decimal | `baseline` + `change`. |
| `percent_change` | decimal or null | The change as a percentage of the baseline's absolute value; `null` when the baseline is zero. |
| `direction` | enum | `up`, `down` or `none`. |
| `effect` | enum | `raises_profit`, `reduces_profit` or `none`: how the change moves profit (higher costs or interest reduce it). |
| `items` | list | The model outputs that make up the change: `model_id`, `item`, `label`, `output`, `monthly_output`, `value`, `by_change`. Empty for operating profit and profit before tax, which are computed from other lines. |
| `by_change` | map | The change attributed to each scenario change, by variable ID: Shapley values within each model, added across models. |
| `monthly`, `cumulative` | lists of decimals | The change in each month of the horizon, and its running total. |
| `baseline_monthly` | decimal | The baseline for one month. |
| `note` | string or null | E.g. "No included model changes it." |
| `knowledge` | `simulated` | Always. |

### Metric

One entry of `metrics`.

| Field | Type | Meaning |
|---|---|---|
| `id`, `label`, `equation` | strings | `operating_margin` (AG6: operating profit as a share of revenue over the horizon) or `interest_coverage` (AG7: how many times operating profit covers interest expense). |
| `unit` | string | `ratio` (the margin) or `times` (coverage). |
| `baseline`, `scenario` | decimals | Before and under the scenario. |
| `change`, `change_unit` | decimal, string | `scenario` − `baseline`, in `ratio_points` (the margin) or `times`. |
| `direction` | enum | `up`, `down` or `none`. |
| `knowledge` | `simulated` | Always. |

### Pathway

`GET /api/v1/scenario-executions/{id}/pathways`, and `pathway` in a preview: how each
change travelled to each line, as the engine computed it. Only links that carried the
scenario's changes are included; nothing is drawn that the engine did not compute, apart
from the graph relationships the Lab cites as context (`context_only`).

| Field | Type | Meaning |
|---|---|---|
| `nodes` | list | [Pathway nodes](#pathway-node). |
| `links` | list | [Pathway links](#pathway-link). |
| `groups` | list | One per included model: `id` (the model), `title`, `version` and the `nodes` that belong to it. |
| `unmodelled` | list | The graph's relationships from the changed variables that no included model simulates: `edge_key`, `edge_type`, `relationship`, `source` and `target` (keys) with `source_name` and `target_name`, `evidence_status`, `is_illustrative` and the `reason`. Listed, never followed: a connection is not evidence of causation. |
| `note` | string | What `context_only` means. |

### Pathway node

| Field | Type | Meaning |
|---|---|---|
| `id` | string | E.g. `change:var_brent_crude`, `airline_fuel_cost:variable:var_jet_fuel`, `airline_fuel_cost:output:fuel_cost_change`, `industry:ind_air_transport`, `line:revenue`, `metric:operating_margin`. |
| `kind` | enum | `change` (a scenario change), `variable` (a graph variable as one model moved it), `context` (the company or industry whose exposure the graph states), `driver` (a model output that is a line item), `line` or `metric`. |
| `label` | string | Display name. |
| `group` | string or null | The model the node belongs to; `null` for changes, context, lines and metrics. |
| `knowledge` | string | `scenario_input` (changes), `graph_relationship` (context) or `simulated` (the others). |
| `value`, `unit` | strings or null | Changes: the value in its unit (`%`, `percentage points` …). Variables: the change while the scenario lasts, once every lag has elapsed (`ratio`, or `percentage_points` for rates). Drivers and lines: the change over the horizon (`currency`). Metrics: the change from the baseline (`ratio_points` or `times`). `null` for context. |
| `first_month` | integer or null | The first month it changes. |
| `monthly` | list or null | Its value in each month (variables, drivers, lines). |
| `detail` | string or null | A short description, e.g. "Months 1–12 of 12". |
| `line`, `item` | strings or null | Drivers: the line and the item they contribute to. |

### Pathway link

| Field | Type | Meaning |
|---|---|---|
| `id`, `source`, `target` | strings | `<source>→<target>`, and the two node IDs. |
| `kind` | enum | `applies` (a change is applied to a model's variable), `transmission` (a model carries the change along a knowledge-graph relationship), `equation` (model equations compute a driver), `aggregation` (the Lab's equations add drivers into lines, and lines into lines and metrics) or `cited` (a graph relationship that made a model apply). |
| `simulation` | enum | How the link was used: `applied`, `propagated`, `computed`, `aggregated`, or `context_only` — a relationship the graph states that decided which models apply and carries no value. |
| `label` | string | E.g. "influences (β, lag)", "adds to", "is deducted from", "enters". |
| `group` | string or null | The model the link belongs to. |
| `equations` | list | The equations used on it (`id`, `name`, `formula`): the model's own, or the Lab's AG1–AG7. |
| `rule` | string or null | Transmission: the model's rule (e.g. `T1`). |
| `edge` | object or null | Transmission and cited links: the graph edge (`edge_key`, `edge_type`, `relationship`, `evidence_status`, `is_illustrative`). |
| `coefficient`, `lag_months` | decimal string, integer, or null | Transmission: the coefficient (β) and the lag in months. |
| `window` | object or null | Applies and transmission: the months the link acts, `first_month` and `last_month` (`null`: to the end of the horizon). |
| `assumptions` | list | The assumption inputs that act on the link: `id`, `label`, `value`, `unit`, `source`, `default`. |
| `statements` | list | The model's written assumptions its equations cite (`id`, `text`). |
| `sign` | integer or null | Aggregation into a line: `1` adds, `-1` is deducted. |
| `active` | boolean | `false` when the driver the link leads to, or comes from, never changes within the horizon. |

### Scenario sensitivity analysis

`scenario_sensitivity_analyses`: one **one-at-a-time** analysis of a completed execution.
Each chosen quantity is moved on its own while everything else keeps the execution's
value; every model that uses it is re-evaluated and the Lab's lines recombined. It is not a
stochastic (Monte Carlo) simulation: no probabilities are involved. The API never changes
or deletes an analysis.

| Field | Type | Meaning |
|---|---|---|
| `id`, `execution_id` | UUIDs | The analysis and the execution analysed. |
| `metric`, `metric_label`, `metric_kind` | strings | What the quantities are ranked by: a line (its change, `line_change`) or a metric (its scenario value, `metric_value`). Default: `profit_before_tax` when interest is modelled, otherwise `operating_profit`. |
| `base` | decimal | The metric in the execution. |
| `items` | list | Per quantity: `target` (`change:<variable>`, `shared:<input>` or `model:<model>:<input>`), `label`, `kind` (`change`, `shared`, `company`, `market` or `assumption`), the `models` that use it, `unit`, `base_value`, `mode` (`absolute`, `relative` or `values`) and `step`; the `points` (`role`: `low`, `high` or `value n`; `value`; the `metric` and its `delta` from `base`, or why the point was `skipped`); and the `range` (`low`, `high`, `spread`), `null` when no point could be evaluated. |
| `ranking` | list | The quantities by spread, largest first: `target`, `label`, `spread`. It ranks inputs by how much the result depends on them, not results by preference. |
| `evaluations` | integer | Evaluations performed: every point evaluated, plus the execution's own values once. |
| `duration_ms` | integer | Time taken. |
| `result_hash` | hex string | SHA-256 over the results, without the evaluation count and duration. |
| `created_at` | UTC timestamp | Bookkeeping. |
| `method` | `one_at_a_time` | Always. |
| `note` | string | What the spread means, and that this is not a Monte Carlo simulation. |

The table also stores the `request`: each quantity as resolved (`target`, `mode`, `step`,
`values`).

### Comparison

`GET /api/v1/scenario-comparisons`: 2–6 completed executions side by side, computed on
request and not stored. Nothing is ranked or recommended: which result is preferable
depends on an objective the user has not stated.

| Field | Type | Meaning |
|---|---|---|
| `reference` | UUID | The execution the others are differenced against (default: the first). |
| `executions` | list | Per execution, in the order requested: `execution_id`, `scenario_id`, `scenario_name`, `version`, `requested_at`, `currency`, `horizon_months`, `timing`, `entity`, its `changes` (as in its plan), its `models` (`model_id`, `version`, `title`) and `result_hash`. |
| `comparable` | map | By execution ID: whether its currency and horizon match the reference's. Nothing is converted, so only comparable executions are differenced. |
| `lines`, `metrics` | lists | Per line or metric (`id`, `label`), one cell per execution: `baseline`, `change`, `scenario`, `percent_change`, `modelled` (`false` when that execution does not cover it) and the `difference` from the reference — of the change for a line, of the scenario value for a metric: `absolute`, and `percent` of the reference's absolute value (`null` when that is zero). `difference` is `null` for the reference itself and for executions that are not comparable. |
| `inputs` | list | The inputs and assumptions whose values differ between the executions that use them: `model_id` (`scenario` for a figure every model shares), `input`, `label`, `category`, and per execution its `value`, `unit` and `source` (`null` where it is not used). |
| `pathways` | list | The pathway links (`link`, its ID) present in some executions but not all, with `present` per execution; cited context links are left out. |
| `sensitivity` | list | Per execution: the `metric` and `ranking` of its latest [sensitivity analysis](#scenario-sensitivity-analysis) (`null` and empty when it has none). Each ranks one execution's inputs; executions are never ranked against each other. |
| `note` | string | Why nothing is ranked. |

### Template

`GET /api/v1/scenario-templates` returns the summaries (the fields down to
`suggested_entities`) and, under `unsupported`, the templates that are not offered, each
with `id`, `title` and `reason` (no registered model simulates it: demand, supply chain).
`GET /api/v1/scenario-templates/{id}` returns every field.

| Field | Type | Meaning |
|---|---|---|
| `id` | slug | E.g. `crude_oil_airline`. |
| `title`, `question`, `summary` | strings | What the template asks, in words. |
| `category` | enum | `commodity`, `currency`, `interest_rate`, `energy_cost` or `combined`. |
| `changes` | list | Its changes: `variable_id`, `change_type`, `value`. |
| `models` | list | The models it is built on: `model_id`, `title`, `version`. |
| `stress_cases` | list | Suggested stress cases: `name`, `scale`, `changes`. |
| `suggested_entities` | list | Companies whose exposure the knowledge graph states for the template's models: `key`, `name`, `type`, `nature`. Empty when the graph is not built. |
| `required_inputs`, `optional_inputs` | lists | Derived from the models' definitions: `path` in the scenario body (e.g. `company.annual_revenue`), `input`, `label`, `kind` (`entity`, `change`, `market`, `company`, `assumption` or `setting`), `unit`, `unit_label`, the `units` accepted, `default`, `description`, `shared` (stated once for every model) and the `models` that use it. |
| `validation_rules` | list | The models' validation rules: `model_id`, `id`, `description`, `severity`. |
| `expected_outputs` | object | The `lines` and items the models contribute to, the `derived` lines and metrics, and each model's own `model_outputs`. |
| `scenario` | object | The template as a scenario body to start from. It holds no company figures: RUMIN never fills those in. |

## Financial intelligence

Financial Intelligence computes its answers from the tables above; its response fields are
described in the OpenAPI contract and in [`docs/intelligence/`](intelligence/README.md).
The one table it writes:

### Stored analysis

`intelligence_analyses`: a snapshot of an analysis of one entity or of the workspace, with
what it read. Never updated or deleted.

| Field | Type | Meaning |
|---|---|---|
| `id` | UUID | The stored analysis. |
| `scope` | `entity` \| `workspace` | What was analysed. |
| `subject_key` | string (≤ 128) or null | The entity's graph key (`company:…`, `industry:…`); null for the workspace. Not a foreign key: graph rows are derived and rebuilt. |
| `subject_name` | string (≤ 200) | The entity's name at the time, or `Workspace`. |
| `label` | string (≤ 200) or null | The label given when storing it, as plain text. |
| `engine_version` | string | `INTELLIGENCE_VERSION` at the time (`1.0.0`). |
| `thresholds` | JSON | Every threshold as used (defaults included): decimals as exact strings, `min_history` and `window` as integers; `window` is null when it followed the series' frequency. |
| `graph_build_id` | integer or null | The graph build the analysis read; null without a completed build. |
| `inputs` | JSON | The fingerprint: `engine_version`, `scope`, `subject`; `graph` (the build's id, finish time and source fingerprint); `data` (per series read: the number of stored rows and the highest row id; for the workspace, the same per instrument's price bars; for an entity, `related_series`); `executions` (entity: the ids of its latest 20 completed executions and the sensitivity analyses of the latest; workspace: the latest completed execution of each listed company and the number of completed executions). |
| `inputs_hash` | hex string | SHA-256 of `inputs` (canonical JSON). |
| `result` | JSON | The analysis exactly as the API returned it: the dossier (entity) or the overview (workspace), with every insight and its chain. |
| `result_hash` | hex string | SHA-256 of `result` (canonical JSON). |
| `insight_count` | integer | Number of insights in the result. |
| `duration_ms` | integer | Time taken to compute it. |
| `created_at` | UTC timestamp | When it was stored. |

Reading an analysis back adds `freshness`, computed each time and never stored: `status`
(`current` or `stale`), `changed` (`graph`, `data`, `executions`, `engine_version`, `subject`,
`scope`), `checked_at` and a `message`.

## Sample dataset catalogue

`rumin-sample` v1.0.0 — `backend/app/data/sample_dataset.json`. Relationship rationales are
in the file and in the Universe's detail panel.

### Countries (3) — real

| ID | Name | ISO 3166-1 | Currency (ISO 4217) |
|---|---|---|---|
| `cty_in` | India | IN | INR |
| `cty_us` | United States | US | USD |
| `cty_ae` | United Arab Emirates | AE | AED |

### Industries (8) — real classifications

| ID | Name | ISIC Rev. 4 division | Reference |
|---|---|---|---|
| `ind_oil_gas_extraction` | Crude petroleum & natural gas extraction | 06 | UN Statistics Division, ISIC Rev. 4, Division 06: Extraction of crude petroleum and natural gas. |
| `ind_petroleum_refining` | Refined petroleum products | 19 | UN Statistics Division, ISIC Rev. 4, Division 19: Manufacture of coke and refined petroleum products. |
| `ind_chemicals` | Chemicals & chemical products | 20 | UN Statistics Division, ISIC Rev. 4, Division 20: Manufacture of chemicals and chemical products. |
| `ind_power` | Electricity & gas supply | 35 | UN Statistics Division, ISIC Rev. 4, Division 35: Electricity, gas, steam and air conditioning supply. |
| `ind_land_transport` | Land transport | 49 | UN Statistics Division, ISIC Rev. 4, Division 49: Land transport and transport via pipelines. |
| `ind_air_transport` | Air transport | 51 | UN Statistics Division, ISIC Rev. 4, Division 51: Air transport. |
| `ind_it_services` | IT services | 62 | UN Statistics Division, ISIC Rev. 4, Division 62: Computer programming, consultancy and related activities. |
| `ind_banking` | Banking | 64 | UN Statistics Division, ISIC Rev. 4, Division 64: Financial service activities, except insurance and pension funding. |

### Economic variables (7) — real definitions, no values

| ID | Name | Unit | Kind | Frequency | Country | Reference |
|---|---|---|---|---|---|---|
| `var_brent_crude` | Brent crude oil price | USD per barrel | price | daily | Global | U.S. Energy Information Administration, Europe Brent spot price FOB (FRED series DCOILBRENTEU). ([link](https://fred.stlouisfed.org/series/DCOILBRENTEU)) |
| `var_jet_fuel` | Jet fuel price (U.S. Gulf Coast) | USD per gallon | price | daily | United States | U.S. Energy Information Administration, U.S. Gulf Coast kerosene-type jet fuel spot price FOB (FRED series DJFUELUSGULF). ([link](https://fred.stlouisfed.org/series/DJFUELUSGULF)) |
| `var_henry_hub_gas` | Natural gas price (Henry Hub) | USD per million Btu | price | daily | United States | U.S. Energy Information Administration, Henry Hub natural gas spot price (FRED series DHHNGSP). ([link](https://fred.stlouisfed.org/series/DHHNGSP)) |
| `var_usd_inr` | USD/INR exchange rate | INR per USD | exchange_rate | daily | India | Board of Governors of the Federal Reserve System, H.10 release (FRED series DEXINUS). ([link](https://fred.stlouisfed.org/series/DEXINUS)) |
| `var_rbi_repo_rate` | RBI policy repo rate | percent per annum | rate | irregular | India | Reserve Bank of India, Monetary Policy Committee statements. ([link](https://www.rbi.org.in)) |
| `var_us_fed_funds` | U.S. effective federal funds rate | percent per annum | rate | monthly | United States | Board of Governors of the Federal Reserve System (FRED series FEDFUNDS). ([link](https://fred.stlouisfed.org/series/FEDFUNDS)) |
| `var_india_cpi_inflation` | India CPI inflation | percent, year-on-year | rate | monthly | India | National Statistics Office, Ministry of Statistics and Programme Implementation (MoSPI), Consumer Price Index (Combined). ([link](https://www.mospi.gov.in)) |

### Companies (12) — all fictional

| ID | Name | Industry | Country |
|---|---|---|---|
| `co_orvane_petroleum` | Orvane Petroleum | Crude petroleum & natural gas extraction | United Arab Emirates |
| `co_tessaline_energy` | Tessaline Energy | Crude petroleum & natural gas extraction | United States |
| `co_deltrin_refining` | Deltrin Refining | Refined petroleum products | India |
| `co_solvane_refining` | Solvane Refining | Refined petroleum products | United States |
| `co_aerisca_airways` | Aerisca Airways | Air transport | India |
| `co_skyvara_air` | Skyvara Air | Air transport | India |
| `co_trakvel_logistics` | Trakvel Logistics | Land transport | India |
| `co_lumeric_chemicals` | Lumeric Chemicals | Chemicals & chemical products | United States |
| `co_gridwell_power` | Gridwell Power | Electricity & gas supply | India |
| `co_kovalent_digital` | Kovalent Digital | IT services | India |
| `co_anvaya_bank` | Anvaya Bank | Banking | India |
| `co_brookvane_bank` | Brookvane Bank | Banking | United States |

### Relationships (41) — all illustrative assumptions

| Source | Relationship | Target | Polarity | Strength |
|---|---|---|---|---|
| Brent crude oil price | affects costs of | Land transport | positive | moderate |
| Brent crude oil price | affects costs of | Refined petroleum products | positive | strong |
| Jet fuel price (U.S. Gulf Coast) | affects costs of | Air transport | positive | strong |
| Natural gas price (Henry Hub) | affects costs of | Lumeric Chemicals | positive | strong |
| USD/INR exchange rate | affects costs of | Aerisca Airways | positive | moderate |
| USD/INR exchange rate | affects costs of | Deltrin Refining | positive | strong |
| USD/INR exchange rate | affects costs of | Skyvara Air | positive | moderate |
| RBI policy repo rate | affects financing costs of | Gridwell Power | positive | moderate |
| RBI policy repo rate | affects financing costs of | Trakvel Logistics | positive | weak |
| U.S. effective federal funds rate | affects financing costs of | Lumeric Chemicals | positive | weak |
| Brent crude oil price | affects revenue of | Crude petroleum & natural gas extraction | positive | strong |
| Jet fuel price (U.S. Gulf Coast) | affects revenue of | Refined petroleum products | positive | moderate |
| Natural gas price (Henry Hub) | affects revenue of | Tessaline Energy | positive | moderate |
| RBI policy repo rate | affects revenue of | Anvaya Bank | mixed | moderate |
| U.S. effective federal funds rate | affects revenue of | Brookvane Bank | mixed | moderate |
| USD/INR exchange rate | affects revenue of | Kovalent Digital | positive | strong |
| Aerisca Airways | competes with | Skyvara Air | — | strong |
| Brent crude oil price | influences | India CPI inflation | positive | moderate |
| Brent crude oil price | influences | Jet fuel price (U.S. Gulf Coast) | positive | strong |
| India CPI inflation | influences | RBI policy repo rate | positive | moderate |
| U.S. effective federal funds rate | influences | USD/INR exchange rate | positive | weak |
| USD/INR exchange rate | influences | India CPI inflation | positive | moderate |
| Anvaya Bank | lends to | Aerisca Airways | — | moderate |
| Anvaya Bank | lends to | Deltrin Refining | — | moderate |
| Anvaya Bank | lends to | Gridwell Power | — | strong |
| Anvaya Bank | lends to | Trakvel Logistics | — | moderate |
| Brookvane Bank | lends to | Lumeric Chemicals | — | moderate |
| Brookvane Bank | lends to | Tessaline Energy | — | moderate |
| Crude petroleum & natural gas extraction | supplies | Refined petroleum products | — | strong |
| Deltrin Refining | supplies | Aerisca Airways | — | strong |
| Deltrin Refining | supplies | Skyvara Air | — | moderate |
| Deltrin Refining | supplies | Trakvel Logistics | — | moderate |
| Kovalent Digital | supplies | Anvaya Bank | — | moderate |
| Kovalent Digital | supplies | Brookvane Bank | — | moderate |
| Orvane Petroleum | supplies | Deltrin Refining | — | strong |
| Refined petroleum products | supplies | Air transport | — | strong |
| Refined petroleum products | supplies | Chemicals & chemical products | — | moderate |
| Refined petroleum products | supplies | Land transport | — | strong |
| Solvane Refining | supplies | Lumeric Chemicals | — | moderate |
| Tessaline Energy | supplies | Lumeric Chemicals | — | moderate |
| Tessaline Energy | supplies | Solvane Refining | — | strong |
