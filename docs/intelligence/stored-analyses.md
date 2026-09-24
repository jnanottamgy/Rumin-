# Stored analyses

Every read of Financial Intelligence is computed from the current store and writes nothing.
To keep what an analysis said at a point in time, for a review, a file note or a later
comparison, store it: `POST /intelligence/analyses`. A stored analysis is a snapshot. It is
never recomputed, updated or deleted, and reading it back says whether anything it read has
changed since.

## Storing one

```http
POST /api/v1/intelligence/analyses
{"scope": "entity", "entity": "company:co_aerisca_airways",
 "label": "Before the data arrived", "thresholds": {"relative_change_percent": "3"}}
```

- `scope` is `entity` (then `entity` is required: a company or an industry) or `workspace`
  (then `entity` must be absent).
- `thresholds` overrides the defaults, with at most 20 entries. A problem is refused with a
  422 naming `thresholds.<name>` in the body.
- `evidence` (`any` or `evidence_backed`) filters the exposure relationships, as on reads.
- `label` is optional, at most 200 characters of plain text.

The answer is `201 Created`, with a `Location` header, and contains the stored analysis as
`GET /intelligence/analyses/{id}` returns it. An invalid request stores nothing. A test sends
invalid thresholds, a missing or superfluous entity, and an unknown entity, then checks that
the table is still empty.

## What is stored

Migration `0006` adds `intelligence_analyses` ([data model](../data-model.md), [data
dictionary](../data-dictionary.md)):

| Column | Contents |
|---|---|
| `id` | UUID |
| `scope`, `subject_key`, `subject_name`, `label` | what was analysed. A check constraint allows only `entity` with a subject, or `workspace` without one |
| `engine_version` | `INTELLIGENCE_VERSION` at the time (1.0.0) |
| `thresholds` | every threshold as used, defaults included |
| `graph_build_id` | the build the analysis read |
| `inputs`, `inputs_hash` | the **fingerprint** of everything it read, and its SHA-256 |
| `result`, `result_hash` | the analysis exactly as the API returned it (the dossier or the overview), and its SHA-256 |
| `insight_count`, `duration_ms`, `created_at` | how many findings, how long it took, when |

Indexes on (`scope`, `created_at`) and (`subject_key`, `created_at`) serve the list, newest
first, filtered by scope or entity. No code path updates or deletes a row, and the API has no
route that could: a test checks that the intelligence paths offer only `GET` (and `POST` on
the collection), and that `DELETE` is refused with 405. Another test stores an analysis,
adds an execution, and checks that the analysis now reads stale (`executions`) while its
result hash and content are unchanged.

## The fingerprint

`inputs` records what the analysis depended on, in a form that can be compared later:

| Section | Entity scope | Workspace scope |
|---|---|---|
| `graph` | the latest build's id, finish time and source fingerprint | same |
| `data` | for each series related to the entity's exposure variables: the number of stored observation rows and the highest row id | the same for every series, and the price bars of every instrument |
| `executions` | the entity's completed executions (latest 20) and the sensitivity analyses of the latest | the latest completed execution of each listed company, and the count of completed executions |
| `engine_version`, `scope`, `subject` | the engine's version and what was analysed | same |

Stored values are append-only (a revision is a new row), so a new value **or** a revision
changes a series' count and highest id. A rebuilt graph changes the build. A new execution
changes the execution lists.

## Freshness

`GET /intelligence/analyses/{id}` returns the analysis **as it was stored**, with a
`freshness` block computed on each read:

- **current**: *"Nothing it read has changed: recomputing it would give the same analysis."*
- **stale**, with the sections that changed (`graph`, `data`, `executions`, `engine_version`,
  `subject`, `scope`) and a sentence, for example: *"Since it was stored, stored values
  changed. It shows the analysis as it was; run a new one to see the current state."*
- If the entity is no longer in the current graph: stale, `subject`, *"The entity is no longer
  in the current knowledge graph."*

A stale analysis is never recomputed in place. It remains a record of what was concluded
from what was known then. To see the current state, run a new one. The fixtures
`analysis.json` and `synthetic-analysis-stale.json` show one analysis before and after
SYNTHETIC values were stored: the second reads *stale, data*.

## In the interface

The workspace and every dossier have a *Store this analysis* button, which stores the view
with the thresholds in use. A label can be given through the API. The workspace lists stored
analyses, newest first. Opening one (`/intelligence/analyses/{id}`) shows *"…, as stored"*
with the date, label, number of findings and engine version. It shows the freshness
statement (*Current* or *Stale*, with the reason), the findings as stored, the fingerprint and
hashes, and a link to *The analysis now*.
