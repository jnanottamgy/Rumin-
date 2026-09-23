# Phase 2 plan — Financial data infrastructure

Written before implementation, after auditing Phase 1 and researching providers. It records
what was found, what was decided and why, and the order of work. The
[Phase 2 report](phase-2-report.md) records what was actually delivered.

## 1. Phase 1 audit

**Verified.** CI run #1 on GitHub passed: backend tests on SQLite and PostgreSQL 16 (125),
frontend tests (117), build, contract checks and the end-to-end smoke test (19 integration
tests). No known defects.

| Area | Finding for Phase 2 |
|---|---|
| **Reusable as-is** | `create_app()` with injected settings; error envelope and request IDs; pagination (`Page[T]`); portable enum columns; `UTCDateTime`; deterministic constraint names; Alembic batch migrations with drift and downgrade tests; seed-loader validation patterns; OpenAPI snapshot → generated TypeScript types; `useApiResource`, `apiClient`, design tokens, `Panel`/`StatTile`/`States`/badges; page-test harness with a fake API |
| **Existing models** | `datasets` (provenance anchor for curated reference data), `entities` + kind tables, `relationships`, `scenarios`, `scenario_shocks`. `countries` and `economic_variables` are the natural anchors for observed data |
| **Existing contracts** | `/api/v1/entities`, `variables`, `relationships`, `network`, `scenarios`, `system`. Capability `historical_observations` is declared "planned for Phase 2" and must flip only when real |
| **Architectural limitations** | No authentication → anything that makes outbound provider requests must not be callable by anonymous HTTP clients. No background worker. SQLite's `NUMERIC` is floating point → values would not be exact in development. The network service assumes the newest `datasets` row is the reference dataset |
| **Required migrations** | Extend `datasets` (kind, provider, licence fields; checksum optional for provider data); new tables for providers, series, observations (with revisions), instruments, price bars, ingestion jobs and items, source captures, quality issues |
| **Dependencies** | No new backend runtime dependency is needed: HTTP via the standard library (`urllib`) behind a small transport interface; CSV via `csv`. Frontend charting: `d3-scale` and `d3-shape` (small, tree-shakeable) — to be confirmed while building the chart |
| **Technical debt** | Docs name FRED as the Phase 2 source — wrong after the licence review below. `seed --reset` deletes by kind; new foreign keys to countries/variables must not block it (use `SET NULL`) |
| **Integration risks** | Series must link to Phase 1 countries and variables without pretending a different measure is the same (a World Bank *annual average* is not the Phase 1 *daily* variable); the dashboard and system page must keep telling the truth as capabilities change |

## 2. Provider research

Official documentation could not be opened directly from the build environment (all
provider hosts are blocked by its network policy), so findings come from official pages via
search results. **Each licence must be re-read in full before commercial use.**

| Provider | Data | Auth | Limits | Licence / terms | Verdict |
|---|---|---|---|---|---|
| **World Bank Indicators API v2** | ~16,000 indicators (WDI annual; some monthly sources); India covered | None | No official number found (a third-party page claims ~1,000 requests/hour — unverified) | Datasets under **CC BY 4.0** unless labelled otherwise; commercial use allowed with attribution; some third-party indicators may carry extra conditions (in indicator metadata) | **Selected** |
| FRED (St. Louis Fed) | US and international series, vintages | API key | 2 requests/second (429 above) | June 2024 API terms **prohibit storing or incorporating FRED content in any database**; third-party series need owner permission | **Rejected** for stored data (would need written permission) |
| MoSPI eSankhyiki API | Official Indian CPI (monthly, base 2012=100), WPI, IIP | Sign-up → access token | Not found | Government data; likely GODL-India (commercial use with attribution) — to confirm | **Next provider** (needs a token and network access) |
| RBI DBIE | Policy rates, reference rates, money markets | — | — | Downloads "for research with courtesy"; no official public API | Not selected |
| Alpha Vantage (free tier) | Global equities | API key | 25 requests/day | Free tier: personal, non-commercial use only | Not selected (RUMIN is a company product) |
| NSE / BSE | Exchange market data | — | — | Licensed data products | Only via **files the user is licensed to use** |

## 3. Scope (decided)

**In Phase 2**

1. **World Bank provider** — a curated catalogue of annual World Development Indicators
   for India (with US and UAE context), linked to Phase 1 countries and, where the concept
   matches, to Phase 1 economic variables (with the difference stated).
2. **Licensed price-file import** — daily OHLC for listed instruments from CSV files the
   user supplies and is licensed to use. No price is ever bundled or invented.
3. One shared pipeline: request/throttle/retry → capture → validate → normalise → quality
   rules → duplicate and revision handling → persistence → job tracking → summary.
4. Read-only API and a Data Explorer in the web client.

**Not in Phase 2** (documented as such): FRED; MoSPI (next); real-time or intraday data;
financial statements; currency conversion; corporate-action adjustment (an adjusted close
is stored only if the file supplies one, labelled as such); scheduling (the job model is
ready for it); starting ingestion over HTTP (no authentication yet).

## 4. Design

### Data model

| Table | Purpose | Uniqueness |
|---|---|---|
| `datasets` (extended) | Provenance anchor for **all** data: curated reference data (Phase 1) and provider datasets (e.g. World Bank WDI, a user's licensed price files) — `kind`, provider, licence, attribution, terms, provider's last update | `id` |
| `data_providers` | Who publishes: kind (`api` / `file`), auth, rate policy, licensing and commercial-use notes, limitations | `id` |
| `economic_series` | One provider series (indicator × country): unit, frequency, aggregation, price basis, currency, links to country/variable | (`dataset_id`, `provider_series_key`) |
| `economic_observations` | One period's value, exact decimal, with revision history | one **current** row per (`series_id`, `period_start`) |
| `instruments` | A listed security: name, ISIN, exchange (MIC), symbol, currency, country | `isin`; (`exchange_mic`, `symbol`) |
| `price_bars` | One trading day's OHLC(V) for an instrument from one dataset, with revision history | one **current** row per (`instrument_id`, `dataset_id`, `trade_date`) |
| `ingestion_jobs` / `ingestion_job_items` | What ran, when, with what result — per job and per series/instrument | `id` |
| `source_captures` | The exact bytes received (HTTP response or file): hash, size, time, sanitised locator | `id` (same content may be captured twice) |
| `data_quality_issues` | Every rejected record and every flag, with rule, severity, outcome and the raw record | `id` |

**Precision.** Values use an exact-decimal column type: `NUMERIC(38, 18)` on PostgreSQL and
a canonical decimal string on SQLite, so no value is rounded by the database in any
environment. JSON numbers are parsed as decimals (never floats). A value that does not fit is
**rejected**, never rounded. The provider's literal is also kept (`raw_value`).

**Revisions, not overwrites.** Re-ingesting identical data changes nothing but "last seen".
A changed value creates a new revision; the previous one is kept and marked superseded, with
the job that superseded it. History is never silently rewritten.

### Quality statuses

| Status | Meaning |
|---|---|
| `validated` | Stored; passed every rule |
| `warning` | Stored; flagged for review (e.g. an unusual but possible value) |
| `rejected` | Not stored as data; kept in `data_quality_issues` with the raw record and the reason |
| `unreviewed` | Review state of a flag: no human has reviewed it (no review workflow yet) |

Structural problems reject; plausibility problems flag. Values a provider reported are never
"corrected".

### Job statuses

`pending` → `running` → `completed` | `completed_with_warnings` | `partially_failed` |
`failed` | `cancelled`. `partially_failed` exists because some series can succeed while
others fail — calling that either "completed" or "failed" would misreport it.

### Ingestion control

Command line only: `python -m app.ingestion …` (and `make` targets). The API is read-only for
jobs. Starting ingestion over HTTP arrives with authentication.

### Freshness

Three separate facts, never merged: the **observation period** (what time the data
describes), the **retrieval time** (when RUMIN fetched it) and the **provider's last update**
(when the provider last revised the dataset). No invented freshness score; no "live" label.

## 5. Order of work

1. Plan (this document).
2. Schema, exact-decimal type, migration `0002`, migration tests.
3. Provider interface, HTTP transport, throttling and retries, World Bank adapter, catalogue.
4. Pipeline stages, quality rules, revisions, job tracking, CLI; price-file import.
5. Read API, OpenAPI snapshot, generated types.
6. Data Explorer UI.
7. Tests throughout; full verification on SQLite and PostgreSQL; live World Bank run once
   network access is granted.
8. Documentation and the Phase 2 report.
