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
| `value_units` | which of those values are percentages (`percent`) and which are changes in percentage points (`points`); every other value is in the record's unit or currency, or is a count |

The same record read twice in a turn is one item (deduplicated by source, period and kind).
Text taken from stored records (names, descriptions, notes) is cleaned before it enters the
ledger ([guardrails](guardrails.md#prompt-injection)). Evidence holds only what RUMIN read:
a tool's arguments (a model's search words, for instance) are never copied into it.

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

1. **Figures.** It extracts each figure: signs (+, −, and an en or em dash written against
   the digits), accounting brackets (`(5)` is −5), Western and Indian digit grouping,
   decimals, percentages, percentage points, basis points, currencies (₹, $, €, £, INR,
   USD, EUR, GBP, Rs, before or after the number) and scale words (thousand, lakh, crore,
   lakh crore, million, billion, trillion, and k, m, b, bn, mn, tn). Each must equal a value
   of the evidence the **sentence** cites **at the precision displayed**: `24.29 %` matches a
   stored `24.2914979757…`, `₹1.25 crore` matches `12,450,000` only to the nearest lakh.
   Rounding half-even and half-up are both accepted. An unsigned figure may match a value's
   magnitude ("fell by 6,325,000" for −6,325,000); a written sign must match. "Doubles",
   "halves" and "triples" are read as +100 %, −50 % and +200 %.
2. **Of the same kind.** A figure matches only a value of its kind. Every tool marks which of
   its values are **percentages** and which are **changes in percentage points**
   (`value_units` on each piece of evidence): a series' values when it is a rate, a ratio or a
   growth rate, the changes RUMIN computes (a percentage for levels and exchange rates, points
   for rates), a stated change to a variable (a percentage change, or points for an absolute
   change to a rate), a finding's facts by their unit, and every `…percent_change` and
   `….share`. So `3 %` can match only a percentage, `+0.5 percentage points` only a change in
   points, and an amount written with a currency or a scale word only a value that is
   neither — in the same currency when both say which. A bare number may match any value.
3. **Nothing unreadable passes.** Anything that looks like a figure but cannot be read
   exactly fails the check rather than being skipped: digits left over once every figure is
   read (`5-45%`, `+/-99%`, `a-700 crore`), other numerals (`½`, `²`, digits of other
   scripts), scientific notation (`1e3`), decimal commas (`12,5 %`), digits grouped by spaces
   (`5 000`), leading zeros (`000`), a figure run into letters (`5x`, `3rd`), a `±` range, and
   figures written in words (`five hundred crore`, `a million`, `twenty-five percent`,
   `thousands of crores`, `a third of`). A language model is asked to write figures as
   digits; RUMIN's templates do.
4. **Dates, periods and versions** (`2024-03-31`, `2024-03`, `2023-24`, `2024-Q1`, `Q3`,
   `FY24`, `1.1.0`) must appear word for word in the cited evidence.
5. **Citations** must name evidence that exists. A sentence with a figure and no citation
   fails. The headline may use any evidence of the answer.
6. **Interpretation** and **general knowledge** paragraphs, which a language model may add
   (labelled as such), may not contain any figure.
7. **Phrasing**: nothing may predict ("will", "is expected to"), claim a cause ("caused",
   "because of" a relationship), guarantee, advise ("should buy") or claim certainty, except
   inside a quotation that is word for word a cited record's text.

What a cited record says itself is not the answer speaking: a **quotation** that is word for
word in a cited record's text is exempt from the figure and phrasing checks, and a cited
record's **name, title or identifier**, written exactly as stored, is exempt from the figure
check ("Population ages 15-64 (% of total population)" names a series; it states no figure).
Evidence holds only what RUMIN read: a tool's arguments — a model's search words, for
instance — are never copied into evidence text, so a model cannot write a figure or a date
into the evidence it then cites.

**Follow-up questions** are offered as one-click questions, so they are checked too: at most
160 characters, no citations, nothing the question screen would decline (instructions aimed
at the Analyst, requests for secrets, advice, forecasts, live data), no forbidden phrasing,
nothing unreadable, and figures only when the evidence holds them or when the follow-up is a
what-if stating its own changes. The rest are dropped.

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
