async function renderBusiness(el) {
  const [b, mkt] = await Promise.all([
    api.get("/api/business"),
    api.get("/api/business/marketing").catch(() => ({ error: "no data" }))]);
  const cur = b.current;
  const KIND_LABELS = { koszt: "cost", "przychód": "revenue" };
  el.innerHTML = `
    <h2>Business</h2>
    <div class="grid cols-4">
      <div class="card kpi"><div class="label">This month: result</div>
        <div class="value ${(cur.wynik ?? cur.przychody - cur.koszty) >= 0 ? "pos" : "neg"}">${fmt.pln((cur.przychody || 0) - (cur.koszty || 0))}</div>
        <div class="sub">revenue ${fmt.pln(cur.przychody || 0)} · costs ${fmt.pln(cur.koszty || 0)}</div></div>
      <div class="card kpi"><div class="label">Invested since launch</div>
        <div class="value">${fmt.pln(b.total_cost)}</div></div>
      <div class="card kpi"><div class="label">Revenue since launch</div>
        <div class="value">${fmt.pln(b.total_revenue)}</div></div>
      <div class="card kpi"><div class="label">Cumulative result</div>
        <div class="value ${b.total_result >= 0 ? "pos" : "neg"}">${fmt.pln(b.total_result)}</div>
        <div class="sub">tracks fixed monthly base (accounting, social security, tools) vs revenue</div></div>
    </div>
    <div class="card mt">
      <h3>Add an entry</h3>
      <div class="row">
        <input type="date" id="bDate" value="${new Date().toISOString().slice(0, 10)}">
        <select id="bKind"><option value="koszt">cost</option><option value="przychód">revenue</option></select>
        <select id="bCat">${b.categories.map((c) => `<option>${c}</option>`).join("")}</select>
        <input data-num id="bAmount" placeholder="net amount PLN">
        <input id="bDesc" placeholder="description (e.g. Ad spend July, materials…)" style="flex:1">
        <button class="primary" id="bAdd">Add</button>
      </div>
      <div class="muted mt">Net amounts (sole proprietorship with VAT — VAT is deducted separately in accounting).
        Tag marketing spend with the "marketing" category — ROAS is computed from it.</div>
    </div>
    <div class="grid cols-2 mt">
      <div class="card"><h3>Costs vs revenue / mo</h3><canvas id="bChart"></canvas></div>
      <div class="card"><h3>Cumulative result</h3><canvas id="bCum"></canvas></div>
    </div>
    ${!mkt.error ? `<div class="card mt" style="border-left:4px solid ${CHART_COLORS[4]}">
      <h3 style="margin-top:0">📣 Performance marketing (Meta) — weekly analysis from marketing agents</h3>
      <div class="row" style="gap:20px;flex-wrap:wrap">
        <span>Spend (recent weeks): <b>€${fmt.num(mkt.recent_spend_eur)}</b></span>
        <span>Clicks: <b>${mkt.recent_clicks}</b></span>
        <span class="muted">report every Monday ~07:00 (ads-analyst)</span>
      </div>
      ${mkt.weeks.length ? `<div class="mt">
        <b>Last week (${mkt.weeks[0].week}, spend €${mkt.weeks[0].spend_eur}):</b>
        <div class="muted">${mkt.weeks[0].summary || "—"}</div>
        ${mkt.weeks[0].recommendation ? `<div class="mt">💡 <b>Recommendation of the week:</b> ${mkt.weeks[0].recommendation}</div>` : ""}
      </div>` : ""}
      ${mkt.insights.length ? `<details class="mt"><summary style="cursor:pointer"><b>Insights</b> (${mkt.insights.length}) — what works</summary>
        <ul style="padding-left:18px">${mkt.insights.map((i) =>
          `<li class="mt"><span class="badge">${i.category}</span> ${i.insight} <span class="muted">(confidence ${Math.round(i.confidence * 100)}%)</span></li>`).join("")}</ul>
      </details>` : ""}
      ${mkt.hypotheses.length ? `<details class="mt"><summary style="cursor:pointer"><b>Active hypotheses</b> (${mkt.hypotheses.length}) — to test</summary>
        <ul style="padding-left:18px">${mkt.hypotheses.map((h) =>
          `<li class="mt"><b>${h.title}</b><div class="muted">${h.predicted_outcome || ""}</div></li>`).join("")}</ul>
      </details>` : ""}
      <details class="mt"><summary class="muted" style="cursor:pointer">previous weeks</summary>
        <table class="mt"><thead><tr><th>Week</th><th>Spend</th><th>Summary</th></tr></thead>
        <tbody>${mkt.weeks.slice(1).map((w) => `<tr><td>${w.week}</td><td>€${w.spend_eur}</td>
          <td class="muted" style="font-size:.85em">${(w.summary || "—").slice(0, 180)}…</td></tr>`).join("")}</tbody></table>
      </details>
    </div>` : `<div class="card mt muted">📣 Performance marketing: ${mkt.error}</div>`}
    <div class="card mt"><h3>Months (marketing → ROAS)</h3><div id="bMonths"></div></div>
    <div class="card mt"><h3>Entries</h3><div id="bTable"></div></div>`;

  const mtbl = document.getElementById("bMonths");
  if (!b.months.length) {
    mtbl.innerHTML = '<div class="empty">No data — add the first entry</div>';
  } else {
    mtbl.innerHTML = `<table><thead><tr><th>Month</th><th style="text-align:right">Costs</th>
      <th style="text-align:right">of which marketing</th><th style="text-align:right">Revenue</th>
      <th style="text-align:right">Result</th><th style="text-align:right">Cumulative</th><th>ROAS</th></tr></thead><tbody>` +
      [...b.months].reverse().map((m) => `<tr>
        <td>${m.month}</td>
        <td style="text-align:right" class="neg">${fmt.pln(m.koszty)}</td>
        <td style="text-align:right">${fmt.pln(m.marketing)}</td>
        <td style="text-align:right" class="pos">${fmt.pln(m.przychody)}</td>
        <td style="text-align:right" class="${m.wynik >= 0 ? "pos" : "neg"}">${fmt.pln(m.wynik)}</td>
        <td style="text-align:right">${fmt.pln(m.narastajaco)}</td>
        <td>${m.roas != null ? m.roas + "×" : "—"}</td>
      </tr>`).join("") + "</tbody></table>";
  }

  const tbl = document.getElementById("bTable");
  if (!b.entries.length) {
    tbl.innerHTML = '<div class="empty">No entries</div>';
  } else {
    tbl.innerHTML = `<table><thead><tr><th>Date</th><th>Type</th><th>Category</th><th>Description</th>
      <th style="text-align:right">Amount</th><th></th></tr></thead><tbody>` +
      b.entries.map((e) => `<tr>
        <td>${e.date}</td>
        <td><span class="badge">${KIND_LABELS[e.kind] || e.kind}</span></td>
        <td>${e.category}</td>
        <td>${e.description || "—"}</td>
        <td style="text-align:right" class="${e.kind === "przychód" ? "pos" : "neg"}">${fmt.pln(e.amount)}</td>
        <td><button class="danger" data-bdel="${e.id}">✕</button></td>
      </tr>`).join("") + "</tbody></table>";
  }
  tbl.querySelectorAll("[data-bdel]").forEach((btn) =>
    btn.addEventListener("click", async () => {
      if (!confirm("Delete this entry?")) return;
      await api.del("/api/business/" + btn.dataset.bdel);
      route();
    }));

  document.getElementById("bAdd").addEventListener("click", async () => {
    const amount = parseNum(document.getElementById("bAmount"));
    if (!amount || isNaN(amount)) { alert("Enter an amount"); return; }
    await api.post("/api/business", {
      date: document.getElementById("bDate").value,
      kind: document.getElementById("bKind").value,
      category: document.getElementById("bCat").value,
      amount,
      description: document.getElementById("bDesc").value,
    });
    route();
  });

  if (b.months.length) {
    trackChart(new Chart(document.getElementById("bChart"), {
      type: "bar",
      data: {
        labels: b.months.map((m) => m.month),
        datasets: [
          { label: "Costs", data: b.months.map((m) => m.koszty), backgroundColor: "#ff6b6b" },
          { label: "Revenue", data: b.months.map((m) => m.przychody), backgroundColor: "#3ecf8e" },
        ],
      },
    }));
    trackChart(new Chart(document.getElementById("bCum"), {
      type: "line",
      data: {
        labels: b.months.map((m) => m.month),
        datasets: [{ label: "Cumulative result", data: b.months.map((m) => m.narastajaco),
          borderColor: CHART_COLORS[0], backgroundColor: "transparent", tension: 0.25 }],
      },
      options: { plugins: { legend: { display: false } } },
    }));
  }
}
