async function renderAllocation(el) {
  const d = await api.get("/api/allocation");
  const flagCls = (f) => f === "too much" ? "neg" : f === "add more" ? "pos" : "muted";
  el.innerHTML = `
    <h2>📊 Asset allocation — structure and concentration</h2>
    <div class="muted" style="margin-bottom:12px">Net wealth ${fmt.pln(d.total)} (real estate counted as equity net of loans).
      Targets are indicative desired shares — editable in code (ALLOC_TARGETS).</div>

    <div class="grid cols-2">
      <div class="card"><h3>Wealth structure</h3><canvas id="allocChart" height="220"></canvas></div>
      <div class="card">
        <h3>Share vs target</h3>
        <div style="overflow-x:auto"><table>
          <thead><tr><th>Class</th><th style="text-align:right">Value</th>
            <th style="text-align:right">Share</th><th style="text-align:right">Target</th><th style="text-align:right">Drift</th></tr></thead>
          <tbody>${d.rows.map((r) => `<tr>
            <td>${r.label}</td>
            <td style="text-align:right">${fmt.pln(r.value)}</td>
            <td style="text-align:right"><b>${r.pct}%</b></td>
            <td style="text-align:right" class="muted">${r.target}%</td>
            <td style="text-align:right" class="${flagCls(r.flag)}">${r.drift > 0 ? "+" : ""}${r.drift} <span style="font-size:.85em">${r.flag}</span></td>
          </tr>`).join("")}</tbody>
        </table></div>
      </div>
    </div>

    <div class="card mt" style="border-left:4px solid #ffd166">
      <h3 style="margin-top:0">💡 Takeaways and rebalancing</h3>
      <ul style="padding-left:18px">${d.hints.map((h) => `<li class="mt" style="font-size:.93em">${h}</li>`).join("")}</ul>
      <div class="muted mt" style="font-size:.85em">The car (car) is counted as an asset, but it is a consumable (depreciates) — in reality "investment" wealth is more concentrated in real estate.</div>
    </div>`;

  const palette = ["#4c8dff", "#3ecf8e", "#ffd166", "#ff6b6b", "#a78bfa", "#f59e0b"];
  trackChart(new Chart(document.getElementById("allocChart"), {
    type: "doughnut",
    data: {
      labels: d.rows.map((r) => r.label.replace(/^\S+\s/, "")),
      datasets: [{ data: d.rows.map((r) => r.value), backgroundColor: palette }],
    },
    options: { plugins: { legend: { position: "bottom", labels: { boxWidth: 12, font: { size: 11 } } } } },
  }));
}
