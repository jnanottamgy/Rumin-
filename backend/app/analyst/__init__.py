"""The AI Analyst (Phase 7).

Answers questions from RUMIN's own records through a fixed set of tools, and cites the
record behind every figure. A router reads the question; a planner (or, when one is
configured, a language model) calls the tools; the answer is built from the evidence those
calls returned and checked against it before anyone sees it. See ``docs/analyst/``.
"""

ANALYST_VERSION = "1.0.0"
