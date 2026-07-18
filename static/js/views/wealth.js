const WEALTH_KINDS = {
  investment: "Investment",
  cushion: "Emergency cushion",
  savings: "Savings",
  income: "Earnings (mo)",
};

async function renderWealth(el) {
  const s = await api.get("/api/wealth/summary");
  const t = s.totals || {};
  el.innerHTML = `
    <h2>Wealth</h2>
    <div class="grid cols-4">
      <div class="card kpi"><div class="label">Investments</div>
        <div class="value">${fmt.pln(t.investment || 0)}</div>
        <div class="sub">stocks, employer pension, retirement accounts…</div></div>
      <div class="card kpi"><div class="label">Emergency cushion</div>
        <div class="value">${fmt.pln(t.cushion || 0)}</div></div>
      <div class="card kpi"><div class="label">Savings</div>
        <div class="value">${fmt.pln(t.savings || 0)}</div></div>
      <div class="card kpi"><div class="label">Net worth</div>
        <div class="value">${fmt.pln((t.investment || 0) + (t.cushion || 0) + (t.savings || 0) - (s.debt_total || 0))}</div>
        <div class="sub">assets ${fmt.pln((t.investment || 0) + (t.cushion || 0) + (t.savings || 0))}
          − loans ${fmt.pln(s.debt_total || 0)} · monthly earnings: ${fmt.pln(t.income || 0)}</div></div>
    </div>
    <div class="card mt">
      <h3>Add an item</h3>
      <div class="row">
        <input id="wName" placeholder="name (e.g. IKZE Lukas)" style="flex:1">
        <select id="wKind">${Object.entries(WEALTH_KINDS).map(([k, v]) => `<option value="${k}">${v}</option>`).join("")}</select>
        <select id="wOwner"><option value="ja">me</option><option value="żona">wife</option><option value="wspólne" selected>joint</option></select>
        <input data-num id="wValue" placeholder="value PLN">
        <select id="wDebt"><option value="">no loan</option>
          ${s.debts.map((d) => `<option value="${d.id}">${d.name}</option>`).join("")}</select>
        <button class="primary" id="wAdd">Add</button>
      </div>
    </div>
    <div class="card mt"><h3>Items</h3><div id="wTable"></div></div>
    <div class="card mt"><h3>Combined trend</h3><canvas id="wChart" height="90"></canvas></div>`;

  const tbl = document.getElementById("wTable");
  if (!s.items.length) {
    tbl.innerHTML = '<div class="empty">No items — add the first one above</div>';
  } else {
    tbl.innerHTML = `<table><thead><tr>
      <th>Name</th><th>Type</th><th>Owner</th><th style="text-align:right">Value</th>
      <th>Loan</th><th style="text-align:right">Equity</th><th>Updated</th><th></th><th></th>
    </tr></thead><tbody>` + s.items.map((i) => `<tr>
      <td>${i.name}</td>
      <td><span class="badge">${WEALTH_KINDS[i.kind] || i.kind}</span></td>
      <td>${i.owner}</td>
      <td style="text-align:right">${fmt.pln(i.latest_value)}</td>
      <td><select data-link="${i.id}">
        <option value="">—</option>
        ${s.debts.map((d) => `<option value="${d.id}" ${i.linked_debt_id === d.id ? "selected" : ""}>${d.name}</option>`).join("")}
      </select></td>
      <td style="text-align:right" class="${i.equity != null ? (i.equity >= 0 ? "pos" : "neg") : ""}">${i.equity != null ? fmt.pln(i.equity) : "—"}</td>
      <td class="muted">${i.latest_date || "—"}</td>
      <td><button data-upd="${i.id}">Update</button></td>
      <td><button class="danger" data-del="${i.id}">✕</button></td>
    </tr>`).join("") + "</tbody></table>";
  }

  tbl.querySelectorAll("[data-upd]").forEach((b) =>
    b.addEventListener("click", async () => {
      const v = prompt("New value (PLN):");
      if (v === null || v === "" || isNaN(parseNum(v))) return;
      await api.post(`/api/wealth/items/${b.dataset.upd}/values`, { value: parseNum(v) });
      route();
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
          label: "Total wealth",
          data: s.trend.map((p) => p.total),
          borderColor: CHART_COLORS[1],
          backgroundColor: "transparent",
          tension: 0.25,
        }],
      },
      options: { plugins: { legend: { display: false } } },
    }));
  }
}
