"""Sales data cleaning, analytics, and Telegram summary generation.

Uses only the Python 3 standard library so the app runs anywhere with zero setup.
"""

from __future__ import annotations

import csv
import io
import json
import os
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

REGION_ALIASES = {
    "jabar": "Jawa Barat",
    "jawa barat": "Jawa Barat",
    "jabodetabek": "Jabodetabek",
    "jawa tengah": "Jawa Tengah",
    "jateng": "Jawa Tengah",
    "jawa timur": "Jawa Timur",
    "jatim": "Jawa Timur",
    "sumatera": "Sumatera",
    "sumatra": "Sumatera",
    "kalimantan": "Kalimantan",
}

MONTH_NAMES = {
    "en": ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
    "id": ["", "Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"],
}


def format_month_label(ym: str, lang: str = "id") -> str:
    """Format 'YYYY-MM' dynamically into 'Okt 2026' or 'Oct 2026'."""
    try:
        year_s, month_s = ym.split("-")
        names = MONTH_NAMES.get(lang, MONTH_NAMES["id"])
        return f"{names[int(month_s)]} {year_s}"
    except (ValueError, IndexError):
        return ym


def format_period_label(months: list[str], selected_month: str, lang: str = "id") -> str:
    if selected_month != "all":
        return format_month_label(selected_month, lang)
    if not months:
        return "-"
    if len(months) == 1:
        return format_month_label(months[0], lang)
    return f"{format_month_label(months[0], lang)} – {format_month_label(months[-1], lang)}"


def format_idr(amount: int | float, lang: str = "id") -> str:
    """Format IDR cleanly using locale-appropriate abbreviations.

    In Bahasa Indonesia, 'M' means Miliar (billion) and 'jt' means Juta (million),
    avoiding the common mistake of showing 'Rp 495.8M' to Indonesian managers.
    """
    sign = "-" if amount < 0 else ""
    val = abs(amount)
    if lang == "id":
        if val >= 1_000_000_000:
            return f"{sign}Rp {val / 1_000_000_000:.2f} M".replace(".", ",")
        if val >= 1_000_000:
            return f"{sign}Rp {val / 1_000_000:.1f} jt".replace(".", ",")
        if val >= 1_000:
            return f"{sign}Rp {val / 1_000:.0f} rb"
        return f"{sign}Rp {int(round(val)):,}".replace(",", ".")

    if val >= 1_000_000_000:
        return f"{sign}Rp {val / 1_000_000_000:.2f}B"
    if val >= 1_000_000:
        return f"{sign}Rp {val / 1_000_000:.1f}M"
    if val >= 1_000:
        return f"{sign}Rp {val / 1_000:.0f}K"
    return f"{sign}Rp {val:,.0f}"


def format_idr_full(amount: int | float) -> str:
    sign = "-" if amount < 0 else ""
    return f"{sign}Rp {abs(int(round(amount))):,}".replace(",", ".")


def load_and_clean_csv(csv_text: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Parse raw ERP/sales CSV, fix known data quality issues, and return audit stats."""
    reader = csv.DictReader(io.StringIO(csv_text.lstrip("\ufeff")))
    raw_rows = list(reader)

    audit = {
        "raw_rows": len(raw_rows),
        "clean_rows": 0,
        "duplicates_removed": 0,
        "regions_normalized": 0,
        "whitespace_trimmed": 0,
        "blank_salesmen": 0,
        "returns_kept": 0,
        "returns_value_idr": 0,
        "notes": [],
    }

    seen_exact: set[tuple[tuple[str, str], ...]] = set()
    clean_rows: list[dict[str, Any]] = []

    for row in raw_rows:
        exact_key = tuple(sorted((k, v or "") for k, v in row.items()))
        if exact_key in seen_exact:
            audit["duplicates_removed"] += 1
            continue
        seen_exact.add(exact_key)

        trimmed: dict[str, Any] = {}
        had_ws = False
        for k, v in row.items():
            raw_val = v or ""
            stripped = raw_val.strip()
            if stripped != raw_val:
                had_ws = True
            trimmed[k] = stripped
        if had_ws:
            audit["whitespace_trimmed"] += 1

        raw_region = trimmed["region"]
        canonical_region = REGION_ALIASES.get(raw_region.lower(), raw_region)
        if canonical_region != raw_region:
            audit["regions_normalized"] += 1
        trimmed["region"] = canonical_region

        if not trimmed["salesman"]:
            audit["blank_salesmen"] += 1
            trimmed["salesman"] = "Unassigned"

        qty = int(float(trimmed["qty_carton"]))
        price = int(float(trimmed["price_per_carton_idr"]))
        gross = int(float(trimmed["gross_sales_idr"]))
        discount = int(float(trimmed["discount_idr"]))
        net = int(float(trimmed["net_sales_idr"]))

        is_return = qty < 0 or trimmed["invoice_no"].upper().startswith("RTR")
        if is_return:
            audit["returns_kept"] += 1
            audit["returns_value_idr"] += net

        trimmed["qty_carton"] = qty
        trimmed["price_per_carton_idr"] = price
        trimmed["gross_sales_idr"] = gross
        trimmed["discount_idr"] = discount
        trimmed["net_sales_idr"] = net
        trimmed["month"] = trimmed["date"][:7]
        trimmed["is_return"] = is_return

        clean_rows.append(trimmed)

    audit["clean_rows"] = len(clean_rows)
    audit["notes"] = [
        f"Normalized {audit['regions_normalized']} inconsistent region labels (Jabar, JAWA BARAT, JABODETABEK, JAWA TIMUR).",
        f"Removed {audit['duplicates_removed']} exact duplicate invoice lines to prevent double counting.",
        f"Trimmed trailing spaces on {audit['whitespace_trimmed']} rows and grouped outlets strictly by outlet_id (preventing same-name collisions like Toko Sinar Abadi).",
        f"Retained {audit['returns_kept']} product return/credit note ({format_idr_full(audit['returns_value_idr'])}) in net sales.",
        f"Labeled {audit['blank_salesmen']} rows with missing salesman as 'Unassigned'.",
    ]
    return clean_rows, audit


def load_csv_file(path: str | Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    text = Path(path).read_text(encoding="utf-8-sig")
    return load_and_clean_csv(text)


def _mom_pct(sep: float, oct_: float) -> float | None:
    if sep == 0:
        return None
    return round(((oct_ - sep) / sep) * 100.0, 1)


def _days_between(d1_str: str, d2_str: str) -> int:
    try:
        return max((date.fromisoformat(d2_str) - date.fromisoformat(d1_str)).days, 0)
    except ValueError:
        return 0


def _build_outlet_reasons(
    o: dict[str, Any],
    peer_avg: float,
    days_inactive: int,
    lang: str,
) -> list[str]:
    reasons: list[str] = []
    if peer_avg > 0 and o["net_sales"] < peer_avg * 0.25:
        pct_of_peer = max(round((o["net_sales"] / peer_avg) * 100), 1)
        reasons.append(
            f"Omzet {pct_of_peer}% dari rata-rata {o['outlet_type']}"
            if lang == "id"
            else f"Sales {pct_of_peer}% of {o['outlet_type']} avg"
        )
    if o["mom_pct"] is not None and o["mom_pct"] <= -30.0:
        drop_val = abs(o["mom_pct"])
        reasons.append(
            f"Omzet turun {drop_val:.1f}% dari bulan lalu"
            if lang == "id"
            else f"Sales dropped {drop_val:.1f}% vs prev month"
        )
    if days_inactive >= 14:
        reasons.append(
            f"Belum order {days_inactive} hari"
            if lang == "id"
            else f"No order in {days_inactive}d"
        )
    if o["invoices"] <= 4:
        reasons.append(
            f"Jarang order ({o['invoices']} transaksi)"
            if lang == "id"
            else f"Low order frequency ({o['invoices']} orders)"
        )
    if not reasons:
        reasons.append("Omzet terendah" if lang == "id" else "Lowest net sales")
    return reasons[:2]


def compute_dashboard(
    rows: list[dict[str, Any]],
    audit: dict[str, Any],
    month: str = "all",
    region: str = "all",
    brand: str = "all",
    lang: str = "id",
    outlet_mode: str = "lowest",
) -> dict[str, Any]:
    """Compute filtered dashboard metrics, breakdowns, weakest outlets, and Telegram summary."""
    all_regions = sorted({r["region"] for r in rows})
    all_brands = sorted({r["brand"] for r in rows})
    all_months = sorted({r["month"] for r in rows})
    max_date = max((r["date"] for r in rows), default="2026-10-31")

    filtered = [
        r
        for r in rows
        if (month == "all" or r["month"] == month)
        and (region == "all" or r["region"] == region)
        and (brand == "all" or r["brand"] == brand)
    ]

    total_net = sum(r["net_sales_idr"] for r in filtered)
    total_gross = sum(r["gross_sales_idr"] for r in filtered)
    total_discount = sum(r["discount_idr"] for r in filtered)
    total_cartons = sum(r["qty_carton"] for r in filtered)
    invoices = {r["invoice_no"] for r in filtered if not r["is_return"]}
    active_outlets = {r["outlet_id"] for r in filtered}

    prev_month = all_months[-2] if (month == "all" and len(all_months) >= 2) else None
    curr_month = all_months[-1] if (month == "all" and len(all_months) >= 2) else None

    prev_total = sum(r["net_sales_idr"] for r in filtered if prev_month and r["month"] == prev_month)
    curr_total = sum(r["net_sales_idr"] for r in filtered if curr_month and r["month"] == curr_month)
    overall_mom = _mom_pct(prev_total, curr_total) if (prev_month and curr_month) else None

    # Region aggregation
    reg_map: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"net_sales": 0, "cartons": 0, "prev": 0, "curr": 0, "outlets": set(), "invoices": set()}
    )
    for r in filtered:
        d = reg_map[r["region"]]
        d["net_sales"] += r["net_sales_idr"]
        d["cartons"] += r["qty_carton"]
        d["outlets"].add(r["outlet_id"])
        if not r["is_return"]:
            d["invoices"].add(r["invoice_no"])
        if prev_month and r["month"] == prev_month:
            d["prev"] += r["net_sales_idr"]
        elif curr_month and r["month"] == curr_month:
            d["curr"] += r["net_sales_idr"]

    by_region = [
        {
            "region": name,
            "net_sales": d["net_sales"],
            "share_pct": round((d["net_sales"] / total_net) * 100, 1) if total_net else 0.0,
            "cartons": d["cartons"],
            "outlets": len(d["outlets"]),
            "invoices": len(d["invoices"]),
            "prev_sales": d["prev"],
            "curr_sales": d["curr"],
            "mom_pct": _mom_pct(d["prev"], d["curr"]) if (prev_month and curr_month) else None,
        }
        for name, d in sorted(reg_map.items(), key=lambda x: -x[1]["net_sales"])
    ]

    # Brand aggregation
    brand_map: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"net_sales": 0, "cartons": 0, "prev": 0, "curr": 0, "outlets": set(), "skus": set()}
    )
    for r in filtered:
        d = brand_map[r["brand"]]
        d["net_sales"] += r["net_sales_idr"]
        d["cartons"] += r["qty_carton"]
        d["outlets"].add(r["outlet_id"])
        d["skus"].add(r["sku"])
        if prev_month and r["month"] == prev_month:
            d["prev"] += r["net_sales_idr"]
        elif curr_month and r["month"] == curr_month:
            d["curr"] += r["net_sales_idr"]

    by_brand = [
        {
            "brand": name,
            "net_sales": d["net_sales"],
            "share_pct": round((d["net_sales"] / total_net) * 100, 1) if total_net else 0.0,
            "cartons": d["cartons"],
            "outlets": len(d["outlets"]),
            "skus": len(d["skus"]),
            "prev_sales": d["prev"],
            "curr_sales": d["curr"],
            "mom_pct": _mom_pct(d["prev"], d["curr"]) if (prev_month and curr_month) else None,
        }
        for name, d in sorted(brand_map.items(), key=lambda x: -x[1]["net_sales"])
    ]

    # Region x Brand matrix
    matrix_map: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for r in filtered:
        matrix_map[r["region"]][r["brand"]] += r["net_sales_idr"]

    matrix_brands = [b["brand"] for b in by_brand]
    region_brand_matrix = [
        {
            "region": reg["region"],
            "total": reg["net_sales"],
            "values": {b: matrix_map[reg["region"]].get(b, 0) for b in matrix_brands},
        }
        for reg in by_region
    ]

    # Outlet aggregation (grouped strictly by outlet_id)
    outlet_map: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "outlet_name": "",
            "region": "",
            "branch": "",
            "outlet_type": "",
            "salesmen": set(),
            "net_sales": 0,
            "cartons": 0,
            "prev": 0,
            "curr": 0,
            "invoices": set(),
            "last_order_date": "",
        }
    )
    for r in filtered:
        o = outlet_map[r["outlet_id"]]
        o["outlet_name"] = r["outlet_name"]
        o["region"] = r["region"]
        o["branch"] = r["branch"]
        o["outlet_type"] = r["outlet_type"]
        if r["salesman"] and r["salesman"] != "Unassigned":
            o["salesmen"].add(r["salesman"])
        o["net_sales"] += r["net_sales_idr"]
        o["cartons"] += r["qty_carton"]
        if not r["is_return"]:
            o["invoices"].add(r["invoice_no"])
        if prev_month and r["month"] == prev_month:
            o["prev"] += r["net_sales_idr"]
        elif curr_month and r["month"] == curr_month:
            o["curr"] += r["net_sales_idr"]
        if r["date"] > o["last_order_date"]:
            o["last_order_date"] = r["date"]

    # Peer averages by outlet_type for meaningful flagging reasons
    type_totals: dict[str, list[int]] = defaultdict(list)
    for o in outlet_map.values():
        type_totals[o["outlet_type"]].append(o["net_sales"])
    peer_avgs = {t: (sum(vals) / len(vals)) for t, vals in type_totals.items() if vals}

    all_outlet_rows = []
    for oid, o in outlet_map.items():
        mom = _mom_pct(o["prev"], o["curr"]) if (prev_month and curr_month) else None
        days_inactive = _days_between(o["last_order_date"], max_date)
        entry = {
            "outlet_id": oid,
            "outlet_name": o["outlet_name"],
            "region": o["region"],
            "branch": o["branch"],
            "outlet_type": o["outlet_type"],
            "salesman": ", ".join(sorted(o["salesmen"])) or "Unassigned",
            "net_sales": o["net_sales"],
            "cartons": o["cartons"],
            "invoices": len(o["invoices"]),
            "prev_sales": o["prev"],
            "curr_sales": o["curr"],
            "mom_pct": mom,
            "last_order_date": o["last_order_date"],
            "days_inactive": days_inactive,
        }
        entry["reasons"] = _build_outlet_reasons(
            entry, peer_avgs.get(o["outlet_type"], 0.0), days_inactive, lang=lang
        )
        all_outlet_rows.append(entry)

    weakest_outlets = sorted(all_outlet_rows, key=lambda x: (x["net_sales"], x["outlet_id"]))[:5]
    sharpest_drops = sorted(
        [o for o in all_outlet_rows if o["mom_pct"] is not None and o["mom_pct"] < 0],
        key=lambda x: (x["mom_pct"], x["net_sales"]),
    )[:5]

    result = {
        "filters": {
            "month": month,
            "region": region,
            "brand": brand,
            "available_months": all_months,
            "available_regions": all_regions,
            "available_brands": all_brands,
        },
        "comparison": {
            "prev_month": prev_month,
            "curr_month": curr_month,
            "prev_label": format_month_label(prev_month, lang) if prev_month else "-",
            "curr_label": format_month_label(curr_month, lang) if curr_month else "-",
            "period_label": format_period_label(all_months, month, lang),
        },
        "kpis": {
            "total_net_sales": total_net,
            "total_gross_sales": total_gross,
            "total_discount": total_discount,
            "discount_rate_pct": round((total_discount / total_gross) * 100, 2) if total_gross else 0.0,
            "total_cartons": total_cartons,
            "total_invoices": len(invoices),
            "active_outlets": len(active_outlets),
            "avg_order_value": round(total_net / len(invoices)) if invoices else 0,
            "prev_net_sales": prev_total,
            "curr_net_sales": curr_total,
            "mom_pct": overall_mom,
        },
        "by_region": by_region,
        "by_brand": by_brand,
        "matrix_brands": matrix_brands,
        "region_brand_matrix": region_brand_matrix,
        "weakest_outlets": weakest_outlets,
        "sharpest_drops": sharpest_drops,
        "audit": audit,
    }

    summary_text, summary_source = build_telegram_summary(
        result, lang=lang, outlet_mode=outlet_mode, use_llm=False
    )
    result["telegram_summary"] = {
        "text": summary_text,
        "lang": lang,
        "source": summary_source,
        "llm_available": bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("OPENAI_API_KEY")),
        "telegram_configured": bool(
            os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID")
        ),
    }
    return result


def query_transactions(
    rows: list[dict[str, Any]],
    month: str = "all",
    region: str = "all",
    brand: str = "all",
    date_from: str = "",
    date_to: str = "",
    search: str = "",
    sort_by: str = "date",
    sort_dir: str = "desc",
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    """Filter, search, sort, and paginate cleaned sales transactions."""
    q = search.strip().lower()
    d_from = date_from.strip()
    d_to = date_to.strip()
    filtered = []
    for r in rows:
        if month != "all" and r["month"] != month:
            continue
        if region != "all" and r["region"] != region:
            continue
        if brand != "all" and r["brand"] != brand:
            continue
        if d_from and r["date"] < d_from:
            continue
        if d_to and r["date"] > d_to:
            continue
        if q:
            haystack = (
                f"{r['date']} {r['invoice_no']} {r['outlet_id']} {r['outlet_name']} "
                f"{r['region']} {r['branch']} {r['salesman']} {r['brand']} {r['sku']}"
            ).lower()
            if q not in haystack:
                continue
        filtered.append(r)

    allowed_sorts = {
        "date",
        "invoice_no",
        "outlet_name",
        "branch",
        "salesman",
        "brand",
        "qty_carton",
        "net_sales_idr",
    }
    key_col = sort_by if sort_by in allowed_sorts else "date"
    reverse = sort_dir != "asc"
    filtered.sort(key=lambda r: (r[key_col], r["invoice_no"]), reverse=reverse)

    page_size = max(1, min(page_size, 100))
    total_rows = len(filtered)
    total_pages = max(1, (total_rows + page_size - 1) // page_size)
    page = max(1, min(page, total_pages))
    start = (page - 1) * page_size
    items = filtered[start : start + page_size]

    return {
        "total_rows": total_rows,
        "total_pages": total_pages,
        "page": page,
        "page_size": page_size,
        "sort_by": key_col,
        "sort_dir": "desc" if reverse else "asc",
        "items": items,
    }


def build_telegram_summary(
    dashboard: dict[str, Any],
    lang: str = "id",
    outlet_mode: str = "lowest",
    use_llm: bool = False,
) -> tuple[str, str]:
    """Generate a concise, mobile-friendly one-paragraph Telegram digest."""
    kpis = dashboard["kpis"]
    by_region = dashboard["by_region"]
    by_brand = dashboard["by_brand"]
    use_drops = outlet_mode == "drops" and bool(dashboard.get("sharpest_drops"))
    flagged = dashboard["sharpest_drops"] if use_drops else dashboard["weakest_outlets"]
    f = dashboard["filters"]

    if kpis["total_invoices"] == 0 and kpis["total_net_sales"] == 0:
        msg = (
            "Tidak ada data penjualan untuk filter yang dipilih."
            if lang == "id"
            else "No sales records match the selected filters."
        )
        return msg, "deterministic"

    period_label = dashboard["comparison"]["period_label"]
    scope_parts = [x for x in (f["region"], f["brand"]) if x != "all"]
    scope_str = f" ({', '.join(scope_parts)})" if scope_parts else ""

    top_reg = by_region[0] if by_region else None
    top_brand = by_brand[0] if by_brand else None

    reg_with_mom = [r for r in by_region if r["mom_pct"] is not None]
    worst_reg = min(reg_with_mom, key=lambda r: r["mom_pct"]) if reg_with_mom else None
    best_reg = max(reg_with_mom, key=lambda r: r["mom_pct"]) if reg_with_mom else None

    brand_with_mom = [b for b in by_brand if b["mom_pct"] is not None]
    worst_brand = min(brand_with_mom, key=lambda b: b["mom_pct"]) if brand_with_mom else None

    if use_drops:
        weak_short = ", ".join(
            f"{o['outlet_name']} ({o['branch']}, {o['mom_pct']:+.1f}% MoM, {o['salesman']})"
            for o in flagged
        )
    else:
        weak_short = ", ".join(
            f"{o['outlet_name']} ({o['branch']}, {format_idr(o['net_sales'], lang)}, {o['salesman']})"
            for o in flagged
        )

    if lang == "id":
        mom_txt = f" ({kpis['mom_pct']:+.1f}% MoM)" if kpis["mom_pct"] is not None else ""
        perf_parts = []
        if top_reg:
            perf_parts.append(
                f"{top_reg['region']} teratas ({format_idr(top_reg['net_sales'], 'id')}, {top_reg['share_pct']}%)"
            )
        if best_reg and worst_reg and best_reg["region"] != worst_reg["region"]:
            perf_parts.append(
                f"{best_reg['region']} naik {best_reg['mom_pct']:+.1f}% sedangkan {worst_reg['region']} turun {worst_reg['mom_pct']:+.1f}%"
            )
        if top_brand:
            b_txt = f"brand utama {top_brand['brand']} ({top_brand['share_pct']}%)"
            if worst_brand and worst_brand["mom_pct"] < 0:
                b_txt += f" sementara {worst_brand['brand']} turun {worst_brand['mom_pct']:+.1f}%"
            perf_parts.append(b_txt)

        perf_sentence = f" {'; '.join(perf_parts)}." if perf_parts else ""
        action_lead = (
            "Mohon PIC segera follow-up 5 outlet dengan penurunan MoM terdalam:"
            if use_drops
            else "Mohon PIC segera follow-up 5 outlet terlemah:"
        )
        deterministic = (
            f"Update Penjualan {period_label}{scope_str}: Net sales {format_idr(kpis['total_net_sales'], 'id')}{mom_txt} "
            f"dari {kpis['total_cartons']:,} karton di {kpis['active_outlets']} outlet aktif."
            f"{perf_sentence} {action_lead} {weak_short}."
        )
    else:
        mom_txt = f" ({kpis['mom_pct']:+.1f}% MoM)" if kpis["mom_pct"] is not None else ""
        perf_parts = []
        if top_reg:
            perf_parts.append(
                f"{top_reg['region']} led at {format_idr(top_reg['net_sales'], 'en')} ({top_reg['share_pct']}%)"
            )
        if best_reg and worst_reg and best_reg["region"] != worst_reg["region"]:
            perf_parts.append(
                f"{best_reg['region']} grew {best_reg['mom_pct']:+.1f}% while {worst_reg['region']} fell {worst_reg['mom_pct']:+.1f}%"
            )
        if top_brand:
            b_txt = f"{top_brand['brand']} anchored {top_brand['share_pct']}% of sales"
            if worst_brand and worst_brand["mom_pct"] < 0:
                b_txt += f" as {worst_brand['brand']} slipped {worst_brand['mom_pct']:+.1f}%"
            perf_parts.append(b_txt)

        perf_sentence = f" {'; '.join(perf_parts)}." if perf_parts else ""
        action_lead = (
            "Action needed on the 5 outlets with sharpest MoM drops:"
            if use_drops
            else "Action needed on the 5 weakest outlets:"
        )
        deterministic = (
            f"Sales Digest {period_label}{scope_str}: Net sales hit {format_idr(kpis['total_net_sales'], 'en')}{mom_txt} "
            f"across {kpis['total_cartons']:,} cartons and {kpis['active_outlets']} active outlets."
            f"{perf_sentence} {action_lead} {weak_short}."
        )

    if use_llm:
        llm_text, provider = _try_llm_summary(deterministic, lang=lang)
        if llm_text:
            return llm_text, provider

    return deterministic, "deterministic"


def send_telegram_message(text: str) -> dict[str, Any]:
    """Optionally send the summary to Telegram when TELEGRAM_BOT_TOKEN & TELEGRAM_CHAT_ID are set."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        raise ValueError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set in environment.")

    payload = json.dumps({"chat_id": chat_id, "text": text}).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _try_llm_summary(grounded_facts: str, lang: str) -> tuple[str | None, str]:
    """Optionally polish the grounded summary using Anthropic Claude or OpenAI if key is set."""
    language_name = "Bahasa Indonesia" if lang == "id" else "English"
    prompt = (
        f"Rewrite the following verified sales metrics into ONE short, scannable paragraph "
        f"in {language_name} for a sales manager reading on Telegram on their phone. "
        f"Rules: strictly 1 paragraph (no bullet points, no line breaks), keep every number "
        f"and outlet name 100% accurate, and end with a clear follow-up action.\n\n"
        f"Verified facts:\n{grounded_facts}"
    )

    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    if anthropic_key:
        try:
            payload = json.dumps(
                {
                    "model": os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514"),
                    "max_tokens": 300,
                    "messages": [{"role": "user", "content": prompt}],
                }
            ).encode("utf-8")
            req = urllib.request.Request(
                "https://api.anthropic.com/v1/messages",
                data=payload,
                headers={
                    "x-api-key": anthropic_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                text = " ".join(body["content"][0]["text"].split())
                return text, "claude"
        except (urllib.error.URLError, KeyError, TimeoutError, ValueError):
            pass

    openai_key = os.environ.get("OPENAI_API_KEY")
    if openai_key:
        try:
            payload = json.dumps(
                {
                    "model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
                    "max_tokens": 300,
                    "messages": [{"role": "user", "content": prompt}],
                }
            ).encode("utf-8")
            req = urllib.request.Request(
                "https://api.openai.com/v1/chat/completions",
                data=payload,
                headers={
                    "Authorization": f"Bearer {openai_key}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                text = " ".join(body["choices"][0]["message"]["content"].split())
                return text, "openai"
        except (urllib.error.URLError, KeyError, TimeoutError, ValueError):
            pass

    return None, "deterministic"
