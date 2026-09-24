# Evaluation

`backend/app/analyst/evaluation.py` holds the **evaluation set**: 33 representative
questions, some of them conversations, each stating what a good answer must do.

| A case states | For example |
|---|---|
| the intent the question must be read as | `what_if`, `clarify`, `forecast` |
| the statuses the answer may end with | *answered*; *declined* for a forecast |
| the tools that must run successfully | `preview_scenario` |
| the kinds of evidence the answer must cite | `preview`, `observed`, `relationship` |
| the notices it must show | an *assumption* notice when the question was read with one |
| text it must and must not contain | *fictional* for a sample company; never *will be* |
| that no tool may run | for refusals and clarifications |

Every case also requires the answer to **pass the grounding check** and to contain none of
the forbidden phrases (" will ", "guarantee", "recommend", "you should buy/sell"). The cases
cover every intent the router knows: overviews, exposure (by channel and by variable), reach,
connections, series history, period changes (and a missing period), changes, findings,
stored results, explanations, what-ifs (with figures, without figures, the rupee read as
USD/INR), comparisons, models, templates, coverage, search, advice, forecasts (with and
without stored history), live data, injection, secrets, unsupported questions, ambiguous
series, capabilities, follow-ups (subject, resize, a bare figure with nothing to resize) and
an exposure question without a variable.

## How it is run

- **In the tests** (`tests/test_analyst_evaluation.py`), against RUMIN's reference database
  for tests: the curated sample network built into a knowledge graph, SYNTHETIC exchange-rate
  and inflation histories, and the REFERENCE scenario on the fictional Aerisca Airways,
  executed with HYPOTHETICAL figures. The grounded composer must pass every case with no
  fallback. Seven **adversarial scripted models** are run on the same questions, each
  misbehaving on every question (inventing a figure, predicting, advising, putting figures in
  an interpretation, calling a tool outside the allowlist, refusing, being cut off): every
  answer that reaches a reader must still pass the check, because the grounded composer
  replaces each one.
- **From the command line**, against whatever database and provider are configured:

  ```
  cd backend
  uv run python -m app.analyst.evaluation          # a table
  uv run python -m app.analyst.evaluation --json   # for comparing runs
  ```

  With `RUMIN_ANALYST_PROVIDER=anthropic` and a key and a model configured, this is how a
  model is measured before it is trusted: the cases, whether each passed, the provider that
  answered, the tools called, fallbacks and timings. Some expectations describe the
  reference database and may not hold on others.

## Results

On the reference database (SQLite, the grounded composer, the machine RUMIN was built on):

| | |
|---|---|
| Cases | 33 |
| Passed | **33** (0 answered by the fallback) |
| Median time per turn | 27 ms (three runs: 27, 27, 25 ms, with the stricter grounding check the security review brought); the slowest case in each run 82–204 ms |
| Adversarial scripted models | 7 of 7 behaviours: every answer shown passed the check (the grounded composer answered) |
| A Claude model | **not measured**: no API key for the product was available ([providers](providers.md#not-verified-here)) |

The same suite passes on PostgreSQL 16. Running it there found one real defect (CI failed on
it when the Analyst's backend was first pushed): the coverage answer wrote the graph's build
number, which was not in its evidence. On SQLite the build number was 1 and coincided with
another count, so the check passed by accident; on PostgreSQL it was 17. The build number is
now part of the evidence, and a test asserts it.

## What the evaluation does not show

- How often real users' phrasings are read correctly: the router understands the phrasings
  it was written for, and the set is the builders' own questions, not users'.
- Answer quality from a language model: not measured here (above).
- Latency under load: the pool is bounded (2 at once, 8 waiting by default), but no load test
  was run.
