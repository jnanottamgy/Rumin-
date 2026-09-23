# Ingestion pipeline

How data gets into RUMIN, what each stage does, how failures are handled and recorded,
and how to run, inspect and troubleshoot it.

## Running it

All commands run from `backend/` (with `uv run` in front, or the virtual environment
active). The database must be migrated first (`make migrate`).

```bash
python -m app.ingestion catalog                 # sync the series catalogue (no network)
python -m app.ingestion catalog --check         # validate it without a database
python -m app.ingestion run worldbank-wdi       # retrieve every catalogued series
python -m app.ingestion run worldbank-wdi --series wb-ind-fp-cpi-totl-zg --start 2010
python -m app.ingestion import-prices --manifest manifest.json --file prices.csv
python -m app.ingestion manifest-template       # a blank manifest to fill in
python -m app.ingestion jobs                    # recent runs
python -m app.ingestion job <job id>            # one run: targets, errors, issues
```

`run` syncs the catalogue first, validates the period range (`--start`/`--end` in the
series' frequency; the end may not be in the future; default: from the catalogue's start
to the current period), refuses to start while another run for the same dataset is
active, and prints a summary with the dataset's attribution.

| Exit code | Meaning |
|---|---|
| 0 | Completed (possibly with warnings) |
| 1 | Failed — no target succeeded |
| 2 | Not started — bad input, unknown dataset or series, another run active, database not migrated |
| 3 | Partially failed — some targets succeeded, others failed or were skipped |
| 130 | Cancelled with Ctrl+C |

## Stages (economic series)

```
catalogue ─► request ─► throttle ─► HTTP (retries) ─► capture ─► parse ─► normalise
         ─► quality rules ─► revisions ─► persist ─► issues ─► summaries ─► job record
```

1. **Request.** For each series, the provider builds a URL from validated parts only
   (indicator code, ISO3 country, period format). Nothing a user types reaches a URL
   unchecked.
2. **Throttle and retry.** At most one request per second. Connection errors, timeouts,
   HTTP 429 and 5xx are retried with exponential backoff and jitter, up to 4 attempts in
   total; a `Retry-After` header is honoured up to 60 s (a longer wait fails the request
   instead of stalling the run). 401/403 and other 4xx are not retried.
3. **Capture.** The exact bytes of every response are kept (gzip, SHA-256, sanitised URL,
   HTTP status, time). Values point to the capture they came from.
4. **Parse.** JSON numbers become `Decimal`s directly — never floats. The World Bank's
   error envelope (often sent with HTTP 200) is detected and reported.
5. **Normalise and check.** Each record is parsed strictly and run through the
   [quality rules](quality.md): structural problems reject the record (kept as an issue
   with the raw record); plausibility problems flag it; informational findings are noted.
6. **Revisions.** For each period: new → inserted; identical → only "last seen" updated;
   different (value, missing/reported, provider flag) → the current row is superseded and
   a new revision inserted. Numbers compare as numbers (`5.10` = `5.1`). Periods absent
   from a response are left untouched.
7. **Persist.** One database transaction per series: a failure part-way through leaves no
   half-stored series, and series already stored stay stored.
8. **Summaries.** The series' coverage, counts and last-retrieval fields are refreshed;
   the dataset's `provider_last_updated` is set from the provider's metadata.

The price-file pipeline is the same from stage 3 on, with one target (the instrument) and
the CSV file as the capture. See [price files](price-files.md).

## Jobs and their statuses

Every run is an `ingestion_jobs` row with one `ingestion_job_items` row per target. The
job's status is **derived from its items** — never set optimistically:

| Status | When |
|---|---|
| `pending` → `running` | Created, then started (the job and its items are visible while it runs) |
| `completed` | Every target succeeded and nothing was rejected or flagged |
| `completed_with_warnings` | Every target succeeded, but records were rejected or flagged, or a target raised a warning (e.g. an empty response) |
| `partially_failed` | Some targets succeeded; others failed or were skipped |
| `failed` | No target succeeded (including a run with nothing to do) |
| `cancelled` | Stopped with Ctrl+C: the target in progress was rolled back and the rest skipped |

Item outcomes: `succeeded`, `failed` (with an error code and a safe message), `skipped`
(with the reason). A series whose every record was rejected is `failed`
(`all_records_rejected`) — its issues are still stored.

Counters: `received = new + revised + unchanged + rejected`; `missing` counts accepted
periods without a value (a subset). The job also records requests sent, bytes received,
warnings and record errors, and a short error summary.

## Failure handling

| What happens | What RUMIN does |
|---|---|
| Provider unreachable / timeout / 5xx | Retried; if it persists, the series fails (`provider_unavailable`, `provider_timeout`). After **3 consecutive** such failures the remaining series are skipped (`circuit_open`) instead of hammering a provider that is down |
| Rate limited (429) | Retried after `Retry-After` (≤ 60 s) or backoff; then `rate_limited` |
| Credentials refused (401/403) | Not retried; `authentication_failed` |
| Provider rejects the request / error envelope | `invalid_request` with the provider's message |
| Malformed response (not JSON, wrong shape, > 20 MB, > 20 pages) | `malformed_response` |
| Empty response | The series succeeds with an `empty_response` warning |
| Every record invalid | The series fails (`all_records_rejected`); the reasons are stored as issues |
| Database error while storing | The series is rolled back and fails (`storage_error`); details go to the log only |
| Unexpected error (a bug) | The series fails (`internal_error`); the run continues; the traceback goes to the log only |
| Ctrl+C | The job is `cancelled`; what was committed stays |
| The process dies | The job stays `running`. After 2 hours without a heartbeat, the next command closes it: started targets `failed` (`interrupted`), the rest `skipped`, status derived as usual |
| Two runs at once | The second is refused (exit 2) while the first shows recent activity |

Messages stored in jobs never contain credentials, response bodies or stack traces.

## Logs

Ingestion writes one structured line per event (`event=… key=value …`), so runs can be
followed and searched with ordinary tools (`grep event=ingestion.series_failed`):

| Event | When |
|---|---|
| `ingestion.started` / `ingestion.finished` | A run starts / ends (with status and counts) |
| `ingestion.series_done` / `ingestion.series_failed` | A series is stored / fails (with error code) |
| `ingestion.fetch_failed` / `ingestion.store_failed` | An unexpected error (with traceback, in the log only) |
| `provider.response` | Every HTTP response: provider, redacted URL, status, attempt, milliseconds |
| `provider.retry` | A retry: error code, attempt, wait |
| `provider.metadata_unavailable` | The indicator's definition could not be fetched (the data is still stored) |
| `import.finished` | A price-file import ends |

URLs are redacted before they are logged; response bodies are never logged.

## Viewing what happened

- **Command line:** `python -m app.ingestion jobs` and `… job <id>` (targets, errors and
  issue counts by rule).
- **Web client:** Data Explorer → *Recent ingestion runs* → a run's page lists each target's
  outcome, the stored responses with their SHA-256, and the issues found.
- **API:** `GET /api/v1/ingestion-jobs`, `/ingestion-jobs/{id}`, `/data-quality/issues`.

## Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| `provider_unavailable: The provider could not be reached` for every series, then `circuit_open` | No internet access to `api.worldbank.org` (a firewall, proxy or sandbox policy). Allow the host (outbound HTTPS honours `HTTPS_PROXY`) and run again |
| `✗ Database error … run: make migrate` | The schema is missing or out of date: `make migrate` |
| `Unknown dataset 'x'` | Run `catalog` first, and use a dataset id from the catalogue (`worldbank-wdi`) |
| `Job … is still running` | Another run for that dataset is active. If its process died, wait until 2 hours after its last activity; the next command closes it |
| Values flagged `outside_review_range` | The value is unusual for RUMIN's review range (an assumption). It is stored as published — check the provider's data; widen the range in the catalogue only with a documented reason |
| `precision_exceeded` | The provider sent more digits than `NUMERIC(38, 18)` holds; the value is refused rather than rounded. Report it — do not edit the data |
| A series shows `No value published` for recent years | Normal publication lag: the World Bank lists the period before publishing a value |
