# Performance

Every Financial Intelligence read recomputes its analysis from the store: nothing is
cached. These measurements show what that costs on the sample network and on much larger
**SYNTHETIC** networks, and how the reads stay bounded as the graph grows.

## Method

`backend/scripts/benchmark_intelligence.py` (see its docstring for usage):

- **sample**: a fresh SQLite database with the illustrative network, the series catalogue
  (no stored values), the knowledge graph, and the backend tests' reference scenario
  executed (hypothetical figures);
- **1000, 5000, 20000**: the SYNTHETIC benchmark network of `benchmark_graph.py` with that
  many fictional companies (industries, variables, exposure edges, supply and credit links;
  no executions, no stored values), and its graph.

The script drives the API in process, through FastAPI's test client, as the pages do. Each
figure is the **median of 5 runs after one warm-up**, in milliseconds. The machine had 4 vCPUs
(Intel Xeon, 2.8 GHz) and 15 GB of memory, with Python 3.11 and SQLite 3.45. The numbers
describe this machine and nothing more.

## Results

| Measure | sample | 1,000 | 5,000 | 20,000 |
|---|---|---|---|---|
| Companies listed / in the graph | 12 / 12 | 200 / 1,000 | 200 / 5,000 | 200 / 20,000 |
| Exposure paths (listed companies) | 37 | 1,694 | 1,857 | 1,758 |
| Workspace findings | 9 | 13 | 13 | 13 |
| **Overview** | 32.5 | 290.2 | 285.1 | 345.1 |
| Entity list | 22.6 (20 entities) | 70.2 (216) | 131.0 (283) | 225.1 (288) |
| **Dossier** of the most exposed company | 36.1 (4 paths, 16 findings) | 32.4 (19, 18) | 44.7 (25, 21) | 35.6 (18, 21) |
| Brief | 33.2 | 28.0 | 31.5 | 32.4 |
| Exposure only | 13.1 | 17.8 | 19.5 | 18.9 |
| Detected changes | 21.2 | 8.3 | 12.4 | 15.1 |
| Store an analysis (entity) | 73.8 | 66.0 | 71.7 | 69.8 |
| Read it back, with freshness | 24.6 | 25.5 | 27.2 | 24.0 |
| Dossier size, uncompressed | 121 KB | 183 KB | 231 KB | 194 KB |

Reading the table:

- **The workspace is bounded by companies.** From 1,000 to 20,000 companies, the overview
  reads the first 200 by name and every validated edge their paths use, so its time barely
  grows (0.29 s → 0.35 s). The coverage says the listing is truncated.
- **A dossier does not depend on the size of the graph.** It reads a handful of queries
  around one entity: about 30–45 ms at every size.
- **Workspace findings stay readable.** On the synthetic networks, the 13 findings are the 12
  shared drivers (X01, capped at the variables reaching the most companies) and the coverage
  finding. The matrix still shows every variable.
- **The sample's detected changes take longer than the synthetic ones** because the sample
  has an execution to compare (and the synthetic networks have none).
- **Responses are compressed.** The sample dossier is about 120 KB of JSON and about 13 KB
  gzip-compressed (decision 52). The workspace overview is 66 KB, or 7 KB compressed.

## What the scaling work changed

Measured during development, before the scaling work, at 5,000 companies:

| | Before | After |
|---|---|---|
| Overview | 728 ms | 285 ms |
| Entity list | 743 ms | 131 ms |
| Detected changes | 389 ms | 12 ms |
| Workspace findings | 195 | 13 |

At 20,000 companies the overview took 808 ms before the reach index and 345 ms after. The
changes were these:

1. **The workspace read is bounded by companies, not edges.** Capping edges could have shown
   a listed company without an exposure the graph states. Bounding companies fixes that, and
   a test checks, for the full and a truncated listing, that each company's paths equal
   those of its own analysis.
2. **The graph slice indexes its edges by endpoint**, instead of scanning every edge for each
   step of a path.
3. **The reach of every variable is indexed in one pass** (`reach_index`). The shared-driver
   rule had scanned every company's paths once per variable.
4. **The shared-driver rule keeps the 12 variables that reach the most companies.** With
   thousands of companies, one finding per variable flooded the ledger with near-identical
   rows.
5. **The entity list reads industries in one query**, and detected changes no longer run the
   whole workspace analysis.
6. **Each listed company's latest execution is chosen in the database** (a window over its
   completed executions). This is exact however many executions exist; it replaced a read of
   the 500 most recent execution rows, which could silently miss a company.

## The interface

In the production build (`npm run build`), the Financial Intelligence route chunk is 59 KB of
JavaScript (15 KB gzip). A shared chunk of 12 KB of JavaScript (4 KB gzip) and 23 KB of CSS
(5 KB gzip) holds what the dashboard's *Latest findings* panel shares with the module: the
evidence marks and the ledger's styles. The browser performs no calculation beyond rounding
for display.

## Reproducing

```bash
cd backend
uv run python scripts/benchmark_intelligence.py                          # sample, 1000, 5000
uv run python scripts/benchmark_intelligence.py --sizes sample,20000 --runs 7
```

The script prints a Markdown table like the one above. The synthetic networks and their
databases are generated afresh on each run, in a new temporary directory.
