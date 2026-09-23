# Providers and data licensing

Which sources RUMIN uses, on what terms, and how to configure them. Licensing notes here
summarise the providers' published terms as reviewed for Phase 2; **they are not legal
advice**. Re-read the provider's terms in full before any commercial use.

> **How the research was done.** The build environment could not open provider websites
> directly (its network policy blocks them), so terms were read from the providers'
> official pages through search results. Every point below that could not be confirmed
> from an official source says so.

## Selected

### World Bank — Indicators API (v2)

| | |
|---|---|
| What | About 16,000 development indicators; RUMIN uses the **World Development Indicators** (WDI, source 2) |
| Access | `https://api.worldbank.org/v2` — no API key, no sign-up |
| Requests RUMIN sends | `GET /country/{ISO3}/indicator/{CODE}?format=json&per_page=1000&page={n}&date={start}:{end}` and `GET /indicator/{CODE}?format=json` (the indicator's definition and original source) |
| Licence | Creative Commons Attribution 4.0 (CC BY 4.0) unless a dataset is labelled otherwise. Some indicators supplied by third parties may carry additional conditions, stated in the indicator's metadata |
| Commercial use | Permitted under CC BY 4.0 with attribution, without implying World Bank endorsement |
| Attribution RUMIN shows | "The World Bank: World Development Indicators. The original source of each series is named on the series." — plus the original source organisation reported by the API, on each series page |
| Rate limit | No numeric limit was found in the official documentation. A third-party page claims about 1,000 requests per hour — **unverified**. RUMIN sends at most one request per second |
| Update cadence | WDI is refreshed several times a year; any value may be revised. The API reports each source's last update date, which RUMIN stores (`provider_last_updated`) |
| Known quirks | Errors can arrive with HTTP 200 as `[{"message": […]}]`; `null` instead of `[]` for no records; some counters sent as strings; recent years are often listed without values |

**Scope (the catalogue, `backend/app/data/series_catalog.json`).** Eleven annual series:
eight for India, with the United States and the United Arab Emirates for context. The
catalogue defines *what to fetch and how to describe it*; it contains no values.

| Series id | Indicator | Country | Unit | Review range | Linked RUMIN variable |
|---|---|---|---|---|---|
| `wb-ind-fp-cpi-totl-zg` | `FP.CPI.TOTL.ZG` | IND | % change on previous year | −50 to 200 | `var_india_cpi_inflation` |
| `wb-ind-pa-nus-fcrf` | `PA.NUS.FCRF` | IND | INR per USD | 1 to 500 | `var_usd_inr` |
| `wb-ind-fr-inr-lend` | `FR.INR.LEND` | IND | % per year | 0 to 50 | — |
| `wb-ind-fr-inr-rinr` | `FR.INR.RINR` | IND | % per year | −50 to 50 | — |
| `wb-ind-ny-gdp-mktp-kd-zg` | `NY.GDP.MKTP.KD.ZG` | IND | % change on previous year | −50 to 50 | — |
| `wb-ind-ny-gdp-mktp-cd` | `NY.GDP.MKTP.CD` | IND | US$ (current prices) | none | — |
| `wb-ind-bn-cab-xoka-gd-zs` | `BN.CAB.XOKA.GD.ZS` | IND | % of GDP | −50 to 50 | — |
| `wb-ind-ne-exp-gnfs-zs` | `NE.EXP.GNFS.ZS` | IND | % of GDP | 0 to 200 | — |
| `wb-usa-fp-cpi-totl-zg` | `FP.CPI.TOTL.ZG` | USA | % change on previous year | −50 to 200 | — |
| `wb-usa-ny-gdp-mktp-kd-zg` | `NY.GDP.MKTP.KD.ZG` | USA | % change on previous year | −50 to 50 | — |
| `wb-are-ny-gdp-mktp-kd-zg` | `NY.GDP.MKTP.KD.ZG` | ARE | % change on previous year | −50 to 50 | — |

Review ranges are **RUMIN's assumptions**, not facts: a value outside them is stored as
reported and flagged for review. Two series link to Phase 1 variables *with the difference
stated*: the World Bank's annual inflation is not the monthly year-on-year CPI the variable
describes, and the annual average exchange rate is not the daily market rate.

### Licensed price files (user-supplied CSV)

| | |
|---|---|
| What | Daily open, high, low, close (and optionally adjusted close and volume) for one instrument per file |
| Access | Files the user already holds; nothing is downloaded |
| Licence | **The user's licence for that file.** The import manifest must state the licence and the attribution it requires; RUMIN stores both with the prices and shows them wherever the prices appear |
| Commercial use | Depends entirely on the user's licence. Exchange data (e.g. NSE, BSE) generally needs a data licence for commercial use; broker exports are usually licensed for personal use |
| RUMIN ships | **No price data at all** |

See [price files](price-files.md) for the file format and the manifest.

## Considered and not selected

| Provider | Why not (now) |
|---|---|
| FRED (Federal Reserve Bank of St. Louis) | The API terms of use (June 2024) prohibit storing or incorporating FRED content in a database, and third-party series need the owner's permission. RUMIN's design stores data, so FRED would need written permission |
| MoSPI eSankhyiki API (India) | The best official source for Indian CPI (monthly), WPI and IIP. Needs sign-up for an access token; licence likely GODL-India (to confirm). **The next provider to add** |
| RBI DBIE | Policy and reference rates; downloads "for research with courtesy" and no official public API |
| Alpha Vantage (free tier) | Free tier is for personal, non-commercial use — RUMIN is a company product |
| NSE / BSE market data | Licensed data products; only through files the user is licensed to use |

## Configuration

All settings are environment variables (see [environment](../environment.md)); none is
secret, because the World Bank needs no key.

| Variable | Default | Purpose |
|---|---|---|
| `RUMIN_WORLDBANK_BASE_URL` | `https://api.worldbank.org/v2` | Base URL. Must be `https://` (plain `http://` only for `localhost`, for test servers) |
| `RUMIN_WORLDBANK_MIN_INTERVAL_SECONDS` | `1.0` | Minimum time between two requests to the World Bank |
| `RUMIN_PROVIDER_TIMEOUT_SECONDS` | `20` | Time allowed for one response |
| `RUMIN_PROVIDER_MAX_ATTEMPTS` | `4` | Attempts per request, including the first (so at most 3 retries) |
| `RUMIN_MAX_IMPORT_FILE_BYTES` | `10485760` | Largest price file accepted (10 MB) |
| `RUMIN_STORE_SOURCE_BODIES` | `true` | Keep the exact bytes of responses and files (gzip-compressed) |

Outbound requests honour the standard `HTTPS_PROXY` variable.

### Adding a provider that needs a key (e.g. MoSPI)

Keys belong in the environment (`RUMIN_<PROVIDER>_API_KEY`, read by `Settings`), never in
code, the catalogue, the database or the frontend. The HTTP layer already redacts
credential-like query parameters (`api_key`, `key`, `token`, …) from every logged or stored
URL, and `AuthenticationError` covers refused credentials. A keyed provider should refuse to
start with a clear message when its key is missing — no keyed provider exists yet, so that
check has not been written.

## Adding a provider — checklist

1. Read the provider's documentation and terms in full; record licence, commercial use,
   attribution and rate limits in a `ProviderProfile` (next to the adapter).
2. Implement only the capabilities the provider has (`EconomicSeriesSource`, …); validate
   everything that goes into a URL; parse numbers as `Decimal`.
3. Add it to `app/ingestion/registry.py` and its datasets/series to the catalogue.
4. Write provider tests with scripted responses (success, malformed, rate limit,
   authentication, empty) — never live calls in automated tests.
5. Document it here.
