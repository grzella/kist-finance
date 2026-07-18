async function renderCashflow(el) {
  const d = await api.get("/api/cashflow");
  if (d.error) { el.innerHTML = `<div class="card">Error: ${d.error}</div>`; return; }
  const a = d.assumptions;
  const rows = d.rows;
  const last = rows[rows.length - 1];
  const at12 = rows[Math.min(11, rows.length - 1)];
  const anyBelow = rows.some((r) => r.below_buffer);

  el.innerHTML = `
    <h2>💧 Liquidity timeline — cash-flow over time</h2>
    <div class="muted" style="margin-bottom:12px">Base surplus + lumpy vests (from RSU) and the September bonus.
      Surplus above the safety buffer is swept into loan overpayment until payoff — then the liquid balance grows toward the goal contribution.</div>

    <div class="grid cols-4">
      <div class="card kpi"><div class="label">Loan paid off</div>
        <div class="value pos">${d.lodz_paid_month || "—"}</div>
        <div class="sub">start ${fmt.pln(d.lodz_start)} · after payoff surplus +${fmt.pln(d.lodz_freed_monthly)}/mo</div></div>
      <div class="card kpi"><div class="label">Liquid balance in 12 mo</div>
        <div class="value">${fmt.pln(at12.liquid)}</div>
        <div class="sub">${at12.month}</div></div>
      <div class="card kpi"><div class="label">Liquid balance in ${rows.length} mo</div>
        <div class="value">${fmt.pln(last.liquid)}</div>
        <div class="sub">${last.month} · toward the goal contribution</div></div>
      <div class="card kpi"><div class="label">Safety buffer</div>
        <div class="value ${anyBelow ? "neg" : ""}">${fmt.pln(d.buffer)}</div>
        <div class="sub">${anyBelow ? "⚠️ balance dips below in some month" : "balance never dips below ✓"}</div></div>
    </div>

    <div class="card mt">
      <h3>Assumptions (editable)</h3>
      <div class="row" style="flex-wrap:wrap;gap:12px">
        <label class="muted">Base surplus/mo<br><input data-num id="cfSurplus" value="${fmt.grouped(a.cf_monthly_surplus)}" style="width:140px"></label>
        <label class="muted">Safety buffer<br><input data-num id="cfBuffer" value="${fmt.grouped(a.cf_safety_buffer)}" style="width:140px"></label>
        <label class="muted">Starting liquid balance<br><input data-num id="cfStart" value="${fmt.grouped(a.cf_liquid_start)}" style="width:140px"></label>
        <label class="muted">Net bonus (September)<br><input data-num id="cfBonus" value="${fmt.grouped(a.annual_bonus_net)}" style="width:140px"></label>
        <button class="primary" id="cfSave" style="align-self:flex-end">Save and recompute</button>
      </div>
      <div class="muted mt" style="font-size:.85em">Vest computed automatically from the RSU tab (${a.vest_value_pln ? fmt.pln(a.vest_value_pln) + "/vest, months " + a.vest_months.join(", ") : "no RSU data"}).</div>
    </div>

    <div class="card mt">
      <h3>Liquid balance and loan balance over time</h3>
      <canvas id="cfChart" height="110"></canvas>
    </div>

    <div class="card mt">
      <h3>Month by month</h3>
      <div style="overflow-x:auto"><table>
        <thead><tr><th>Month</th><th style="text-align:right">Inflows</th>
          <th style="text-align:right">Loan overpayment</th><th style="text-align:right">Liquid balance</th>
          <th style="text-align:right">Loan balance</th></tr></thead>
        <tbody>${rows.map((r) => `<tr class="${r.below_buffer ? "cf-warn" : ""}">
          <td>${r.month} ${r.is_vest ? '<span class="badge">vest</span>' : ""}${r.is_bonus ? '<span class="badge">bonus</span>' : ""}</td>
          <td style="text-align:right" title="${r.inflow_parts}">${fmt.pln(r.inflow)}</td>
          <td style="text-align:right" class="${r.overpay_lodz > 0 ? "pos" : "muted"}">${r.overpay_lodz > 0 ? fmt.pln(r.overpay_lodz) : "—"}</td>
          <td style="text-align:right" class="${r.below_buffer ? "neg" : ""}"><b>${fmt.pln(r.liquid)}</b></td>
          <td style="text-align:right" class="${r.lodz_balance === 0 ? "pos" : "muted"}">${r.lodz_balance === 0 ? "paid off 🎉" : fmt.pln(r.lodz_balance)}</td>
        </tr>`).join("")}</tbody>
      </table></div>
    </div>`;

  trackChart(new Chart(document.getElementById("cfChart"), {
    type: "line",
    data: {
      labels: rows.map((r) => r.month),
      datasets: [
        { label: "Liquid balance", data: rows.map((r) => r.liquid),
          borderColor: CHART_COLORS[0], backgroundColor: "transparent", borderWidth: 3, tension: 0.2, pointRadius: 2 },
        { label: "Loan balance", data: rows.map((r) => r.lodz_balance),
          borderColor: CHART_COLORS[3], backgroundColor: "transparent", tension: 0.2, pointRadius: 0 },
        { label: "Buffer", data: rows.map(() => d.buffer),
          borderColor: "#888", borderDash: [4, 4], backgroundColor: "transparent", pointRadius: 0, borderWidth: 1 },
      ],
    },
    options: { scales: { y: { ticks: { callback: (v) => (v / 1000) + "k" } } } },
  }));

  document.getElementById("cfSave").addEventListener("click", async () => {
    await api.put("/api/settings", {
      cf_monthly_surplus: parseNum(document.getElementById("cfSurplus")),
      cf_safety_buffer: parseNum(document.getElementById("cfBuffer")),
      cf_liquid_start: parseNum(document.getElementById("cfStart")),
      annual_bonus_net: parseNum(document.getElementById("cfBonus")),
    });
    route();
  });
}
