# Tools

The Analyst reaches RUMIN only through these tools. They are an **allowlist**: a name that is
not in it is refused, whoever asks for it. Each tool has a typed input model that refuses
unknown fields and out-of-range values, a time limit, and a function that turns its result
into evidence and, where useful, a display (a table, a series, paths or a scenario card).
None writes anything. One tool computes (`preview_scenario`), and what it computes is never
stored.

| Tool | Kind | Limit | Inputs | Answers | Service reused |
|---|---|---|---|---|---|
| `search_records` | read | 4 s | `query`, `kinds`, `country_key`, `limit` | records matching a name, or a listing by kind and country | graph nodes, series catalogue, scenarios, models, templates |
| `get_entity_dossier` | read | 10 s | `entity_key` | what RUMIN knows about a company or industry: record, exposure, counterparties, latest execution, findings | Phase 6 dossier |
| `get_exposure` | read | 8 s | `entity_key`, `channel`, `variable_key`, `evidence` | which variables reach an entity, through which relationships, by channel, with the weakest evidence on each path | Phase 6 exposure |
| `get_variable_reach` | read | 8 s | `variable_key` | every company a variable reaches, and the series recorded as its related measures | Phase 6 variable reach |
| `find_paths` | read | 8 s | `from_key`, `to_key`, `max_depth` (1–6, default 4) | the shortest chains of relationships between two records | Phase 3 shortest paths |
| `get_relationship` | read | 4 s | `edge_key` | one relationship with its evidence, rationale and caveat | Phase 3 edge detail |
| `get_series` | read | 8 s | `series_id`, `start_year`, `end_year`, `last` | stored values with provenance, the latest, the last change, trend, volatility, revisions | Phase 2 observations, Phase 6 series analysis |
| `compare_periods` | read | 4 s | `series_id`, `from_period`, `to_period` | the exact change between two stored values | Phase 6 exact statistics |
| `list_changes` | read | 10 s | — | new observations over the default thresholds, revisions, simulated changes, graph changes | Phase 6 changes |
| `get_findings` | read | 10 s | `entity_key`, `kind`, `limit` | Financial Intelligence findings with their grades | Phase 6 insights |
| `list_scenarios` | read | 5 s | `entity_key`, `limit` | stored scenarios and their latest executions | Phase 5 scenarios |
| `get_execution` | read | 8 s | `execution_id` or `entity_key` | a stored execution: lines, changes, models, assumptions, the figures a person entered, drivers | Phase 5 results, Phase 6 drivers |
| `explain_line` | read | 8 s | `line`, `execution_id` or `entity_key` | why a line of an execution changed: the contribution of each change | Phase 5 explanation |
| `preview_scenario` | compute | 15 s | `changes` (1–5), `entity_key`, `horizon_months`, `use_stored_figures` | what the models compute for a what-if, **not stored**; or, without figures, the plan and what is missing | Phase 5 preview and plan |
| `list_models` | read | 4 s | — | the registered models, versions, what they need | Phase 4 registry |
| `list_templates` | read | 6 s | — | the scenario templates and what they need | Phase 5 templates |
| `get_data_coverage` | read | 4 s | — | which series hold values, how many, the graph build, stored scenarios | Phase 2 catalogue, Phase 3 builds |

Keys follow the graph's form (`company:co_…`, `industry:ind_…`, `variable:var_…`,
`series:wb-…`), validated by pattern.

## What every call goes through

`tools/registry.py`, `ToolRunner.call`:

1. **Allowlist**: an unknown name is recorded as `refused` and returns an error to the caller.
2. **Validation**: the arguments are parsed by the tool's input model; a failure is recorded
   as `invalid` with the field and returned (a model can correct itself; nothing runs).
3. **Access**: compute tools run only when the access context allows it (`Access.may_compute`),
   the one place per-user checks will go when RUMIN has authentication.
4. **Limits**: at most `RUMIN_ANALYST_MAX_TOOL_CALLS` calls per turn (default 12) and none
   after the turn's deadline (`skipped`); each call's time limit is the tool's own or the time
   left, whichever is shorter (`timeout`).
5. **Isolation**: the call runs with its own database session, in its own thread; a transient
   database error is retried once; any other error is recorded as `failed` with a safe message,
   never a stack trace.
6. **Evidence**: the result is rendered into numbered evidence in the turn's ledger, and the
   call is recorded (arguments, status, summary, a bounded result, the evidence ids, timing).
   Only then does the caller see it.

A tool that fails, times out or finds nothing adds **no evidence**: nothing can be cited from
it, so nothing can be claimed from it.

## Why no general-purpose tool

There is no SQL tool, no code execution, no web access, no file access and no tool that
writes. A language model sees only the 17 descriptions and their input schemas (plus
`submit_answer`, which ends the turn). Anything a question needs that the tools cannot read
is answered as *not held by RUMIN*.
