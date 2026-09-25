# Phase 10 plan — Productization, security and launch

Phase 10 turns RUMIN from a working technical platform into something a team can run
safely. It starts from evidence: a full product audit (10.1), then a gap list ranked by
severity, and only then the work. It is not a feature rewrite.

Starting point: commit `6136eea` (the Phase 9 report); CI run #34 green on `836bdf7`, the last
code commit; backend 1,149 passed + 1 skipped (SQLite and PostgreSQL 16), frontend 404,
integration 66.

## 1. How the audit was done (10.1)

| Area | Method | Evidence |
|---|---|---|
| Every route | A fresh database built as the smoke test builds it (sample network, series catalogue, a SYNTHETIC price file, the graph) plus, through the API, the reference scenario executed with sensitivity, a grid and a Monte Carlo analysis, a simulation run with sensitivity, a stored intelligence analysis and an Analyst conversation. A Chromium script opened all 23 routes (landing to 404) at 1440 px in both themes and at 390 px: `axe-core`, console errors, sideways scrolling, titles and headings, screenshots | 69 page loads; findings below |
| Security | Code scan (unsafe rendering, `eval`/`exec`, raw SQL, shell calls, logging of bodies), configuration and headers, CORS, the committed files and the whole history for secrets, the production bundle for secrets, `pip-audit` on the 121 locked Python packages, `npm audit` on all frontend packages | No known vulnerable dependency; no secret; findings below |
| Performance | Page loads (TTFB, DOMContentLoaded, first and largest contentful paint, JavaScript size) for nine routes, three cold loads each; API latency (20 requests each) for 13 endpoints | Localhost figures below (no network latency, no compression in the preview server) |
| Operations | Health and readiness, logging, configuration, the compose file, CI, the documentation | Findings below |
| Skills | The installed skills listed and inspected again (§ 5) | — |

## 2. Findings

### Works end to end (no action)

- Every route loads without a console error or warning in either theme; 18 of 23 routes at
  desktop (in both themes) and 16 of 23 at phone width have no axe violation (the rest are
  listed below).
- Journeys verified by the suites and the walk-through: exploring the network and the graph
  (search, neighbourhoods, evidence, paths), the Data Explorer with provenance and quality,
  a simulation run with its pathway and reproducibility check, a scenario from template to
  execution, results, stress, sensitivity, grids, Monte Carlo and comparison, intelligence
  findings with evidence chains, Analyst answers with citations, the 3D universe.
- Provenance stays attached (licence, retrieval time, revisions, evidence status); synthetic
  and illustrative data is labelled wherever it appears; stale graphs and failed retrievals
  are surfaced.
- Code: no `dangerouslySetInnerHTML` or `innerHTML`; no `eval`, `exec`, `pickle` or shell
  calls in the application; SQL only through SQLAlchemy (the one textual query is
  `SELECT 1`); parameters hidden from SQL logs; request logs carry method, path (no query
  string), status and duration only.
- Dependencies: `pip-audit` — no known vulnerabilities; `npm audit` — 0. Secrets: none tracked
  or in history; `.env` ignored; nothing secret in the production bundle.
- Performance on localhost: first contentful paint 108–200 ms and largest 108–256 ms on nine
  routes; 369–551 kB of JavaScript (1,027 kB on the 3D page, whose renderer loads only
  there); API medians 3–26 ms, the slowest p95 135 ms (an intelligence dossier).

### Gaps

| ID | Gap | Severity | Impact and likelihood | Action |
|---|---|---|---|---|
| G1 | **No authentication or authorisation.** Anyone who can reach the API can read everything, create, execute and delete scenarios, and read or delete every Analyst conversation | **Critical** | Blocks any shared use; certain to be exploited on a network | Accounts, sessions, roles, ownership, enforced in the backend (§ 3) |
| G2 | **No production deployment path.** No images, no web server for the built app (so no Content-Security-Policy or security headers on the HTML), API docs on by default, SQLite and localhost CORS as defaults, no check that production is not running on development settings | **Critical** | A deployment would be improvised, with development defaults | Images, a web server with headers and an API proxy, a production compose file, a configuration check that refuses unsafe production settings |
| G3 | **No backup or restore procedure** | **High** | Loss of every scenario, execution and conversation on a disk or operator error | A tested `pg_dump` / `pg_restore` procedure and a documented rollback |
| G4 | **No inbound rate limiting** beyond the execution and analysis pools; once logins exist, passwords could be guessed | **High** | Brute force, resource exhaustion | Login throttling per account and per client; request rate limits at the web server |
| G5 | **Operational visibility is thin**: plain-text logs, no metrics, no documented checks or alerts | **High** | Failures noticed late; slow diagnosis | Structured (JSON) logs as an option, a metrics endpoint, a runbook with checks |
| G6 | **Accessibility and phone defects**: heading-order skips (2D network, graph with a focus, a company's intelligence dossier), empty table headers (graph, simulation run), scroll regions unreachable by keyboard at 390 px (ingestion run, simulation run, System), sideways scrolling at 390 px (Overview 15 px, System 112 px: a status line that cannot wrap), a generic tab title on seven routes (universe ×2, graph, intelligence ×3, not found) | **Medium** | Screen-reader and keyboard users; phone users | Fix each; add browser checks to CI so they stay fixed |
| G7 | **No automated browser checks** (journeys, accessibility, responsiveness) | **Medium** | Regressions like G6 return unnoticed | A Playwright launch suite with `axe-core`, run in CI |
| G8 | **No first-use guidance**: a new user meets nine navigation items and no suggested path | **Medium** | Confusion; features missed | A short *Getting started* with real starter tasks and a help page |
| G9 | **Public source maps**: the production build ships `.map` files, which publish the source | **Low** | Code disclosure for a closed deployment | Hidden source maps, never served |
| G10 | **The API's own description is out of date** (it describes Phases 1–4) | **Low** | Misleading documentation | Update it |
| G11 | **One API process only**: execution, Analyst and analysis pools are per process | **Medium** (for scale) | A second process would split limits and recovery | Enforce one API process in the deployment; a shared queue remains next work |
| G12 | **Legal and regulatory questions unexamined**: personal data in accounts and logs, client figures entered into scenarios, questions sent to an external model provider when the Analyst's model is configured, data licences, "not advice" positioning | **Medium** | Obligations unknown | List the areas for qualified review; claim no compliance |

## 3. Scope and design decisions

**In scope**, in this order:

1. **Accounts and access (G1, G4).** Local accounts created by an administrator (no
   self-registration): e-mail and password, hashed with Argon2id through an established
   library; server-side sessions in an `HttpOnly`, `SameSite=Lax` cookie (`Secure` outside
   development), with idle and absolute expiry, renewal on use, sign-out and revocation;
   login throttling per account and per client; an audit trail of security events. Three
   roles: **viewer** (read the workspace, use the Analyst), **analyst** (also create and run
   scenarios, simulations and analyses), **admin** (also manage people and their sessions).
   RUMIN keeps its **single shared workspace** (as Phases 5–9 built it): signed-in members
   read the workspace's scenarios, runs and findings; only a resource's **owner or an admin
   changes it**; **Analyst conversations are private to their owner**. Enforced in the
   backend for every route; the interface only mirrors it. Unsafe requests with a cookie
   must come from an allowed origin (Origin and Fetch-Metadata checks) — the CSRF defence.
2. **Production configuration and hardening (G2, G9, G10).** A startup check that refuses
   production with development defaults; security headers and a Content-Security-Policy for
   the web app; hidden source maps; dependency audits and a secret scan in CI.
3. **Observability (G5).** JSON logs as an option with request and job identifiers; a
   metrics endpoint (requests, latency, errors, executions, analyses, logins) for
   administrators and the internal network; a runbook.
4. **Deployment (G2, G3, G11).** An API image (non-root, one process), a web image (nginx
   serving the build with headers, rate limits and the API proxy), a production compose file
   with PostgreSQL, deliberate migrations, a tested backup and restore, rollback notes —
   built and run here.
5. **Accessibility, consistency and onboarding (G6, G8).** Fix every audit finding; a
   *Getting started* for real tasks and a help page.
6. **Launch verification (G7).** A browser suite over the critical journeys with `axe-core`
   and phone widths, in CI; every suite run and recorded.
7. **Documentation, the readiness assessment and the report (G12).**

**Not in scope, and why:** single sign-on and multi-factor authentication (the local accounts
are designed so an identity provider can be added; recommended before public launch);
several workspaces or per-client isolation (one deployment per workspace until then); a
shared job queue for several API processes (the deployment runs one); e-mail-based password
recovery (no mail service; administrators reset passwords); load testing beyond single-user
measurements; any production deployment (not authorised; the stack is verified locally).

## 4. Security principles for the work

Established libraries only (Argon2 via `argon2-cffi`; no homemade cryptography); random
session tokens stored only as SHA-256 hashes; generic login errors; constant work for unknown
accounts; no secret, token or password in logs, errors or the bundle; permission checks in the
backend with tests for each role and for access to another user's resources; nothing
irreversible outside this environment.

## 5. Installed skills inspected

The installed list was read again: `dataviz` (bundled) — its anti-pattern catalogue was
applied to every chart in the product (no dual axes, no dashed grids, no tooltip-only values,
table twins; the dashed strokes that exist are semantic: cited links and a loading ring);
`kapture-browser-automation` — needs the Kapture Chrome extension, which is not connected
here, so the audit and the launch suite use Playwright with the pre-installed Chromium;
`docs`, `docx`, `pptx`, `xlsx`, `pdf`, `morning`, `import-memory`, `skill-creator` and
`claude-api` — inspected, not relevant to product quality work. No installed skill covers
product design, usability, accessibility, responsive layout or motion; that work follows
WCAG 2.2 and the design system, checked with `axe-core`.

## 6. Order of work

1. This plan (audit and gaps).
2. Accounts, sessions, roles and ownership in the backend, with migration `0009` and tests.
3. Sign-in, the session, role-aware controls and administration in the web app; the
   integration suite and the smoke test sign in.
4. Production configuration, headers, audits in CI, observability.
5. Images, compose, nginx, backup and restore — built and run.
6. Accessibility and phone fixes, onboarding and help.
7. The browser launch suite; every suite run.
8. Documentation, the readiness assessment, the report.
