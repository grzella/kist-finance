async function renderAllocation(el) {
  const d = await api.get("/api/allocation");
  const flagCls = (f) => f === "too much" ? "neg" : f === "add more" ? "pos" : "muted";
  el.innerHTML = `
    <h2>📊 Asset allocation — structure and concentration</h2>
    <div class="card" style="border-left:4px solid var(--accent);margin-bottom:12px;font-size:.9em">
      This tab compares how your wealth is split (<b>Share</b>) against a target split (<b>Target</b>).
      ${d.targets_customized
        ? "Your targets are set — the <b>Drift</b> is how far each class is from where you want it."
        : `The targets start from a <b>📐 Model</b> — a textbook diversified allocation (e.g. real estate ~${d.rows.find((r) => r.key === "real_estate") ? (d.rows.find((r) => r.key === "real_estate").model) : 55}%, stocks/ETF ~${(d.rows.find((r) => r.key === "etf") || {}).model || 22}%), <b>not your own choice yet</b>. So the initial <b>Drift</b> is measured against that model. Edit the <b>Target</b> cells and Save to make them yours.`}
      Flags follow the 5/25 rule (rebalance at ±5pp absolute or 25% relative drift) and feed the Recommendations tab.
    </div>
    <div class="muted" style="margin-bottom:12px">Net wealth ${fmt.pln(d.total)} (real estate counted as equity net of loans).</div>

    ${d.leverage ? `<div class="card" style="margin-bottom:12px">
      <h3 style="margin-top:0">🏦 Debt vs value</h3>
      <div class="row" style="gap:24px;flex-wrap:wrap">
        <div><div class="muted">Debt / assets</div><div class="value">${d.leverage.debt_to_assets_pct}%</div>
          <div class="muted">${fmt.pln(d.leverage.debt_total)} / ${fmt.pln(d.leverage.assets_total)}</div></div>
        <div><div class="muted" title="mortgage balances / property values">Real-estate LTV</div><div class="value">${d.leverage.ltv_pct}%</div>
          <div class="muted">${fmt.pln(d.leverage.debt_total)} / ${fmt.pln(d.leverage.re_value)}</div></div>
        <div style="flex:1;min-width:260px"><canvas id="levChart" height="70"></canvas></div>
      </div>
      <div class="muted mt">A falling line = debt shrinking relative to wealth. Enter debt balances monthly in the strip — each entry adds a point.</div>
    </div>` : ""}
    <div class="grid cols-2">
      <div class="card"><h3>Wealth structure</h3><canvas id="allocChart" height="220"></canvas></div>
      <div class="card">
        <h3>Share vs target</h3>
        <div style="overflow-x:auto"><table>
          <thead><tr><th>Class</th><th style="text-align:right">Value</th>
            <th style="text-align:right">Share</th>
            <th style="text-align:right" title="Textbook model allocation — the starting reference">📐 Model</th>
            <th style="text-align:right" title="Your target — editable; starts from the model">Target</th>
            <th style="text-align:right">Drift</th></tr></thead>
          <tbody>${d.rows.map((r) => `<tr>
            <td>${r.label}</td>
            <td style="text-align:right">${fmt.pln(r.value)}</td>
            <td style="text-align:right"><b>${r.pct}%</b></td>
            <td style="text-align:right" class="muted">${r.model}%</td>
            <td style="text-align:right"><input data-num data-tgt="${r.key}" value="${r.target}" style="width:52px;text-align:right">%</td>
            <td style="text-align:right" class="${flagCls(r.flag)}">${r.drift > 0 ? "+" : ""}${r.drift} <span style="font-size:.85em">${r.flag}</span></td>
          </tr>`).join("")}</tbody>
        </table></div>
        <div class="row mt" style="justify-content:flex-end"><button class="primary" id="tgtSave">Save targets</button></div>
      </div>
    </div>

    <div class="card mt" style="border-left:4px solid var(--warn)">
      <h3 style="margin-top:0">💡 Takeaways and rebalancing</h3>
      <ul style="padding-left:18px">${d.hints.map((h) => `<li class="mt" style="font-size:.93em">${h}</li>`).join("")}</ul>
      <div class="muted mt" style="font-size:.85em">A vehicle counts as an asset here, but it is a consumable (it depreciates) — in reality "investment" wealth is usually more concentrated in real estate.</div>
    </div>`;

  const palette = ["var(--accent)", "var(--pos)", "var(--warn)", "var(--neg)", "var(--violet)", "#f59e0b"];
  trackChart(new Chart(document.getElementById("allocChart"), {
    type: "doughnut",
    data: {
      labels: d.rows.map((r) => r.label.replace(/^\S+\s/, "")),
      datasets: [{ data: d.rows.map((r) => r.value), backgroundColor: palette }],
    },
    options: { plugins: { legend: { position: "bottom", labels: { boxWidth: 12, font: { size: 11 } } } } },
  }));

  if (d.leverage && d.leverage.trend && d.leverage.trend.length > 1) {
    trackChart(new Chart(document.getElementById("levChart"), {
      type: "line",
      data: {
        labels: d.leverage.trend.map((t) => t.month),
        datasets: [{ label: "Debt / assets %", data: d.leverage.trend.map((t) => t.pct),
          borderColor: "var(--amber)", backgroundColor: "transparent", tension: 0.25 }],
      },
      options: { plugins: { legend: { display: false } },
        scales: { y: { ticks: { callback: (v) => v + "%" } } } },
    }));
  }

  document.getElementById("tgtSave").addEventListener("click", async () => {
    const t = {};
    el.querySelectorAll("[data-tgt]").forEach((inp) => { t[inp.dataset.tgt] = parseNum(inp) || 0; });
    await api.put("/api/settings", { alloc_targets: JSON.stringify(t) });
    route();
  });
}
