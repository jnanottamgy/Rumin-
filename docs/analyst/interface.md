# Interface

`/analyst` (`frontend/src/pages/AnalystPage.tsx`, `frontend/src/features/analyst/`).

## Layout

- **Header**: the page title and who answers: *Grounded answers* (RUMIN composes every answer
  itself; no language model is configured), *Language model configured*, or, when a model is
  configured but not ready, why not (the missing setting) and that RUMIN answers instead.
- **Rail** (left): *New conversation* and the conversations, newest first, with their number
  of questions and date.
- **Conversation** (centre): its title with *Rename*, *Export as Markdown* and *Delete* (with a
  confirmation), then one **note** per question, then the question box, which stays at the
  bottom of the window.
- An empty conversation shows what the Analyst answers from, suggested questions **built from
  the data** (the API picks a company that has a stored execution, a stored series, a
  variable), and what it does not do.

## A note

Each answer reads as a research note:

1. The **question**, set off by a rule.
2. The **headline**, in the display face, and the answer's status (*Answered*, *Partly
   answered*, *RUMIN holds no data for this*, *Needs a choice*, *Declined*, *Outside RUMIN's
   records*, *Could not be answered*).
3. The **blocks**, in the order the provider wrote them:
   - paragraphs with inline citation chips; *Interpretation* and *General knowledge*
     paragraphs are labelled; refusals are set as a policy statement;
   - **tables** with a source column (each row's citations) and links to the records;
   - **series**: the Data Explorer's chart (one line, direct end label, hover and keyboard
     readout) with the values as a table behind *Values as a table*;
   - **paths**: chains of relationships, each step a link to the record, with the channel,
     how directly it reaches, the weakest evidence and the models that can simulate it;
   - **scenario cards**: a stored execution (solid border, *Open the stored execution*), a
     preview computed now and not stored (dashed border), or a plan that needs figures (the
     missing figures listed); with the changes, the lines (baseline, change, change %), the
     models and what is not modelled. A preview or plan offers **Open in the Scenario Lab**;
   - **notices**: assumptions, missing data, limitations, conflicting sources, not stored,
     illustrative, fallback;
   - **clarifications**: the question and one button per choice.
4. **Ask next**: follow-up questions, one click each.
5. **How this was answered** (collapsed): the tool calls that actually ran, in order, with
   their status, timing, summary and the evidence they produced; who composed the answer;
   the grounding check (figures and citations checked); any fallback; token usage when a
   model answered; the intent it was read as. **Copy answer** copies the note as Markdown.

## The evidence margin

The signature element: the sources sit **beside** the sentences that cite them, as in an
annotated research note. The margin lists the evidence the answer cites, in the order it is
first cited, each with its id, its kind of knowledge (a label and a shape, never colour alone,
following RUMIN's [knowledge labels](../design-system.md#knowledge-labels): a filled circle
for an observation, a ring for an assumption, a filled square for a person's figure, a hatched
square for a simulated result and a dashed hatched square for a preview, plus an open square
for a RUMIN record, two linked dots for a relationship and a triangle for a finding), its title linking to the record, its
period and units, and *Details*: evidence status or grade, models and versions, assumptions,
provenance (dataset, build, hashes), retrieval time. Evidence read but not cited is listed
under *Also read, not cited*.

Hovering or focusing a citation chip highlights its source, and the source highlights its
chips; activating a chip moves focus to the source. On wide screens the margin is a sticky
column that scrolls on its own; below 78rem it follows the answer.

## Waiting for an answer

Asking stores the question and shows it at once. While it is answered, the note says what
the server reports: *Sending the question…*, *Waiting for a worker…*, *Reading RUMIN's
records…*, with each tool call listed as soon as it is recorded. There is no typing effect
and no invented progress. The page reads the turn again every `poll_after_ms` (at least
300 ms, at most 3 s) and gives up after 3 minutes, saying the answer can be seen later.
A conversation opened while one of its questions is still being answered follows that
question the same way.

If asking fails (the pool is full, the question is too long, the server is unreachable),
the note shows the API's message with **Try again** and **Dismiss**; if the question was
stored and reading it failed, *Try again* reads it again rather than asking twice. A failed
question offers **Ask again**.

## The Scenario Lab hand-over

*Open in the Scenario Lab* on a preview or plan opens `/scenarios/new` with the draft in the
router's state (never in the URL): the changes, the company, the horizon and, for a preview,
the figures a person entered in the stored scenario it reused. The Lab validates the draft's
shape before using it, marks it *Not saved*, and says *Opened from the AI Analyst. Nothing is
saved until you save it; enter or check the figures before executing.* The Lab's own live
preview then runs as for any draft. Saving and executing are the person's actions.

## Export

*Export as Markdown* saves the conversation as a `.md` file built in the browser: each
question, the answer with its citations kept, its tables and cards, and the sources it cites
with links to them. Nothing is sent anywhere. Figures in exported cards use the same rounding
as the answer's sentences (half-even, two places for percentages).

## Accessibility and responsiveness

Notes are articles named by their question; the margin is a complementary region per note;
citation chips are links named *Source E1: …*; the question box has a label and a
description of its keys (Enter asks, Shift+Enter adds a line) and states when a question is
over the limit. Status changes are announced politely. Kinds of knowledge are distinguished
by label and shape as well as colour. The layout has three columns on wide screens, two
below 78rem (the margin under the answer), one below 60rem (the conversation list becomes a
horizontal strip), with no horizontal scrolling down to 320 px; suggested questions and
follow-ups wrap. Reduced motion is respected.
