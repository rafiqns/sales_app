# Dua Kelinci Sales Pulse (AI Builder Build Test)

A lightweight, zero-dependency web app that cleans messy sales CSV exports, visualizes **sales by region and brand**, flags the **5 weakest outlets** with diagnostic reasons, and writes a **one-paragraph Telegram digest** ready for a sales manager to read on their phone.

## How to Run

Requires **Python 3.10+** (standard library only — no `pip install`, database, or API key required).

```bash
# macOS (Mac mini) / Linux
python3 app.py

# Windows
python app.py
```

Open **http://127.0.0.1:8000** in your browser.

### Optional: Run with Docker
```bash
docker build -t dk-sales-pulse .
docker run -p 8000:8000 dk-sales-pulse
```

### Run Automated Tests
```bash
python3 -m unittest test_analytics.py -v
```

---

## Optional Integrations (Zero-Config by Default)

The app works 100% offline out of the box. Additional buttons unlock automatically if you provide environment variables:

```bash
# Optional: Send the digest directly to Telegram
TELEGRAM_BOT_TOKEN=123456:ABC... TELEGRAM_CHAT_ID=-100123456789 python3 app.py

# Optional: Polish the grounded digest with Claude or OpenAI
ANTHROPIC_API_KEY=sk-ant-... python3 app.py
# or OPENAI_API_KEY=sk-... python3 app.py
```

---

## Data Quality Issues Caught in `sales.csv`

Auditing the 1,891 raw invoice lines surfaced 5 real-world ERP export issues handled automatically by `analytics.py` and surfaced in the UI:

1. **Inconsistent region labels (10 rows):** `Jabar` (4), `JAWA BARAT` (4), `JABODETABEK` (1), and `JAWA TIMUR` (1) normalized into 6 canonical regions.
2. **Exact duplicate lines (3 rows):** Deduplicated (`INV500201`, `INV500386`, `INV500791`) to avoid double-counting revenue (1,888 clean lines).
3. **Trailing spaces & same-name outlets (4 rows):** Trimmed whitespace and grouped strictly by `outlet_id` rather than `outlet_name` (`Toko Sinar Abadi` appears as 3 distinct outlets across Jakarta Barat, Medan, and Jabodetabek; `Toko Anugerah` appears twice). Grouping by name would corrupt the 5 weakest outlets ranking.
4. **Product return / credit note (1 row):** `RTR900001` (`-2` cartons, `-Rp 528.000` at `OUT1049`) preserved in net sales rather than dropped.
5. **Missing salesman values (5 rows):** Labeled as `Unassigned` so no revenue is silently excluded.

---

## Key Product & Engineering Decisions

- **Indonesian currency conventions (`Rp 1,73 M` / `Rp 495,8 jt`):** Indonesian sales managers read `M` as *Miliar* (billion), not million. Default mode is Bahasa Indonesia (`ID`) with `M`/`jt`/`rb` formatting, plus a 1-click toggle to English (`B`/`M`/`K`).
- **Diagnostic flagging for weakest outlets:** Ranking solely by lowest net sales flags small *warung* naturally. Each flagged outlet shows *why* it was flagged (e.g., `% of peer outlet-type average`, `sharp MoM drop`, `days inactive`, `low order frequency`), plus a **Sharpest MoM Drop** tab (synced with the Telegram digest) to catch larger accounts that are churning (e.g., `OUT1043 Minimarket Sido Muncul -68.7%`).
- **Dynamic multi-month support & transaction drill-down:** Period labels and MoM comparisons automatically adapt to any uploaded CSV (1 month, 2 months, or 12+ months), and managers can drill into raw transactions via the paginated table (date-range filter, search, and column sorting).
- **Deterministic grounding before LLM polish:** All numbers in the Telegram digest are computed deterministically in Python so the summary never hallucinates figures, even if an optional LLM key is enabled to polish phrasing.
- **Zero-dependency footprint:** Kept to Python's standard library + vanilla HTML/CSS/JS so any reviewer on a Mac mini, Linux, or Windows machine can run and inspect every line in seconds.

---

## Path to Production (Dua Kelinci Context)

If brought into production for Dua Kelinci's sales, marketing, and operations teams:
- **Automated Ingestion:** Scheduled job pulling daily QAD ERP / Excel exports into PostgreSQL with schema validation and anomaly alerts (duplicates, unmapped regions, negative spikes).
- **Role-Based Access & Per-Manager Digests:** Filter dashboards by region/branch/brand and dispatch personalized 06:00 AM digests to each Head of Region or Brand Manager via Microsoft Teams or Telegram.
- **Observability:** Structured run logs, delivery failure alerts, and audit trails for every digest sent.
