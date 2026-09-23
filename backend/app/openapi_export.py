"""Write the OpenAPI document to ``docs/api/openapi.json`` (the committed API contract).

    python -m app.openapi_export          # regenerate the snapshot
    python -m app.openapi_export --check  # exit 1 if the snapshot is out of date

The frontend generates its TypeScript API types from this file, and a backend test fails
when the snapshot no longer matches the code, so contract changes are always reviewed.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from app.core.config import REPO_ROOT, Settings
from app.main import create_app

SNAPSHOT_PATH = REPO_ROOT / "docs" / "api" / "openapi.json"


def build_openapi() -> dict[str, Any]:
    settings = Settings(_env_file=None, database_url="sqlite://", docs_enabled=True)
    return create_app(settings).openapi()


def render(document: dict[str, Any]) -> str:
    return json.dumps(document, indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Only verify the snapshot.")
    args = parser.parse_args(argv)

    rendered = render(build_openapi())
    if args.check:
        current = SNAPSHOT_PATH.read_text(encoding="utf-8") if SNAPSHOT_PATH.exists() else ""
        if current != rendered:
            print(f"✗ {SNAPSHOT_PATH} is out of date. Run: python -m app.openapi_export")
            return 1
        print(f"✓ {SNAPSHOT_PATH.name} is up to date.")
        return 0

    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_PATH.write_text(rendered, encoding="utf-8")
    print(f"✓ Wrote {SNAPSHOT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
