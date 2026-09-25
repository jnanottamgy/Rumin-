# Operations

Running RUMIN once it is deployed ([deployment](deployment.md)): what to watch, where to
look, how to manage people, and what to do when something goes wrong. In the commands,
`$C` stands for `docker compose -f compose.production.yml --env-file .env.production`.

## Health

| Check | Answers | Use it for |
|---|---|---|
| `GET /health` | 200 `{"status": "ok", …}` whenever the process serves requests; never touches the database | Liveness: restart the API if it stops answering (the image's own health check does this) |
| `GET /health/ready` | 200 `{"status": "ready"}` when the database answers, the migrations are current and a dataset is loaded; otherwise **503** with each check: `database` `ok`/`unavailable`, `migrations` `up_to_date`/`outdated`/`missing`, `dataset` `loaded`/`missing` | Readiness and alerting: send traffic only when ready |

Both are reachable through the web server (`https://<host>/health`, `/health/ready`) without
signing in; they reveal no data. The web server has its own container check at
`http://127.0.0.1:8080/nginx-health`.

## Metrics

`GET /metrics` on the API answers in the Prometheus text format. It is **not** served by the
web server (404): read it from inside the stack, either signed in as an administrator or from
an address listed in `RUMIN_METRICS_ALLOWED_CLIENTS` (a scraper on the host's Docker network).
Values live in the API process and restart from zero with it, as Prometheus counters expect.
Labels are route **templates** (`/api/v1/scenarios/{scenario_id}`), never raw paths, e-mail
addresses or client addresses; unknown paths count as `route="unmatched"`.

| Metric | Type | Labels | Meaning |
|---|---|---|---|
| `rumin_http_requests_total` | counter | `method`, `route`, `status` | Requests answered |
| `rumin_http_request_duration_seconds` | histogram | `method`, `route` | Time to answer (buckets 5 ms – 30 s) |
| `rumin_http_requests_in_flight` | gauge | — | Requests being answered now |
| `rumin_security_events_total` | counter | `event` | Security events written to the audit trail (below) |
| `rumin_scenario_executions_pending`, `…_capacity` | gauge | — | Executions running or waiting, and how many the process accepts (2 running + 8 waiting by default) |
| `rumin_analyst_turns_pending`, `…_capacity` | gauge | — | Analyst questions being answered or waiting, and the limit (2 + 8) |
| `rumin_process_start_time_seconds` | gauge | — | When the API process started |

Alerts worth setting (starting points, not tuned on real traffic — none exists yet):

| Condition | Example rule | Why |
|---|---|---|
| Not ready | `/health/ready` not 200 for 2 minutes | Database down, a migration missing after an upgrade |
| Server errors | `sum(rate(rumin_http_requests_total{status=~"5.."}[5m])) > 0` | Every 5xx is a defect or an outage; its request ID leads to the log |
| Slow answers | `histogram_quantile(0.95, sum by (le) (rate(rumin_http_request_duration_seconds_bucket[5m]))) > 2` | Measured medians are milliseconds; Monte Carlo analyses take seconds |
| Password guessing | `increase(rumin_security_events_total{event=~"login_failed\|login_throttled\|password_change_failed"}[15m]) > 20` | Someone is trying passwords |
| Queues full | `rumin_scenario_executions_pending >= rumin_scenario_executions_capacity` (same for the Analyst) | People are being refused with 429 |
| Restarts | `changes(rumin_process_start_time_seconds[1h]) > 2` | Crash loop |

## Logs

In production the API writes **one JSON object per line** to standard output
(`RUMIN_LOG_FORMAT=json`); Docker keeps 5 files of 10 MB per container
(`$C logs api`). Fields: `time` (UTC, milliseconds), `level`, `logger`, `request_id`,
`message`, and for each request `http` = `{method, path, status, duration_ms}`; an error adds
`exception` (the stack trace, which is never sent to the client).

- **A request ID follows each request**: nginx creates it (`$request_id`, 32 hex characters),
  passes it as `X-Request-ID`, logs it in its access line (`id=…`), and the API logs it and
  returns it in the `X-Request-ID` header and in every error body. To trace a complaint, ask
  for the ID shown with the error and search both logs for it.
- **Never logged**: request or response bodies, query strings, cookies, passwords, tokens,
  Analyst questions and answers, SQL parameters.
- The web server's access log (`$C logs web`) holds the client address, the request line,
  status, size, time and user agent.

RUMIN keeps logs only as long as Docker's rotation does. If you ship them to a collector, the
retention there is your policy (and see [privacy](privacy.md#logs)).

## Accounts

People are created and managed by administrators in **People** (the audit trail is there
too). The command line does the same from the host, for the first administrator and for
recovery:

```bash
$C run --rm api python -m app.auth create-user --email ana@example.org --name "Ana Rao" --role admin
$C run --rm api python -m app.auth set-password --email ana@example.org   # a password they keep
$C run --rm api python -m app.auth list-users
$C run --rm api python -m app.auth deactivate --email ana@example.org      # and signs them out
$C run --rm api python -m app.auth revoke-sessions --email ana@example.org
$C run --rm api python -m app.auth prune --events-older-than-days 365
```

Passwords are typed at a hidden prompt, or read from standard input with `--password-stdin`;
never as arguments. `set-password` also clears a lock and ends the person's sessions;
`create-user --temporary` makes the password one to replace at the first sign-in.

| Situation | What to do |
|---|---|
| Someone forgot their password | An administrator sets a temporary one (People → *Manage* → *Set temporary password*); they choose their own at the next sign-in. There is no e-mail reset |
| Someone is told "Too many sign-in attempts. Try again in N minutes." | Five wrong passwords for their account from their address in 15 minutes: that address waits for that account (they can still sign in from elsewhere), and it clears itself. If the audit trail shows `login_throttled` with scope `account`, the account itself is locked (50 failures from anywhere): it unlocks after 15 minutes, or at once when an administrator sets a password — then look at where the failures came from |
| A shared office address is told to wait | 20 failed sign-ins from one address in 10 minutes make that address wait, for everyone behind it. It clears itself; check the audit trail for the failures |
| Someone leaves | Deactivate the account: their sessions end at once; what they created keeps their name. Accounts are never deleted |
| A laptop is lost | *Sign out everywhere* for that person, then set a temporary password |
| The last administrator is gone | `create-user … --role admin` from the host |

**Roles**: *viewer* reads the whole workspace and uses the Analyst; *analyst* also creates and
runs scenarios, simulations and analyses; *admin* also manages people. Only a record's owner
or an administrator changes it; Analyst conversations are private to their owner.

**The audit trail** records `login_succeeded`, `login_failed` (with a reason; an unknown
e-mail address is not stored), `login_throttled` (with its scope: `client` for the address,
`account_client` for the account from that address, `account` for the account), `logout`,
`user_created`, `user_updated`,
`password_reset`, `password_changed`, `password_change_failed` and `sessions_revoked`, each
with who acted, whom it concerned, the client address, the request ID and time. It is never
pruned automatically: `prune --events-older-than-days N` removes older events (the same
command deletes sessions that ended more than a day ago). Choose N with your retention policy.

## Routine tasks

| When | Task |
|---|---|
| Daily | `scripts/backup.sh`; copy the file off the host, encrypted ([deployment](deployment.md#backups-and-restore)) |
| Before every upgrade | A backup; read the release notes |
| Monthly | Restore the latest backup on another machine; review People (roles, inactive accounts) and the audit trail |
| When certificates renew | `$C exec web nginx -s reload` |
| Monthly, and on advisories | Rebuild the images for base-image fixes; `make audit` (pip-audit, npm audit, the secret scan) |
| By your retention policy | `python -m app.auth prune --events-older-than-days N` |

## Troubleshooting

| Symptom | Likely cause | What to do |
|---|---|---|
| The API does not start: `Unsafe production configuration: …` | A setting unsafe in production: SQLite, a local or `http://` CORS origin, `RUMIN_SESSION_COOKIE_SECURE=false` | Fix each setting the message names |
| The web server restarts; its log says it cannot load `privkey.pem` | The key is not readable by user 101, or the path is wrong | `chgrp 101 privkey.pem && chmod 640 privkey.pem`; check `RUMIN_TLS_DIR` |
| `/health/ready` answers 503, `migrations: outdated` | New images, migrations not run | Back up, then `$C run --rm api alembic upgrade head` |
| `/health/ready` answers 503, `dataset: missing` | No dataset loaded | `$C run --rm api python -m app.db.seed` (and the catalogue and graph, [deployment](deployment.md#first-start)) |
| `/health/ready` answers 503, `database: unavailable` | PostgreSQL down, or `POSTGRES_PASSWORD` no longer matches the `rumin` role's | `$C ps db`, `$C logs db`; the passwords are set when the volume is first created: change one with `$C exec db psql -U postgres -c "ALTER ROLE rumin PASSWORD '…'"` and the env file together |
| Signing in seems to work, then the next page asks again | The browser refused the cookie: a `__Host-` cookie needs `https://` and the exact host name (sessions themselves survive restarts: they are in the database) | Serve over `https://` on `RUMIN_SERVER_NAME` only |
| Changes answer 403 "Requests that change data must come from RUMIN's own pages." | The request's `Origin` is not the site's own origin: a proxy in front rewrote `Host`, or the site is reached under another name | Pass the original `Host` through every proxy; use one host name |
| 429 "Too many requests" | The web server's rate limit (20 requests a second per address, sign-in 10 a minute), the API's sign-in limits, or a full execution or Analyst queue | Wait; for a shared address, see Accounts. A queue: `rumin_*_pending` metrics |
| A scenario execution or Analyst question ended *failed* after a restart | It was running when the API stopped | Run it again; nothing half-done was stored |
| A page is blank after an upgrade | The browser kept an old `index.html` (it should not: it is sent `no-cache`) | Reload; check that the web server is the new release |
| A 500 error | A defect | Find the request ID in the API log (`$C logs api \| grep <id>`); the stack trace is there |

## Incidents

1. **Contain**: deactivate affected accounts or *Sign out everywhere*; if the host is
   compromised, stop the stack (`$C stop web`) and keep the volumes.
2. **Preserve**: copy the logs (`$C logs --no-log-prefix api web > incident.log`) and take a
   backup before changing anything.
3. **Investigate** with the audit trail (People), the request IDs and the metrics.
4. **Recover** from a backup taken before the incident if data was changed
   ([restore](deployment.md#backups-and-restore); it ends every session); rotate both
   database passwords and any model key.
5. **Notify** as your obligations require. Reporting duties (for example to CERT-In in India,
   or data-protection authorities and affected people) are for qualified advice: see
   [privacy](privacy.md#areas-for-qualified-review).
