async function renderCashflow(el) {
  const d = await api.get("/api/cashflow");
  if (d.error) { el.innerHTML = `<div class="card">Error: ${d.error}</div>`; return; }
  const a = d.assumptions;
  const rows = d.rows;
  const last = rows[rows.length - 1];
  const at12 = rows[Math.min(11, rows.length - 1)];
  const anyBelow = rows.some((r) => r.below_buffer);
  const debt = d.sweep_mode === "debt";  // surplus overpays a loan

  el.innerHTML = `
    <h2>💧 Liquidity timeline — cash-flow over time</h2>
    <div class="muted" style="margin-bottom:12px">Monthly savings (base) + <b>net</b> vests from the grant schedule (× 1 − ${a.tax_pct}%) + net cash-vest + bonus.
      ${debt ? `Surplus above the buffer overpays <b>${d.sweep_target_name}</b> until payoff — then the liquid balance grows toward the goal.` : `Loan overpayments from surplus are off, so the whole surplus stays in cash and the liquid balance grows.`}
      The tax reserve on sold shares is tracked separately — it is not your liquidity.</div>

    <div class="grid cols-4">
      <div class="card kpi"><div class="label">${debt ? d.sweep_target_name + " paid off" : "Loan overpayments"}</div>
        <div class="value ${debt ? "pos" : ""}">${debt ? (d.target_paid_month || "beyond horizon") : "off"}</div>
        <div class="sub">${debt ? `start ${fmt.pln(d.target_start)} · after payoff surplus +${fmt.pln(d.target_freed_monthly)}/mo` : "the surplus stays in cash"}</div></div>
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
        <label class="muted">Monthly savings (base) ${d.surplus_source === "dashboard" ? `<span class="badge pos" title="income minus fixed costs, as on the Dashboard">auto from dashboard</span>` : `<span class="badge" title="entered manually; clear to compute from the dashboard">manual</span>`}<br><input data-num id="cfSurplus" value="${d.surplus_source === "manual" ? fmt.grouped(a.cf_monthly_surplus) : ""}" placeholder="auto: ${fmt.grouped(a.cf_monthly_surplus)}" style="width:140px"></label>
        <label class="muted">Safety buffer<br><input data-num id="cfBuffer" value="${fmt.grouped(a.cf_safety_buffer)}" style="width:140px"></label>
        <label class="muted">Starting liquid balance ${d.liquid_start_source === "wealth" ? `<span class="badge pos" title="sum of cash from Wealth">auto from wealth</span>` : `<span class="badge" title="entered manually; clear to compute from wealth">manual</span>`}<br><input data-num id="cfStart" value="${a.cf_liquid_start ? fmt.grouped(a.cf_liquid_start) : ""}" placeholder="auto: ${fmt.grouped(d.liquid_start_auto || 0)}" style="width:140px"></label>
        <label class="muted" title="Name (or part of it) of the loan to overpay with surplus above the buffer; &quot;debt&quot; = the most expensive one; &quot;none&quot; = don't overpay">Overpay this loan with surplus<br><input id="cfSweep" value="${a.cf_sweep_target || ""}" placeholder="loan / debt / none" style="width:140px"></label>
        <label class="muted">Net bonus (configured month)<br><input data-num id="cfBonus" value="${fmt.grouped(a.annual_bonus_net)}" style="width:140px"></label>
        <button class="primary" id="cfSave" style="align-self:flex-end">Save and recompute</button>
      </div>
      <div class="muted mt" style="font-size:.85em">Vests from the grant schedule in the RSU tab (next ${a.vest_value_pln ? fmt.pln(a.vest_value_pln) + " net" : "—"}; months ${a.vest_months.join(", ")}); net factors: shares ${Math.round(a.net_factor * 100)}%, cash-vest ${Math.round(a.cash_vest_net_factor * 100)}%. Tax reserve at the end of the horizon: <b>${fmt.pln(d.tax_reserve_total)}</b>.</div>
    </div>

    <div class="card mt">
      <h3>${debt ? "Liquid balance and loan balance over time" : "Liquid balance over time"}</h3>
      <canvas id="cfChart" height="110"></canvas>
    </div>

    <div class="card mt">
      <h3>Month by month</h3>
      <div style="overflow-x:auto"><table>
        <thead><tr><th>Month</th><th style="text-align:right">Inflows (net)</th>
          ${debt ? `<th style="text-align:right">Overpayment ${d.sweep_target_name}</th>` : ""}<th style="text-align:right">Liquid balance</th>
          <th style="text-align:right">Tax reserve</th>${debt ? '<th style="text-align:right">Loan balance</th>' : ""}</tr></thead>
        <tbody>${rows.map((r) => `<tr class="${r.below_buffer ? "cf-warn" : ""}">
          <td>${r.month} ${r.is_vest ? '<span class="badge">vest</span>' : ""}${r.is_bonus ? '<span class="badge">bonus</span>' : ""}</td>
          <td style="text-align:right" title="${r.inflow_parts}">${fmt.pln(r.inflow)}</td>
          ${debt ? `<td style="text-align:right" class="${r.overpay > 0 ? "pos" : "muted"}">${r.overpay > 0 ? fmt.pln(r.overpay) : "—"}</td>` : ""}
          <td style="text-align:right" class="${r.below_buffer ? "neg" : ""}"><b>${fmt.pln(r.liquid)}</b></td>
          <td style="text-align:right" class="muted">${r.tax_reserve ? fmt.pln(r.tax_reserve) : "—"}</td>
          ${debt ? `<td style="text-align:right" class="${r.target_balance === 0 ? "pos" : "muted"}">${r.target_balance === 0 ? "paid off 🎉" : fmt.pln(r.target_balance)}</td>` : ""}
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
        ...(debt ? [{ label: d.sweep_target_name + " balance", data: rows.map((r) => r.target_balance),
          borderColor: CHART_COLORS[3], backgroundColor: "transparent", tension: 0.2 }] : []),
        { label: "Buffer", data: rows.map(() => d.buffer),
          borderColor: "#888", borderDash: [4, 4], backgroundColor: "transparent", borderWidth: 1 },
      ],
    },
    options: { scales: { y: { ticks: { callback: (v) => (v / 1000) + "k" } } } },
  }));

  document.getElementById("cfSave").addEventListener("click", async () => {
    await api.put("/api/settings", {
      cf_monthly_surplus: isNaN(parseNum(document.getElementById("cfSurplus"))) ? "" : parseNum(document.getElementById("cfSurplus")),
      cf_safety_buffer: parseNum(document.getElementById("cfBuffer")),
      cf_liquid_start: isNaN(parseNum(document.getElementById("cfStart"))) ? "" : parseNum(document.getElementById("cfStart")),
      cf_sweep_target: document.getElementById("cfSweep").value.trim() || "none",
      annual_bonus_net: parseNum(document.getElementById("cfBonus")),
    });
    route();
  });
}
