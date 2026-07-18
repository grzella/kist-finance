async function renderDashboard(el) {
  const cfg = await appCfg();
  const bizOn = !cfg.enabled_views || cfg.enabled_views.includes("firma");
  const [sum, w, nw, rec, xtb, gs, biz, bizMkt] = await Promise.all([
    api.get("/api/dashboard/summary"),
    api.get("/api/wealth/summary"),
    api.get("/api/dashboard/net-worth-history"),
    api.get("/api/recommendation"),
    api.get("/api/recommendation/xtb"),
    api.get("/api/goal-scenarios"),
    api.get("/api/biz").catch(() => null),
    api.get("/api/biz/marketing").catch(() => ({ error: 1 })),
  ]);

  el.innerHTML = `
    <h2>Dashboard — ${sum.month}</h2>
    <details class="card" style="border-left:4px solid ${CHART_COLORS[2]}">
      <summary style="cursor:pointer"><b>💡 ${rec.headline.length > 140 ? rec.headline.slice(0, 140) + "…" : rec.headline}</b>
        <span class="muted">(${rec.items.length} recommendations — expand / full list in the Recommendations tab)</span></summary>
      <ul class="muted mt" style="padding-left:18px">
        ${rec.items.map((r) => `<li class="mt"><b>[${r.area}]</b> ${r.text}</li>`).join("")}
      </ul>
    </details>
    ${xtb.headline ? `<details class="card mt" style="border-left:4px solid ${CHART_COLORS[4]}">
      <summary style="cursor:pointer"><b>📈 XTB (${fmt.pln(xtb.facts.total)}):</b>
        ${xtb.headline.length > 120 ? xtb.headline.slice(0, 120) + "…" : xtb.headline}
        <span class="muted">(expand)</span></summary>
      <ul class="muted mt" style="padding-left:18px">
        ${xtb.items.map((r) => `<li class="mt"><b>[${r.area}]</b> ${r.text}</li>`).join("")}
      </ul>
      <div class="muted mt">Themes: ${Object.entries(xtb.facts.themes).map(([k, v]) => `${k} ${v}%`).join(" · ")}</div>
    </details>` : ""}
    ${gs.goal ? `<div class="card mt" style="border-left:4px solid ${CHART_COLORS[1]}">
      <h3 style="margin-top:0">🎯 ${gs.goal} — path to goal (${fmt.pln(gs.target_remaining)} to go, pace ${fmt.pln(gs.monthly_savings)}/mo)</h3>
      ${gs.extras ? `<div class="muted">Pace = savings ${fmt.pln(gs.base_savings)} + annual bonus ${fmt.pln(gs.extras.bonus_net)}/12 + RSU vests ${fmt.pln(gs.extras.rsu_annual)}/12 (${gs.extras.pct_to_goal}% of surplus toward the goal)</div>` : ""}
      <table><thead><tr><th>Scenario</th><th>Goal reached</th><th>Time</th><th>Loan paid off</th><th>Interest saved</th></tr></thead>
      <tbody>${gs.scenarios.map((sc) => `<tr>
        <td>${sc.label}</td>
        <td>${sc.eta || "—"}</td>
        <td>${sc.years ? sc.years + " yrs" : "—"}</td>
        <td>${sc.payoff_month ? "after " + sc.payoff_month + " mo" : "—"}</td>
        <td class="pos">${sc.interest_saved != null ? fmt.pln(sc.interest_saved) : "—"}</td>
      </tr>`).join("")}</tbody></table>
      <div class="muted mt">Month-by-month simulation: in the overpayment scenarios all free funds go into the loan first
        (effective interest rate); after payoff the freed installment + insurance feed the goal.</div>
    </div>` : ""}
    ${bizOn && biz ? `<details class="card mt" style="border-left:4px solid ${CHART_COLORS[6]}">
      <summary style="cursor:pointer"><b>🚁 Business:</b>
        result since launch <b class="${biz.total_result >= 0 ? "pos" : "neg"}">${fmt.pln(biz.total_result)}</b>
        ${!bizMkt.error && bizMkt.weeks.length ? `· last week of ads: €${bizMkt.weeks[0].spend_eur}
          <span class="muted">${(bizMkt.weeks[0].summary || "").slice(0, 90)}…</span>` : ""}
        <span class="muted">(expand)</span></summary>
      <div class="row mt" style="gap:20px;flex-wrap:wrap">
        <span>This month: <b class="neg">${fmt.pln((biz.current.przychody || 0) - (biz.current.koszty || 0))}</b></span>
        <span>Invested: <b>${fmt.pln(biz.total_cost)}</b></span>
        <span>Revenue: <b>${fmt.pln(biz.total_revenue)}</b></span>
        <span class="muted">goal: 1 job/mo · launch: August</span>
      </div>
      ${!bizMkt.error && bizMkt.weeks.length && bizMkt.weeks[0].recommendation ?
        `<div class="mt">💡 <b>Marketing (week):</b> ${bizMkt.weeks[0].recommendation}</div>` : ""}
    </details>` : ""}
    <div class="grid cols-4">
      <div class="card kpi"><div class="label">Net worth</div>
        <div class="value">${fmt.pln(sum.net_worth)}</div>
        <div class="sub">cash ${fmt.pln(sum.cash_total)} · investments ${fmt.pln(sum.investments_total)} · debt −${fmt.pln(sum.debt_total)}</div></div>
      <div class="card kpi"><div class="label">Income / mo</div>
        <div class="value pos">${fmt.pln(sum.planned_income)}</div>
        <div class="sub">avg net salary + rent</div></div>
      <div class="card kpi"><div class="label">Costs / mo</div>
        <div class="value neg">${fmt.pln(sum.planned_costs)}</div>
        <div class="sub">of which essential ${fmt.pln(sum.planned_essential)}</div></div>
      <div class="card kpi"><div class="label">Surplus / mo</div>
        <div class="value ${sum.planned_surplus > 0 ? "pos" : "warn"}">${fmt.pln(sum.planned_surplus)}</div>
        <div class="sub">+ Sep bonus and RSU vests (Feb/May/Aug/Nov) on top</div></div>
    </div>
    <div class="grid cols-2 mt">
      <div class="card"><h3>Monthly costs by category${sum.planned_categories && sum.planned_categories.length ? " (fixed plan)" : ""}</h3><canvas id="catChart"></canvas></div>
      <div class="card"><h3>Wealth over time — assets and net of loans</h3><canvas id="trendChart"></canvas></div>
    </div>
`;

  const cats = (sum.planned_categories && sum.planned_categories.length)
    ? sum.planned_categories : sum.expenses_by_category;
  if (cats.length) {
    trackChart(new Chart(document.getElementById("catChart"), {
      type: "doughnut",
      data: {
        labels: cats.map((c) => c.category),
        datasets: [{ data: cats.map((c) => c.total), backgroundColor: CHART_COLORS }],
      },
      options: { plugins: { legend: { position: "right" } } },
    }));
  }

  const wTrend = (w.trend || []).filter((t) => t.total);
  const nwByMonth = {};
  nw.forEach((s2) => { nwByMonth[(s2.date || "").slice(0, 7)] = s2.net_worth; });
  const months = [...new Set([...wTrend.map((t) => t.month), ...Object.keys(nwByMonth)])].sort();
  const wByMonth = {};
  wTrend.forEach((t) => { wByMonth[t.month] = t.total; });
  trackChart(new Chart(document.getElementById("trendChart"), {
    type: "line",
    data: {
      labels: months,
      datasets: [
        { label: "Assets", data: months.map((m) => wByMonth[m] ?? null),
          borderColor: "#3ecf8e", backgroundColor: "transparent", tension: 0.25, pointRadius: 3 },
        { label: "Net (after loans)", data: months.map((m) => nwByMonth[m] ?? null),
          borderColor: "#4c8dff", backgroundColor: "transparent", tension: 0.25, pointRadius: 3, borderWidth: 3 },
      ],
    },
  }));


}
