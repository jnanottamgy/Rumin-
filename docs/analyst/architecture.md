# Architecture

## Modules

`backend/app/analyst/`, in the order a question meets them:

| Module | What it does |
|---|---|
| `policy.py` | Screens a question for instructions aimed at the Analyst, requests for secrets, investment decisions, forecasts and live data. Cleans stored text before a model sees it (`data_text`). Holds the fixed texts of every refusal and the forbidden phrasings |
| `vocabulary.py`, `parsing.py` | The names RUMIN knows (companies, industries, countries, economic variables, series, instruments, models, templates, with curated aliases), loaded from the database for each turn; figures (%, percentage points, basis points, doubles/halves, currency amounts), periods and horizons read from the question |
| `router.py` | Reads the question into a **route**: an intent (one of 24), the records named, the changes of a what-if with the assumptions made in reading them, periods, the line or channel asked about; fills a missing subject from the conversation's focus, or asks a **clarification** |
| `context.py` | The conversation's **focus** (the entity, variable, series, scenario, execution and changes under discussion) and the bounded summary of recent turns |
| `tools/` | The **registry** (allowlist, validation, time limits, retries, recording) and the 17 tools over existing services ([tools](tools.md)) |
| `evidence.py` | The **evidence ledger**: every tool result becomes numbered evidence (E1, E2 …) with its kind of knowledge, source, period, units, provenance and values ([evidence](evidence.md)) |
| `answer.py` | The answer's schema: status, headline, **blocks** (text with citations, tables, series, paths, scenario cards, notices, clarifications), evidence, follow-ups, grounding result |
| `composer.py` | RUMIN's **grounded composer**: per intent, which tools to call and the templates that turn their results into cited sentences |
| `grounding.py` | The **grounding check**: every figure, date and version in the answer must be in the evidence its sentence cites; citations must exist; interpretation carries no figures; no forbidden phrasing |
| `providers/` | `grounded` (the composer), `anthropic` (a Claude model through the official SDK), `scripted` (tests) ([providers](providers.md)) |
| `orchestrator.py` | One turn: route, provider, check, fallback, withholding, the new focus |
| `runner.py` | The bounded worker pool (the Scenario Lab's design) |
| `evaluation.py` | The evaluation set and its scorer; `python -m app.analyst.evaluation` ([evaluation](evaluation.md)) |

`backend/app/services/analyst.py` holds the runtime (provider, runner, token budget, the
turn's lifecycle in the database) and the session operations; `backend/app/api/v1/analyst.py`
the routes; `backend/app/schemas/analyst.py` the API's schemas.

## One turn

```
POST /analyst/sessions/{id}/turns {question}
  │  length ≤ RUMIN_ANALYST_MAX_QUESTION_CHARS · turns ≤ RUMIN_ANALYST_MAX_TURNS_PER_SESSION
  │  one pending question per conversation · a place in the pool (else 429, nothing stored)
  ▼
turn stored: queued ──► 202 Accepted {turn, poll_after_ms}
  │
  ▼  a worker claims it (queued → running, in one UPDATE: never twice)
orchestrator
  ├─ vocabulary loaded; question screened and routed against the conversation's focus
  ├─ fixed intents (clarify, injection, secrets, unsupported, capabilities) → grounded composer
  ├─ otherwise the configured provider:
  │     grounded composer ──► tools ──► cited blocks
  │     or a Claude model ⇄ tools (bounded loop) ──► submit_answer ──► RUMIN's displays
  ├─ every tool call: allowlisted, validated, own session and time limit, recorded as it ends
  ├─ grounding check ── failed (model) ──► the grounded composer answers instead, with a notice
  │                  └─ failed (grounded) ──► failing parts withheld, with a notice
  └─ the new focus
  ▼
turn stored: completed (answer, evidence, grounding, provider, usage, timings) or failed
```

The reader polls `GET /analyst/sessions/{id}/turns/{turn_id}` every `poll_after_ms`; each tool
call appears as soon as it is recorded. Nothing is streamed or invented in between: the page
shows what the server has stored.

## The worker pool

`runner.py` follows the Scenario Lab's runner: at most `RUMIN_ANALYST_MAX_CONCURRENT` turns
at once and `RUMIN_ANALYST_MAX_QUEUED` waiting. A place is **reserved before anything is
stored**, so a full pool answers 429 and leaves no trace. A worker claims a turn with a
conditional update (`queued → running`), so a turn is never answered twice, even across
processes. Each turn has its own deadline (`RUMIN_ANALYST_DEADLINE_SECONDS`), passed to every
tool call as the time left. When the server starts, turns left queued or running by a
stopped process are marked failed. `inline` mode answers in the request itself (tests).

Each tool call runs in its own thread with its own database session and a time limit; a
transient database error (`OperationalError`) is retried once. The tool's result is turned
into evidence on the calling thread, so the ledger is never shared between threads.

## Storage

Migration `0007_analyst` adds three tables ([data model](../data-model.md#ai-analyst-phase-7)):

- `analyst_sessions`: a conversation: its title (the first question, until renamed), its
  focus and turn count.
- `analyst_turns`: one question and its answer: status (`queued`, `running`, `completed`,
  `failed`), intent, the answer (headline, blocks, evidence, follow-ups, grounding result) with
  its SHA-256 hash, the route and focus, the configured and the actual provider, the model
  (when one answered), the fallback reason, the rejected model draft's check (if any), token
  usage, the Analyst version and timings. A final turn never changes.
- `analyst_tool_calls`: every tool call of a turn: tool, arguments, status, summary, its
  result with its hash (a result longer than 32,000 characters is kept as its size and hash
  only), the evidence ids it produced, attempts and timing.

Deleting a conversation deletes its turns and tool calls. A conversation cannot be deleted
while one of its questions is being answered (409).

## Reuse, not re-implementation

Every tool calls a service that already existed: Phase 2's series and observations,
Phase 3's paths and edges, Phases 4–5's models, templates, previews, executions and
explanations, and Phase 6's dossiers, exposure, variable reach, changes, findings and
drivers. The Analyst computes no financial figure of its own: the only arithmetic it does is
in Phase 6's exact statistics (a period change) and the Scenario Lab's models (a preview),
both of which predate it.
