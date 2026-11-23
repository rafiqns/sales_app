const state = {
  month: "all",
  region: "all",
  brand: "all",
  lang: "id",
  outletMode: "lowest", // "lowest" | "drops"
  txSearch: "",
  txDateFrom: "",
  txDateTo: "",
  txSortBy: "date",
  txSortDir: "desc",
  txPage: 1,
  data: null,
};

function fmtIDR(n) {
  const sign = n < 0 ? "-" : "";
  const v = Math.abs(n);
  if (state.lang === "id") {
    if (v >= 1e9) return `${sign}Rp ${(v / 1e9).toFixed(2).replace(".", ",")} M`;
    if (v >= 1e6) return `${sign}Rp ${(v / 1e6).toFixed(1).replace(".", ",")} jt`;
    if (v >= 1e3) return `${sign}Rp ${(v / 1e3).toFixed(0)} rb`;
    return `${sign}Rp ${Math.round(v).toLocaleString("id-ID")}`;
  }
  if (v >= 1e9) return `${sign}Rp ${(v / 1e9).toFixed(2)}B`;
  if (v >= 1e6) return `${sign}Rp ${(v / 1e6).toFixed(1)}M`;
  if (v >= 1e3) return `${sign}Rp ${(v / 1e3).toFixed(0)}K`;
  return `${sign}Rp ${Math.round(v).toLocaleString("en-US")}`;
}

function fmtIDRFull(n) {
  const sign = n < 0 ? "-" : "";
  return `${sign}Rp ${Math.abs(Math.round(n)).toLocaleString("id-ID")}`;
}

function deltaBadge(pct) {
  if (pct === null || pct === undefined) return `<span class="delta delta-flat">—</span>`;
  const cls = pct > 0 ? "delta-up" : pct < 0 ? "delta-down" : "delta-flat";
  const sign = pct > 0 ? "+" : "";
  return `<span class="delta ${cls}">${sign}${pct.toFixed(1)}%</span>`;
}

async function fetchDashboard() {
  const params = new URLSearchParams({
    month: state.month,
    region: state.region,
    brand: state.brand,
    lang: state.lang,
    outlet_mode: state.outletMode,
  });
  const res = await fetch(`/api/dashboard?${params.toString()}`);
  const data = await res.json();
  state.data = data;
  renderAll(data);
  fetchTransactions();
}

async function fetchTransactions() {
  const params = new URLSearchParams({
    month: state.month,
    region: state.region,
    brand: state.brand,
    date_from: state.txDateFrom,
    date_to: state.txDateTo,
    search: state.txSearch,
    sort_by: state.txSortBy,
    sort_dir: state.txSortDir,
    page: String(state.txPage),
    page_size: "20",
  });
  const res = await fetch(`/api/transactions?${params.toString()}`);
  const data = await res.json();
  renderTransactions(data);
}

function renderTransactions(data) {
  const tbody = document.getElementById("tx-tbody");
  if (!data.items.length) {
    tbody.innerHTML = `<tr><td colspan="8">Tidak ada transaksi yang cocok.</td></tr>`;
  } else {
    tbody.innerHTML = data.items
      .map(
        (r) => `
        <tr>
          <td class="num">${r.date}</td>
          <td>${r.invoice_no}${r.is_return ? ' <span class="badge badge-danger">Retur</span>' : ""}</td>
          <td><strong>${r.outlet_name}</strong><span class="outlet-id">${r.outlet_id} · ${r.outlet_type}</span></td>
          <td>${r.region}<span class="outlet-id">${r.branch}</span></td>
          <td>${r.salesman}</td>
          <td><strong>${r.brand}</strong><span class="outlet-id">${r.sku}</span></td>
          <td class="num">${r.qty_carton}</td>
          <td class="num"><strong>${fmtIDRFull(r.net_sales_idr)}</strong></td>
        </tr>`
      )
      .join("");
  }

  document.getElementById("tx-page-info").textContent =
    `Halaman ${data.page} dari ${data.total_pages} (${data.total_rows.toLocaleString("id-ID")} transaksi)`;
  document.getElementById("tx-prev").disabled = data.page <= 1;
  document.getElementById("tx-next").disabled = data.page >= data.total_pages;

  document.querySelectorAll("th.sortable").forEach((th) => {
    const ind = th.querySelector(".sort-ind");
    if (th.dataset.sort === state.txSortBy) {
      ind.textContent = state.txSortDir === "asc" ? "↑" : "↓";
    } else {
      ind.textContent = "";
    }
  });
}

function populateSelect(el, items, currentValue, allLabel) {
  el.innerHTML = `<option value="all">${allLabel}</option>`;
  items.forEach((val) => {
    const opt = document.createElement("option");
    opt.value = val;
    opt.textContent = val;
    if (val === currentValue) opt.selected = true;
    el.appendChild(opt);
  });
}

function renderAll(data) {
  document.getElementById("source-name").textContent = data.source_name || "sales.csv";
  document.title = `Dua Kelinci Sales Pulse · ${data.comparison.period_label}`;

  populateSelect(
    document.getElementById("filter-month"),
    data.filters.available_months,
    state.month,
    `All Months (${data.comparison.period_label})`
  );
  populateSelect(
    document.getElementById("filter-region"),
    data.filters.available_regions,
    state.region,
    "All Regions"
  );
  populateSelect(
    document.getElementById("filter-brand"),
    data.filters.available_brands,
    state.brand,
    "All Brands"
  );

  // Audit Banner
  const a = data.audit;
  document.getElementById("audit-headline").textContent =
    `${a.clean_rows.toLocaleString()} clean lines from ${a.raw_rows.toLocaleString()} raw rows · ` +
    `${a.regions_normalized} region typos fixed · ${a.duplicates_removed} duplicates removed · ` +
    `${a.returns_kept} return kept`;
  const auditList = document.getElementById("audit-details");
  auditList.innerHTML = a.notes.map((n) => `<li>${n}</li>`).join("");

  // KPIs
  const k = data.kpis;
  const cmp = data.comparison;
  document.getElementById("kpi-net").textContent = fmtIDR(k.total_net_sales);
  document.getElementById("kpi-mom").innerHTML =
    k.mom_pct !== null
      ? `${cmp.curr_label} vs ${cmp.prev_label}: ${deltaBadge(k.mom_pct)} (${fmtIDR(k.prev_net_sales)} → ${fmtIDR(k.curr_net_sales)})`
      : fmtIDRFull(k.total_net_sales);

  document.getElementById("kpi-cartons").textContent = `${k.total_cartons.toLocaleString()} cartons`;
  document.getElementById("kpi-invoices").textContent = `${k.total_invoices.toLocaleString()} invoices`;

  document.getElementById("kpi-outlets").textContent = k.active_outlets.toLocaleString();
  document.getElementById("kpi-aov").textContent = `Avg order: ${fmtIDR(k.avg_order_value)}`;

  document.getElementById("kpi-discount").textContent = `${k.discount_rate_pct}%`;
  document.getElementById("kpi-gross").textContent = `Gross: ${fmtIDR(k.total_gross_sales)}`;

  // Telegram Digest
  const tg = data.telegram_summary;
  document.getElementById("telegram-text").textContent = tg.text;
  document.getElementById("tg-source").textContent =
    tg.source === "deterministic" ? "Grounded Summary" : `AI Polished (${tg.source})`;

  document.getElementById("btn-llm").classList.toggle("hidden", !tg.llm_available);
  document.getElementById("btn-send-tg").classList.toggle("hidden", !tg.telegram_configured);

  // Bars: Region
  renderBars(
    document.getElementById("region-bars"),
    data.by_region,
    "region",
    "",
    state.region,
    (val) => {
      state.region = state.region === val ? "all" : val;
      state.txPage = 1;
      fetchDashboard();
    }
  );

  // Bars: Brand
  renderBars(
    document.getElementById("brand-bars"),
    data.by_brand,
    "brand",
    "brand-fill",
    state.brand,
    (val) => {
      state.brand = state.brand === val ? "all" : val;
      state.txPage = 1;
      fetchDashboard();
    }
  );

  // Weakest Outlets Table
  renderWeakestTable(data);

  // Region x Brand Matrix
  renderMatrix(data.matrix_brands, data.region_brand_matrix);
}

function renderWeakestTable(data) {
  const cmp = data.comparison;
  document.getElementById("th-prev").textContent = cmp.prev_label;
  document.getElementById("th-curr").textContent = cmp.curr_label;

  const list =
    state.outletMode === "drops" && data.sharpest_drops.length
      ? data.sharpest_drops
      : data.weakest_outlets;

  const tbody = document.getElementById("weakest-tbody");
  if (!list.length) {
    tbody.innerHTML = `<tr><td colspan="11">No matching outlets.</td></tr>`;
    return;
  }

  tbody.innerHTML = list
    .map(
      (o, idx) => `
      <tr>
        <td><span class="rank-pill">${idx + 1}</span></td>
        <td><strong>${o.outlet_name}</strong><span class="outlet-id">${o.outlet_id}</span></td>
        <td>${o.region} <span class="outlet-id">${o.branch}</span></td>
        <td>${o.outlet_type}</td>
        <td>${o.salesman}</td>
        <td>${(o.reasons || []).map((r) => `<span class="reason-pill">${r}</span>`).join("")}</td>
        <td class="num">${o.invoices}</td>
        <td class="num">${fmtIDR(o.prev_sales)}</td>
        <td class="num">${fmtIDR(o.curr_sales)}</td>
        <td class="num">${deltaBadge(o.mom_pct)}</td>
        <td class="num"><strong>${fmtIDRFull(o.net_sales)}</strong></td>
      </tr>`
    )
    .join("");
}

function renderBars(container, items, key, fillClass, activeVal, onClick) {
  if (!items.length) {
    container.innerHTML = `<p class="card-sub">No matching records.</p>`;
    return;
  }
  const maxVal = Math.max(...items.map((i) => i.net_sales), 1);
  container.innerHTML = "";
  items.forEach((item) => {
    const pct = Math.max((item.net_sales / maxVal) * 100, 1);
    const div = document.createElement("div");
    div.className = `bar-item ${activeVal === item[key] ? "active-filter" : ""}`;
    div.innerHTML = `
      <div class="bar-row-top">
        <span class="bar-name">${item[key]}</span>
        <span class="bar-meta">
          <span>${item.share_pct}%</span>
          ${item.mom_pct !== null ? deltaBadge(item.mom_pct) : ""}
          <span class="bar-amount">${fmtIDR(item.net_sales)}</span>
        </span>
      </div>
      <div class="bar-track">
        <div class="bar-fill ${fillClass}" style="width:${pct.toFixed(1)}%"></div>
      </div>
    `;
    div.addEventListener("click", () => onClick(item[key]));
    container.appendChild(div);
  });
}

function renderMatrix(brands, rows) {
  const table = document.getElementById("matrix-table");
  if (!rows.length) {
    table.innerHTML = `<tbody><tr><td>No data</td></tr></tbody>`;
    return;
  }
  let maxCell = 1;
  rows.forEach((r) => {
    brands.forEach((b) => {
      if (r.values[b] > maxCell) maxCell = r.values[b];
    });
  });

  const head = `<thead><tr><th>Region</th>${brands
    .map((b) => `<th class="num">${b}</th>`)
    .join("")}<th class="num">Total</th></tr></thead>`;

  const body = `<tbody>${rows
    .map((r) => {
      const cells = brands
        .map((b) => {
          const val = r.values[b] || 0;
          const alpha = val > 0 ? (0.06 + (val / maxCell) * 0.34).toFixed(2) : 0;
          return `<td class="heat-cell" style="background:rgba(2,132,199,${alpha})">${
            val > 0 ? fmtIDR(val) : "—"
          }</td>`;
        })
        .join("");
      return `<tr><td><strong>${r.region}</strong></td>${cells}<td class="num"><strong>${fmtIDR(
        r.total
      )}</strong></td></tr>`;
    })
    .join("")}</tbody>`;

  table.innerHTML = head + body;
}

// Event listeners
document.getElementById("filter-month").addEventListener("change", (e) => {
  state.month = e.target.value;
  state.txPage = 1;
  fetchDashboard();
});

document.getElementById("filter-region").addEventListener("change", (e) => {
  state.region = e.target.value;
  state.txPage = 1;
  fetchDashboard();
});

document.getElementById("filter-brand").addEventListener("change", (e) => {
  state.brand = e.target.value;
  state.txPage = 1;
  fetchDashboard();
});

document.getElementById("btn-reset").addEventListener("click", () => {
  state.month = "all";
  state.region = "all";
  state.brand = "all";
  state.txSearch = "";
  state.txDateFrom = "";
  state.txDateTo = "";
  state.txPage = 1;
  document.getElementById("tx-search").value = "";
  document.getElementById("tx-date-from").value = "";
  document.getElementById("tx-date-to").value = "";
  fetchDashboard();
});

document.getElementById("btn-toggle-audit").addEventListener("click", () => {
  const details = document.getElementById("audit-details");
  const btn = document.getElementById("btn-toggle-audit");
  details.classList.toggle("hidden");
  btn.textContent = details.classList.contains("hidden") ? "View details" : "Hide details";
});

document.getElementById("lang-id").addEventListener("click", () => {
  state.lang = "id";
  document.getElementById("lang-id").classList.add("active");
  document.getElementById("lang-en").classList.remove("active");
  fetchDashboard();
});

document.getElementById("lang-en").addEventListener("click", () => {
  state.lang = "en";
  document.getElementById("lang-en").classList.add("active");
  document.getElementById("lang-id").classList.remove("active");
  fetchDashboard();
});

document.getElementById("mode-lowest").addEventListener("click", () => {
  state.outletMode = "lowest";
  document.getElementById("mode-lowest").classList.add("active");
  document.getElementById("mode-drops").classList.remove("active");
  fetchDashboard();
});

document.getElementById("mode-drops").addEventListener("click", () => {
  state.outletMode = "drops";
  document.getElementById("mode-drops").classList.add("active");
  document.getElementById("mode-lowest").classList.remove("active");
  fetchDashboard();
});

document.getElementById("btn-copy").addEventListener("click", async () => {
  const text = document.getElementById("telegram-text").textContent;
  const fb = document.getElementById("copy-feedback");
  try {
    await navigator.clipboard.writeText(text);
    fb.textContent = "Copied to clipboard!";
  } catch {
    fb.textContent = "Select text to copy.";
  }
  setTimeout(() => {
    fb.textContent = "";
  }, 2000);
});

document.getElementById("btn-send-tg").addEventListener("click", async () => {
  const btn = document.getElementById("btn-send-tg");
  const fb = document.getElementById("copy-feedback");
  const text = document.getElementById("telegram-text").textContent;
  btn.disabled = true;
  btn.textContent = "Sending...";
  try {
    const res = await fetch("/api/send-telegram", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    if (res.ok) {
      fb.textContent = "Sent to Telegram!";
    } else {
      const err = await res.json();
      fb.textContent = `Telegram error: ${err.error}`;
    }
  } finally {
    btn.disabled = false;
    btn.textContent = "Send to Telegram";
    setTimeout(() => {
      fb.textContent = "";
    }, 3000);
  }
});

document.getElementById("btn-llm").addEventListener("click", async () => {
  const btn = document.getElementById("btn-llm");
  btn.disabled = true;
  btn.textContent = "Polishing...";
  try {
    const res = await fetch("/api/summary", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        month: state.month,
        region: state.region,
        brand: state.brand,
        lang: state.lang,
        outlet_mode: state.outletMode,
        use_llm: true,
      }),
    });
    const data = await res.json();
    if (data.text) {
      document.getElementById("telegram-text").textContent = data.text;
      document.getElementById("tg-source").textContent = `AI Polished (${data.source})`;
    }
  } finally {
    btn.disabled = false;
    btn.textContent = "Polish with AI";
  }
});

document.getElementById("csv-upload").addEventListener("change", async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  const csvText = await file.text();
  const res = await fetch("/api/upload", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ filename: file.name, csv_text: csvText }),
  });
  if (res.ok) {
    state.month = "all";
    state.region = "all";
    state.brand = "all";
    state.txSearch = "";
    state.txPage = 1;
    document.getElementById("tx-search").value = "";
    fetchDashboard();
  } else {
    const err = await res.json();
    alert(`Upload failed: ${err.error}`);
  }
  e.target.value = "";
});

// Transactions date range, search, sort, pagination
document.getElementById("tx-date-from").addEventListener("change", (e) => {
  state.txDateFrom = e.target.value;
  state.txPage = 1;
  fetchTransactions();
});

document.getElementById("tx-date-to").addEventListener("change", (e) => {
  state.txDateTo = e.target.value;
  state.txPage = 1;
  fetchTransactions();
});

let searchTimer = null;
document.getElementById("tx-search").addEventListener("input", (e) => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    state.txSearch = e.target.value;
    state.txPage = 1;
    fetchTransactions();
  }, 200);
});

document.querySelectorAll("th.sortable").forEach((th) => {
  th.addEventListener("click", () => {
    const col = th.dataset.sort;
    if (state.txSortBy === col) {
      state.txSortDir = state.txSortDir === "asc" ? "desc" : "asc";
    } else {
      state.txSortBy = col;
      state.txSortDir = "desc";
    }
    state.txPage = 1;
    fetchTransactions();
  });
});

document.getElementById("tx-prev").addEventListener("click", () => {
  if (state.txPage > 1) {
    state.txPage -= 1;
    fetchTransactions();
  }
});

document.getElementById("tx-next").addEventListener("click", () => {
  state.txPage += 1;
  fetchTransactions();
});

fetchDashboard();
