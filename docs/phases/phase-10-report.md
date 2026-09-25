# Phase 10 report — Productization, security and launch

Phase 10 turned RUMIN from a single-user local tool into something a team can run: accounts,
roles and ownership enforced by the backend; a production deployment that is built, started,
checked, backed up, restored and rolled back end to end on one machine; operations tooling;
onboarding; a browser launch suite in CI; and the documentation to run it. It started from an
audit ([plan](phase-10-plan.md)) and ends with the evidence-based
[launch readiness assessment](#launch-readiness) below.

## At a glance

| | |
|---|---|
| **Accounts and access** | Local accounts created by administrators; Argon2id; server-side sessions in an `HttpOnly` cookie with idle and absolute expiry; viewer, analyst and admin roles and ownership enforced on every route (a test walks the route table); private Analyst conversations; limits on guessing per address, per account from an address and per account, and at the web server; a security audit trail; *People* for administrators; a command line for the first administrator and recovery |
| **Deployment** | API and web images (unprivileged, read-only, no capabilities), a production compose file (PostgreSQL on an internal network), nginx (TLS 1.2/1.3, HTTP/2, HSTS, a strict Content-Security-Policy, rate limits), deliberate migrations, a refusal of development settings in production, backup, restore and rollback — **verified locally and in CI, never on a production host** |
| **Operations** | `/metrics` (requests, latency, security events, queues), JSON logs with request IDs from nginx to the API, health and readiness, a [runbook](../operations.md) with alert rules and troubleshooting |
| **Product** | A getting-started guide with six starter tasks and a first-use card; every page titled; the audit's accessibility and phone defects fixed, and four more found and fixed by the launch suite |
| **Launch suite** | Playwright + `axe-core` in Chromium on a desktop and a phone: 26 pages and the core workflows by role — **68 passed, 2 skipped by design, 0 failed**, locally, in CI and against the production stack |
| **Tests** | Backend 1,183 passed + 1 skipped (SQLite and PostgreSQL), frontend 444, integration 76, launch suite 68 + 2 skipped, deployment check 43 + restore + rollback, audits clean — [details](#9-tests-run-and-results) |
| **Readiness** | **Ready for internal testing** with non-confidential data. **Not yet ready for a limited beta** outside the team, and **not ready for a public launch** — [why](#launch-readiness) |

## 1. Product audit and prioritised gaps (10.1)

The audit (a fresh database with every kind of record, a Chromium crawl of all 23 routes at
desktop and phone widths in both themes with `axe-core`, a code and configuration security
review, dependency and secret scans, page-load and API latency measurements) is recorded in
the [plan](phase-10-plan.md#1-how-the-audit-was-done-101). Its twelve gaps, and where they
stand now:

| ID | Gap (severity) | Status |
|---|---|---|
| G1 | No authentication or authorisation (**Critical**) | **Fixed**: accounts, sessions, roles, ownership, CSRF defence, audit trail (`f48cbb7`, `9aed265`) |
| G2 | No production deployment path (**Critical**) | **Fixed and verified locally**: images, compose, nginx, production settings check (`7300ba2`); not run on a production host |
| G3 | No backup or restore (**High**) | **Fixed and tested**: `backup.sh`, `restore.sh`, exercised by every deployment check |
| G4 | No inbound rate limiting (**High**) | **Fixed**: limits per address, per account from an address and per account (sign-in and password change), nginx limits (`f48cbb7`, `c2a9ef3`, `7300ba2`, and the review's fixes); in one process's memory |
| G5 | Thin operational visibility (**High**) | **Fixed**: metrics, JSON logs, request IDs end to end, runbook (`c2a9ef3`, [operations](../operations.md)); no alerting deployed |
| G6 | Accessibility and phone defects (**Medium**) | **Fixed** (`3a75f62`), and four more found by the launch suite fixed (`31a09d5`, `60ac303`) |
| G7 | No automated browser checks (**Medium**) | **Fixed**: the launch suite in CI (`fa5cc16`) |
| G8 | No first-use guidance (**Medium**) | **Fixed**: `/guide` and the welcome card (`3a75f62`) |
| G9 | Public source maps (**Low**) | **Fixed**: hidden maps, deleted from the image, 404 at the web server |
| G10 | Out-of-date API description (**Low**) | **Fixed** (`3a75f62`) |
| G11 | One API process only (**Medium**, for scale) | **Enforced** in the deployment (decision [95](../decisions.md#95-one-api-process-per-deployment)); a shared queue is next work |
| G12 | Legal and regulatory questions unexamined (**Medium**) | **Identified, not resolved**: the areas for qualified review are listed in [privacy](../privacy.md#areas-for-qualified-review); RUMIN claims no compliance |

## 2. Improvements completed

### Usability and consistency (10.2) and onboarding (10.3)

- Every page names itself in the browser tab; heading order fixed on the 2D network, the graph
  and the dossiers; empty column headers named; "Local workspace" became "Workspace".
- Wide tables scroll inside a region that becomes named and focusable only while it overflows
  (22 tables, then every table named after the suite found duplicate region names).
- The status indicator wraps on a phone (Overview and System had overflowed by 15 and 112 px).
- **Getting started** (`/guide`): what RUMIN is, the five kinds of knowledge, six starter tasks
  that each open a working page on real functionality (explore the network, a what-if
  scenario, how much a result depends on its inputs, the findings, the Analyst, where the data
  came from), what each role allows (a viewer is told which steps they cannot take), and the
  limits to keep in mind. The Overview opens with a card pointing to it, hidden once dismissed.
- Role-aware controls: a viewer sees *Execute*, *Run simulation* and similar controls disabled
  with the reason; *People* is offered only to administrators; a temporary password leads
  straight to *Choose your own password*; an ended session returns to sign-in and back.
- Found by the launch suite and fixed: the Scenario Lab's sticky controls panel covered
  *Save and execute* at 1440 px; a long scenario name widened the phone 3D page by 130 px;
  the builder's repeated fields now have row-specific names for screen readers.

### Authentication and authorisation (10.4)

Designed in [security](../security.md#accounts-sessions-and-access-phase-10) and decisions
[88–93](../decisions.md#88-local-accounts-and-server-side-sessions-in-an-httponly-cookie):
local accounts by administrators; Argon2id (RFC 9106 low-memory profile) and a NIST SP
800-63B policy; 256-bit session tokens stored as SHA-256, idle 120 minutes, absolute 12 hours,
ended by sign-out, deactivation, password change or *sign out everywhere*; viewer, analyst,
admin; owner-or-admin changes; conversations private even from administrators; the last
administrator protected; cross-site changes refused by `Origin` and Fetch Metadata; one
message for a wrong password or an unknown account, with the same Argon2 work;
a per-address limit (20 failures in 10 minutes, wrong current passwords included), a
per-account-and-address limit (5 in 15 minutes: the owner elsewhere is not locked out), an
account-wide lock after 50 failures from anywhere, and nginx's 10 sign-ins a minute; an audit
trail of every security event. Tested by `test_auth.py` (25 tests, including a walk of every
route and simultaneous failures), the web app's session and People tests,
`auth.integration.test.ts` (10) and the launch suite's access and viewer workflows.

### Security (10.5), privacy and provenance (10.6)

See [§ 4](#4-security-and-privacy).

### Reliability (10.7)

Most of the failure handling predates Phase 10 and was re-checked in the audit: bounded
provider requests (20 s, 4 attempts, `Retry-After` honoured up to 60 s, stop after 3 outages),
failed ingestion recorded and shown; bounded executions (a pool of 2 + 8 queued, 20 s, cancel,
429 before storing anything) and analyses (two at once, deadlines), executions interrupted by a
restart marked failed at the next start; the Analyst's deadline and fallback to RUMIN's own
composer when a model fails; no automatic retry of any write (a stale save is refused with
409); errors in one envelope with a request ID and never a stack trace; readiness naming the
failing dependency. Phase 10 added: sessions that survive restarts (they are in the
database); container health checks and `restart: unless-stopped`; a web server that answers
429 instead of queueing floods; the restore drill in every deployment check; and the web
app's session layer, which returns to sign-in on a 401 from any request and clears cached
data when the signed-in person changes.

### Performance (10.8)

Measured, not assumed ([§ 6](#6-reliability-and-performance-findings)). No optimisation was
needed for the launch suite's pages; the one heavy asset (the 3D renderer, 540 KiB raw /
134 KiB gzip) already loads only on the 3D page.

### Observability (10.9) and deployment (10.10)

See [§ 7](#7-deployment-and-operational-readiness).

### Launch verification (10.11)

A Playwright suite with `axe-core` (70 tests: 26 pages and 9 access and workflow tests on
each of two viewports), run by `scripts/e2e.sh` on a fresh database and in CI; the same suite
run by URL against the production stack. [Testing](../testing.md#the-launch-suite-frontende2e)
describes it. It found five defects, all fixed ([§ 5](#5-ux-and-accessibility)).

### Documentation (10.12)

New: [deployment](../deployment.md) (first start, settings, upgrades, rollback, backups,
certificates), [operations](../operations.md) (health, metrics and alert rules, logs, accounts,
routine tasks, troubleshooting, incidents), [privacy, integrity and provenance](../privacy.md)
(what is stored, where it goes, retention, guarantees, areas for qualified review).
Rewritten for Phase 10: [security](../security.md), the README, [setup](../setup.md) (an
account and signing in, `curl` with a session), [API](../api.md#accounts-and-people),
[environment](../environment.md), [data model](../data-model.md) (migration `0009`),
[architecture](../architecture.md), [testing](../testing.md), [known limitations](../known-limitations.md),
[roadmap](../roadmap.md) and decisions 88–99. User guidance for the core workflows is in the
product (`/guide`) and in [setup](../setup.md).

## 4. Security and privacy

### What was checked (10.5)

| Area | What was checked | Result |
|---|---|---|
| Authentication | Password hashing, policy, session tokens, cookie flags, expiry, revocation, the first administrator | Implemented and tested (§ 2); an independent review of this code is below |
| Access control | Every API route's dependencies (a test walks the route table), owner-or-admin changes, private conversations, the last administrator, the web app mirroring the rules | Enforced in the backend; tested per role |
| Cross-site scripting | No `dangerouslySetInnerHTML` or `innerHTML` with data; names on the 3D canvas set with `textContent`; Analyst answers rendered as text; the Content-Security-Policy allows no inline script and no `eval` | No unsafe rendering found; CSP enforced in production and in the launch suite |
| Cross-site request forgery | `Origin` and `Sec-Fetch-Site` checks on every change, `SameSite=Lax`, JSON-only bodies | Refused from another site (tested in the backend, the integration suite and `verify_deployment.sh`) |
| Sessions and cookies | `HttpOnly`, `SameSite=Lax`, `Secure`, `__Host-` in production; no token in any body; `Cache-Control: no-store` on session answers | Checked in tests and against the production stack |
| Sensitive information | Logs (a test reads a turn's logs), error bodies, the production bundle, metrics labels, the audit trail | No password, token, question, cookie or stack trace found; source maps not published |
| File handling | Price-file import (size, columns, manifest validation) — command line only, no upload over HTTP | Unchanged; no upload endpoint exists |
| Resource exhaustion | Body limits (64 KiB API, 128 KiB nginx), pagination caps, graph and simulation bounds, pools with 429, analysis deadlines, nginx request and connection limits | Bounded; not load-tested |
| Code execution | No `eval`, `exec`, templates or expression parsers on user input; models are code | None found |
| Dependencies | `pip-audit` (Python lock), `npm audit` (high and critical), in CI on every push | No known vulnerability at the last run |
| CORS, transport, headers | CORS empty in production (one origin); TLS 1.2 (forward-secret suites only) and 1.3, HSTS, nosniff, frame denial, no-referrer, COOP, Permissions-Policy, CSP; `no-store` on API answers | Checked by `verify_deployment.sh` (43 checks) |
| Secrets in source or bundle | gitleaks over the whole history in CI; `.env` files ignored; bundle inspected | None found |

**Fixed during the phase**: everything under G1, G4 and G9; a guessing path through the
password-change form (wrong current passwords now count towards the address limit); the Vite
proxy's `changeOrigin`, which made every sign-in look cross-site; an inline theme script that
the CSP would block (moved to a file); a font inlined as a `data:` URI that the CSP blocked in
production; every finding of the independent review below; and the session cookie the
deployment verification still put on command lines (the `security-review` skill's pass).

### The independent review

Before the phase closed, an independent review agent read the accounts, sessions and access
checks, the middleware, metrics and logging, the web app's session handling and the whole
deployment, and tried to break them; it reproduced its first six findings on a throwaway
database. It found **ten issues — three Medium, seven Low — and six smaller points**, all
verified against the code and fixed with a test or a deployment check
([the list](../security.md#the-internal-review-of-phase-10)):

- **Medium**: client-invented HTTP methods became metrics labels, growing memory without bound
  (now `OTHER`, and nginx refuses them); simultaneous wrong passwords overwrote each other's
  count (now one `UPDATE … RETURNING`); and the account lock let anyone keep chosen accounts —
  every administrator — locked with one request per lock period (now an address that keeps
  failing waits for that account only, and the account-wide lock needs 50 failures from
  anywhere; decision [92](../decisions.md#92-guessing-is-slowed-per-address-per-account-from-an-address-and-per-account)).
- **Low**: a success cleared the address's failures; a `next` with a tab could become a link
  to another site; `%0A` could forge a text log line; the deployment check passed a password
  as a `curl` argument; two administrators demoting each other could leave none; the API
  connected to PostgreSQL as a superuser; TLS 1.2 accepted suites without forward secrecy.
- **Smaller points**: the System page still said authentication was not implemented; API
  answers could be cached; a restore revived ended sessions; the dev proxy passed a client's
  `X-Forwarded-For`; `Password1234!` passed the policy; the launch suite's output could reach
  the web image's build context.

The review also confirmed as sound: every router but signing in is protected; writes check
role and ownership; no conversation can be read by another person; tokens, cookies, expiry and
revocation; the cross-site checks; nginx's forwarded headers and `/metrics` refusal; errors
that echo no input; owner-only backups; non-root, read-only containers.

### The `security-review` skill's pass

The bundled `security-review` skill was run last, on the whole Phase 10 change after the
fixes above (182 files; [§ 8](#8-installed-skills-inspected-and-used) describes its method).
**It reported no High or Medium vulnerability.** Its search found one Low candidate, which the
skill's own false-positive check scored 5 out of 10 (the search 6), below the skill's bar of 8,
so its final report is empty:

- `verify_deployment.sh`, which is run against production, no longer put the administrator's
  password on a command line, but it did put the administrator's **session cookie** there
  (`curl -H "Cookie: …"` and a `docker compose exec … python -c` argument), where any user of
  that machine can read it while the script runs, and it never signed that session out (usable
  for up to 12 hours). Exploiting it needs an untrusted user on the production Docker host.
  **Fixed anyway**, since it completes the password fix above: the cookie stays in a file only
  its owner can read, reaches `curl` through `-H @file` and the in-container metrics check on
  standard input, and the script signs the session out when it ends (`deployment_check.sh`
  keeps its cookie the same way). Verified: `make deployment-check` passes, and against a
  second production stack the check's own session is revoked when the script ends.

The pass also confirmed as sound, among others: every router but signing in is protected;
role and ownership on every write; private conversations; session tokens (256 random bits,
stored as SHA-256, idle and absolute expiry, the role read on every request); the cross-site
check, including `Origin: null`; bounded metrics labels and nginx's refusal of `/metrics`;
overwritten forwarded headers; the non-superuser database role; no unsafe HTML in the new
frontend code; the CI workflow's read-only permissions.

### Privacy, integrity and provenance (10.6)

[Privacy](../privacy.md) lists what RUMIN stores about people (accounts, session hashes, the
audit trail with client addresses, authorship, free-text questions, typed figures), where it
can go (nowhere by default; with a language model configured, questions and the records the
Analyst gathers go to the model provider), retention and deletion (sessions expire; audit
events until pruned; accounts deactivated, never deleted; executed scenarios immutable), and
what RUMIN guarantees about its records (append-only history with hashes and re-verification,
provenance on every figure, authorship, outputs labelled as calculations, not advice). Checked
in the product by the launch suite: illustrative and SYNTHETIC data are labelled on the pages
that show them; failed retrievals and stale graphs are surfaced. **Areas for qualified
review** (not decided by this phase): India's DPDP Act 2023 and Rules, GDPR/UK GDPR where
applicable, the CERT-In Directions of April 2022, professional confidentiality (the ICAI Code
of Ethics, for a firm of Chartered Accountants), SEBI's investment adviser and research analyst
regulations, data licences, the model provider's terms, record keeping and staff monitoring.

### Remaining risks

| Risk | Severity | Mitigation today | Action |
|---|---|---|---|
| No formal security assessment | High (for external use) | Internal reviews, automated checks, tests per role | Penetration test before a public launch |
| Password-only sign-in | High (outside the team) | Locks, limits, audit trail, short sessions | MFA or SSO before external users |
| One shared workspace | High (for client data) | Conversations private; owner-only changes | Qualified confidentiality review; one deployment per client or several workspaces |
| Per-address limits (NAT sharing, per process) | Medium | Documented; administrators can reset | Shared limits with a queue (decision 95) |
| Account enumeration through the account-wide lock's 429 (after 50 failures) | Low | The per-address layers answer alike for unknown accounts | A uniform answer before public launch (decision 92) |
| No memory limits on the containers | Low | The one unbounded growth found (metrics labels) is fixed | Set limits once memory use is measured under load |
| Base images pinned by tag, not scanned | Medium | Tagged minor versions; rebuild monthly | Digest pinning and image scanning in CI |
| No quotas on stored records | Medium | Bounded requests and pools | Quotas and retention per person |

## 5. UX and accessibility

- **Audit fixes** (G6): heading order, empty headers, keyboard-reachable scroll regions,
  sideways scrolling at 390 px, page titles on seven routes.
- **Found by the launch suite and fixed**: the covered execute button (desktop); the 130 px
  overflow on the phone 3D page; duplicate and parent-shadowing region names (`axe`
  `landmark-unique`) on the phone Data and Scenario library pages; identical field names in the
  builder's repeated rows; the blocked font in production.
- **Result**: on every one of the 26 pages, at 1440 × 900 and 390 × 844, no `axe-core`
  violation, no console error, no sideways scrolling — through the preview server and through
  the production stack under its Content-Security-Policy.
- **Not done**: no session with people who use assistive technology; Chromium only; the launch
  suite runs in the light theme (the audit's crawl covered both themes).
- **Skills**: see [§ 8](#8-installed-skills-inspected-and-used).

## 6. Reliability and performance findings

| Measure | Result | Conditions |
|---|---|---|
| Page loads, desktop (launch suite, preview server) | First contentful paint 144–252 ms (median 198), largest 144–356 ms (median 210) | 26 pages, localhost, gzip, one run |
| Page loads, phone viewport (same run) | 132–328 ms (median 214) | Same |
| Page loads through the production stack | Desktop FCP 204–432 ms (median 292), LCP 204–824 ms (median 308; the executed scenario's page); phone 160–224 ms (median 200) | nginx, TLS 1.3, HTTP/2, a new browser context (TLS handshake) per test, localhost |
| JavaScript | Entry bundle 270 KiB raw / 85 KiB gzip; 129–311 kB transferred per page; the 3D renderer (540 KiB / 134 KiB gzip) only on the 3D page | Production build |
| API latency (audit) | Medians 3–26 ms on 13 endpoints; slowest 95th percentile 135 ms (an intelligence dossier) | 20 requests each, localhost, SQLite |
| Heavy computations (earlier phases) | Monte Carlo worst case 5.7 s of a 20 s deadline; graph reads benchmarked to 20,000 companies | See the Phase 8 and 9 reports |
| Concurrency | **Not measured** | No load test was run |

Reliability evidence: the backend suite covers database outages (503 with the failing check),
provider outages and partial ingestion, execution timeouts, cancellation and interrupted
executions, Analyst provider failures and fallbacks; the deployment check stops and restarts
the API and web server around a restore and verifies the stack answers again. Not exercised:
a real network, a database failover, a full disk, sustained load.

## 7. Deployment and operational readiness

- **Reproducible**: `docker compose -f compose.production.yml build`, the documented first
  start ([deployment](../deployment.md#first-start)), and `scripts/verify_deployment.sh` to check
  it. `make deployment-check` does all of it on a throwaway stack with a self-signed
  certificate — 43 checks, a backup, a change, a restore that removes the change, a switch of
  release images and back — locally in 94 s and in CI on every push.
- **Configuration**: development, test and production are separate (`RUMIN_ENVIRONMENT`);
  production refuses development defaults; secrets come from an owner-only env file; the
  launch suite and the smoke test create random credentials per run.
- **Migrations** are a deliberate step after a backup; **rollback** runs the previous images,
  restoring the pre-upgrade backup when the release migrated.
- **Observability**: `/metrics` (administrators and listed scrapers; not served by nginx), JSON
  logs with nginx's request ID carried to the API, readiness naming the failing dependency, the
  audit trail; alert rules to start from and a troubleshooting table in
  [operations](../operations.md). No monitoring system or alerting is deployed.
- **Not done**: no deployment to a production host (not authorised); no real certificate;
  no restore drill on another machine; no high availability.

## 8. Installed skills inspected and used

The installed skills were listed and inspected again at the start of the phase
([plan § 5](phase-10-plan.md#5-installed-skills-inspected)). That list missed one: the
bundled **`security-review`** skill, which the Phase 8 report had set aside for this phase. It
was used at the end of the phase, as below.

- **`security-review`** (bundled) — used once, at the end, on the whole Phase 10 change (from
  the Phase 9 report commit to the reviewed head, 182 files), after the independent review's
  fixes: one sub-task looked for vulnerabilities with the skill's categories and method; each
  candidate went to its own sub-task, which checked it against the skill's false-positive rules
  and scored it; only findings scored 8 or more out of 10 were kept.
  Its result is in [§ 4](#the-security-review-skills-pass).
- **`dataviz`** (bundled) — used: its anti-pattern catalogue was applied again to every chart
  in the audit (no dual axes, no dashed grids, table twins, text in text colours); no chart
  changed in Phase 10 needed a correction.
- **`kapture-browser-automation`** — not usable: it drives a Chrome extension that is not
  connected here. The audit and the launch suite use Playwright with the pre-installed
  Chromium instead.
- `docs`, `docx`, `pptx`, `xlsx`, `pdf`, `morning`, `import-memory`, `skill-creator`,
  `claude-api`, and the bundled configuration and workflow skills — inspected, not relevant to
  product quality, security or deployment work.
- **No installed skill covers** product design, usability, accessibility, responsive layout
  or deployment. That work followed WCAG 2.2 and the design system, checked with `axe-core`,
  and established practice (OWASP guidance, NIST SP 800-63B, RFC 9106).

## 9. Tests run and results

Every suite was run on the final code; nothing failing was left or hidden.

| Suite | Where | Passed | Failed | Skipped | Notes |
|---|---|---|---|---|---|
| Backend (pytest) | SQLite, locally and CI | 1,183 | 0 | 1 | The skip needs a model key ([testing](../testing.md)) |
| Backend (pytest) | PostgreSQL 16, locally and CI | 1,183 | 0 | 1 | Same |
| Frontend unit and pages (Vitest) | locally and CI | 444 | 0 | 0 | CI run 40 failed once on a test that read the tab title too early — fixed in the test (`67ff72c`), then 8 runs in a row with every CPU busy. CI run 44 failed once on the Analyst's hand-over to the Scenario Lab: the 3 s wait for the Lab also covered its first import (2.6–3.2 s with every CPU busy); the test now loads the Lab first (`c8437ec`), then 3 full runs with every CPU busy |
| Integration (live API, signed in) | `make smoke`, locally and CI | 76 | 0 | 0 | 2 runs in 8 failed one test after the review fixes: a stored intelligence analysis read back *stale* — correctly, as another test file had just executed a scenario for the same company. The files now run one at a time; 8 runs in a row passed |
| Launch suite (preview server) | `make e2e`, locally and CI | 68 | 0 | 2 | Skips by design: two stored-once workflows run on the desktop only |
| Launch suite (production stack) | locally, `RUMIN_E2E_URL` | 68 | 0 | 2 | After the font fix, and again on images rebuilt after the review fixes; the first run there failed 59 tests on that one defect |
| Deployment check | `make deployment-check`, locally and CI | 43 checks + restore + rollback | 0 | — | |
| Dependency audit and secret scan | `make audit`, CI | clean | — | — | pip-audit, npm audit (high/critical), gitleaks |
| Lint, format, types | backend and frontend, CI | clean | — | — | ruff, mypy, Biome, tsc |
| Analyst evaluation | inside the backend suite | 33 cases | 0 | — | Grounded composer and scripted models; no live model |

**CI**: run #45 on `c8437ec`, the phase's last code change: all six jobs green — backend
(lint, format, types, the sample dataset, the OpenAPI snapshot, tests on SQLite and on
PostgreSQL 16), frontend (lint, types, tests, build, API types), security (pip-audit, npm
audit, gitleaks), the smoke test, the launch suite and the deployment check. Runs #40 and #44
each failed once on a frontend test's timing (fixed as above); #42 was superseded by a newer
push before it finished.

**Not performed**: a load or concurrency test; a penetration test; a run on a production host
or public network; Firefox or Safari; a session with assistive-technology users; a live
language model (no key); a live World Bank retrieval (the provider is unreachable here).

## 10. Known issues and launch blockers

Known issues (documented in [known limitations](../known-limitations.md)): one shared
workspace; local accounts without MFA or SSO; administrators reset passwords by hand; rate
limits per address and per process; no quotas or automatic retention; no erase or export of
one person's data; one host and one API process; the sample network is illustrative (fictional
companies) and no real observations are stored here; the Analyst's language model and the
World Bank retrieval are unverified in this environment.

**Blockers**, by scope, are in the readiness assessment below.

## Launch readiness

Assessed on the evidence above, for the build at the end of Phase 10. No score is given.

| Area | What was checked | Evidence | Remaining gaps | Severity and user impact | Action before launch |
|---|---|---|---|---|---|
| **Core feature completeness** | Every module against its documentation; the starter tasks | All 26 pages load and pass their checks; the six starter tasks open working pages; the core workflows run in a browser | The knowledge graph holds only the illustrative (fictional) network; no real observations are stored here; ingestion and graph builds are command-line only | **High** for real analysis: users can run scenarios on their own figures, but the graph's companies are fictional | Decide the data scope and licences; load real data under them, or run a beta explicitly on illustrative data |
| **Critical workflow reliability** | Sign-in to sign-out, scenario from template to stored execution, the Analyst, People, the viewer's limits; failure paths in the suites | Launch suite 68/68 (preview and production stack); integration 76/76; backend failure-path tests | No test of a database failover, full disk or sustained load | Medium: behaviour under infrastructure failure is known only from tests | A restore drill and a failure drill on the real host |
| **Security and access control** | § 4: every route, roles, ownership, sessions, CSRF, XSS, headers, secrets, dependencies; an independent review | Tests per role; 43 deployment checks; clean audits; the independent review's ten findings fixed; the `security-review` skill's pass (§ 4) | No formal assessment; password-only sign-in; per-address limits | **High** for users outside the team; acceptable inside it | MFA or SSO before external users; a penetration test before a public launch |
| **Data quality and provenance** | Labels on illustrative and SYNTHETIC data, provenance, freshness, failed retrievals | Page and integration tests; the launch suite's pages | Unverified live provider runs here | Medium | A live World Bank run reviewed on the target host |
| **Simulation integrity and validation** | Reproducibility, hashes, the verification register (Phase 9) | Verification registers pass; executions reproduce exactly | No parameter estimated from data; nothing back-tested | **High** if results were read as forecasts — they are labelled as calculations | Keep the labels; state the limits in any client material |
| **User experience and accessibility** | 26 pages × 2 viewports with axe; keyboard access; onboarding | No axe violation, no overflow, no console error; guide and first-use card | Chromium only; no assistive-technology session | Medium for users of other browsers or of assistive technology | A session with assistive-technology users; Firefox and Safari runs |
| **Performance and resource limits** | Page loads, bundle sizes, API latency, bounded work | § 6 | No load or concurrency test | Medium: capacity unknown | A load test at the expected number of users |
| **Deployment reproducibility** | Images, compose, first start, verification, upgrade mechanics | `make deployment-check` locally and in CI | Never run on a production host, a real certificate or a real network | **High** until done once | First deployment on the intended host, then `verify_deployment.sh` |
| **Monitoring and recovery** | Metrics, logs, readiness, backup and restore | Tested restore; metrics and log tests | No monitoring system or alerts deployed; no off-host backup schedule | High for an unattended service | Wire the alerts in [operations](../operations.md#metrics); schedule and encrypt off-host backups; a restore drill |
| **Documentation and support** | Deployment, operations, privacy, security, setup, API, guide | The documents listed in § 2 | No privacy notice or terms in the product; no support process | Medium | A privacy notice and a named owner for support and incidents |

### Verdict, by scope

- **Ready for internal testing** — by the team that runs it, on a private network, with
  hypothetical or non-confidential figures. The evidence supports this: every suite passes,
  access control is enforced and tested, and the deployment is reproducible and recoverable
  on one machine.
- **Not yet ready for a limited beta** (named users outside the team, or any client data).
  Blockers: (1) a first deployment on the intended host, verified, with scheduled off-host
  backups and a restore drill; (2) a qualified review of the privacy, confidentiality and
  regulatory questions, and a privacy notice; (3) MFA or SSO, or access restricted to a private
  network; (4) a decision on the data scope (real data and its licences, or a beta explicitly on
  illustrative data); (5) alerts on the metrics.
- **Not ready for a public launch.** Beyond the beta blockers: a formal security assessment;
  load testing; separation between clients or workspaces; quotas and retention; protection
  beyond per-address limits; a uniform answer for locked and unknown accounts.

## 11. Completion gate (10.14)

| # | Requirement | Status | Evidence |
|---|---|---|---|
| 1 | Full product audit and prioritised gap analysis | **Done** | [Plan](phase-10-plan.md), § 1 |
| 2 | Critical usability and consistency issues addressed | **Done** | § 2, § 5; launch suite clean |
| 3 | Authentication and authorisation reviewed and tested | **Done** | § 2, § 4; `test_auth.py` (25), integration and launch suites; the independent review's ten findings fixed |
| 4 | Security and privacy risks assessed and documented | **Done** | § 4; [security](../security.md), [privacy](../privacy.md); legal areas left for qualified review |
| 5 | Critical user journeys tested across the product | **Done** | Launch suite (preview and production stack), integration suite |
| 6 | Reliability, error handling and performance evaluated | **Done, within limits** | § 6; no load test (stated) |
| 7 | Deployment and configuration documented and reproducible | **Done, locally** | [Deployment](../deployment.md); `make deployment-check` in CI; no production host |
| 8 | Operational visibility and troubleshooting guidance | **Done** | Metrics, logs, [operations](../operations.md); no alerting deployed |
| 9 | User and technical documentation updated | **Done** | § 2 (10.12) |
| 10 | Phases 1–9 remain functional | **Done** | Every suite passes, including all earlier phases' tests and the launch suite's pages for every module |
| 11 | Relevant installed UI/UX skills inspected and applied | **Done** | § 8 (`dataviz` applied, and `security-review` for security; `kapture` unavailable; none other relevant) |
| 12 | Remaining risks and launch blockers stated | **Done** | § 4, § 10, [readiness](#launch-readiness) |

## 12. Recommended next steps

In order, from the [roadmap](../roadmap.md#launch-follow-ups-after-phase-10): the qualified legal
review and a privacy notice; a first deployment on the intended host with verification,
alerts, off-host backups and a restore drill; MFA or SSO; a penetration test; a load test;
separation between clients or workspaces; quotas, retention and a per-person erase and export;
a shared job queue; a session with assistive-technology users and Firefox and Safari runs;
base images pinned by digest and scanned.
