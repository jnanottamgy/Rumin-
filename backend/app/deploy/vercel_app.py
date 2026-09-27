"""The ASGI application Vercel runs (``entrypoint`` in vercel.json).

RUMIN's settings are prepared for Vercel before the application reads them
(``app.deploy.vercel``). Without a database it answers every request with a 503 that says
what is missing, rather than failing to start.
"""

from __future__ import annotations

import os

from app.deploy.vercel import not_configured, prepare_environment

if prepare_environment(os.environ):
    from app.main import app
else:
    app = not_configured()
