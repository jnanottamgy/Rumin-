# Deployment

How to run RUMIN for a team: one host, Docker Compose, PostgreSQL, the API and a web server
that terminates TLS (Phase 10). Day-to-day running — health, metrics, logs, accounts,
troubleshooting — is in [operations](operations.md); what the stack defends against is in
[security](security.md).

**Status.** The stack below is built and exercised end to end by
`scripts/deployment_check.sh` (`make deployment-check`) on every CI run and locally: both
images built, a throwaway stack started with a self-signed certificate, 43 checks from
outside, a backup, a change, a restore, a switch to another release's images and back.
**RUMIN has not been deployed to a production host** in Phase 10: nothing here has run on a
public network, with a real certificate, or under real load.

## What runs

```
             :80 ──► 301 to https
browser ──► :443 ─► web (nginx, TLS, headers, rate limits) ──► api:8000 ──► db:5432
                     serves the built app                       uvicorn     PostgreSQL 16
                                                                 1 process   internal network only
```

| Service | Image | What it does | Hardening |
|---|---|---|---|
| `db` | `postgres:16-alpine` | The database, on the volume `rumin-db` | No published port; on the `data` network, which has no route out; the API connects as `rumin`, which owns its database and is not a superuser |
| `api` | `rumin-api:<version>` (`backend/Dockerfile`) | The API: **one** uvicorn process, JSON logs, `RUMIN_ENVIRONMENT=production` | User 10001; read-only file system (`/tmp` in memory); all capabilities dropped; `no-new-privileges`; no access log from uvicorn (the API logs each request itself) |
| `web` | `rumin-web:<version>` (`frontend/Dockerfile`) | nginx 1.30: the built web app, TLS 1.2/1.3 with HTTP/2, security headers and CSP, request limits, the `/api/` and `/health` proxy | User 101; read-only file system; all capabilities dropped; `no-new-privileges`; no version in the `Server` header |

The web server answers `/metrics`, `/docs`, `/redoc`, `/openapi.json` and `*.map` with 404:
metrics are for an internal scraper or an administrator ([operations](operations.md#metrics)),
the interactive API documentation is off in production, and source maps are deleted from
the image.

**One API process, always.** The scenario and Analyst runners, the analysis limit, the
sign-in throttle and the metrics live in the API process (ADR 95). Do not scale `api` to
more than one replica or add `--workers`: limits would split and a restarted process would
not see another's work.

## Before you start

- A Linux host with Docker Engine and Docker Compose v2. Sizing was **not load-tested**; the
  figures measured on one machine are in [performance](#performance-measured).
- A DNS name for RUMIN and a TLS certificate for it: `fullchain.pem` and `privkey.pem` in one
  directory. nginx runs as user 101, so that user must be able to read the key (for
  example `chgrp 101 privkey.pem && chmod 640 privkey.pem`, or a copy made by your renewal
  hook). A key readable only by root stops the web server from starting
  ([troubleshooting](operations.md#troubleshooting)).
- Outbound HTTPS from the API only if you retrieve World Bank series or configure the
  Analyst's language model. Nothing else calls out.
- Someone who will own backups, updates and the people list.

## First start

All commands run from the repository root at the release you deploy.

1. **Settings.** Copy the template and fill in every value; keep the file private.

   ```bash
   cp deploy/production.env.example .env.production
   chmod 600 .env.production
   # POSTGRES_PASSWORD and POSTGRES_ADMIN_PASSWORD: openssl rand -hex 32 (hex: the first
   # goes into a database URL, where some characters of base64 would need escaping)
   ```

2. **Images.** Build both, tagged with `RUMIN_VERSION`:

   ```bash
   docker compose -f compose.production.yml --env-file .env.production build
   ```

   Behind a proxy that re-signs TLS, pass its CA bundle as a build secret (it is not kept in
   the image): build each image with `docker build --secret id=extra_ca,src=/path/ca.crt`
   as `scripts/deployment_check.sh` does.

3. **The database, then the schema.** On its first start the database container runs
   `deploy/postgres/init/10-rumin-role.sh`, which creates the `rumin` role and database.
   Migrations are never run on start-up: they are a deliberate step.

   ```bash
   C="docker compose -f compose.production.yml --env-file .env.production"
   $C up -d --wait db
   $C run --rm api alembic upgrade head
   ```

4. **Reference data.** This build needs a dataset: the knowledge graph, the network and the
   models' company figures come from it, and readiness reports `not_ready` (`dataset:
   missing`) until one is loaded. The only dataset RUMIN ships is the **illustrative** sample
   network — fictional companies and relationships, labelled as such wherever they appear.
   A curated dataset of your own, in the same validated format
   ([data dictionary](data-dictionary.md)), loads with `--file`.

   ```bash
   $C run --rm api python -m app.db.seed            # the illustrative sample network
   $C run --rm api python -m app.ingestion catalog  # the series catalogue (no values)
   $C run --rm api python -m app.graph build        # the knowledge graph
   ```

5. **The first administrator.** The password is asked twice at a hidden prompt (never an
   argument); everyone else is created in the web app.

   ```bash
   $C run --rm api python -m app.auth create-user --email you@example.org \
     --name "Your Name" --role admin
   ```

6. **Start and check.**

   ```bash
   $C up -d --wait
   scripts/verify_deployment.sh https://rumin.example.org .env.production \
     you@example.org /path/to/a/file/holding/the/password
   ```

   `verify_deployment.sh` prints PASS or FAIL for each of its 43 checks (the redirect, HTTP/2
   and TLS, the TLS 1.2 suites, every security header and the CSP, caching, what is never
   served, refused methods, readiness, the API refusing a request without a session, the
   `__Host-` cookie's flags, the cross-site refusal, the body limit, the client address the
   API records, JSON logs, the containers' users, read-only file systems, the database role
   and the database's unpublished port) and exits 1 if any failed. It signs in with the
   password file you give it: the password reaches `curl` on its standard input and the
   session cookie stays in a file only you can read, so neither appears on a command line,
   and the session is signed out when the script ends. It spends the sign-in rate limit of
   the address it runs from for a minute.

7. **People.** Sign in, open **People**, and create each account with a role and a temporary
   password; each person chooses their own at first sign-in. Pass temporary passwords by a
   channel other than the one carrying the e-mail address.

## Settings

Set in `.env.production` (template: `deploy/production.env.example`):

| Variable | Meaning |
|---|---|
| `RUMIN_VERSION` | The release: images are tagged with it, and rollback runs the previous tag |
| `POSTGRES_PASSWORD` | The password of `rumin`, the API's database role (long, random, hex) |
| `POSTGRES_ADMIN_PASSWORD` | The password of the `postgres` superuser, used only inside the database container (restores). Both are set when the volume is first created; later changes need `ALTER ROLE` |
| `RUMIN_SERVER_NAME`, `RUMIN_PUBLIC_ORIGIN` | The host name, and the `https://` origin plain HTTP redirects to |
| `RUMIN_HTTP_PORT`, `RUMIN_HTTPS_PORT` | The ports published on the host (80 and 443) |
| `RUMIN_TLS_DIR` | The directory holding `fullchain.pem` and `privkey.pem` |
| `RUMIN_METRICS_ALLOWED_CLIENTS` | Addresses that may read the API's `/metrics` without signing in (empty: administrators only) |
| `RUMIN_ANALYST_PROVIDER`, `RUMIN_ANALYST_MODEL`, `RUMIN_ANTHROPIC_API_KEY` | The Analyst's optional language model; `grounded` (the default) uses none. Read [privacy](privacy.md#the-analysts-language-model) before setting another |

Fixed by `compose.production.yml` or the image: `RUMIN_ENVIRONMENT=production`,
`RUMIN_LOG_FORMAT=json`, `RUMIN_CORS_ORIGINS` empty (the app is served from the API's own
origin), `RUMIN_SESSION_COOKIE_NAME=__Host-rumin_session`, and `FORWARDED_ALLOW_IPS="*"`
(uvicorn trusts `X-Forwarded-For` from any peer, which is safe only because nothing but the
web server can reach the API's port; keep it that way).

Every other setting keeps its default unless you add it to the `api` service's
`environment`: sessions end after 120 idle minutes and 12 hours in any case; an address waits
after 20 failed sign-ins in 10 minutes, and after 5 in 15 minutes for one account; an account
locks for 15 minutes after 50 failures from anywhere. All settings are listed in
[environment](environment.md).

**Production refuses unsafe settings.** With `RUMIN_ENVIRONMENT=production` the API does not
start on SQLite, with local or `http://` CORS origins, or with
`RUMIN_SESSION_COOKIE_SECURE=false`, and turns the interactive API documentation off unless
it is asked for. The refusal names each problem ([operations](operations.md#troubleshooting)).

## Upgrades

1. Read the release's notes: does it add a migration?
2. **Back up**: `scripts/backup.sh` (below).
3. Set `RUMIN_VERSION` to the new release and build its images. Keep the previous release's
   images on the host: they are the rollback.
4. Stop the web server and the API, migrate, start:

   ```bash
   $C stop web api
   $C run --rm api alembic upgrade head
   $C up -d --wait
   ```

   Sign-ins and pages are unavailable for the minute this takes; scenario executions or
   Analyst questions in progress when the API stops are marked failed at the next start.
5. Run `scripts/verify_deployment.sh` again.

## Rollback

- **A release without a migration:** set `RUMIN_VERSION` back to the previous tag and
  `$C up -d --wait --no-build`. Nothing else changes.
- **A release with a migration:** stop the web server and the API, restore the backup taken
  before the upgrade (`scripts/restore.sh`), then start the previous tag. **Everything
  written after that backup is lost** — say so to the team before you do it. Alembic's
  downgrades exist and are tested from the latest revision to the empty schema on SQLite,
  but they are not the supported rollback: restoring the backup is.

`scripts/deployment_check.sh` exercises the mechanics (a switch to another release's images
and back, and a restore), not a real version difference.

## Backups and restore

```bash
scripts/backup.sh                          # writes backups/rumin-<UTC time>.dump
scripts/restore.sh backups/rumin-….dump --yes
```

- `backup.sh` runs `pg_dump` in the custom format inside the database container, writes the
  file readable only by its owner (`umask 077`), and checks it by reading its table of
  contents back; a file that cannot be read is not kept. `RUMIN_BACKUP_DIR` changes the
  directory.
- `restore.sh` **replaces the whole database**: it checks the file, stops the web server and
  the API, drops and recreates the database (as the `postgres` superuser), restores it as
  `rumin`, **ends every session** (sessions ended after the backup would otherwise come
  back), and starts both again. Passwords changed since the backup are back to their earlier
  values: tell those people, or set temporary passwords. It refuses to run without `--yes`.
- **Schedule it** (for example a daily `cron` entry running `scripts/backup.sh`), and before
  every upgrade. RUMIN sets no retention period for backups: that is your policy.
- **A backup holds everything**: scenarios and results, conversations, the accounts (password
  hashes, never passwords) and the security audit trail with client addresses. Encrypt the
  copies and keep them off the host. See [privacy](privacy.md).
- **Test a restore** regularly on another machine; `make deployment-check` does it on a
  throwaway stack.

## Certificates

The web server reads `fullchain.pem` and `privkey.pem` from `RUMIN_TLS_DIR` at start-up.
After a renewal, reload it: `$C exec web nginx -s reload`. `Strict-Transport-Security` is sent
with `max-age=31536000` (no `includeSubDomains`, no preload): once a browser has seen it,
it will refuse plain HTTP to this host for a year.

## Checking the deployment on one machine

```bash
make deployment-check      # or scripts/deployment_check.sh
```

Builds both images, starts the stack as project `rumin-check` on ports 18080 and 18443 with a
self-signed certificate for `localhost`, follows the first-start steps above, runs
`verify_deployment.sh`, backs up, changes the data, restores and checks that the change is
gone, switches image tags and back, and removes the stack, its volume and the certificate
whatever the outcome. It needs Docker with Compose v2, `openssl`, `curl` and `python3`, and
sends nothing anywhere. Measured: 94 seconds locally with warm image caches; CI job
*Deployment*.

## Performance (measured)

On one development machine (localhost, no network latency), through the launch suite
([testing](testing.md#the-launch-suite-frontende2e)): first contentful paint 144–252 ms
(median 198) on the 26 pages at desktop size and 132–328 ms (median 214) on a phone
viewport; the API's medians 3–26 ms with the slowest 95th percentile 135 ms (the Phase 10
audit, [plan](phases/phase-10-plan.md)). Nothing was measured under concurrent load, over a
real network or on production hardware.

## Known limits

- One host, one API process, one database: no high availability, no horizontal scaling.
- The rate limits work per client address, so people behind one NAT share them (sign-in:
  10 a minute with a burst of 5 at the web server; 20 failures per 10 minutes at the API).
- No e-mail: administrators reset passwords ([operations](operations.md#accounts)).
- More in [known limitations](known-limitations.md#deployment-and-operations).
