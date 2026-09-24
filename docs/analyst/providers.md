# Providers

A provider turns a routed question and the tools into a draft answer. All providers share
the router, the tools, the evidence ledger, the grounding check, storage and the interface;
only the drafting differs.

| Provider | Drafts with | When |
|---|---|---|
| `grounded` | RUMIN's own composer: per intent, the tools to call and templates filled from their results. No language model | The default (`RUMIN_ANALYST_PROVIDER=grounded`); always used for clarifications, refusals and the capabilities question; the fallback for everything else |
| `anthropic` | A Claude model through the official `anthropic` Python SDK, calling the same tools in a loop RUMIN controls | When `RUMIN_ANALYST_PROVIDER=anthropic` and a key and a model are configured |
| `scripted` | Replayed tool calls and text, deterministic | Tests only |

The page states who answers (*Grounded answers* or *Language model configured*), and every
answer's method says who composed it and whether a fallback happened.

## The grounded composer

`composer.py` holds one method per intent. Each calls the tools it needs through the same
registry a model would use and writes sentences whose figures come straight from the tool
results, each ending with its citations. It also decides the answer's status (*answered*,
*partly answered*, *RUMIN holds no data for this*, *needs a choice*, *declined*, *outside
RUMIN's records*), the follow-up questions, the notices (assumptions made in reading the
question, missing data, limitations, what is illustrative or not stored), and the
conversation's new focus.

It has no model, no network access and no randomness: the same question on the same data
gives the same answer, in about 20 ms on the reference database
([evaluation](evaluation.md)). It is limited to the phrasings its router understands; see
[limitations](limitations.md).

## The Anthropic provider

`providers/anthropic.py` uses the official SDK (`anthropic`, pinned in
`backend/pyproject.toml`), the only runtime dependency added in this phase.

**Configuration is explicit, and the model is configuration.** The client is built from
RUMIN's settings only:

| Setting | Default | Meaning |
|---|---|---|
| `RUMIN_ANALYST_PROVIDER` | `grounded` | `anthropic` to use a Claude model |
| `RUMIN_ANTHROPIC_API_KEY` | — | the API key (a secret: never logged, never returned by the API) |
| `RUMIN_ANALYST_MODEL` | — | the model to call. **No model identifier is written in the repository**: choose one when deploying |
| `RUMIN_ANTHROPIC_BASE_URL` | `https://api.anthropic.com` | must be `https://` (plain `http://` only for localhost) |
| `RUMIN_ANALYST_THINKING` | `adaptive` | `adaptive` or `off` |
| `RUMIN_ANALYST_MAX_TOKENS` | 4096 | output tokens per model request |
| `RUMIN_ANALYST_REQUEST_TIMEOUT_SECONDS` | 60 | per model request |
| `RUMIN_ANALYST_MAX_RETRIES` | 2 | the SDK's retries of a failed request (with its backoff) |
| `RUMIN_ANALYST_MAX_MODEL_REQUESTS` | 6 | model requests per turn |
| `RUMIN_ANALYST_DAILY_TOKEN_BUDGET` | 2,000,000 | input + output tokens a day across all turns; beyond it the grounded composer answers |

The SDK would otherwise read `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN` and
`ANTHROPIC_BASE_URL` from the environment when no value is passed; RUMIN always passes its
own, so those variables are ignored (tests prove it). The SDK also adds headers from
`ANTHROPIC_CUSTOM_HEADERS`; if that variable is set, RUMIN refuses to build a client rather
than send headers it did not choose, and the grounded composer answers.

**The loop is manual and bounded.** RUMIN sends the question with a bounded context (the
conversation's focus and the headlines of up to four earlier turns), the 17 tool
definitions and `submit_answer`. Each `tool_use` the model returns is run through the
registry (allowlist, validation, limits) and answered with a compact JSON result that lists
its evidence ids; stored text in it has been cleaned. The model finishes by calling
`submit_answer` with a headline, paragraphs (each with a role: answer, detail,
interpretation, general) and the tool calls whose displays to show. The tables, charts,
paths and scenario cards are RUMIN's, built from the tool results; the model only chooses
them. The system prompt is cached (`cache_control`), and adaptive thinking is used unless
turned off.

**Failures fall back, and say so.** An authentication, permission, rate-limit, timeout,
connection or server error; a refusal; an answer cut off at the token limit; too many model
requests; or a draft that fails the grounding check: each ends the model's attempt with a
safe reason, the grounded composer answers from the same tools, and the answer carries a
*Fallback* notice naming the reason. Token usage is recorded either way.

## Not verified here

No API key for the product was available where RUMIN was built, so **no request to a Claude
model has been made**. The provider is tested through the real SDK against a mocked HTTP
transport (request shape, the tool loop, every error class, refusals, cut-offs, cached
system prompt, environment isolation) and against adversarial scripted models; a live test
(`tests/test_analyst_live.py`) runs only when `RUMIN_ANTHROPIC_API_KEY` and
`RUMIN_ANALYST_MODEL` are set. How well a given model answers RUMIN's questions is therefore
unmeasured; the evaluation set is the way to measure it ([evaluation](evaluation.md)).
