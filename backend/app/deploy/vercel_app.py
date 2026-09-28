"""The ASGI application Vercel runs (``entrypoint`` in vercel.json).

RUMIN's settings are prepared for Vercel before the application reads them
(``app.deploy.vercel``). Without a database it answers every request with a 503 that says
what is missing, rather than failing to start.
"""

from __future__ import annotations

import os

from app.deploy.vercel import application

# A plain assignment among the module's own statements: Vercel's build looks for the
# handler there (not inside an ``if``) and fails without it.
app = application(os.environ)
