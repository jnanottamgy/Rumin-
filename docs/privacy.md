# Privacy, data integrity and provenance

What RUMIN keeps about people and their work, where it can go, how long it stays, what
RUMIN guarantees about its records — and the legal and regulatory questions a deployment
raises, **for qualified review**. This page is not legal advice, and RUMIN claims compliance
with no law, regulation or standard.

## What RUMIN stores about people

| Where | What | Notes |
|---|---|---|
| Accounts (`users`) | Name, e-mail address, role, Argon2id password hash, when the password changed, whether it must change, whether the account is active, failed sign-ins and a lock time, last sign-in time | Never deleted, only deactivated, so the records a person made keep their author |
| Sessions (`user_sessions`) | The SHA-256 hash of a random token (the cookie holds the token), the person, and when the session started, was last used, expires and was ended | No address, no browser details. Ended sessions are deleted by `prune` a day later |
| Audit trail (`audit_events`) | Security events (sign-ins, failures, sign-outs, changes to people and their sessions): who acted, whom it concerned, the **client address**, the request ID, the time, and what changed (a role, a reason) | A failed sign-in for an unknown e-mail address does not store the address typed. Kept until pruned |
| Authorship | Scenarios, versions, executions, simulation runs, analyses and conversations record who created them | Shown to every member of the workspace |
| Analyst conversations | The questions and answers, as typed | Free text: can contain anything, including a client's name or personal data. Private to their owner, who can delete them |
| Scenario and simulation inputs | Names, notes and figures people type (a company's revenue, costs, debt) | Visible to every member: RUMIN has **one shared workspace** |
| Logs | The web server's access log: client address, request line, status, size, time, user agent. The API's log: method, path (no query string), status, duration, request ID | No bodies, cookies, passwords, tokens, questions or answers. Kept by Docker's rotation (5 files of 10 MB per container) unless shipped elsewhere |
| The browser | One `HttpOnly` session cookie; in local storage the theme and motion preferences, whether the 3D universe shows the scene or the list, and whether the welcome card was dismissed (per account id) | No analytics, no third-party requests, fonts served by RUMIN |

## Where data can go

- **Nowhere, by default.** RUMIN makes no outbound request with personal or workspace data.
- **The World Bank**, only when someone retrieves series from the command line: the requests
  carry indicator and country codes, nothing else.
- **The Analyst's language model** — see below.

### The Analyst's language model

Off by default (`RUMIN_ANALYST_PROVIDER=grounded`: RUMIN answers from its own records
without any model). When an administrator configures a model (`anthropic`, a model
identifier and a key), **each question, the last four questions of the conversation with
their answers' headlines, and the records the Analyst's tools gather — company names,
figures from stored scenarios and executions, series values, findings — are sent to the
model provider's API** to draft the answer. What
the provider keeps, for how long, and where it processes the data are set by the
provider's terms and your agreement with it, not by RUMIN. RUMIN limits what is sent (tools
return bounded, cleaned records; a daily token budget), but it cannot make that transfer
private. Decide before enabling it, and tell the people who use the Analyst.

## Retention and deletion

| Data | How long | How it goes |
|---|---|---|
| Sessions | 120 minutes idle, 12 hours at most | Ended at once by sign-out, deactivation or *Sign out everywhere*; deleted by `prune` |
| Audit events | Until pruned | `python -m app.auth prune --events-older-than-days N` |
| Accounts | For good | Deactivated, never deleted. **There is no function to erase a person** (name and e-mail address stay as the author of their records): a request to erase needs a procedure and, today, a database change |
| Conversations | Until their owner deletes them | Deleted with everything in them |
| Scenarios | Versions and executions are immutable; an executed scenario **cannot be deleted** | By design (history cannot be rewritten) — which may conflict with a retention or erasure duty |
| Backups | Your policy | They hold everything above; encrypt them and keep them off the host |
| Logs | Docker's rotation, or your collector's retention | — |

## Integrity and provenance: what RUMIN guarantees

- **History cannot be rewritten.** Scenario versions, executions, simulation runs and stored
  analyses are append-only; each keeps its inputs and hashes, and *verify* recomputes it
  and says whether it is reproduced. A save from a stale version is refused.
- **Every figure says where it came from**: observed (with source, licence, retrieval time and
  revisions), typed by a person, a model default, or computed. Illustrative and synthetic
  data are labelled wherever they appear; nothing is invented to fill a gap.
- **Every record has an owner**, and only its owner or an administrator changes it; the audit
  trail records every security event with the request ID that links it to the logs.
- **Outputs are calculations, not advice.** Each run states that it is a deterministic
  calculation from stated inputs, not a forecast or investment advice; the Analyst answers
  only with figures it can cite.

## Areas for qualified review

Questions a deployment raises. Whether each applies depends on who runs RUMIN, for whom,
where, and what goes into it — that is for a qualified professional to decide.

| Area | Why it may be relevant | Questions to settle |
|---|---|---|
| **India: Digital Personal Data Protection Act, 2023** and the DPDP Rules, 2025, as notified and phased in | Accounts, the audit trail (with client addresses) and conversations hold personal data of the people who use RUMIN; scenario inputs and questions may hold clients' personal data | Your role (data fiduciary or processor); the notice to users; the lawful ground for staff data; retention periods; how to honour erasure given immutable history and undeletable accounts; breach notification; transfer to a model provider outside India |
| **EU / UK GDPR** | Only if data about people in the EU or UK is processed | The same questions, plus the transfer rules |
| **India: CERT-In Directions of 28 April 2022** (Information Technology Act, 2000, section 70B) | They set incident reporting (within six hours of noticing) and log retention (180 days, within India) duties for many organisations | Whether they apply; if so, ship logs to storage kept 180 days (Docker's rotation is size-based, not 180 days) and synchronise clocks |
| **Professional confidentiality** (for a firm of Chartered Accountants: the ICAI Code of Ethics) | Client figures typed into scenarios are visible to every member of the workspace, and, with a language model configured, reach its provider | Whether one shared workspace is acceptable across engagements (otherwise, one deployment per client or team); whether client consent is needed before any data reaches a model provider |
| **Securities regulation** (SEBI (Investment Advisers) Regulations, 2013; SEBI (Research Analysts) Regulations, 2014) | RUMIN's outputs are calculations and evidence about companies and markets. If they are passed to clients as recommendations about securities, that activity may be regulated | How outputs may be used and labelled; who may see them |
| **Data licences** | World Bank data is CC BY 4.0 (attribution required); price files are imported under the importer's own licence; stored responses are kept byte for byte | Attribution when sharing exports; whether a price-data licence allows storing and showing the data to every member |
| **The model provider's terms** | Only with a language model configured | Data use and retention by the provider; a data-processing agreement; confidentiality |
| **Record keeping** | If RUMIN's results support client work or audit evidence | Which retention rules apply to the records and exports, and whether RUMIN's backups meet them |
| **Staff monitoring** | The audit trail records staff sign-ins with their addresses | Notice to staff; access to the trail (administrators only) |
| **Accessibility** | If RUMIN is offered to the public or a public body | RUMIN was checked with automated tools (axe) in a browser and by keyboard; it has **not** been audited by people using assistive technology |

## What is missing today

- No privacy notice or terms shown in the app (a deployment should add its own).
- No function to erase or export one person's data.
- No retention schedule applied automatically (pruning is a command an administrator runs).
- No encryption at rest inside RUMIN: that is the host's disk encryption and the backups'
  encryption.
- One shared workspace: no separation between clients or engagements inside a deployment.
