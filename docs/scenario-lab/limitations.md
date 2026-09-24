# Scenario Lab limitations

What the Scenario Lab does not do, and why. The platform-wide list is in
[known limitations](../known-limitations.md).

## What it models

- **Five narrow models.** Airline fuel cost, foreign-currency revenue and costs,
  floating-rate interest, crude-oil-linked costs and natural-gas-linked costs. A change no
  model simulates cannot be executed; it is not approximated.
- **No volumes.** Every model holds volumes fixed (fuel consumed, US dollars invoiced, debt
  outstanding). There is therefore **no demand-shock or supply-chain template**: combining a
  volume change with models that hold volumes fixed would be wrong, and the graph's supplier
  relationships carry no quantities to simulate with.
- **Partial statements.** The Lab computes revenue, operating costs, operating profit,
  interest expense and profit before tax, operating margin and interest coverage — only the
  lines an included model contributes to. **Cash flow, tax, working capital and the balance
  sheet are not modelled** and never shown.
- **Constant baselines.** The baseline is the user's annual figures × horizon ÷ 12, held
  constant. It is an input, not a forecast: there is no growth, seasonality or inflation in
  the baseline.
- **Deterministic.** One path per scenario. Stress cases are other magnitudes of the same
  changes; sensitivity moves one quantity at a time. There are **no probabilities** and no
  Monte Carlo simulation (Phase 9).
- **Step changes.** A change starts in a month and lasts a number of months at a constant
  size; paths (a gradual rise, a spike and decay) are not supported. All changes of a
  scenario share one timing.
- **One company, one currency.** A scenario describes one company in one reporting currency;
  nothing is converted between currencies, and executions in different currencies or with
  different horizons are compared side by side, not differenced.
- **No second-round effects.** A change moves what the included models declare. The graph
  may state further relationships (Brent crude *influences* India CPI inflation, which
  *influences* the repo rate…); the Lab lists them as not modelled and does not follow them.

## What it rests on

- **Illustrative data.** The companies are fictional; the knowledge graph's relationships are
  recorded or assumed, and in the sample network all economic ones are *model assumptions*.
  A result that depends on an assumed relationship says so (for example: "Rule T1 follows a
  relationship the knowledge graph records as a model assumption").
- **Model assumptions have neutral defaults.** Pass-throughs, hedges, lags and elasticities
  default to documented values; a default is labelled as one wherever it is used.
- **The graph decides applicability, not amounts.** Including a model by default needs the
  graph to state the company's exposure; the amounts always come from the user's figures.

## How it runs

- **In-process worker pool.** Executions run on a thread pool inside the API process (2 at
  once, 8 waiting, 20 s each). An execution interrupted by a server stop is marked failed at
  the next start; it is not resumed. **Run one API process**: with several, each has its own
  pool and limits, and a process that starts marks the others' running executions
  interrupted too (they stop and store nothing; no final execution is changed). A shared job
  queue with leases is Phase 10 work.
- **Polling, not push.** The page polls an execution at the interval the server asks for;
  there are no server-sent events or websockets.
- **No accounts.** Scenarios and executions are shared by everyone who can reach the API; there
  is no authentication, ownership or audit of who ran what (Phase 10).
- **Previews are recomputed.** Each preview plans and computes the scenario again (about 50–130
  ms); nothing is cached between previews.

## The interface

- **Phones.** The Lab works at 360 px, but the pathway diagram scrolls sideways inside its
  frame and the builder is long; it is designed for a desktop screen first.
- **Replay granularity.** The replay steps month by month through the stored monthly values;
  it cannot show anything finer than a month.
- **Templates are starting points.** They carry changes, models and stress cases, never company
  figures; every figure must be entered.
