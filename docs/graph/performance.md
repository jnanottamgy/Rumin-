# Performance

Measured build and query times for the knowledge graph, the bottlenecks found and fixed,
and the ones that remain. **Every number here was measured on synthetic data, on one
machine, and describes that machine only.** None of it is a claim about production.

## How it was measured

- **Backend:** `backend/scripts/benchmark_graph.py`. For each size it writes a
  **SYNTHETIC** dataset, loads it through the real validating seed loader into a fresh
  database, runs the real graph build, then an unchanged rebuild, and times the service
  behind each graph endpoint. Each timing is the median of 5 runs after one warm-up.
- **Synthetic networks:** *n* companies named "Synthetic Company …", all marked
  fictional, each with two `supplies_to` links, a 10 % chance of `lends_to`, a 20 %
  chance of `competes_with` and one assumed effect from a variable. They sit in 20 real
  countries (with their real ISO codes and currencies) and up to 88 synthetic industries
  on real ISIC divisions, with one variable per 25 companies. The 20,000-company network
  has **20,948 nodes and 107,832 edges**.
- **Machine:** 4 vCPUs (Intel Xeon, 2.10 GHz) and 15 GB of memory. Python 3.11.15,
  SQLite 3.45.1 (a file database), and PostgreSQL 16.13 on the same machine.
- **Frontend:** `frontend/scripts/measure-graph.mjs` times the explorer's pure work
  (merging answers into a view, and the layout) with Node 22. A Playwright script timed
  the page in Chromium against an API serving the 20,000-company graph.

To re-run:

```bash
cd backend
uv run python scripts/benchmark_graph.py                   # SQLite: 100, 1,000, 5,000, 20,000
uv run python scripts/benchmark_graph.py --sizes 100,1000  # faster
uv run python scripts/benchmark_graph.py --postgres postgresql+psycopg://user:pass@localhost/rumin_bench
cd ../frontend && node scripts/measure-graph.mjs
```

`--postgres` **wipes** the database it is given (it drops the `public` schema). Point it
at a scratch database only.

## Results: SQLite

| Measure | 100 companies | 1,000 companies | 5,000 companies | 20,000 companies |
|---|---|---|---|---|
| Nodes / edges | 149 / 570 | 1,098 / 5,429 | 5,341 / 27,093 | 20,948 / 107,832 |
| Load the dataset (s) | 0.10 | 0.36 | 1.91 | 8.19 |
| Build: read + assemble (s) | 0.02 + 0.02 | 0.10 + 0.12 | 0.47 + 0.62 | 2.25 + 3.29 |
| First build (s) | 0.11 | 0.74 | 4.08 | 21.05 |
| Unchanged rebuild (s) | 0.05 | 0.43 | 2.66 | 16.24 |
| Nodes and edges added or changed by the rebuild | 0 | 0 | 0 | 0 |
| Overview, first request (ms) | 13.9 | 149.1 | 919.3 | 6,109.6 |
| Overview, cached (ms) | 0.6 | 0.4 | 0.5 | 0.6 |
| Search by name (ms) | 3.3 | 4.1 | 11.4 | 36.9 |
| Node detail (ms) | 5.1 | 4.7 | 4.7 | 6.1 |
| Neighbourhood of a company, depth 1 (ms) | 3.9 (8 nodes) | 4.2 (10) | 5.0 (10) | 9.9 (7) |
| … depth 2 (ms) | 17.2 (80) | 32.1 (179) | 27.3 (200, cut) | 38.5 (200, cut) |
| … depth 3 (ms) | 28.2 (133) | 33.3 (200, cut) | 30.3 (200, cut) | 43.6 (200, cut) |
| Neighbourhood of a hub country, depth 1 (ms) | 3.0 (4) | 11.1 (65) | 23.2 (200, cut) | 32.1 (200, cut) |
| … depth 2 (ms) | 5.2 (16) | 37.2 (200, cut) | 24.4 (200, cut) | 32.6 (200, cut) |
| … depth 3 (ms) | 20.2 (92) | 36.6 (200, cut) | 29.5 (200, cut) | 31.9 (200, cut) |
| Shortest paths between two companies (ms) | 6.4 (3 hops, 74 explored) | 2.7 (2 hops, 17) | 6.3 (3 hops, 381) | 11.8 (3 hops, 1,318) |
| Components (ms) | 3.2 | 5.1 | 29.0 | 86.5 |

A neighbourhood used one query per level plus one (2 queries at depth 1, 3 at depth 2, 4
at depth 3), or fewer when the 200-node cap stopped it early. "Cut" means the cap was
reached and the response said so.

## Results: PostgreSQL

| Measure | 100 companies | 1,000 companies | 5,000 companies | 20,000 companies |
|---|---|---|---|---|
| Load the dataset (s) | 0.10 | 0.60 | 3.23 | 12.87 |
| Build: read + assemble (s) | 0.03 + 0.03 | 0.12 + 0.09 | 0.54 + 0.80 | 2.41 + 3.82 |
| First build (s) | 0.42 | 2.07 | 8.09 | 38.07 |
| Unchanged rebuild (s) | 0.07 | 0.53 | 3.29 | 16.63 |
| Overview, first request (ms) | 21.2 | 169.9 | 1,024.3 | 5,893.0 |
| Overview, cached (ms) | 1.1 | 1.0 | 1.3 | 1.3 |
| Search by name (ms) | 6.2 | 8.2 | 13.9 | 62.2 |
| Node detail (ms) | 15.5 | 12.5 | 10.9 | 12.9 |
| Neighbourhood of a company, depth 1 / 2 / 3 (ms) | 8.2 / 23.6 / 41.2 | 12.3 / 48.0 / 49.4 | 10.9 / 53.4 / 85.9 | 11.9 / 45.8 / 53.4 |
| Neighbourhood of a hub country, depth 1 / 2 / 3 (ms) | 7.5 / 9.6 / 26.6 | 19.7 / 48.9 / 58.0 | 82.3 / 78.9 / 84.5 | 59.7 / 64.0 / 54.4 |
| Shortest paths between two companies (ms) | 9.5 | 7.3 | 9.5 | 19.3 |
| Components (ms) | 7.5 | 11.2 | 37.3 | 69.3 |

The graphs, node counts, answer sizes and query counts were the same as on SQLite.

## What the numbers show

- **Bounded requests stay bounded.** Node detail, neighbourhoods, paths and search stay
  under about 90 ms at every size on both databases. Their cost follows the size of the
  *answer* (capped at 200 nodes), not the size of the graph.
- **Whole-graph work grows with the data.** Loading, building, rebuilding and the first
  overview request read every source record, so they grow a little faster than the data:
  about 1 second per 1,000 companies for a first build on SQLite at 20,000 companies
  (about 2 on PostgreSQL).
- **Rebuilds change nothing when nothing changed.** Nothing was added or changed at any
  size, because keys are deterministic and content is hashed.

## Bottlenecks found and fixed

Found by profiling on the 1,000- and 20,000-company networks (SQLite), then fixed and
measured again. "Before" and "after" are the same benchmark run immediately before and
after each fix, so each row shows that fix's own effect.

| Problem | Fix | Before | After |
|---|---|---|---|
| Entity resolution compared every pair of names that shared any word, so thousands of "Synthetic Company …" names were compared pair by pair (quadratic) | Normalise each name once. Find candidates by blocking: the same normalised name, the same words, or a shared word used by at most 100 names ([details](entity-resolution.md#finding-candidates-without-comparing-every-pair)) | assemble 4.79 s, first build 6.51 s, rebuild 5.49 s (1,000 companies) | 0.13 s, 1.58 s, 0.83 s |
| Edge lookups used `source IN … OR target IN …`, which SQLite answered by scanning every edge | A `UNION ALL` of two searches on the partial indexes over current edges, by source and by target | at 20,000 companies: node detail 517 ms; neighbourhoods 401–720 ms; paths 557 ms | 6 ms; 11–43 ms; 13 ms |
| Persistence compared and wrote rows one at a time | Compare content hashes from plain rows. Insert and update in bulk, by primary key | first build 42.0 s, unchanged rebuild 22.4 s (20,000 companies) | 21.1 s, 16.2 s |
| The overview hashed every source record on every request, with deep copies, and counted the type map each time | Hash field values without deep copies (the same hash, so existing builds stay current). Keep the freshness answer for 30 s per API process, and the type map for the life of the build | 6.9 s per request (20,000 companies) | 6.1 s for the first request, then 0.6 ms |

The fixes were verified by the full backend suite on SQLite and PostgreSQL, and by a test
that pins the blocking behaviour, including its trade-off
(`test_common_words_do_not_make_every_name_a_candidate`).

## Remaining bottlenecks

| Where | Cost at 20,000 companies | Why it remains | What would fix it |
|---|---|---|---|
| **First overview request** after a build or an API restart | ~6 s (SQLite and PostgreSQL) | Checking freshness reads every source record (about 2.3 s at this size) and hashes it. Counting the type map adds about 0.5 s | Record a change counter or a per-table checksum when sources are written, so freshness can be checked without reading every record |
| **Unchanged rebuild** | ~16 s | A rebuild re-reads and re-assembles everything before it can tell that nothing changed. Components are computed twice (once for the metrics, once for the stored component numbers) | Skip the build when the source fingerprint is unchanged. Compute components once |
| **Search by name** | 37 ms (SQLite), 62 ms (PostgreSQL) | A `LIKE '%text%'` scan over the search text | A trigram index (PostgreSQL `pg_trgm`) or a full-text index |
| **Selecting a node in a 150-node view** | ~100 ms | The whole canvas re-renders on selection | Render emphasis in a separate layer, or memoise per node |

None of these limits correctness. At the sample graph's size (50 nodes) every request
takes a few milliseconds.

### The freshness cache

`GET /api/v1/graph/overview` says whether the graph is **current** or **stale** by
comparing the latest build's fingerprint with the current sources. To avoid reading
every source record on every request, each API process keeps the answer for **30
seconds** (`FRESHNESS_TTL_SECONDS` in `app/services/graph.py`). The trade-off:

- a source change can take up to 30 seconds to show as **stale** on a running API;
- a new build is seen immediately, because the cache is keyed by the build.

Every test starts and ends with an empty cache, and one test pins the 30-second window
(`test_freshness_is_cached_briefly`).

## Validation at scale

The benchmark builds exercise the validator on real rules. At 20,000 companies (SQLite):

```
Nodes processed: 20,948    Valid nodes: 20,948    Flagged: 0    Rejected: 0
Edges processed: 107,920   Valid edges: 107,832   Flagged: 0    Rejected: 88
Issues: 88 reality_mismatch (rejected) · 21 isolated_node (noted)
Entity resolution: 108 linked by identifier
```

The 88 rejected edges are the sector links of the 88 synthetic industries. Those
industries are fictional, and an evidence-backed edge may not touch fictional data. The
21 ISIC sections were left without edges and noted as isolated. Both are the rules
working as designed.

## The explorer

**Pure work per view change** (`measure-graph.mjs`, synthetic views, about 2.5 edges per
node):

| Nodes in view | Edges | Merge into a view (ms) | Radial layout (ms) |
|---|---|---|---|
| 50 | 123 | 0.41 | 0.27 |
| 100 | 248 | 0.89 | 0.54 |
| 150 | 373 | 1.73 | 1.34 |
| 200 | 498 | 2.77 | 2.20 |
| 1,000 | 2,498 | 16.10 | 13.74 |

The explorer draws at most 150 nodes, so merging and layout take under 2 ms per change.

**In the browser** (Chromium 1440 × 900, the Vite development server, the API serving the
20,000-company graph on SQLite):

| Step | Reduced motion (ms) | With animation (ms) |
|---|---|---|
| Open a hub country's neighbourhood (depth 1, 100 nodes), including the request | 310 | 254 |
| Raise the limit to 150 nodes (a new request and a full re-layout) | 66 | 81 |
| Depth 2, 150 nodes | 20 | 18 |
| Select a node (rendering only, to the second animation frame) | 108 | 102 |

The first three steps are wall-clock times from a Playwright script that polls the page
every 10 ms, so they are approximate. The selection time was measured inside the page
with the Performance API. The canvas is SVG. It is suitable for the 150-node cap, and a
larger view would need canvas or WebGL rendering and a layout in a Web Worker.
