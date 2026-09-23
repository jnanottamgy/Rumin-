"""Licensed price files — daily prices for one instrument, from a CSV the user supplies.

RUMIN ships no price data. A user who is licensed to use an end-of-day price file (for
example a broker export, or data under an exchange data licence) imports it together with
a manifest that states where it came from and under what licence (see
``app.ingestion.prices``). This module only reads the file; validation, quality rules and
persistence happen in the pipeline like for any other provider.

File format (RUMIN's template; UTF-8, comma-separated, one header row):

    date,open,high,low,close,adjusted_close,volume

``date`` is ISO 8601 (YYYY-MM-DD). Prices are plain decimals with a dot and no thousands
separators or currency symbols. ``adjusted_close`` and ``volume`` are optional columns.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from app.db.base import utcnow
from app.domain.enums import CaptureKind, ProviderAuth, ProviderKind
from app.ingestion.errors import ImportFileError
from app.ingestion.providers.base import Capture, PriceFileRead, ProviderProfile, RawPriceRow

REQUIRED_COLUMNS = ("date", "open", "high", "low", "close")
OPTIONAL_COLUMNS = ("adjusted_close", "volume")

PROFILE = ProviderProfile(
    id="price-file",
    name="Licensed price file (CSV import)",
    kind=ProviderKind.FILE,
    description=(
        "End-of-day prices for one listed instrument per file, supplied by the user from a "
        "source they are licensed to use. RUMIN ships no price data."
    ),
    authentication=ProviderAuth.NOT_APPLICABLE,
    data_categories=(
        "Daily open, high, low and close prices, with optional adjusted close and volume."
    ),
    coverage="Whatever the user imports: one instrument per file, any exchange.",
    update_frequency="When the user imports a new file. Nothing is refreshed automatically.",
    rate_limit_policy="Not applicable (local files). Files larger than the configured limit "
    "(10 MB by default) are refused.",
    licensing=(
        "Set by the user's licence for each file. The import manifest must state the licence "
        "and the required attribution; RUMIN stores both with the prices and shows them "
        "wherever the prices are shown."
    ),
    commercial_use=(
        "Depends entirely on the user's licence. Exchange data (e.g. NSE, BSE) generally "
        "needs a data licence for commercial use; broker exports are usually for personal use."
    ),
    reliability=(
        "As reliable as the file's source. RUMIN checks structure and price consistency, but "
        "cannot confirm values against the market."
    ),
    known_limitations=(
        "One instrument and one currency per file; daily prices only; ISO dates only; no "
        "thousands separators; RUMIN never adjusts prices for corporate actions."
    ),
)


class PriceFileProvider:
    profile = PROFILE

    def __init__(self, *, max_bytes: int, clock: Callable[[], datetime] = utcnow) -> None:
        self.max_bytes = max_bytes
        self.clock = clock

    def read_price_file(self, path: Path) -> PriceFileRead:
        try:
            size = path.stat().st_size
        except OSError as error:
            raise ImportFileError(f"The file {path.name} cannot be read.") from error
        if size > self.max_bytes:
            raise ImportFileError(
                f"The file is {size:,} bytes; the limit is {self.max_bytes:,} bytes."
            )
        body = path.read_bytes()
        try:
            text = body.decode("utf-8-sig")  # tolerate a byte-order mark
        except UnicodeDecodeError as error:
            raise ImportFileError("The file is not valid UTF-8 text.") from error

        reader = csv.reader(io.StringIO(text, newline=""))
        try:
            header = next(reader)
        except StopIteration as error:
            raise ImportFileError("The file is empty; a header row is required.") from error
        columns = [name.strip().lower() for name in header]
        self._check_columns(columns)

        rows: list[RawPriceRow] = []
        for line, cells in enumerate(reader, start=2):
            if not any(cell.strip() for cell in cells):
                continue  # blank line
            if len(cells) != len(columns):
                raise ImportFileError(
                    f"Line {line} has {len(cells)} cells; the header has {len(columns)}."
                )
            rows.append(
                RawPriceRow(
                    line=line,
                    fields={name: cell.strip() for name, cell in zip(columns, cells, strict=True)},
                )
            )

        capture = Capture(
            kind=CaptureKind.FILE,
            locator=path.name,  # the name only: full paths can reveal local user names
            body=body,
            received_at=self.clock(),
            content_type="text/csv",
        )
        return PriceFileRead(rows=rows, captures=[capture], columns=columns)

    @staticmethod
    def _check_columns(columns: list[str]) -> None:
        if len(set(columns)) != len(columns):
            raise ImportFileError("The header repeats a column name.")
        missing = [name for name in REQUIRED_COLUMNS if name not in columns]
        if missing:
            raise ImportFileError(f"Required columns are missing: {', '.join(missing)}.")
        unknown = [name for name in columns if name not in REQUIRED_COLUMNS + OPTIONAL_COLUMNS]
        if unknown:
            raise ImportFileError(
                f"Unknown columns: {', '.join(unknown)}. Expected: "
                f"{', '.join(REQUIRED_COLUMNS + OPTIONAL_COLUMNS)}."
            )
