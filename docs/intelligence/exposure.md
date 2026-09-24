# Exposure

Exposure analysis answers *which economic variables reach an entity, and through which
validated relationships?* It says **that** an entity is exposed, never **how much**. Sizes
come only from simulations with the user's own figures ([drivers](drivers.md)). The code
is in `backend/app/intelligence/graphview.py` and `exposure.py`.

## Validated relationships only

An edge is used when it is **current in the latest completed build** and its
`quality_status` is `validated`, meaning it passed every validation rule of the build
([graph construction](../graph/construction.md)). The analysis lists edges the build flagged,
but never uses them. Every edge keeps its evidence status, its registry label and caveat,
and its curated attributes (polarity, strength, rationale, the curator's stated difference
for related measures). Every statement built on an edge can therefore say what kind of
support it has.

The `evidence` filter (`any`, the default, or `evidence_backed`) keeps only paths whose
every edge has a cited source. On the sample network this returns no paths: every exposure
relationship there is a model assumption. The response says so and counts what the filter
removed (`removed_by_filter`).

## Paths

An **exposure path** runs from an economic variable to the entity. Its evidence status is
the weakest of its edges.

| Directness | Shape | What it states |
|---|---|---|
| **direct** | `variable —affects_costs / affects_revenue / affects_financing→ company` | the graph states the company's own exposure |
| **via its industry** | `variable —affects_*→ industry ←in_industry— company` | stated for the industry as a whole, not for this company: *companies in one industry can be affected very differently* |
| **upstream** | `origin —influences→ … —influences→ variable`, at most two hops, in front of a direct or via-industry path | the origin is *assumed to transmit* to the exposed variable, and reaches the company only through that assumption |

Each path records its **channel** (costs, revenue or financing costs), the hops and edges in
order, and the **registered models that can simulate it**, read from the models' scenario
profiles ([Scenario Lab](../scenario-lab/architecture.md)). Variables are grouped by
category: commodities, exchange rates, interest rates, inflation, other.

**Apart from exposure**, and never presented as exposure:

- **Counterparties**: `supplies_to` and `lends_to` in both directions (supplier, customer,
  lender, borrower), at company or industry level, with the registry's caveat that they say
  nothing about size or terms.
- **Context**: the entity's industry, sector, country, that country's currency and its
  competitors, each with the caveat that it is not an exposure.
- **Series coverage**: the stored series recorded as related measures of each exposure
  variable, with their value counts and the curator's stated difference between the series
  and the variable.

Example, from the sample's Aerisca Airways (4 paths, 4 variables, every edge a model
assumption except the industry classification):

| Variable | Path | Directness | Models |
|---|---|---|---|
| USD/INR exchange rate | USD/INR → affects costs of → Aerisca Airways | direct | `fx_exposure` |
| Jet fuel price (U.S. Gulf Coast) | jet fuel → affects costs of → Air transport ← operates in ← Aerisca | via its industry | `airline_fuel_cost` |
| Brent crude oil price | Brent → influences → jet fuel → affects costs of → Air transport ← Aerisca | upstream | `airline_fuel_cost` |
| U.S. effective federal funds rate | Fed funds → influences → USD/INR → affects costs of → Aerisca | upstream | none: no registered model carries a rate change into the exchange rate, so E01 suggests `model_gap` |

Listed apart: two suppliers (Deltrin Refining, and the refined petroleum products industry)
and one lender (Anvaya Bank) as counterparties. The context is Air transport, Transportation
and storage, India, INR and a competitor, Skyvara Air. One related series (INR per US$,
World Bank) has no stored values, so E01 also suggests `ingest_series`.

## The workspace and the matrix

The workspace lists the **first 200 companies by name**, together with every validated edge
their paths use: their industries, the variables that affect either, up to two
`influences` hops upstream, and the related series. The read is bounded by companies, never
by edges, so a listed company is never shown without an exposure it has. A test checks, for
the full listing and for a truncated one, that each listed company's paths are exactly those
of its own analysis. With more than 200 companies, the coverage says *X of the first 200
(N in the graph)* and `coverage.truncated` is true.

The **exposure matrix** is a table of companies × variables. Each cell names the channels
(C costs, R revenue, F financing costs) and says how the variable reaches the company:
directly (solid border), through its industry (dashed) or only upstream (dotted). It gives
the number of paths, the weakest evidence status and the models able to simulate it. Every
cell also reads as a sentence, for example *"Brent crude oil price reaches the costs of
Aerisca Airways: upstream; 1 path; weakest evidence model assumption; simulatable by
airline_fuel_cost."*

The workspace also indexes, in one pass, which listed companies each variable reaches. That
index drives the X01 findings (the 12 variables reaching the most companies). When the listing
is truncated, X01 and D02 say that their counts cover the listed companies only (*"reaches 9 of
the listed companies"*, with a limitation naming the bound).

`GET /intelligence/variables/{key}/exposure` does not depend on the listing. It walks
**downstream** from the variable through the whole graph: the variables it `influences`
(at most two hops), the companies and industries those affect, and the companies in those
industries. It lists the first 200 of the companies reached, by name, each with the paths
through the variable that its own analysis finds. It also returns the `total` and whether the
list is `truncated`. A test checks that it finds companies a short listing would not show,
and compares each company's paths with its own analysis.

## Signals and findings from exposure

- **Exposure breadth**: distinct variables and paths, by channel, directness and evidence
  status.
- **Dependency**: the largest share of the entity's paths that pass through one variable.
  It is *concentrated* at or above 50 % by default. On Aerisca, jet fuel and USD/INR each lie
  on 2 of 4 paths. This is a share of relationships, not of costs or revenue.
- Rules **E01** (one finding per variable reaching the entity), **E02** (concentrated
  dependency), **E03** (counterparties), **X01** (shared drivers), **C01** (coverage) and
  **D02** (an observed change on an exposure variable); see [rules](rules.md).

## What exposure does not say

- **Not a size.** Two exposures with the same count can differ by orders of magnitude.
- **Not causation.** *A connection in the graph is not evidence of causation.* Every
  exposure finding carries this sentence, and upstream paths say that the transmission is
  assumed.
- **Not complete.** An exposure the graph does not record is invisible. C01 says which
  simulated changes have no stated exposure. In the sample's reference execution, the RBI
  repo rate is simulated for Aerisca without one, so that part of the result rests on the
  entered figures alone.
