"""Framework-independent domain definitions (no FastAPI or SQLAlchemy imports).

Everything that encodes financial meaning — entity kinds, relationship semantics and
scenario input rules — lives here, so future engines (graph analytics in Phase 3,
simulation in Phase 4) can reuse it without depending on the web or database layers.
"""
