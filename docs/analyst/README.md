# AI Analyst

The AI Analyst answers questions about RUMIN's own records in plain language: which
companies a variable reaches and through which relationships, what a stored series shows,
what a stored scenario simulated and why, what a what-if would do, how two records are
connected, what changed, and what RUMIN holds. It reads RUMIN only through a fixed set of
**tools** over the services Phases 1–6 built, and every figure it writes **cites the
evidence it came from**. An answer, or a part of one, whose figures are not in its evidence
is not shown.

It is a research assistant, not an oracle. It does not forecast, does not hold live market
data, does not make investment decisions and does not state anything it cannot cite. When
RUMIN lacks what a question needs, it says so and says what would supply it.

| | |
|---|---|
| **Where** | `/analyst` in the web app (`?session=` opens a conversation); 8 operations under `/api/v1/analyst` ([API](../api.md#ai-analyst)) |
| **Backend** | `backend/app/analyst/` (policy, vocabulary and parsing, router, context, tools, evidence, answer blocks, composer, grounding, providers, orchestrator, runner, evaluation), `backend/app/services/analyst.py`, `backend/app/api/v1/analyst.py` |
| **Frontend** | `frontend/src/pages/AnalystPage.tsx`, `frontend/src/features/analyst/`; the Scenario Lab opens a what-if the Analyst hands over (`ScenarioLabPage.tsx`) |
| **Data** | Reads the Phase 1–6 tables and changes none of them. Migration `0007` adds `analyst_sessions`, `analyst_turns` and `analyst_tool_calls` ([data model](../data-model.md#ai-analyst-phase-7)) |
| **Who answers** | RUMIN's **grounded composer** (the default: no language model, fully offline), or a **Claude model** through the official `anthropic` SDK when configured, held to the same check ([providers](providers.md)) |
| **Version** | `ANALYST_VERSION` 1.0.0, recorded with every turn |

## What you can ask

| Kind of question | Example | What answers it |
|---|---|---|
| A company or an industry | *What does RUMIN know about Aerisca Airways?* | its record, exposure paths, counterparties, latest stored execution, findings |
| Exposure | *Which variables affect Aerisca Airways' costs?* | the stated relationships from each variable, by channel, with evidence status |
| Reach of a variable | *Which companies are exposed to the USD/INR exchange rate?* | every company the graph states it reaches, and how |
| A connection | *How is Aerisca Airways connected to the USD/INR exchange rate?* | the shortest chains of relationships (a connection, not a cause) |
| A stored series | *Show India's official exchange rate since 2015* | the stored values, the latest, the last change, the trend, revisions |
| A change between periods | *How much did USD/INR change between 2020 and 2025?* | the exact change, computed from the two stored values |
| What changed | *What changed recently?* | new observations over thresholds, revisions, simulated changes, graph changes |
| Findings | *What are the findings for Aerisca Airways?* | Financial Intelligence findings with their evidence grade |
| Stored simulations | *What did the latest scenario on Aerisca Airways show?*, *Why did profit before tax change?* | the stored execution, its lines, drivers and explanation |
| A what-if | *What if Brent crude rises 20% for Aerisca Airways?* | a **preview** computed on request by the Scenario Lab's models, never stored |
| The catalogue | *Which models are there?*, *What scenario templates are there?*, *What data does RUMIN hold?* | the model registry, the templates, the data coverage |

Follow-ups use the conversation: *and its revenue exposure?*, *what about 30%?* (resizes the
previous what-if). An ambiguous or incomplete question gets a **clarification** with choices,
never a guess. Questions for investment decisions, forecasts, live prices, secrets or
instructions aimed at the Analyst are **declined**, with what RUMIN can offer instead
([guardrails](guardrails.md)).

## A worked example

Everything below comes from the frontend's test fixtures: the backend's own answers,
captured by `backend/scripts/capture_analyst_fixtures.py` from the illustrative sample
network, SYNTHETIC stored values (test values, not World Bank data) and the backend tests'
REFERENCE scenario on the fictional Aerisca Airways with HYPOTHETICAL figures.

**Asking.** *What if Brent crude rises 20% for Aerisca Airways?* The router reads a
what-if: a change of +20 % to the Brent crude oil price, for Aerisca Airways. One tool runs,
`preview_scenario`, reusing the company figures a person entered in the stored scenario
*Oil, rupee and rates on Aerisca*, and the Scenario Lab's models compute without storing
anything. The answer:

> **Operating profit −5,500,000 INR under Brent crude oil price +20 % (preview, not stored)**
>
> Under Brent crude oil price +20 % [E1], over 12 months, the registered models compute
> for Aerisca Airways [E2]:
> Revenue: +3,500,000 INR (+1.17 %) against a baseline of 300,000,000 INR [E2].
> Operating costs: +9,000,000 INR (+3.60 %) against a baseline of 250,000,000 INR [E2].
> Operating profit: −5,500,000 INR (−11.00 %) against a baseline of 50,000,000 INR [E2].
> The company figures are those a person entered in "Oil, rupee and rates on Aerisca"
> (version 1) [E3].

Beside it, the **evidence margin** lists E1 (*Your question, as read*, entered by a person),
E2 (*Preview for Aerisca Airways*: preview, not stored; 12 months simulated, INR; the
model `airline_fuel_cost 1.1.0` and its assumptions) and E3 (*Figures entered in …*, entered by a person). Below it, a
scenario card repeats the lines in a table, names what no model covers (*Not modelled:
Interest expense, Profit before tax*; *Cash flow*), and offers **Open in the Scenario Lab**,
which opens the same draft there, unsaved. The Analyst never saves or executes a scenario.

**How it was answered** opens the method: one tool call (`preview_scenario`, done, 33 ms
when the fixture was captured), *Composed by RUMIN's grounded composer (no language
model)*, and *Grounding check: Passed: 14 figures and 12 citations checked against the
evidence*.

## Documents

| | |
|---|---|
| [Architecture](architecture.md) | the modules, one turn from question to stored answer, the worker pool, storage |
| [Tools](tools.md) | the 17 tools, their inputs, limits and the services they reuse |
| [Evidence and grounding](evidence.md) | the evidence ledger, kinds of knowledge, citations, the grounding check, withholding |
| [Providers](providers.md) | the grounded composer, the Anthropic provider and its configuration, fallback |
| [Conversations](conversations.md) | sessions, focus, follow-ups, clarifications, deletion |
| [Guardrails](guardrails.md) | advice, forecasts, live data, injection, secrets, limits, logging |
| [Interface](interface.md) | the workspace, the evidence margin, blocks, the method trace, the Lab hand-over |
| [Evaluation](evaluation.md) | the evaluation set, how it is scored, results |
| [Limitations](limitations.md) | what the Analyst does not do, and where it can be wrong |
