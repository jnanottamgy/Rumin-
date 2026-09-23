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

| Field | Type | Meaning |
|---|---|---|
| `id` | UUID | Assigned by the server. |
| `name` | string, 1–120 | Required; no control characters. |
| `description` | string, ≤ 2,000 | The question the scenario explores. Optional. |
| `status` | `draft` | The only status in Phase 1. |
| `shocks` | list, 1–10 | The changes, in order. |
| `latest_run` | null | Always null: no simulation engine exists. Reserved for Phase 4. |
| `created_at`, `updated_at` | UTC timestamp | Bookkeeping. |

### Scenario shock

| Field | Type | Meaning |
|---|---|---|
| `variable_id` | entity ID | The economic variable changed. At most once per scenario. |
| `change_type` | enum | `percent_change`: relative change, `value` in percent (30 = +30 %). `absolute_change`: `value` in the variable's unit; for rates, **percentage points** (0.25 = +25 basis points). |
| `value` | decimal, ≤ 4 places | Non-zero; within the variable's published limits. Stored exactly as `NUMERIC(14, 4)`. |
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
