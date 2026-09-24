# Limitations

What the AI Analyst does not do, and where it can be wrong. Each item says what would lift
it.

## Understanding questions

- **The grounded composer reads the phrasings its router was written for.** It recognises
  the names RUMIN holds (with curated aliases such as *the rupee*, *crude oil*, *fed funds*, *repo rate*),
  figures, periods and 24 kinds of question. A question phrased outside those patterns may
  be read as a different intent, sent to a clarification, or answered as *outside RUMIN's
  records*. The reading is always shown (the intent under *How this was answered*, and
  assumptions in a notice), so a misreading is visible, but it is not prevented. A language
  model reads more phrasings; the evaluation set should grow with real questions.
- **One subject at a time.** Comparisons cover two or more companies' exposure; other
  questions take one company, variable or series. *Compare Aerisca's and Skyvara's latest
  scenarios* is not supported.
- **What-ifs take up to five changes** to variables RUMIN holds, as percentages, percentage
  points (or basis points) or amounts in the variable's unit. A rate written in percent is read
  as percentage points, and a weaker rupee as a USD/INR rise; both readings are stated.
- **English only.**

## Answers

- **No figures of its own.** The Analyst computes nothing beyond what existing services
  compute: it will not add up exposures, weight scenarios, annualise or convert currencies.
  A question that needs such a figure gets the records it would need, not the figure.
- **Relationships are stated, not measured.** Exposure answers say *who* is exposed and
  *through what*, never *how much*: the sample graph's relationships are recorded or assumed,
  not estimated (Phase 3). Sizing needs a scenario with a company's figures.
- **Simulations are deterministic.** A preview or stored result is one path under stated
  changes and entered figures, with no probability and no range (Phases 4–5).
- **The sample network is illustrative.** Its companies are fictional; answers about them
  say so. Series values are whatever has been ingested; where RUMIN was built, only SYNTHETIC
  test values were stored, because the World Bank API was not reachable.

## The language model

- **Not verified against a live model** (no key where RUMIN was built). The integration is
  tested through the real SDK against a mocked transport; its answer quality, latency and
  cost are unmeasured. Run the evaluation set with a key before relying on it.
- **Grounding checks figures, not reasoning.** A model's sentence can cite the right evidence
  and still misdescribe it in words that contain no figure ("the largest", "most exposed",
  "sharply"). Forbidden phrasing is caught, figures must match a value of their own kind
  (a percentage, percentage points, an amount in its currency), and anything that looks like
  a figure but cannot be read exactly fails; a subtle misreading in words is not caught. The
  grounded composer's templates do not have this problem; a model's answers should be read
  with their sources, which is why the margin sits beside them.
- **The check is strict, so a model's correct answer can be refused.** A figure written in
  words, a range written with a hyphen (`5-45%`), a name with digits that is not written
  exactly as stored, or a percentage matched against a value no tool marked as one fails the
  check, and the grounded composer answers instead. That is the intended trade-off; the
  rejected draft and its problems are stored with the turn for review.
- **Context is bounded.** A model sees the focus and up to four earlier headlines, not the
  full conversation; long, winding conversations lose earlier context by design.

## System

- **No authentication** (Phase 10): anyone who can reach the API can read and delete every
  conversation. Bind the API to localhost, as by default.
- **One process's pool.** The worker pool and the daily token budget are per API process;
  several processes would each apply their own limits, and one process's start would mark
  the others' running turns failed (`recover`). A shared queue and budget are future work.
- **The token budget is checked before each turn.** It counts every token a model read or
  wrote, cached or not, but a turn in progress is not stopped when the total passes the
  budget: the overshoot is at most one turn's use (bounded by the requests per turn and the
  tokens per request).
- **Polling, not streaming.** The page reads the turn every half-second or so while it is
  answered; tool calls appear as they are recorded, but a model's text appears only when the
  turn is complete.
- **Stored answers are not re-checked.** A stored answer is shown as it was answered, with
  its evidence as read then. Asking again reads the data as it is now.
