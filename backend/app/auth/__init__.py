"""Accounts, sessions and access control (Phase 10).

``passwords`` hashes and checks passwords (Argon2id through ``argon2-cffi``; no homemade
cryptography), ``tokens`` makes session tokens and their hashes, ``throttle`` slows guessing
from one client, and ``policy`` says who may do what. The service that ties them to the
database is ``app.services.auth``; the command line is ``python -m app.auth``.
"""
