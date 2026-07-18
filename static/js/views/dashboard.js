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
        <span class="muted">(${rec.items.length} rekomendacji — rozwiń / pełne w zakładce Rekomendacje)</span></summary>
      <ul class="muted mt" style="padding-left:18px">
        ${rec.items.map((r) => `<li class="mt"><b>[${r.area}]</b> ${r.text}</li>`).join("")}
      </ul>
    </details>
    ${xtb.headline ? `<details class="card mt" style="border-left:4px solid ${CHART_COLORS[4]}">
      <summary style="cursor:pointer"><b>📈 brokerage (${fmt.pln(xtb.facts.total)}):</b>
        ${xtb.headline.length > 120 ? xtb.headline.slice(0, 120) + "…" : xtb.headline}
        <span class="muted">(rozwiń)</span></summary>
      <ul class="muted mt" style="padding-left:18px">
        ${xtb.items.map((r) => `<li class="mt"><b>[${r.area}]</b> ${r.text}</li>`).join("")}
      </ul>
      <div class="muted mt">Motywy: ${Object.entries(xtb.facts.themes).map(([k, v]) => `${k} ${v}%`).join(" · ")}</div>
    </details>` : ""}
    ${gs.goal ? `<div class="card mt" style="border-left:4px solid ${CHART_COLORS[1]}">
      <h3 style="margin-top:0">🎯 ${gs.goal} — droga do celu (brakuje ${fmt.pln(gs.target_remaining)}, tempo ${fmt.pln(gs.monthly_savings)}/mies.)</h3>
      ${gs.extras ? `<div class="muted">Tempo = oszczędności ${fmt.pln(gs.base_savings)} + bonus roczny ${fmt.pln(gs.extras.bonus_net)}/12 + vesty RSU ${fmt.pln(gs.extras.rsu_annual)}/12 (${gs.extras.pct_to_goal}% nadwyżek na cel)</div>` : ""}
      <table><thead><tr><th>Scenariusz</th><th>Cel osiągnięty</th><th>Czas</th><th>Kredyt spłacony</th><th>Odsetki oszczędzone</th></tr></thead>
      <tbody>${gs.scenarios.map((sc) => `<tr>
        <td>${sc.label}</td>
        <td>${sc.eta || "—"}</td>
        <td>${sc.years ? sc.years + " lat" : "—"}</td>
        <td>${sc.payoff_month ? "po " + sc.payoff_month + " mies." : "—"}</td>
        <td class="pos">${sc.interest_saved != null ? fmt.pln(sc.interest_saved) : "—"}</td>
      </tr>`).join("")}</tbody></table>
      <div class="muted mt">Symulacja mies. po mies.: w scenariuszach nadpłat całe wolne środki idą najpierw w kredyt
        (efektywne oprocentowanie), po spłacie uwolniona rata + ubezpieczenia zasilają cel.</div>
    </div>` : ""}
    ${bizOn && biz ? `<details class="card mt" style="border-left:4px solid ${CHART_COLORS[6]}">
      <summary style="cursor:pointer"><b>🚁 Firma działalności:</b>
        wynik od startu <b class="${biz.total_result >= 0 ? "pos" : "neg"}">${fmt.pln(biz.total_result)}</b>
        ${!bizMkt.error && bizMkt.weeks.length ? `· ostatni tydzień ads: €${bizMkt.weeks[0].spend_eur}
          <span class="muted">${(bizMkt.weeks[0].summary || "").slice(0, 90)}…</span>` : ""}
        <span class="muted">(rozwiń)</span></summary>
      <div class="row mt" style="gap:20px;flex-wrap:wrap">
        <span>Ten mies.: <b class="neg">${fmt.pln((biz.current.przychody || 0) - (biz.current.koszty || 0))}</b></span>
        <span>Zainwestowane: <b>${fmt.pln(biz.total_cost)}</b></span>
        <span>Przychody: <b>${fmt.pln(biz.total_revenue)}</b></span>
        <span class="muted">cel: 1 zlecenie/mies. · launch: sierpień</span>
      </div>
      ${!bizMkt.error && bizMkt.weeks.length && bizMkt.weeks[0].recommendation ?
        `<div class="mt">💡 <b>Marketing (tydzień):</b> ${bizMkt.weeks[0].recommendation}</div>` : ""}
    </details>` : ""}
    <div class="grid cols-4">
      <div class="card kpi"><div class="label">Wartość netto</div>
        <div class="value">${fmt.pln(sum.net_worth)}</div>
        <div class="sub">gotówka ${fmt.pln(sum.cash_total)} · inwestycje ${fmt.pln(sum.investments_total)} · dług −${fmt.pln(sum.debt_total)}</div></div>
      <div class="card kpi"><div class="label">Dochody / mies.</div>
        <div class="value pos">${fmt.pln(sum.planned_income)}</div>
        <div class="sub">pensja netto śr. + najem</div></div>
      <div class="card kpi"><div class="label">Koszty / mies.</div>
        <div class="value neg">${fmt.pln(sum.planned_costs)}</div>
        <div class="sub">w tym niezbędne ${fmt.pln(sum.planned_essential)}</div></div>
      <div class="card kpi"><div class="label">Nadwyżka / mies.</div>
        <div class="value ${sum.planned_surplus > 0 ? "pos" : "warn"}">${fmt.pln(sum.planned_surplus)}</div>
        <div class="sub">+ bonus IX i vesty RSU (II/V/VIII/XI) ponad to</div></div>
    </div>
    <div class="grid cols-2 mt">
      <div class="card"><h3>Koszty mies. wg kategorii${sum.planned_categories && sum.planned_categories.length ? " (plan stały)" : ""}</h3><canvas id="catChart"></canvas></div>
      <div class="card"><h3>Majątek w czasie — aktywa i netto po kredytach</h3><canvas id="trendChart"></canvas></div>
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
        { label: "Aktywa", data: months.map((m) => wByMonth[m] ?? null),
          borderColor: "#3ecf8e", backgroundColor: "transparent", tension: 0.25, pointRadius: 3 },
        { label: "Netto (po kredytach)", data: months.map((m) => nwByMonth[m] ?? null),
          borderColor: "#4c8dff", backgroundColor: "transparent", tension: 0.25, pointRadius: 3, borderWidth: 3 },
      ],
    },
  }));


}
