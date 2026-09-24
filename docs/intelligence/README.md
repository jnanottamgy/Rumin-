# Financial Intelligence

Financial Intelligence answers *what changed, who is exposed to it and through which
relationships, what the stored simulations say, what drives them, what the result rests on
and what to look at next*. It reads what RUMIN already stores: observations, the knowledge
graph and Scenario Lab executions. Every answer is a **finding**, a structured statement
with the **evidence chain** that produced it.

It is not a chatbot and generates no text. A documented rule fills each sentence from a
template with computed values, and every value refers to the record or calculation it came
from. It never forecasts, never ranks companies or recommends anything, and never turns a
relationship into a causal claim. The one rule behind everything on these pages is
**no statement without evidence**: an insight without a chain cannot be built (`ChainError`),
and a test checks every insight the API returns.

| | |
|---|---|
| **Where** | `/intelligence` (the workspace), `/intelligence/{entity}` (a company's or an industry's dossier) and `/intelligence/analyses/{id}` (a stored analysis) in the web app; 16 operations under `/api/v1/intelligence` |
| **Backend** | `backend/app/intelligence/` (the engine: statistics, thresholds, evidence model, graph slices, exposure, series, drivers, relationship changes, signals, insight rules, interpretation, registry, serialisation), `backend/app/services/intelligence.py`, `backend/app/api/v1/intelligence.py` |
| **Frontend** | `frontend/src/pages/IntelligencePage.tsx`, `frontend/src/features/intelligence/`, and the *Latest findings* panel on the Overview dashboard |
| **Data** | Reads the Phase 1–5 tables and changes none of them. Migration `0006` adds `intelligence_analyses`: stored snapshots, append-only ([data model](../data-model.md)) |
| **Version** | `INTELLIGENCE_VERSION` 1.0.0, recorded in every result |

## What you can do

1. **Read the ledger.** The workspace lists every finding in a fixed order (new observations
   first, then what the stored simulations say, then relationships and exposure, then
   coverage), grouped by the kind of knowledge it reports. Filter by group or by a minimum
   evidence grade. Nothing is ranked or scored.
2. **Open a finding** to see the chain it rests on (observations, calculations,
   relationships with their evidence status, records, simulations, assumptions and the
   threshold that selected it), with the step that sets its grade marked, and its values,
   assumptions, limitations, next steps and sources.
3. **See who is exposed to what**: the exposure matrix (companies × variables), where each
   cell names the channels and says whether the variable reaches the company directly,
   through its industry or only upstream.
4. **Open a dossier** for a company or an industry: its findings, exposure paths, drivers
   of its latest simulated result, signals, history (related series, revisions, the model
   interpretation of the latest observed change, stored executions), sources, and the
   **brief** a future AI Analyst would receive.
5. **Change the thresholds** that decide what counts as a change, a trend or high
   volatility. They are part of the URL, validated by the backend, and recorded in every
   result.
6. **Store an analysis** and read it back later: it is shown exactly as stored, with a
   statement of whether anything it read has changed since.

## A worked example

Everything below comes from the frontend's test fixtures, which are the backend's own
answers captured by `backend/scripts/capture_intelligence_fixtures.py`. Nothing in them is
market data or any company's accounts.

**The sample network, before anything is simulated.** RUMIN's illustrative graph holds 12
fictional companies. 37 exposure paths from 7 economic variables reach them. The catalogue
lists 11 World Bank series, but none has stored values: the World Bank API is not reachable
from the environment where RUMIN was built. The workspace therefore says little:

| Rule | Finding | Grade |
|---|---|---|
| X01 ×7 | *Brent crude oil price reaches 9 companies*, *USD/INR exchange rate reaches 7 companies*, … | assumed: every exposure relationship in the sample is a model assumption |
| C02 | *What the stored data can support*: 0 of 11 series have two or more stored values | observed |

**After the reference execution.** The backend tests' scenario "oil, rupee and rates" on
the fictional Aerisca Airways, with **hypothetical** round figures
([Scenario Lab](../scenario-lab/README.md#the-reference-example)), adds:

- S01 *Profit before tax −6,700,000 INR (−17.63 %) under “Oil, rupee and rates on Aerisca”*,
  graded **assumed** and marked conditional on a simulation. The figure comes from the
  stored execution, but the models apply because of relationships recorded as model
  assumptions, and the chain includes them.
- In Aerisca's dossier (16 findings): five S02 contributions (for example *Operating costs:
  Brent crude oil price contributes +9,225,000 INR of the +13,250,000 INR change*), three
  S03 effects per unit (*per 1 % of Brent, profit before tax changes by −281,875 INR on
  average over this scenario's +20 %*), four E01 exposures, E02 (*stated exposures
  concentrate on jet fuel and USD/INR: 2 of 4 paths each; this counts relationships, not
  money*), E03 (suppliers and lenders) and C01, which says what is and is not covered:
  *the latest execution also simulates the RBI repo rate, although the graph states no
  exposure of Aerisca Airways to it: that part of the result rests on the entered figures
  alone.*

**With stored histories (SYNTHETIC test values).** The tests and the `synthetic-*`
fixtures store made-up exchange-rate and inflation histories through the real ingestion
pipeline, including one revision. These values are test values, not World Bank data. With
them the workspace leads with observed data:

- D01 *INR per US$ rose 9.38 %* (84.2 → 92.1, 2024 to 2025) and *CPI inflation fell 1.80
  percentage points* (4.9 → 3.1). These are observed, and each meets its threshold.
- D02 *INR per US$ moved; 7 companies are exposed to USD/INR*. The chain goes from the
  observation through the series' `related_measure_of` edge to the exposure edges, so it is
  graded assumed. It names who is exposed and says it *does not* say the change affected
  them.
- D06 *2024 was revised from 83.7 to 84.2 INR per USD (+0.60 %); both values are kept.*
- D04 *has been rising over 2021 to 2025: +4.2 INR per USD per year (t = 8.35, critical
  value 3.182).*
- S06, in Aerisca's dossier: the observed +9.38 %, applied alone to the stored scenario,
  gives *operating profit −1,032,064 INR (−2.06 %) over 12 months: a model interpretation
  computed on request, not stored, and not an observation.*

## Read next

- [Architecture](architecture.md): the layers (findings, signals, insights), the module
  registry, one read per request, the two scopes, and what is computed and what is stored.
- [Evidence](evidence.md): references, steps, the six grades, the weakest-link rule, and
  what a grade is not.
- [Insight rules](rules.md): the 19 rules, their chains, next steps and ordering.
- [Signals, statistics and thresholds](signals.md): six signals, the exact statistics,
  and every threshold with its default, bounds and reason.
- [Exposure](exposure.md): validated relationships, paths, counterparties and context,
  and the matrix.
- [Changes and interpretation](changes.md): observed changes, revisions, relationship
  changes, execution changes, and the model interpretation of an observed change.
- [Drivers](drivers.md): contributions from stored runs, effects per unit, sensitivity.
- [Stored analyses](stored-analyses.md): snapshots, fingerprints and freshness.
- [The entity brief](brief.md): the structured object for a future AI Analyst.
- [The interface](interface.md): layout, the ledger, the evidence chain, the matrix, the
  dossier, design choices and accessibility.
- [Performance](performance.md): measured times and sizes, up to 20,000 companies.
- [Limitations](limitations.md): what Financial Intelligence does not do.
- [The API](../api.md#financial-intelligence) and [the Phase 6 report](../phases/phase-6-report.md).
