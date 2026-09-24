# Conversations

## Sessions

A conversation (`analyst_sessions`) is created when its first question is asked (or
explicitly, with a title). It is titled after its first question until renamed, lists its
questions in order, and keeps a **focus**. Conversations are listed newest first in the
workspace's rail and can be reopened at `/analyst?session={id}`, renamed, exported as
Markdown, or **deleted** with everything in them.

One question is answered at a time in a conversation: asking while the previous one is
still being answered is refused (409). A conversation holds at most
`RUMIN_ANALYST_MAX_TURNS_PER_SESSION` questions (200); then a new one is needed.

## Focus

The focus is what the conversation is about: the company or industry, the variable, the
series, the scenario and execution, the changes of the last what-if and its horizon. Each
answer sets it (`focus_after` on the turn, `focus` on the session). The next question is
read against it:

| Question | Previous focus | Read as |
|---|---|---|
| *and its revenue exposure?* | Aerisca Airways | the exposure of Aerisca Airways, revenue channel |
| *What about 30%?* | a what-if: Brent crude +20 % for Aerisca Airways | the same what-if resized to +30 %, with *a new size for the previous change* stated as an assumption |
| *What about 30%?* | a connection question (no change to resize) | a clarification: *Which variable should change by 30%?*, with choices |
| *Which companies are exposed?* | the USD/INR exchange rate | the companies the USD/INR exchange rate reaches |
| *Which companies are exposed?* | nothing | a clarification: *Which variable do you mean?* |
| *What about Anvaya Bank's exposure?* | Aerisca Airways | Anvaya Bank: a named subject replaces the focus |
| *What about India's GDP growth?* | Aerisca Airways | the stored series for India's GDP growth: a named country is not replaced by the focus |

When the focus supplied part of the reading, the answer says so in an assumption notice
(*Taken from the conversation: this follow-up was read as being about the conversation's
subject (Aerisca Airways)*), so a wrong reading is visible.

## Fresh data every turn

Each turn calls its tools again. No earlier tool result is reused as current: a
conversation opened days later answers from the data as it is then, and every item of
evidence has the time it was read.

## What a language model sees of the past

A model receives the question, the focus (as record keys and names) and the questions and
headlines of up to four earlier completed turns, never earlier answers' full text or
evidence. It must call tools to know anything.

## Clarifications

When a question is ambiguous (a name that fits several records, a series that exists for
several countries), incomplete (a what-if without a variable, an exposure question without
a subject) or unreadable, the Analyst asks instead of guessing. A clarification lists
choices; each choice is a complete question, asked with one click. Clarifications never call
a tool or a model.
