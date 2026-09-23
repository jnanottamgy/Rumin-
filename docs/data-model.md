# Data model

Phase 1 stores **datasets** (where data came from), **entities** (companies, industries,
countries, economic variables), **relationships** between entities (modelling
assumptions) and **scenarios** (user-defined changes to variables). Phase 2 adds the
**financial data layer**: providers, economic series and their observations, instruments
and their daily prices, and the records of every ingestion run — the jobs, the exact bytes
received, and the data-quality issues found ([below](#phase-2-financial-data)). The same
schema runs on SQLite (development) and PostgreSQL (production), and is created only
through Alembic migrations.

Field-level definitions and the contents of the sample dataset are in the
[data dictionary](data-dictionary.md).

## Entity–relationship diagram

```mermaid
erDiagram
    datasets ||--o{ entities : "provides"
    datasets ||--o{ relationships : "provides"
    entities ||--o| companies : "is a"
    entities ||--o| industries : "is a"
    entities ||--o| countries : "is a"
    entities ||--o| economic_variables : "is a"
    industries ||--o{ companies : "classifies"
    countries ||--o{ companies : "domiciles"
    countries |o--o{ economic_variables : "is measured for"
    entities ||--o{ relationships : "source"
    entities ||--o{ relationships : "target"
    scenarios ||--|{ scenario_shocks : "contains"
    economic_variables ||--o{ scenario_shocks : "is changed by"

    datasets {
        string id PK
        string version
        bool is_illustrative
        text provenance_note
        string checksum_sha256
        datetime loaded_at
    }
    entities {
        string id PK
        string kind
        string name
        bool is_fictional
        string reference
        string dataset_id FK
    }
    relationships {
        string id PK
        string type
        string source_id FK
        string target_id FK
        string polarity
        string strength
        string evidence_level
        text rationale
    }
    scenarios {
        uuid id PK
        string name
        string status
    }
    scenario_shocks {
        int id PK
        uuid scenario_id FK
        string variable_id FK
        string change_type
        numeric value
    }
```

## Entities: joined-table inheritance

Every entity has one row in `entities` (the fields all kinds share) and one row in the
table for its kind, with the same primary key:

| Table | Kind-specific columns |
|---|---|
| `companies` | `industry_id` → `industries.id`, `country_id` → `countries.id` |
| `industries` | `classification_system` (e.g. `ISIC Rev. 4`), `classification_code` (e.g. `19`) |
| `countries` | `iso_alpha2` (unique), `currency_code` (ISO 4217) |
| `economic_variables` | `unit`, `value_kind`, `frequency`, `category`, `country_id` → `countries.id` (nullable: Brent crude is global) |

This gives relationships one foreign-key target (`entities.id`) whatever the kinds they
connect, while kind-specific references stay real foreign keys — a company cannot point at
an industry that does not exist, in either database.

`entities.attributes` (JSON) is reserved for descriptive extras that do not warrant a
column yet. It is empty in the sample dataset.

## Relationships

A relationship is a curated, **assumed** effect or link between two entities: always
`epistemic_category = assumption`, with a written `description` and `rationale`, a
`polarity`, a `strength` and an `evidence_level` saying how well it is supported. It is
never an observation.

Integrity is enforced at three levels:

1. **Database**: foreign keys to `entities`, `CHECK (source_id <> target_id)`, valid enum
   values, and `UNIQUE (type, source_id, target_id)`.
2. **Registry** (`app/domain/relationship_types.py`): which entity kinds each type may
   connect, whether it is directed and whether it has a polarity (below).
3. **Seed loader**: every reference resolves, types connect allowed kinds, polarity is
   `not_applicable` exactly when the type has none, and any evidence level above
   `illustrative` must cite a reference.

| Type | Reads as | Directed | Polarity | Allowed source → target |
|---|---|---|---|---|
| `supplies_to` | supplies | yes | — | company → company, industry → industry |
| `lends_to` | lends to | yes | — | company → company |
| `competes_with` | competes with | no | — | company ↔ company |
| `affects_costs` | affects costs of | yes | yes | variable → company / industry |
| `affects_revenue` | affects revenue of | yes | yes | variable → company / industry |
| `affects_financing` | affects financing costs of | yes | yes | variable → company / industry |
| `influences` | influences | yes | yes | variable → variable |

**Polarity** describes the assumed direction of effect: `positive` means an *increase* in
the source is assumed to *increase* the target measure (its costs, revenue, financing
costs, or the target variable). A positive cost effect is therefore usually bad for
margins. `mixed` means it can go either way depending on circumstances.

### Structural links (derived, not stored)

`/api/v1/network` also returns three structural link types, computed from entity columns
at query time so they can never disagree with the records: `in_industry` (company →
industry), `domiciled_in` (company → country) and `measured_for` (variable → country).

## Scenarios

`scenarios` holds a draft's `name`, `description`, `status` and timestamps;
`scenario_shocks` holds its 1–10 changes, in order (`position`):

- `variable_id` → `economic_variables.id` (`RESTRICT`: a variable in use cannot vanish);
- `change_type` (`percent_change` | `absolute_change`) and `value` as `NUMERIC(14, 4)` —
  exact decimals, never binary floating point;
- `UNIQUE (scenario_id, variable_id)`: a variable is changed at most once per scenario.

`status` can only be `draft` (enforced by a CHECK constraint). There is **no table for
simulation runs or results**: none exist until the Phase 4 engine, and the API reports
`latest_run: null`.

## Datasets and provenance

Every entity and relationship belongs to a `datasets` row (`RESTRICT` on delete), which
records the dataset's version, whether it is illustrative, a provenance note, its licence,
the SHA-256 checksum of the file it was loaded from, and when it was loaded. The system
page and `/api/v1/system` show this, so the origin of what is on screen is always visible.

## Phase 2: financial data

```mermaid
erDiagram
    data_providers ||--o{ datasets : "publishes"
    datasets ||--o{ economic_series : "contains"
    datasets ||--o{ instruments : "declares"
    datasets ||--o{ price_bars : "provides"
    economic_series ||--o{ economic_observations : "has (revisions)"
    instruments ||--o{ price_bars : "has (revisions)"
    countries |o--o{ economic_series : "describes"
    economic_variables |o--o{ economic_series : "relates to"
    ingestion_jobs ||--|{ ingestion_job_items : "targets"
    ingestion_jobs ||--o{ source_captures : "received"
    ingestion_jobs ||--o{ data_quality_issues : "found"
    source_captures |o--o{ economic_observations : "is the source of"
    source_captures |o--o{ price_bars : "is the source of"
    economic_observations |o--o{ data_quality_issues : "flagged by"
    price_bars |o--o{ data_quality_issues : "flagged by"

    economic_series {
        string id PK
        string dataset_id FK
        string provider_series_key
        string unit
        string frequency
        string measure_type
        numeric plausible_min
        numeric plausible_max
    }
    economic_observations {
        int id PK
        string series_id FK
        date period_start
        numeric value
        string raw_value
        string status
        string quality_status
        int revision
        datetime superseded_at
        int capture_id FK
    }
    price_bars {
        int id PK
        string instrument_id FK
        string dataset_id FK
        date trade_date
        numeric close
        int revision
        datetime superseded_at
    }
    ingestion_jobs {
        uuid id PK
        string status
        int items_total
        int records_rejected
    }
    source_captures {
        int id PK
        string locator
        string sha256
        bytes body_gzip
    }
```

| Table | Purpose | Uniqueness and key constraints |
|---|---|---|
| `data_providers` | Who publishes data and on what terms (licensing, commercial use, rate policy, limitations) — mirrored from the provider profiles in code | `id` |
| `datasets` (extended) | The provenance anchor for **all** data. `kind` is `curated` (the Phase 1 network, identified by its file checksum) or `provider` (with provider, licence, licence URL, terms URL, attribution, update frequency, provider's last update) | `CHECK`: curated rows have a checksum; provider rows have a provider |
| `economic_series` | One provider series (for the World Bank: one indicator for one country) with unit, frequency, measure type, aggregation, price basis, seasonal adjustment, currency, optional links to a Phase 1 country and variable (with how they differ), review range, and a summary (coverage, counts, last retrieval) | `UNIQUE (dataset_id, provider_series_key)` |
| `economic_observations` | One period's value as published, with the provider's literal, status (`reported`/`missing`), quality status, provider flags, revision number, first/last seen (job and time) and the capture it came from | **one current row per (`series_id`, `period_start`)**: a unique index on those columns `WHERE superseded_at IS NULL` |
| `instruments` | A listed security: name, type, ISIN, exchange (ISO 10383 MIC), symbol, currency, optional country, coverage | `UNIQUE (isin)`; `UNIQUE (exchange_mic, symbol)` |
| `price_bars` | One trading day's open/high/low/close (+ optional adjusted close and volume) for an instrument **from one dataset**, with currency, adjustment status, quality status, file line, revisions and provenance | one current row per (`instrument_id`, `dataset_id`, `trade_date`) `WHERE superseded_at IS NULL` |
| `ingestion_jobs` | One run: provider, dataset, trigger, parameters, derived status, timestamps and heartbeat, counters (targets, records, warnings, errors, requests, bytes), error summary | `id` (UUID) |
| `ingestion_job_items` | One target of a run (a series or an instrument) and its outcome, counters and error code/message | `job_id` (cascade) |
| `source_captures` | The exact bytes received (gzip) with SHA-256, size, sanitised URL or file name, HTTP status, time and the provider's last-update date | `job_id` (cascade) |
| `data_quality_issues` | A rejected record (with the raw record), a flagged value or a note: rule, severity, outcome, message, the period or date concerned, review status | links to job, series/instrument and observation/price bar |

### Revisions, not overwrites

Observations and price bars are never edited in place. Receiving the same content again
only updates `last_seen_job_id`/`last_seen_at` (and re-assesses the quality status).
Receiving different content sets `superseded_at` and `superseded_by_job_id` on the current
row and inserts a new row with `revision + 1`. The partial unique indexes guarantee, in the
database itself, that each period (or trading day) has exactly one current row; the
superseded rows remain as the history of what each provider said and when.

### Exact decimals

`ExactDecimal` (`app/db/types.py`) stores values as `NUMERIC(38, 18)` on PostgreSQL and as a
canonical decimal string on SQLite (whose `NUMERIC` would silently use binary floating
point). Values that do not fit are refused with an error — never rounded — and the
ingestion pipeline rejects them earlier with the `precision_exceeded` rule. Insignificant
trailing zeros are not stored (`5.10` is `5.1`); the provider's literal is kept in
`raw_value`.

### Foreign-key behaviour

- Observations and price bars reference their job and capture with `RESTRICT`: provenance
  cannot be deleted from under a value.
- A series' links to Phase 1 countries and variables use `SET NULL`, so reloading the
  reference data (`seed --reset`) never deletes observation history; the catalogue
  restores the links.
- Items, captures and issues cascade with their job.

### Indexes

Besides the unique indexes above: observations by (`series_id`, `period_start`), price bars
by (`instrument_id`, `trade_date`), foreign keys used in filters (dataset, provider,
country, variable, job, series, instrument), job status and creation time, issue rule,
and capture SHA-256.

## Enumerations

Enumerations are stored as `VARCHAR` with a `CHECK` constraint, not native database enum
types: identical on SQLite and PostgreSQL, readable in raw SQL, and changed by an ordinary
migration.

| Enumeration | Values |
|---|---|
| Entity kind | `company`, `industry`, `country`, `economic_variable` |
| Relationship type | `supplies_to`, `lends_to`, `competes_with`, `affects_costs`, `affects_revenue`, `affects_financing`, `influences` |
| Structural link type (derived) | `in_industry`, `domiciled_in`, `measured_for` |
| Polarity | `positive`, `negative`, `mixed`, `not_applicable` |
| Strength | `weak`, `moderate`, `strong` |
| Evidence level | `illustrative`, `documented`, `estimated`, `validated` |
| Value kind | `price`, `rate`, `exchange_rate`, `index` |
| Frequency | `daily`, `weekly`, `monthly`, `quarterly`, `annual`, `irregular` |
| Variable category | `commodity`, `monetary_policy`, `exchange_rate`, `inflation` |
| Change type | `percent_change`, `absolute_change` |
| Scenario status | `draft` |
| Epistemic category | `observation`, `assumption`, `scenario_input`, `simulated_output`, `uncertainty` |
| Dataset kind | `curated`, `provider` |
| Provider kind / authentication | `api`, `file` / `none`, `api_key`, `not_applicable` |
| Measure type | `level`, `change`, `rate`, `ratio`, `exchange_rate` |
| Price basis | `nominal`, `real`, `not_applicable` |
| Seasonal adjustment | `seasonally_adjusted`, `not_seasonally_adjusted`, `not_applicable` |
| Observation status | `reported`, `missing` |
| Quality status | `validated`, `warning` |
| Issue severity / outcome | `error`, `warning`, `info` / `rejected`, `flagged`, `noted` |
| Review status | `unreviewed` |
| Job status | `pending`, `running`, `completed`, `completed_with_warnings`, `partially_failed`, `failed`, `cancelled` |
| Job item status | `pending`, `succeeded`, `failed`, `skipped` |
| Job trigger / target kind | `cli` / `economic_series`, `instrument` |
| Capture kind | `http_response`, `file` |
| Instrument type | `equity`, `etf`, `index` |
| Price adjustment | `unadjusted`, `adjusted` |

## Conventions

- **Timestamps** are timezone-aware UTC (`TIMESTAMP WITH TIME ZONE` on PostgreSQL; stored
  as UTC and returned with `Z` on SQLite).
- **Constraint names are deterministic** (`ck_<table>_<name>`, `uq_<table>_<columns>`,
  `ix_<table>_<column>`, …), so migrations can reference them on both databases.
- **IDs** of reference data are stable, readable slugs (`co_deltrin_refining`), so a
  dataset can be reloaded without breaking links or saved scenarios.

## Migrations

Alembic, in `backend/migrations/`. `0001_initial_schema` creates the nine Phase 1 tables;
`0002_financial_data_infrastructure` extends `datasets` and adds the nine Phase 2 tables
(its downgrade removes provider datasets first, then the tables and columns).

- Every schema change is a new revision: edit the models, run
  `uv run alembic revision --autogenerate -m "…"`, **review the generated file**, apply it
  with `uv run alembic upgrade head`.
- Migrations run in batch mode so the same revision works on SQLite (which cannot alter
  most constraints in place) and PostgreSQL.
- Tests build their database with the real migrations (not `create_all`), check that the
  migrated schema matches the models exactly, and check that downgrading to empty and
  upgrading again works.
- `/health/ready` reports "not ready" until the database is at the latest revision.
