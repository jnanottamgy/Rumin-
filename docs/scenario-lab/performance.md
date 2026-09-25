# Scenario Lab performance

Measured times and sizes for the Scenario Lab. **Every number here was measured on one
machine, with the illustrative sample network and hypothetical figures, and describes that
machine only.** None of it is a claim about production.

## How it was measured

- **Backend:** `backend/scripts/benchmark_lab.py` migrates a fresh database, loads the sample
  dataset, builds the knowledge graph and times the API in-process (FastAPI's test client, so
  no network): the backend tests' reference scenario (three models, three changes, 12
  months, two stress cases) and a large one (the same over 36 months with five stress cases).
  Each figure is the median of 7 runs after one warm-up. Executions run **inline** (the whole
  execution inside the request) for the per-stage figures, then through the background runner
  (thread mode) from the request to the final state, polling as a browser does.
- **Frontend:** `frontend/scripts/measure-lab.mjs` times the pathway layout (the real module,
  loaded through Vite) on the reference pathway and on a SYNTHETIC one with its lanes repeated
  three times. A Playwright script timed the page in Chromium at 1,440 × 1,000 against the
  local API, on the production build (`vite build` + `vite preview`), median of 5 runs after
  one warm-up.
- **Machine:** 4 vCPUs (Intel Xeon, 2.10 GHz), 15 GB of memory; Python 3.11, SQLite 3.45
  (file database), PostgreSQL 16 on the same machine; Node 22; Chromium from Playwright.

```bash
cd backend
uv run python scripts/benchmark_lab.py                   # SQLite in a temporary directory
uv run python scripts/benchmark_lab.py --postgres postgresql+psycopg://user:pass@localhost/scratch
cd ../frontend && node scripts/measure-lab.mjs
```

`--postgres` **wipes** the database it is given (it drops the `public` schema).

## Backend (ms, median)

| Measure | Reference, SQLite | Large, SQLite | Reference, PostgreSQL | Large, PostgreSQL |
|---|---|---|---|---|
| Plan (`POST /scenarios/plan`) | 32.5 | 31.5 | 68.2 | 60.4 |
| Live preview (`POST /scenarios/preview`) | 54.1 | 87.1 | 86.9 | 128.0 |
| Save a scenario (scenario + version 1) | 8.8 | 9.0 | 14.4 | 13.1 |
| Execute, inline (the whole execution in the request) | 120.9 | 207.4 | 224.8 | 298.9 |
| … validating (as stored) | 29.7 | 45.8 | 66.1 | 57.9 |
| … simulating (as stored) | 17.2 | 75.7 | 24.9 | 53.7 |
| … propagating (as stored) | 4.7 | 11.3 | 5.6 | 7.4 |
| … aggregating, including storing every run (as stored) | 30.1 | 88.6 | 47.1 | 159.0 |
| Results | 6.5 | 9.3 | 9.1 | 16.5 |
| Pathway | 5.7 | 7.1 | 8.4 | 9.6 |
| Explanation of profit before tax | 14.2 | 20.0 | 22.7 | 30.9 |
| Default sensitivity analysis (15 evaluations) | 25.0 | 40.1 | 32.1 | 47.4 |
| Reproducibility check | 22.8 | 50.0 | 30.6 | 55.7 |
| Compare two executions | 12.4 | 13.5 | 20.8 | 23.4 |
| Background execution, request → completed (first answer: `queued`) | 184.9 | — | 475.2 | — |

Re-measured on SQLite after every change of an execution's state became a conditional
update: inline execution 123.3 ms (reference) and 201.3 ms (large), background execution
174.6 ms — the same as above within run-to-run variation.

Most of the plan's time is spent reading the knowledge graph: the exposures of the chosen
company and the companies tied to the changes. It is computed on every preview.

## Payloads (compact JSON)

| Response | Reference | Large |
|---|---|---|
| Preview (plan + results + pathway) | 115,773 bytes | 161,489 bytes |
| Execution (with its plan and stages) | 53,839 | 54,247 |
| Results | 28,908 | 69,395 |
| Pathway | 34,990 | 39,796 |
| Explanation | 50,402 | 50,429 |

Responses over 1 KiB are **gzip-compressed** when the client accepts it (Starlette's
middleware, added in Phase 5): the reference preview travels as **15,390 bytes** instead of
114,762, for about 5 ms of server time (median 53 ms against 48 ms, measured with `curl` on
the local server).

## Frontend

| Measure | Reference (22 steps, 27 links) | SYNTHETIC, 9 lanes (42 steps, 65 links) |
|---|---|---|
| Pathway layout | 0.08 ms | 0.11 ms |
| Layout with one lane collapsed | 0.05 ms | 0.15 ms |
| A step's chain (upstream and downstream) | 0.05 ms | 0.01 ms |

| In Chromium, production build | Median |
|---|---|
| Open a saved scenario → its pathway drawn (stored execution, results and pathway loaded) | 360 ms |
| Edit a change → the new preview on screen | 545 ms, of which 450 ms is the deliberate pause after the last keystroke |

The Scenario Lab route is loaded on demand: **111 KB of JavaScript (31 KB gzip)** and 34 KB of
CSS (6 KB gzip), on top of the application's shared bundle.

## Advanced analyses (Phase 9)

Measured by a script through the running API (SQLite, one process) on the reference
scenario's three models, one request at a time: the server's recorded duration and the wall
time at the client. The work is in memory — one full re-evaluation of the three models takes
about 1.1 ms for 12 months — so the database does not change it.

| Analysis (evaluations) | 12 months: server / wall | 36 months: server / wall | Result |
|---|---|---|---|
| Monte Carlo, 500 draws × 3 quantities (501) | 593 / 618 ms | 1,578 / 1,603 ms | 9.6 kB |
| Monte Carlo, 2,000 draws × 8 quantities (2,001) — the maximum | 2,867 / 2,966 ms | 5,749 / 5,833 ms | 12.5 kB |
| *Run again and compare* of the maximum | — / 3,078 ms | — / 5,819 ms | identical results |
| Grid, 7 × 7 (49) | 64 / 85 ms | 104 / 123 ms | 6.8–6.9 kB |
| One at a time, 8 quantities, default points (17) | 14 / 28 ms | 22 / 35 ms | 5.3 kB |
| Verification register, one model version | 45–111 ms | — | 5–6 kB |

The worst case uses under a third of the 20-second Monte Carlo deadline. In Chromium, from
the click on *Run the analysis* to the result drawn (histogram, tables, stored list updated),
five quantities took 1.6 s for 1,000 draws and 3.2 s for 2,000.

## What keeps it responsive

- Executions run on a bounded pool (2 at once, 8 waiting) with a 20-second limit and
  cancellation between stages; a full queue answers 429 at once rather than waiting.
- The preview is debounced and cancellable; the previous result stays on screen, dimmed,
  until the new one arrives, so the page never blanks or freezes while the backend computes.
- Every read is bounded: at most 10 changes, 5 stress cases, 36 months, 8 sensitivity
  quantities × 7 points (60 evaluations), 6 executions compared, 200 companies tied.
- Analyses are bounded too: 2,000 draws, 8 quantities, a 7 × 7 grid, deadlines (20 s and
  10 s) after which nothing is stored, and two analyses at once per process (429 beyond).
