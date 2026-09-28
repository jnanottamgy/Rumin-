# RUMIN on Vercel (a test deployment)

A way to try RUMIN online with its illustrative sample data: the web app and the API run on
Vercel, the database on Neon Postgres (from Vercel's Marketplace). It is **not** the
production design: that is the Docker deployment in [deployment](deployment.md), verified
end to end with 43 checks, a restore and a rollback. The differences are listed
[below](#how-it-differs-from-the-docker-deployment); keep client data out of a test
deployment ([privacy](privacy.md)).

## How it is set up

[`vercel.json`](../vercel.json) defines two services and routes between them:

| Service | Root | What Vercel builds | Serves |
|---|---|---|---|
| `web` | `frontend/` | the Vite build (`npm run build`); no source maps are written on Vercel | every path not listed below; a path that is not a file gets `index.html`, so links into the app open |
| `api` | `backend/` | the FastAPI app `app.deploy.vercel_app:app`, dependencies from `backend/pyproject.toml` and `uv.lock`; RUMIN itself is not installed as a package (`package = false`), so the function has one copy of `app/`, next to `migrations/` and `alembic.ini` | `/api/*`, `/health`, `/health/ready` |

Every response carries the same browser protections as the Docker deployment's web server
(Content-Security-Policy without inline script, `nosniff`, frame denial, no referrer,
COOP, Permissions-Policy; Vercel adds its own HSTS); a test keeps the two lists equal.
`/metrics`, `/docs` and `/openapi.json` are not routed to the API.

On Vercel, [`app.deploy.vercel`](../backend/app/deploy/vercel.py) fills in RUMIN's settings
before the API reads them. A variable the project sets itself wins.

| Setting | Value on Vercel | Why |
|---|---|---|
| `RUMIN_DATABASE_URL` | from the Neon integration's `DATABASE_URL_UNPOOLED` (else `POSTGRES_URL_NON_POOLING`, `DATABASE_URL`, `POSTGRES_URL`) | the direct connection: a transaction pooler can lose the prepared statements psycopg makes |
| `RUMIN_ENVIRONMENT` | `production` | `Secure` cookies, no API docs, and the production checks |
| `RUMIN_SESSION_COOKIE_NAME` | `__Host-rumin_session` | as in the Docker deployment: browsers bind the cookie to the exact host, `https` and path `/` |
| `RUMIN_CORS_ORIGINS` | empty | the API shares the web app's origin |
| `RUMIN_SCENARIO_EXECUTION_MODE`, `RUMIN_ANALYST_EXECUTION_MODE` | `inline` | nothing runs after a response on Vercel, so work is done in the request that asks for it |
| `RUMIN_ANALYST_DEADLINE_SECONDS` | `45` | an answer ends within the function's time limit |
| `RUMIN_TRUST_FORWARDED_HEADERS` | `true` | Vercel overwrites `X-Forwarded-For` and `X-Forwarded-Proto` on every request, so they give the client's address (for the limits on guessing and the audit trail) and `https` (for the cross-site check) |
| `RUMIN_LOG_FORMAT` | `json` | one object per line in Vercel's runtime logs |

**The build prepares the database.** The backend's build step,
`python -m app.deploy.vercel` (declared in `backend/pyproject.toml`), runs
[`app.deploy.bootstrap`](../backend/app/deploy/bootstrap.py): the migrations; the
illustrative sample dataset and the series catalogue (definitions only: nothing is fetched);
the knowledge graph, only when none exists or its sources changed; and the first
administrator, only when no account is an active administrator. Each step does nothing when
it is already done, so it runs on every deployment; a PostgreSQL advisory lock keeps two
deployments from doing it at once. A failed step fails the build. **Without a database** the
build still succeeds and the API answers every request with a 503 that says what is missing
(`not_configured`).

## Setting it up

Once, in the Vercel dashboard of the project connected to this repository:

1. **Add the database.** *Storage* → *Create Database* → *Neon* (Postgres) → the Free plan →
   a region near the people who will use it → connect it to the project for Development,
   Preview and Production, with no environment-variable prefix.
2. **Name the first administrator.** *Settings* → *Environment Variables*, for Preview and
   Production: `RUMIN_BOOTSTRAP_ADMIN_EMAIL`, `RUMIN_BOOTSTRAP_ADMIN_NAME`, and
   `RUMIN_BOOTSTRAP_ADMIN_PASSWORD` marked *Sensitive* — a temporary password of at least 12
   characters, which must be replaced at the first sign-in
   ([environment](environment.md#first-administrator-on-a-fresh-database-the-vercel-build)).
3. **Deploy.** A push to a branch makes a preview deployment; the production branch, a
   production one. The build log shows each preparation step (`==> …`).
4. **Sign in** at the deployment's URL with that address and password, and choose your own
   password. Then delete the three `RUMIN_BOOTSTRAP_ADMIN_*` variables; everyone else is
   created in *People*.

The functions' region is set in the project (*Settings* → *Functions*); keep it next to the
database's, since every request queries it.

## Who can open it

Vercel's own **Deployment Protection** (*Vercel Authentication*, on by default) shows a Vercel
sign-in page to anyone outside the Vercel team. To let someone else test, use the
deployment's *Share* button: a link that works without a Vercel account and expires (23
hours). RUMIN's own sign-in applies after that. Turning protection off makes the URL public;
do that only while the deployment holds nothing but sample data.

## How it differs from the Docker deployment

| | Docker ([deployment](deployment.md)) | Vercel |
|---|---|---|
| Processes | one API process (decision 95) | several short-lived ones; none runs after a response |
| Executions and Analyst answers | a bounded background pool; the page polls | in the request that asks (`inline`): the request waits for the result, within the function's limit |
| Work left unfinished by a stopped process | marked interrupted when the API starts | marked interrupted only after 10 minutes, since another process may still be running it |
| Limits on guessing passwords, pool capacity | per process, in memory (the account-wide lock is in the database) | the same, but per process of several: weaker |
| Request rate limits | nginx (per address) | none of RUMIN's own; Vercel's platform protections only |
| Metrics | `/metrics` for administrators and listed scrapers | not routed |
| Backups and restore | `backup.sh`, `restore.sh`, checked by every deployment check | Neon's own (point-in-time restore, per Neon's plan); RUMIN's scripts do not apply |
| First request after a pause | immediate | slower: the function starts and Neon's compute wakes (seconds) |
| Verified by | `make deployment-check` in CI (43 checks, restore, rollback) and the launch suite | the backend's tests for the Vercel settings and preparation, and requests to the deployment |

## Troubleshooting

| What you see | Why | What to do |
|---|---|---|
| `404: NOT_FOUND` on every page | a deployment made before `vercel.json` existed: nothing was built | deploy a commit that has `vercel.json` |
| The build fails with `Handler function "app" not found in app/deploy/vercel_app.py` | Vercel's build looks for `app` among the module's own statements, not inside an `if` (the first deployment of this setup failed so) | keep `app = application(os.environ)` at the top level; `test_the_vercel_entrypoint_defines_its_handler_at_the_top_level` checks it |
| A Vercel sign-in page | Deployment Protection | sign in to Vercel, or open a share link |
| "RUMIN's database is not set up on this deployment" (503) | no database variables | step 1, then redeploy |
| The build stops at *Checking for an administrator* | the temporary password fails the policy, or the e-mail address already belongs to a deactivated account | choose another password (12+ characters, not a common one) or address |
| Nobody can sign in | no administrator was created (the variables were not set when the database was prepared) | step 2 and redeploy, or `python -m app.auth create-user` from a machine with `RUMIN_DATABASE_URL` set to the database |
| A Scenario Lab execution or an Analyst answer fails with a time limit | the function's time limit | smaller analyses; the Docker deployment has no such limit |

## Checking a deployment

`GET /health/ready` answers `{"status":"ready","checks":{"database":"ok","migrations":"up_to_date","dataset":"loaded"}}`.
Then sign in and follow the starter tasks in the app's guide (`/guide`). The launch suite
([testing](testing.md#the-launch-suite-frontende2e)) can run against a deployment by URL, but
not through Vercel Authentication: it needs a deployment without protection, or the
suite would have to send Vercel's protection-bypass header, which it does not yet.

**The same build, locally.** `vercel build` at the repository's root runs Vercel's build
(the project's settings from `vercel pull`, in `.vercel/`, which git ignores; its Python step
needs uv 0.9.25 or newer). The API function's files are listed in
`.vercel/output/services/api/functions/*/.vc-config.json`.
