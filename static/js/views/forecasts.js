async function renderForecasts(el) {
  el.innerHTML = '<div class="empty">Computing scenarios…</div>';
  const [debtsData, rsu, cfg, sum, fire, stress] = await Promise.all([
    api.get("/api/debts"), api.get("/api/rsu"),
    api.get("/api/settings"), api.get("/api/dashboard/summary"),
    api.get("/api/fire-projection").catch(() => null),
    api.get("/api/stress-test").catch(() => null)]);

  const loan = debtsData.debts.find((d) => d.balance > 0);
  const secondLoan = debtsData.debts.filter((d) => d.balance > 0)[1];
  const vestPln = rsu.next_vest_value_pln || 0;

  async function overpay(debt, amount) {
    if (!debt || amount >= debt.balance) return null;
    return api.post("/api/forecast/mortgage", {
      balance: debt.balance,
      monthly_payment: debt.minimum_payment,
      months_left: debt.months_left || debt.schedule.months,
      overpayment: amount,
    });
  }

  const bonus = +cfg.annual_bonus_net || 20000;
  const [bonusLoan, vestLoan, bothLoan] = await Promise.all([
    overpay(loan, bonus), overpay(loan, vestPln), overpay(loan, bonus + vestPln)]);

  const refiSavYr = secondLoan ? secondLoan.balance * 1.0 / 100 : 0;  // example: −1.0 pp
  const loanFreed = loan ? loan.monthly_cost_total : 0;

  const scenarioCard = (title, rows, note) => `
    <div class="card">
      <h3>${title}</h3>
      <table>${rows.map(([k, v, cls]) => `<tr><td>${k}</td><td class="${cls || ""}"><b>${v}</b></td></tr>`).join("")}</table>
      ${note ? `<div class="muted mt">${note}</div>` : ""}
    </div>`;

  const ym = (m) => {
    const mm = Math.round(m);
    const y = Math.floor(mm / 12), rest = mm % 12;
    return y ? `${y} ${y === 1 ? "yr" : "yrs"}${rest ? ` ${rest} mo` : ""}` : `${rest} mo`;
  };
  const op = (r) => r ? [
    ["Left to pay off", `${ym(r.months_left_after)} (instead of ${ym(r.months_left_now)})`, "pos"],
    ["Interest saved", fmt.pln(r.interest_saved), "pos"],
    ["Shortened by", ym(r.months_saved)],
  ] : [["—", "the overpayment covers the whole balance — loan paid off 🎉", "pos"]];

  el.innerHTML = `
    <h2>Forecasts — your scenarios</h2>
    <div class="muted" style="margin-bottom:12px">Computed on live data: loan balances,
      the RSU stock price, savings pace. Amounts come from your settings (e.g. annual_bonus_net).</div>
    <div class="grid cols-2">
      ${scenarioCard(`Annual bonus (~${fmt.pln(bonus)}) → loan overpayment`, op(bonusLoan),
        loan ? `Loan balance: ${fmt.pln(loan.balance)} · installment ${fmt.pln(loan.minimum_payment)}` : "")}
      ${scenarioCard(`Next vest of ${rsu.shares_next_vest} shares (≈${fmt.pln(vestPln)}) → loan overpayment`, op(vestLoan),
        "Sell at vest — capital gains tax only on the gain after vest (≈0 when selling right away)")}
      ${scenarioCard("Vest + bonus combined (≈" + fmt.pln(bonus + vestPln) + ") → loan", op(bothLoan),
        bothLoan ? "" : "This combination covers the whole balance — loan paid off 🎉")}
      ${scenarioCard(`Refinance/annex scenario${secondLoan ? " for " + secondLoan.name : ""}: rate −1.0 pp`, [
        ["Savings per year (example)", fmt.pln(refiSavYr), "pos"],
        ["Over ~18 months", fmt.pln(refiSavYr * 1.5), "pos"],
        ["Capital involved", "0"],
      ], "Playbook: collect real competing offers → ask your bank's retention team to match")}
      ${scenarioCard("After the loan is paid off — what gets freed", [
        ["Installment + insurance", fmt.pln(loanFreed) + "/mo", "pos"],
        ["Property unencumbered", "yes — profile ready for a property mortgage"],
      ], "From this moment all surpluses build the goal contribution")}
    </div>

    ${fire ? `<div class="card mt" style="border-left:4px solid #3ecf8e">
      <h3 style="margin-top:0">🏁 Path to work-optional (${fmt.pln(fire.target)} liquid portfolio)</h3>
      <div class="muted" style="font-size:.88em;margin-bottom:8px">
        Liquid portfolio today ${fmt.pln(fire.start)} → target ${fmt.pln(fire.target)}. Contribution: ${fire.assumptions.contrib_note}.
        Three return scenarios + the target line. When a line crosses the target = you are work-optional.</div>
      <div class="grid cols-4">
        <div class="card kpi"><div class="label">Cautious (4%)</div><div class="value">${(fire.crossover["cautious (4%)"] || "—").slice(0, 7)}</div></div>
        <div class="card kpi"><div class="label">Base (6.5%)</div><div class="value pos">${(fire.crossover["base (6.5%)"] || "—").slice(0, 7)}</div></div>
        <div class="card kpi"><div class="label">Optimistic (9%)</div><div class="value">${(fire.crossover["optimistic (9%)"] || "—").slice(0, 7)}</div></div>
        <div class="card kpi"><div class="label">Real (after 3% inflation)</div><div class="value">${(fire.real_crossover || "—").slice(0, 7)}</div><div class="sub">purchasing power</div></div>
      </div>
      <canvas id="fireChart" height="90" class="mt"></canvas>
      <div class="mt"><b>Milestones (base scenario):</b>
        <table><tbody>
          <tr><td>First liquid million</td><td><b>${fire.milestones["1000000"] || "—"}</b></td></tr>
          <tr><td>2M</td><td><b>${fire.milestones["660000"] || "—"}</b></td></tr>
          <tr><td>${fmt.pln(fire.target)} — work-optional 🏁</td><td class="pos"><b>${fire.milestones[String(fire.target)] || fire.crossover || "—"}</b></td></tr>
        </tbody></table></div>
      <div class="muted mt" style="font-size:.82em">This replaces Monte Carlo with readable lines. Hover over the chart to see the value in a given month. "Real" uses the after-inflation return (~3.5% real) — the date in today's purchasing power.</div>
    </div>

    <div class="grid cols-2 mt">
      ${fire.property ? `<div class="card" style="border-left:4px solid #e0a458">
        <h3 style="margin-top:0">Goal contribution (house)</h3>
        <table>
          <tr><td>Down-payment target (50%)</td><td><b>${fmt.pln(fire.property.target)}</b></td></tr>
          <tr><td>Saved so far</td><td>${fmt.pln(fire.property.start)}</td></tr>
          <tr><td>Down payment ready (starts after loan payoff)</td><td class="pos"><b>${fire.property.crossover || "—"}</b></td></tr>
        </table>
        <canvas id="propertyChart" height="70" class="mt"></canvas>
        <div class="muted mt" style="font-size:.82em">${fire.property.note}</div>
      </div>` : ""}

    ${stress ? `<div class="card mt" style="border-left:4px solid #ff8c66">
      <h3 style="margin-top:0">🧯 Stress test — financial fire drill</h3>
      <div class="muted" style="font-size:.85em;margin-bottom:8px">Deterministic what-ifs computed from your data (no simulation, no AI). The point: know the answers <i>before</i> markets ask the questions.</div>
      <div class="grid cols-3">
        ${stress.scenarios.map((sc) => `<div class="card" style="margin:0">
          <div class="row" style="justify-content:space-between"><b>${sc.icon} ${sc.title}</b><b class="neg">${sc.impact}</b></div>
          <div class="muted mt" style="font-size:.85em">${sc.detail}</div>
        </div>`).join("")}
      </div>
      ${stress.policy ? `<div class="mt" style="padding:8px 12px;background:#00000022;border-radius:6px;font-size:.9em">
        <b>🛡️ Withdrawal policy (Guyton-Klinger guardrails):</b> ${stress.policy.verdict}
        ${stress.policy.current_pct != null ? `<div class="muted mt" style="font-size:.9em">Start rate ${stress.policy.initial_pct}% · guardrails ${stress.policy.lower_pct}–${stress.policy.upper_pct}% · portfolio ${fmt.pln(stress.policy.portfolio)} · essential spend ${fmt.pln(stress.policy.annual_spend)}/yr${stress.policy.portfolio_needed ? ` · calm-start portfolio ${fmt.pln(stress.policy.portfolio_needed)}` : ""}</div>` : ""}
      </div>` : ""}
    </div>` : ""}

      ${fire.tracking ? `<div class="card" style="border-left:4px solid #4c8dff">
        <h3 style="margin-top:0">📡 Progress vs plan (learning every month)</h3>
        ${fire.tracking.status === "ok" ? `
          <div style="font-size:1.05em"><b class="${fire.tracking.cum_delta >= 0 ? "pos" : "neg"}">${fire.tracking.verdict}</b>
            — total ${fire.tracking.cum_delta >= 0 ? "+" : ""}${fmt.pln(fire.tracking.cum_delta)} vs plan</div>
          <div class="muted" style="font-size:.85em;margin:6px 0">Liquid portfolio: ${fmt.pln(fire.tracking.latest_liquid)} · tracking for ${fire.tracking.months_tracked} mo</div>
          <table><thead><tr><th>Mo</th><th style="text-align:right">Actual growth</th><th style="text-align:right">Plan</th><th style="text-align:right">Δ</th></tr></thead>
          <tbody>${fire.tracking.rows.map((r) => `<tr><td>${r.month}</td>
            <td style="text-align:right">${fmt.pln(r.actual_growth)}</td>
            <td style="text-align:right" class="muted">${fmt.pln(r.expected_growth)}</td>
            <td style="text-align:right" class="${r.delta >= 0 ? "pos" : "neg"}">${r.delta >= 0 ? "+" : ""}${fmt.pln(r.delta)}</td></tr>`).join("")}</tbody></table>`
        : `<div class="muted">${fire.tracking.status === "collecting data" ? `Collecting data — first snapshot ${fire.tracking.first || "today"}. In a month the first comparison of the actual pace vs the plan will appear.` : "No data."}</div>
          <div class="muted mt" style="font-size:.85em">Every month the liquid portfolio balance is recorded and compared with the expected pace (6.5% + contributions). You will see whether you are ahead of or behind the plan.</div>`}
      </div>` : ""}
    </div>` : ""}

    <div class="card mt">
      <h3>Overpayment calculator — any variant</h3>
      <div class="row">
        <select id="mDebt">${debtsData.debts.map((d) => `<option value="${d.id}">${d.name}</option>`).join("")}</select>
        <input data-num id="mOver" placeholder="overpayment amount">
        <button class="primary" id="mRun">Compute</button>
      </div>
      <div id="mOut" class="mt"></div>
    </div>`;

  document.getElementById("mRun").addEventListener("click", async () => {
    const debt = debtsData.debts.find((d) => d.id === document.getElementById("mDebt").value);
    const amount = parseNum(document.getElementById("mOver"));
    if (!debt || isNaN(amount)) { alert("Enter an amount"); return; }
    const r = await overpay(debt, amount);
    document.getElementById("mOut").innerHTML = r
      ? `<table>${op(r).map(([k, v, c]) => `<tr><td>${k}</td><td class="${c || ""}"><b>${v}</b></td></tr>`).join("")}</table>`
      : '<span class="pos"><b>The overpayment covers the whole balance — loan paid off 🎉</b></span>';
  });

  if (fire && document.getElementById("fireChart")) {
    const names = Object.keys(fire.series);
    const colors = { 0: CHART_COLORS[3], 1: CHART_COLORS[0], 2: CHART_COLORS[1] };
    trackChart(new Chart(document.getElementById("fireChart"), {
      type: "line",
      data: {
        labels: fire.labels,
        datasets: [
          ...names.map((n, i) => ({
            label: n, data: fire.series[n], borderColor: colors[i],
            backgroundColor: "transparent", borderWidth: i === 1 ? 3 : 2, pointRadius: 0, tension: 0.2,
          })),
          { label: "target", data: fire.labels.map(() => fire.target),
            borderColor: "#888", borderDash: [6, 4], pointRadius: 0, borderWidth: 1 },
        ],
      },
      options: {
        interaction: { mode: "index", intersect: false },
        plugins: { tooltip: { callbacks: {
          title: (items) => items[0].label,
          label: (ctx) => `${ctx.dataset.label}: ${fmt.pln(ctx.parsed.y)}`,
        } } },
        scales: { y: { ticks: { callback: (v) => (v / 1000000).toFixed(1) + "M" } } },
      },
    }));
  }
  if (fire && fire.property && document.getElementById("propertyChart")) {
    const yrs = fire.property.series.map((_, i) => `${new Date().getFullYear() + i}`);
    trackChart(new Chart(document.getElementById("propertyChart"), {
      type: "line",
      data: {
        labels: yrs,
        datasets: [
          { label: "Saved so far", data: fire.property.series, borderColor: CHART_COLORS[4],
            backgroundColor: "transparent", borderWidth: 3, pointRadius: 2, tension: 0.2 },
          { label: "down-payment target", data: yrs.map(() => fire.property.target),
            borderColor: "#888", borderDash: [6, 4], pointRadius: 0, borderWidth: 1 },
        ],
      },
      options: {
        interaction: { mode: "index", intersect: false },
        plugins: { legend: { display: false }, tooltip: { callbacks: {
          label: (ctx) => `${ctx.dataset.label}: ${fmt.pln(ctx.parsed.y)}`,
        } } },
        scales: { y: { ticks: { callback: (v) => (v / 1000) + "k" } } },
      },
    }));
  }
}
