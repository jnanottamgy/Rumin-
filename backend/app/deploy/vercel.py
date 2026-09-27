"""RUMIN on Vercel: a test deployment (docs/deployment-vercel.md).

Vercel runs the API as a serverless function. Several short-lived processes may serve it at
once, nothing runs after a response has been sent, and the database is a managed PostgreSQL
(Neon, added from the project's Storage tab). ``prepare_environment`` turns that into RUMIN's
own settings before anything reads them:

- ``RUMIN_DATABASE_URL`` from the variables the Neon integration adds, the direct (unpooled)
  connection first;
- production mode, with the API on the web app's own origin, so no CORS origins;
- work done in the request that asks for it (``inline``), since nothing runs after a
  response, and an Analyst deadline inside the function's time limit;
- the client's address and scheme from the headers Vercel overwrites on every request.

A setting the project defines itself wins: only unset ones are filled in.

``python -m app.deploy.vercel`` is the backend's build step on Vercel: it prepares the
database with ``app.deploy.bootstrap``, or says why it cannot.
"""

from __future__ import annotations

import os
import sys
from collections.abc import MutableMapping, Sequence

from fastapi import FastAPI
from fastapi.responses import JSONResponse

# The Neon integration's variables, the direct connection first: a transaction pooler can
# lose the prepared statements psycopg makes for repeated queries.
DATABASE_VARIABLES = (
    "DATABASE_URL_UNPOOLED",
    "POSTGRES_URL_NON_POOLING",
    "DATABASE_URL",
    "POSTGRES_URL",
)

DEFAULTS = {
    "RUMIN_ENVIRONMENT": "production",
    # As in the Docker deployment: browsers bind a __Host- cookie to the exact host, https
    # and path /.
    "RUMIN_SESSION_COOKIE_NAME": "__Host-rumin_session",
    "RUMIN_CORS_ORIGINS": "",
    "RUMIN_LOG_FORMAT": "json",
    "RUMIN_SCENARIO_EXECUTION_MODE": "inline",
    "RUMIN_ANALYST_EXECUTION_MODE": "inline",
    "RUMIN_ANALYST_DEADLINE_SECONDS": "45",
    "RUMIN_TRUST_FORWARDED_HEADERS": "true",
}

NOT_CONFIGURED = (
    "RUMIN's database is not set up on this deployment. Add a Neon Postgres database from "
    "the Vercel project's Storage tab, connected to every environment, then redeploy "
    "(docs/deployment-vercel.md)."
)


def database_url(environ: MutableMapping[str, str]) -> str | None:
    """The PostgreSQL URL the database integration provides, if any."""
    for name in DATABASE_VARIABLES:
        value = environ.get(name, "").strip()
        if value:
            return value
    return None


def prepare_environment(environ: MutableMapping[str, str]) -> bool:
    """Fill in RUMIN's settings for Vercel; whether a database is configured."""
    for name, value in DEFAULTS.items():
        environ.setdefault(name, value)
    if environ.get("RUMIN_DATABASE_URL", "").strip():
        return True
    url = database_url(environ)
    if url is None:
        return False
    environ["RUMIN_DATABASE_URL"] = url
    return True


def not_configured() -> FastAPI:
    """The API without a database: every request gets a 503 in RUMIN's error envelope that
    names what is missing."""
    fallback = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @fallback.api_route(
        "/{path:path}", methods=["GET", "HEAD", "POST", "PUT", "DELETE"], include_in_schema=False
    )
    def unavailable(path: str) -> JSONResponse:
        del path
        return JSONResponse(
            {
                "error": {
                    "code": "not_configured",
                    "message": NOT_CONFIGURED,
                    "details": [],
                    "request_id": None,
                }
            },
            status_code=503,
            headers={"Cache-Control": "no-store"},
        )

    return fallback


def main(argv: Sequence[str] | None = None) -> int:
    """The build step: prepare the database, or explain why not (the build still succeeds,
    so the pages deploy and the API answers with the reason)."""
    del argv
    if not prepare_environment(os.environ):
        print(f"! {NOT_CONFIGURED}", file=sys.stderr)
        return 0
    from app.deploy import bootstrap

    return bootstrap.main([])


if __name__ == "__main__":
    raise SystemExit(main())
