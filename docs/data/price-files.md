# Importing licensed price files

RUMIN ships no price data and connects to no market feed. If you hold daily prices you
are **licensed to use** — a broker export, or data under an exchange data licence — you
can import them with a manifest that states where they came from.

> **Your responsibility.** RUMIN records the licence and attribution you declare and shows
> them with the prices, but cannot verify them. Exchange data (e.g. NSE, BSE) generally
> needs a data licence for commercial use; broker exports are usually licensed for
> personal use. Import only what your licence allows.

## 1. The price file (CSV)

UTF-8 (a byte-order mark is tolerated), comma-separated, one header row, one instrument
and one currency per file:

```csv
date,open,high,low,close,adjusted_close,volume
2025-03-03,100.00,101.50,99.50,101.00,,1200
2025-03-04,101.00,102.25,100.75,102.00,,1350
```

| Column | Required | Format |
|---|---|---|
| `date` | yes | ISO `YYYY-MM-DD` |
| `open`, `high`, `low`, `close` | yes | Plain decimals with a dot: no thousands separators, currency symbols or exponents |
| `adjusted_close` | no | Only if your source supplies it — RUMIN never computes adjustments |
| `volume` | no | A whole, non-negative number |

Unknown or repeated columns, a missing required column, or a row with the wrong number of
cells make the whole file invalid (the job fails with `invalid_file`). Individual bad rows
are rejected with a reason and kept as issues; the rest of the file is imported. The size
limit is 10 MB (`RUMIN_MAX_IMPORT_FILE_BYTES`).

## 2. The manifest (JSON)

Print a blank one with `python -m app.ingestion manifest-template`, then fill it in:

```json
{
  "dataset": {
    "id": "broker-eod-reliance",
    "name": "End-of-day prices — broker export",
    "description": "Daily prices exported from our broker's terminal.",
    "license": "Broker terminal licence — internal use only",
    "license_url": null,
    "terms_url": null,
    "homepage_url": null,
    "attribution": "Source: <broker name>",
    "provenance_note": "Exported by <person> on 2026-09-01.",
    "is_illustrative": false
  },
  "instrument": {
    "id": "xnse-reliance",
    "name": "Reliance Industries Ltd",
    "instrument_type": "equity",
    "isin": "INE002A01018",
    "exchange_mic": "XNSE",
    "symbol": "RELIANCE",
    "currency": "INR",
    "country_id": "cty_in"
  },
  "adjustment": "unadjusted"
}
```

| Field | Rules |
|---|---|
| `dataset.id` | Lowercase letters, digits and hyphens; one dataset per source of prices. Must not be an existing curated or World Bank dataset |
| `dataset.license`, `attribution`, `provenance_note` | Required: they are shown wherever the prices are shown |
| `*_url` | Optional; `https://` only |
| `dataset.is_illustrative` | `true` for sample or test files: the prices are then labelled "Sample data — not real" everywhere |
| `instrument.id` | Lowercase letters, digits and hyphens, e.g. `xnse-reliance` |
| `instrument.instrument_type` | `equity`, `etf` or `index` |
| `instrument.isin` | Optional; checked against its check digit |
| `instrument.exchange_mic` | ISO 10383 code: `XNSE` (NSE), `XBOM` (BSE), … |
| `instrument.symbol` | The ticker on that exchange |
| `instrument.currency` | ISO 4217 code; one currency per instrument, never converted |
| `instrument.country_id` | Optional link to a Phase 1 country (`cty_in`); reported if not found |
| `adjustment` | `unadjusted` (as traded) or `adjusted` (as supplied by your source) |

Unknown fields are rejected, so a misspelt field name cannot be silently ignored.

## 3. Import

```bash
cd backend
python -m app.ingestion import-prices --manifest manifest.json --file prices.csv
```

The command prints the job: rows received, new, revised, unchanged and rejected, and the
attribution. The prices then appear in the Data Explorer under *Instruments and prices*.

## What RUMIN refuses

- A manifest whose instrument conflicts with a stored one: same id with a different
  exchange or symbol, an exchange and symbol (or ISIN) that belong to another instrument,
  or a different currency. Identifiers are never merged.
- Mixing adjusted and unadjusted prices in one dataset for an instrument: use a separate
  dataset.
- Blending sources: prices from different datasets are kept and shown apart; the API
  requires a `dataset_id` when an instrument has more than one.

## Re-importing

Importing the same file again changes nothing but "last seen". A corrected file creates a
new revision for each changed day; the previous prices are kept and marked superseded.
Days missing from a new file are not deleted.
