"""``python -m app.graph`` — see ``app.graph.cli``."""

import os
import sys

from app.graph.cli import main

try:
    code = main()
except BrokenPipeError:
    # The output was piped into a program that stopped reading (e.g. `| head`).
    os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
    code = 0
raise SystemExit(code)
