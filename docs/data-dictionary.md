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
- **Absent:** prices, rates, exchange rates, financial statements, time series or any other
  observed value. The variables are *defined*, not *measured*. Observations arrive with the
  Phase 2 data infrastructure, each with its source and retrieval date.

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
| `id`, `version` | strings | E.g. `rumin-sample`, `1.0.0`. |
| `is_illustrative` | boolean | `true` for the sample: its contents demonstrate the model and are not research findings. |
| `provenance_note` | text | Where each part of the data comes from and how far it can be relied on. |
| `license` | string | Terms of the dataset. |
| `checksum_sha256` | hex string | SHA-256 of the file the data was loaded from, so a loaded dataset can be matched to its exact source file. |
| `loaded_at` | UTC timestamp | When it was loaded. |

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
