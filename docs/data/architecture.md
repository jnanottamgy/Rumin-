# Financial data architecture

How RUMIN retrieves, checks, stores and serves financial data — and the rules that keep
every number honest. Written for a developer joining the project; see
[ingestion](ingestion.md), [data quality](quality.md), [providers](providers.md) and
[price files](price-files.md) for the details of each part.

## The rules the design enforces

1. **Nothing is invented.** No value is fabricated, interpolated, filled in, rounded,
   converted or adjusted. A period without a value is stored as *missing*, and the
   interface shows it as a gap.
2. **Nothing is live.** Everything is a stored copy of published, historical data, with
   the time it was retrieved. There is no market feed.
3. **Everything is traceable.** Every value records its provider, dataset, licence,
   the response or file it came from (stored byte-for-byte, with its SHA-256), the
   ingestion job that first received it and the job that last confirmed it.
4. **History is kept.** When a provider revises a value, the old value stays in the
   database, marked as superseded — by which run, and when.
5. **Failures are visible.** Every run is a job with a status derived from what actually
   happened. A partially successful run is `partially_failed`, never `completed`.
6. **Exactness.** Values are decimals end to end: parsed from JSON as `Decimal`, stored
   as `NUMERIC(38, 18)` (PostgreSQL) or a canonical decimal string (SQLite), and sent to
   clients as decimal strings. A value that does not fit is rejected, never rounded.

## Components

```
                 command line (python -m app.ingestion …)         web client
                                   │                                   │
      ┌────────────────────────────┼──────────────┐                    │ HTTP (read-only)
      │ app/ingestion              ▼              │                    ▼
      │   catalog ── series_catalog.json    cli ──┤            app/api/v1/data.py
      │                                     │     │            app/api/v1/ingestion.py
      │   economic.run_economic_ingestion ◄─┤     │                    │
      │   prices.import_price_file ◄────────┘     │            app/services/data.py
      │        │                                  │            app/services/ingestion_history.py
      │        ├─ providers/  (WorldBankProvider, PriceFileProvider)   │
      │        │     └─ http.py (throttle · retries · typed errors)    │
      │        ├─ normalize.py (periods, dates, decimals, identifiers)  │
      │        ├─ quality.py   (rules: reject · flag · note)            │
      │        ├─ persistence.py (captures, revisions, issues)          │
      │        └─ jobs.py      (items, derived status, stale runs)      │
      └──────────────────────────┬──────────────────────────────────────┘
                                 ▼                                      ▼
                        database (SQLite or PostgreSQL) ◄───────────────┘
```

| Module | Responsibility |
|---|---|
| `providers/base.py` | What a provider is (`ProviderProfile`: terms, licence, limits) and what it can do (capabilities: `EconomicSeriesSource`, `PriceFileSource`). A provider implements only the capabilities it really has. |
| `providers/worldbank.py` | World Bank Indicators API v2: builds validated requests, pages through results, detects error envelopes, returns raw records and the exact bytes received. |
| `providers/price_file.py` | Reads a user's CSV (size limit, UTF-8, required columns); returns raw rows and the file's bytes. |
| `http.py` | The only code that talks to the network: a standard-library transport, a per-provider rate limiter, bounded retries with backoff, typed errors, URL redaction. |
| `normalize.py` | Strict parsing: periods (`2023`, `2023Q1`, `2023M03`), ISO dates, decimals (never floats), volumes, ISIN/MIC/currency codes. Refuses anything ambiguous. |
| `quality.py` | The data-quality rules (30), each with a severity and an outcome. See [data quality](quality.md). |
| `persistence.py` | Stores captures (gzip + SHA-256), writes observations and price bars as revisions, records quality issues, refreshes summaries. |
| `jobs.py` | Creates jobs and items, derives the job status from the items, closes runs abandoned by a crashed process. |
| `economic.py` / `prices.py` | The two pipelines (orchestration, transactions, failure handling). |
| `catalog.py` | Validates and syncs `app/data/series_catalog.json`: which series to fetch and how to describe them (it contains no values). |
| `cli.py` | The only way to start ingestion. |

## Data model in one picture

```
data_providers ──< datasets ──< economic_series ──< economic_observations (revisions)
                        │                                    │
                        ├──< instruments ──< price_bars (revisions, one dataset each)
                        │
ingestion_jobs ──< ingestion_job_items        source_captures (exact bytes, SHA-256)
       │                                              ▲
       └──< data_quality_issues ── observation / price bar / series / instrument
```

Tables and columns are described in the [data model](../data-model.md) and the
[data dictionary](../data-dictionary.md).

## Freshness: three facts, never merged

| Fact | Where it comes from | Shown as |
|---|---|---|
| **Observation period** — what time the value describes | The provider's period (`2023`) or the file's trade date | "Latest period with a value: 2023" |
| **Retrieval time** — when RUMIN received the value | Clock time of the response, per value (`retrieved_at`) and per series (`last_successful_ingestion_at`) | "Retrieved by RUMIN: 23 Sep 2026, 13:01 UTC · stored copy" |
| **Provider's last update** — when the provider last revised the dataset | The provider's own metadata (World Bank `lastupdated`); not available for price files | "Provider's last update: 1 Jul 2026 · as the provider reports it" |

There is no freshness score. A failed or skipped retrieval is shown next to the data it
did not refresh ("The last retrieval failed … the values below were retrieved on …").

## What each label means in the interface

| Label | Meaning |
|---|---|
| Observation (glyph ●) | Historical data from a cited source — the epistemic category of all provider data |
| Historical · not live | A stored copy of published data; nothing is real-time |
| Sample data — not real | The dataset is marked illustrative (the Phase 1 network, or a price file whose manifest says so) |
| No values retrieved yet | The series is in the catalogue, but no retrieval has stored a value |
| No value published | The provider listed the period without a value; it is a gap, never filled in |
| Flagged for review (▲) | Stored exactly as reported, but a plausibility rule flagged it; nobody has reviewed it yet |
| Last retrieval failed / skipped | The most recent job did not refresh this series; the data shown is older |

## Why ingestion is not an API endpoint

RUMIN has no authentication yet. An HTTP endpoint that starts ingestion would let anyone
who can reach the server make it send requests to providers (spending the provider's rate
limit and RUMIN's reputation) and write to the database. Until authentication exists
(Phase 10), ingestion runs from the command line on the machine that holds the database,
and the API is read-only for data. The job model (`trigger`, `parameters`, `heartbeat_at`)
is ready for a scheduler or an authenticated endpoint later.

## Compatibility with later phases

| Phase | What Phase 2 already provides |
|---|---|
| 3 — Knowledge graph | Series link to Phase 1 countries and variables (with the difference in measure stated); instruments carry normalised identifiers (ISIN, MIC + symbol); every record has a source reference |
| 4 — Simulation | Historical observations with units, frequency, measure type, price basis, seasonal adjustment and currency; review ranges labelled as assumptions |
| 5 — Scenario Lab | Series are addressable by stable IDs and linked to the variables scenarios already use |
| 6 — Financial intelligence | Consistent measure metadata and exact values; price bars with explicit adjustment status |
| 7 — AI Analyst | Every value is traceable to a stored response, a dataset licence and an attribution |
| 8 — 3D universe | Structured entities and relationships (Phase 1) plus the data now attached to them |

None of these phases is built here.
