const WEALTH_KINDS = {
  investment: "Investment",
  cushion: "Emergency cushion",
  savings: "Savings",
  income: "Earnings (mo)",
};

function _overviewCard(o) {
  const n = o.months.length, last = (k) => o.series[k][n - 1] || 0, prev = (k) => (n > 1 ? o.series[k][n - 2] : null);
  const inv = last("invest") + last("retirement");
  const invPrev = n > 1 ? prev("invest") + prev("retirement") : null;
  const netNow = o.net[n - 1], netPrev = n > 1 ? o.net[n - 2] : null;
  const delta = (a, b) => (a == null || b == null) ? "" : Math.abs(a - b) < 1 ? `<span class="muted">no change vs ${o.months[n - 2]} (no new entries)</span>`
    : `<span class="${a - b >= 0 ? "pos" : "neg"}">${a - b >= 0 ? "+" : "−"}${fmt.pln(Math.abs(a - b))} vs ${o.months[n - 2]}</span>`;
  const target = o.cushion.target, cush = last("cushion"), cash = last("cash");
  const ok = target ? cush >= target : null;
  const free = cash - (o.tax_uncovered ?? o.tax_reserve);  // cash after the part of the reserve nothing else covers
  const f3 = o.forecast[o.forecast.length - 1];
  return `<div class="card" style="border-left:4px solid ${CHART_COLORS[0]}">
    <h3 style="margin:0">📊 Overview: cash, cushion, tax, investments</h3>
    <div class="mt" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px">
      <div class="card kpi" style="margin:0"><div class="label">Cash on account</div>
        <div class="value">${fmt.pln(cash)}</div>
        <div class="sub">${o.tax_uncovered ? `of which for tax ${fmt.pln(o.tax_uncovered)}<br>free: <b class="${free >= 0 ? "pos" : "neg"}">${fmt.pln(free)}</b>` : "all free (tax set aside separately)"}
          <br>${delta(cash, n > 1 ? prev("cash") : null)}${f3 ? `<br>in 3 mo ~${fmt.pln(f3.cash)}` : ""}</div></div>
      <div class="card kpi" style="margin:0"><div class="label">Emergency cushion</div>
        <div class="value ${ok ? "pos" : ""}">${fmt.pln(cush)}</div>
        <div class="sub">${(o.cushion_items || []).map((c) => esc(c.name)).join(", ") || "set aside off the account"}
          ${target ? `<br>${ok ? "✓" : "⚠️"} ${fmt.num(cush / target * 100, 0)}% of the ${fmt.pln(target)} target (6 months of essential costs)` : ""}</div></div>
      <div class="card kpi" style="margin:0"><div class="label">Tax reserve</div>
        <div class="value">${fmt.pln(o.tax_reserve)}</div>
        <div class="sub">${!o.tax_reserve ? "no tax due"
          : o.tax_set_aside && !o.tax_uncovered ? `✓ set aside: ${fmt.pln(o.tax_set_aside)}<br>${(o.tax_items || []).map((t) => esc(t.name)).join(", ")}`
          : o.tax_set_aside ? `set aside ${fmt.pln(o.tax_set_aside)}, the remaining ${fmt.pln(o.tax_uncovered)} in cash${free < 0 ? ` ⚠️ short by ${fmt.pln(-free)}` : ""}`
          : `${free >= 0 ? "✓" : "⚠️"} held in cash on the account${free < 0 ? `, short by ${fmt.pln(-free)}` : ""}`}${o.tax_reserve_note ? "<br>" + esc(o.tax_reserve_note) : ""}</div></div>
      <div class="card kpi" style="margin:0"><div class="label">Investments (brokerage, retirement)</div>
        <div class="value">${fmt.pln(inv)}</div>
        <div class="sub">${delta(inv, invPrev)}${f3 ? `<br>in 3 mo ~${fmt.pln(f3.invest)} (6.5%/yr)` : ""}</div></div>
      <div class="card kpi" style="margin:0"><div class="label">Net worth</div>
        <div class="value">${fmt.pln(netNow)}</div>
        <div class="sub">${delta(netNow, netPrev)}<br>real estate and car ${fmt.pln(last("illiquid"))} · loans ${fmt.pln(o.debt_total)}</div></div>
    </div>
    <canvas id="wOverview" height="85" class="mt"></canvas>
    <div class="muted mt" style="font-size:.82em">Solid lines: values from your entries (a month without an entry carries the last value). Dashed: a 3-month forecast: cash from the Cash-flow tab (surplus, vests, bonus; cushion unchanged), investments +6.5%/yr. The cushion is money set aside (e.g. bonds), cash is the account; items of type Savings (e.g. a refundable deposit) sit outside these groups. Real estate is left off the chart so it doesn't flatten the scale. An item named “Tax reserve…” counts as money set aside for tax.</div>
  </div>`;
}

function _overviewChart(o) {
  const fm = o.forecast.map((f) => f.month);
  const labels = [...o.months, ...fm];
  const n = o.months.length, pad = (arr) => [...arr, ...fm.map(() => null)];
  const inv = o.series.invest.map((v, i) => v + o.series.retirement[i]);
  const fc = (cur, key) => [...o.months.map((_, i) => (i === n - 1 ? cur : null)), ...o.forecast.map((f) => f[key])];
  trackChart(new Chart(document.getElementById("wOverview"), {
    type: "line",
    data: { labels, datasets: [
      { label: "Cash on account", data: pad(o.series.cash), borderColor: CHART_COLORS[1], backgroundColor: "transparent", pointRadius: 3 },
      { label: "Cash: forecast", data: fc(o.series.cash[n - 1], "cash"), borderColor: CHART_COLORS[1], borderDash: [6, 4], backgroundColor: "transparent", pointRadius: 2, spanGaps: true },
      { label: "Cushion", data: [...o.series.cushion, ...fm.map(() => o.series.cushion[n - 1])], borderColor: CHART_COLORS[4], backgroundColor: "transparent", pointRadius: 3,
        segment: { borderDash: (ctx) => (ctx.p0DataIndex >= n - 1 ? [6, 4] : undefined) } },
      { label: "Investments", data: pad(inv), borderColor: CHART_COLORS[0], backgroundColor: "transparent", pointRadius: 3 },
      { label: "Investments: forecast", data: fc(inv[n - 1], "invest"), borderColor: CHART_COLORS[0], borderDash: [6, 4], backgroundColor: "transparent", pointRadius: 2, spanGaps: true },
      { label: "Tax reserve", data: [...o.months.map((_, i) => (i === n - 1 ? o.tax_reserve : null)), ...o.forecast.map((f) => o.tax_reserve + f.tax_reserve)],
        borderColor: CHART_COLORS[3], borderDash: [2, 3], backgroundColor: "transparent", pointRadius: 2, spanGaps: true },
    ] },
    options: { interaction: { mode: "index", intersect: false },
      scales: { y: { ticks: { callback: (v) => fmt.grouped(Math.round(v / 1000)) + "k" } } },
      plugins: { tooltip: { callbacks: { label: (ctx) => ctx.parsed.y == null ? null : `${ctx.dataset.label}: ${fmt.pln(ctx.parsed.y)}` } } } },
  }));
}

async function renderWealth(el) {
  const [s, o] = await Promise.all([api.get("/api/wealth/summary"), api.get("/api/wealth/overview").catch(() => null)]);
  el.innerHTML = `
    <h2>Wealth</h2>
    ${o ? _overviewCard(o) : ""}
    <div class="card mt">
      <h3>Add an item</h3>
      <div class="row">
        <input id="wName" placeholder="name (e.g. Brokerage account)" style="flex:1">
        <select id="wKind">${Object.entries(WEALTH_KINDS).map(([k, v]) => `<option value="${k}">${v}</option>`).join("")}</select>
        <select id="wOwner"><option value="me">Me</option><option value="partner">Partner</option><option value="joint" selected>Joint</option></select>
        <input data-num id="wValue" placeholder="value ${window.APP_CURRENCY || "PLN"}">
        <select id="wDebt"><option value="">no loan</option>
          ${s.debts.map((d) => `<option value="${d.id}">${esc(d.name)}</option>`).join("")}</select>
        <button class="primary" id="wAdd">Add</button>
      </div>
    </div>
    <div class="card mt"><h3>Items</h3><div id="wTable"></div></div>
    <div class="card mt"><h3>Combined trend</h3>
      <div class="muted" style="font-size:.85em">Total assets (without monthly earnings) and net worth after loans and the tax reserve. Paying a loan off from cash lowers assets, not net worth.</div>
      <canvas id="wChart" height="90"></canvas></div>`;
  if (o) _overviewChart(o);

  const tbl = document.getElementById("wTable");
  if (!s.items.length) {
    tbl.innerHTML = '<div class="empty">No items — add the first one above</div>';
  } else {
    // same order as the overview: cash, cushion, tax reserve, investments, retirement, illiquid, other, earnings last
    const isTax = (i) => i.group === "tax";
    const order = ["cash", "cushion", "tax", "invest", "retirement", "illiquid", "other", "income"];
    const rank = (i) => { const r = order.indexOf(i.group); return r < 0 ? order.length : r; };
    s.items.sort((a, b) => rank(a) - rank(b) || a.name.localeCompare(b.name));
    tbl.innerHTML = `<table><thead><tr>
      <th>Name</th><th>Type</th><th>Owner</th><th style="text-align:right">Value</th>
      <th>Loan</th><th style="text-align:right">Equity</th><th>Updated</th><th></th><th></th>
    </tr></thead><tbody>` + s.items.map((i) => `<tr>
      <td>${esc(i.name)}</td>
      <td><span class="badge">${isTax(i) ? "Tax reserve" : WEALTH_KINDS[i.kind] || i.kind}</span></td>
      <td>${i.owner}</td>
      <td style="text-align:right" data-val="${i.id}">${fmt.pln(i.latest_value)}</td>
      <td><select data-link="${i.id}">
        <option value="">—</option>
        ${s.debts.map((d) => `<option value="${d.id}" ${i.linked_debt_id === d.id ? "selected" : ""}>${esc(d.name)}</option>`).join("")}
      </select></td>
      <td style="text-align:right" class="${i.equity != null ? (i.equity >= 0 ? "pos" : "neg") : ""}">${i.equity != null ? fmt.pln(i.equity) : "—"}</td>
      <td class="muted">${i.latest_date || "—"}</td>
      <td>${i.live ? `<span class="muted" title="valued from the cached quote (${i.live_units} shares) — updates itself">🔄 auto</span>` : `<button data-upd="${i.id}">Update</button>`}</td>
      <td><button class="danger" data-del="${i.id}">✕</button></td>
    </tr>`).join("") + "</tbody></table>";
  }

  tbl.querySelectorAll("[data-upd]").forEach((b) =>
    b.addEventListener("click", () => {
      const item = s.items.find((i) => i.id === b.dataset.upd);
      inlineEdit(tbl.querySelector(`[data-val="${b.dataset.upd}"]`), {
        value: item && item.latest_value != null ? item.latest_value : "",
        placeholder: window.APP_CURRENCY || "PLN",
        onSave: async (v) => {
          await api.post(`/api/wealth/items/${b.dataset.upd}/values`, { value: v });
          route();
        },
      });
    }));
  tbl.querySelectorAll("[data-link]").forEach((sel) =>
    sel.addEventListener("change", async () => {
      await api.put("/api/wealth/items/" + sel.dataset.link,
        { linked_debt_id: sel.value || null });
      route();
    }));
  tbl.querySelectorAll("[data-del]").forEach((b) =>
    b.addEventListener("click", async () => {
      if (!confirm("Delete this item along with its history?")) return;
      await api.del("/api/wealth/items/" + b.dataset.del);
      route();
    }));

  document.getElementById("wAdd").addEventListener("click", async () => {
    const name = document.getElementById("wName").value.trim();
    const value = parseNum(document.getElementById("wValue"));
    if (!name) { alert("Enter a name"); return; }
    await api.post("/api/wealth/items", {
      name,
      kind: document.getElementById("wKind").value,
      owner: document.getElementById("wOwner").value,
      value: isNaN(value) ? undefined : value,
      linked_debt_id: document.getElementById("wDebt").value || null,
    });
    route();
  });

  if (s.trend.length) {
    trackChart(new Chart(document.getElementById("wChart"), {
      type: "line",
      data: {
        labels: s.trend.map((p) => p.month),
        datasets: [{
          label: "Total assets",
          data: s.trend.map((p) => p.total),
          borderColor: CHART_COLORS[1],
          backgroundColor: "transparent",
          tension: 0.25,
        }, ...(o ? [{
          label: "Net worth",
          data: s.trend.map((p) => o.net[o.months.indexOf(p.month)] ?? null),
          borderColor: CHART_COLORS[0],
          backgroundColor: "transparent",
          tension: 0.25, spanGaps: true,
        }] : [])],
      },
    }));
  }
}
