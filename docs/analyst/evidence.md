# Evidence and grounding

## The evidence ledger

Every tool result becomes **evidence** in the turn's ledger (`evidence.py`), numbered in the
order it is read: E1, E2 … Each item records:

| Field | Meaning |
|---|---|
| `tool`, `call` | the tool and the position of the call that produced it |
| `kind` | the kind of knowledge (below) |
| `title`, `detail` | what it is, in words |
| `source` | the record: its kind, id, label and a link inside RUMIN (a node, an edge, a series, a scenario or execution, a model, a template) |
| `period`, `as_of`, `retrieved_at` | the period it describes, when it was true, when the Analyst read it |
| `unit`, `currency` | units of its values |
| `evidence_status`, `grade` | for a relationship, its evidence status (evidence-backed, analyst-created, model assumption, unverified); for a finding, its grade |
| `models`, `assumptions` | for simulated and preview results: the models and versions, and their assumptions |
| `provenance` | ids and hashes: dataset and job, graph build, scenario version, inputs and result hashes |
| `values` | the exact values a sentence may quote, as exact decimal strings |

The same record read twice in a turn is one item (deduplicated by source, period and kind).
Text taken from stored records (names, descriptions, notes) is cleaned before it enters the
ledger ([guardrails](guardrails.md#stored-text-is-data)).

## Kinds of knowledge

An answer never mixes what was observed with what was assumed or simulated without saying
which is which. Every item carries one of eight kinds, shown in the margin with a label and a
shape (never colour alone):

| Kind | Label | What it is |
|---|---|---|
| `observed` | Observed | a stored observation from a cited dataset (Phase 2) |
| `record` | RUMIN record | RUMIN's own catalogue, graph, registry or counts |
| `relationship` | Relationship | a knowledge-graph relationship; its evidence status says what supports it |
| `finding` | Finding | a Financial Intelligence finding, with its grade (Phase 6) |
| `user_input` | Entered by a person | figures typed in the Scenario Lab, or the question's own figures as read |
| `assumption` | Assumption | a model assumption or a stated default |
| `simulated` | Simulated | a stored execution: it holds only under its changes, figures and assumptions |
| `preview` | Preview, not stored | computed on request by the models, and not saved |

## Citations

Answer text cites evidence inline: `[E2]` or `[E2, E5]` at the end of the sentence that
uses it. Tables, series, paths and scenario cards carry their own citations, per row, per
path or per line. The interface turns each citation into a link to the source in the margin
([interface](interface.md)); an export keeps them, with a list of sources and their links.

## The grounding check

`grounding.py` checks every answer before it is stored, whoever wrote it. It reads the
headline, every paragraph and every notice sentence by sentence:

1. **Figures.** It extracts each figure: signs (+, −), Western and Indian digit grouping,
   decimals, percentages, percentage points, basis points and scale words (thousand, lakh,
   crore, million, billion). Each must equal a value of the evidence the **sentence** cites
   **at the precision displayed**: `24.29 %` matches a stored `24.2914979757…`,
   `₹1.25 crore` matches `12,450,000` only to the nearest lakh. Rounding half-even and
   half-up are both accepted. An unsigned figure may match a value's magnitude ("fell by
   6,325,000" for −6,325,000); a written sign must match.
2. **Dates, years and versions** must appear word for word in the cited evidence.
3. **Citations** must name evidence that exists. A sentence with a figure and no citation
   fails. The headline may use any evidence of the answer.
4. **Interpretation** and **general knowledge** paragraphs, which a language model may add
   (labelled as such), may not contain any figure.
5. **Phrasing**: nothing may predict ("will", "is expected to"), claim a cause ("caused",
   "because of" a relationship), guarantee, advise ("should buy") or claim certainty, except
   inside a quotation that is word for word a cited record's text.

Tables, series, paths and scenario cards are built by RUMIN from tool results, not written by
a provider, so only their citations are checked.

The result is stored with the answer (`grounding`: passed, figures and citations checked,
problems) and shown under *How this was answered*.

## What happens when the check fails

| Draft from | Outcome |
|---|---|
| A language model | The draft is discarded. RUMIN's grounded composer answers the same question from the same tools, and a *Fallback* notice says why the model's answer was not used. The rejected draft's check is stored with the turn (`rejected`) for review |
| RUMIN's grounded composer | The parts with problems (the headline, or whole paragraphs and notices) are **withheld**, a notice says so, and the answer becomes *partly answered* (or *could not be answered* if nothing verified is left). This is a guard against a bug in RUMIN's own templates; the evaluation set requires it never to happen ([evaluation](evaluation.md)) |

Either way, **no answer is shown with a figure its evidence does not hold**.

## A question's own figures

A person's figures are evidence too. When a question states a change ("rises 20%"), a period
("since 2015") or a horizon ("over 18 months"), the composer records *Your question, as read*
(`user_input`) with those values, so an answer may repeat them with a citation. A
clarification that repeats a figure ("Which variable should change by 30%?") rests on the
same record.
