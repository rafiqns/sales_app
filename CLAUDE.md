# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

"Dua Kelinci Sales Pulse" — a zero-dependency sales-analytics dashboard. It cleans a messy ERP sales CSV, visualizes sales by region/brand/outlet, flags the 5 weakest outlets (or sharpest month-over-month drops) with diagnostic reasons, and generates a one-paragraph Telegram digest for a sales manager. It is deliberately **standard-library Python + vanilla HTML/CSS/JS only** — no `pip install`, no database, no build step, no API key required to run.

## Commands

Requires **Python 3.10+** (CI uses 3.12). No dependencies, no lint step, no build step.

```bash
# Run the server (Linux/macOS: python3; Windows: python)
python3 app.py            # serves at http://127.0.0.1:8000

# Run the full test suite
python3 -m unittest test_analytics.py -v

# Run a single test
python3 -m unittest test_analytics.TestSalesAnalytics.test_data_cleaning_catches_all_traps

# Docker (optional)
docker build -t dk-sales-pulse .
docker run -p 8000:8000 dk-sales-pulse
```

GitHub Actions (`.github/workflows/test.yml`) runs `python3 -m unittest test_analytics.py -v` on every push/PR.

## Architecture

Two Python modules with a strict split, plus a static frontend:

- **`analytics.py`** — all business logic, with **no web/HTTP dependency**. This is the module the tests import. Contains data cleaning, metric computation, IDR/locale formatting, and Telegram summary generation.
- **`app.py`** — a thin HTTP layer using only the stdlib `http.server` (`ThreadingHTTPServer`). Maps URL routes to `analytics` functions and serves `static/`.
- **`static/`** — `index.html`, `app.js`, `style.css`. No framework; `app.js` holds all UI state in a single `state` object and re-fetches on every interaction.

### Data flow

1. On startup, `app.py` creates a module-level singleton `STATE = AppState(DEFAULT_CSV)`. `AppState` calls `load_and_clean_csv` and holds the cleaned rows (`list[dict]`) plus the `audit` dict. Upload/reset mutate this singleton in memory — there is no persistence.
2. `load_and_clean_csv(csv_text)` (the single entry point for parsing) does, in order: strip BOM → exact-duplicate removal → whitespace trim → region canonicalization via `REGION_ALIASES` → blank salesman → `Unassigned` → numeric coercion of the `*_idr`/`qty` fields to `int` → return detection (`qty < 0` or invoice prefix `RTR`) → derive `month` (`date[:7]`) and `is_return`. It returns `(rows, audit)`.
3. `compute_dashboard(rows, audit, month, region, brand, lang, outlet_mode)` returns **one large dict** containing everything the frontend renders: `filters`, `comparison`, `kpis`, `by_region`, `by_brand`, `region_brand_matrix`, `weakest_outlets`, `sharpest_drops`, `audit`, and an embedded `telegram_summary`. Any change to the dashboard payload is driven by this single return shape.
4. `build_telegram_summary` is **deterministic first**: all numbers are computed in Python, then optionally polished by an LLM (`_try_llm_summary`) only if an API key env var is set — the LLM rewrites phrasing but must not change figures. The same deterministic path is embedded in `compute_dashboard` and exposed again via `POST /api/summary` (with `use_llm`).

### API surface (all in `app.py`)

- `GET /api/dashboard` — full dashboard dict (query: `month`, `region`, `brand`, `lang`, `outlet_mode`).
- `GET /api/transactions` — filtered/searched/sorted/paginated raw rows (`query_transactions` in `analytics.py`).
- `POST /api/summary` — regenerate the Telegram summary, optionally `use_llm`.
- `POST /api/upload` / `POST /api/reset` — replace or restore `STATE`.
- `POST /api/send-telegram` — push the summary via the Telegram Bot API.

### Optional integrations (zero-config by default)

Buttons appear only when the corresponding env vars are set. All gated in code, no feature flags needed:

- `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` → "Send to Telegram" button.
- `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` → "Polish with AI" button (defaults: `ANTHROPIC_MODEL`=`claude-sonnet-4-20250514`, `OPENAI_MODEL`=`gpt-4o-mini`).

## Data schema

`sales.csv` is the default dataset (~1,891 raw rows). Header (16 columns, comma-separated):

```
date,invoice_no,region,branch,outlet_id,outlet_name,outlet_type,salesman,brand,sku,qty_carton,price_per_carton_idr,gross_sales_idr,discount_idr,net_sales_idr
```

Cleaning adds two derived fields on every row: `month` (`YYYY-MM`) and `is_return` (`bool`). Money fields are coerced to `int`.

## Conventions that matter

- **Outlets are grouped strictly by `outlet_id`, never by `outlet_name`** — same-name outlets exist across regions (e.g. `Toko Sinar Abadi` is 3 distinct outlets). Grouping by name would corrupt the weakest-outlet ranking.
- **Indonesian currency formatting is locale-specific**: in `id` mode, `M` = *Miliar* (billion), `jt` = *Juta* (million), `rb` = thousand, with `,` as the decimal separator (`Rp 1,73 M`). English mode uses `B`/`M`/`K` with `.` (`Rp 1.73B`). `format_idr` (Python) and `fmtIDR` (JS) must stay in sync — a `test_indonesian_and_english_currency_formatting` test pins this.
- **Returns are preserved in net sales, not dropped** (invoice prefix `RTR` or negative quantity), so totals reflect net revenue.
- **The tests assert exact expected values** against `sales.csv` (e.g. `clean_rows == 1888`, exact weakest-outlet IDs, exact currency strings). If you change cleaning logic or ranking, `test_analytics.py` will tell you precisely what shifted — update both the code and the expectation intentionally, not by loosening assertions.
