async function renderItaly(el) {
  const [a, goals, eurplnRes] = await Promise.all([
    api.get("/api/analysis/italy_location").catch(() => ({})),
    api.get("/api/goals").catch(() => []),
    api.get("/api/market/analytics/EURPLN=X").catch(() => ({}))]);
  const eurpln = eurplnRes.last_close || 4.34;

  if (!a.headline) {
    el.innerHTML = '<div class="card"><h2>Italy — location analysis</h2>'
      + '<div class="muted">No saved analysis. Ask Claude: "refresh the Italy location analysis".</div></div>';
    return;
  }

  const italyGoal = (goals || []).find((g) => /wło|italy|garda/i.test(g.name));
  const dots = (n) => '<span style="letter-spacing:2px">'
    + "●".repeat(n) + '<span class="muted">' + "○".repeat(5 - n) + "</span></span>";
  const scoreColor = (n) => n >= 5 ? "pos" : n >= 4 ? "" : n >= 3 ? "muted" : "neg";

  // weighted total per location
  const weighted = (loc) => {
    let sum = 0, w = 0;
    a.criteria.forEach((c) => { sum += (loc.scores[c.key] || 0) * c.weight; w += c.weight * 5; });
    return Math.round((sum / w) * 100);
  };
  const ranked = [...a.locations].map((l) => ({ ...l, total: weighted(l) }))
    .sort((x, y) => y.total - x.total);

  const critHead = a.criteria.map((c) => `<th style="text-align:center">${c.label}</th>`).join("");

  el.innerHTML = `
    <div class="muted" style="margin-bottom:4px"><a href="#goals" style="text-decoration:none">← Goals</a></div>
    <h2>🇮🇹🇪🇸 A home abroad — Italy vs Andalusia</h2>
    <div class="card" style="border-left:4px solid #3ecf8e">
      <div style="font-size:1.05em"><b>${a.headline}</b></div>
      <div class="muted mt" style="font-size:.85em">As of ${a.as_of} · goal budget ${fmt.eur ? fmt.eur(a.budget_eur) : "€" + fmt.grouped(a.budget_eur)}
        ${italyGoal ? ` · goal progress: ${fmt.pln(italyGoal.current_amount)} / ${fmt.pln(italyGoal.target_amount)}` : ""}</div>
    </div>

    ${a.country_comparison ? `<div class="card mt" style="border-left:4px solid #e0a458">
      <h3 style="margin-top:0">🇮🇹 vs 🇪🇸 Italy or Andalusia? — comparison at a €400k budget</h3>
      <div style="font-size:1.0em"><b>${a.country_comparison.headline}</b></div>
      <div style="overflow-x:auto" class="mt"><table>
        <thead><tr><th>Criterion</th><th>🇮🇹 Italy</th><th>🇪🇸 Andalusia</th></tr></thead>
        <tbody>${a.country_comparison.dimensions.map((d) => `<tr>
          <td><b>${d.label}</b></td>
          <td style="font-size:.88em;${d.winner === "italy" ? "background:rgba(62,207,142,0.10)" : ""}">${d.italy}${d.winner === "italy" ? ' <span class="pos">✓</span>' : ""}</td>
          <td style="font-size:.88em;${d.winner === "spain" ? "background:rgba(62,207,142,0.10)" : ""}">${d.spain}${d.winner === "spain" ? ' <span class="pos">✓</span>' : ""}</td>
        </tr>`).join("")}</tbody>
      </table></div>
      <div class="mt" style="padding:8px 12px;background:#00000022;border-radius:6px;font-size:.92em">
        <b>Verdict:</b> ${a.country_comparison.verdict}</div>
      <div class="muted mt" style="font-size:.88em"><b>Where in Andalusia:</b> ${a.country_comparison.spain_pick}</div>
    </div>` : ""}

    <div class="card mt" style="border-left:4px solid #4c8dff">
      <h3 style="margin-top:0">🧮 Purchase calculator — real cost and balance</h3>
      <div class="row" style="align-items:center;gap:10px;margin-bottom:8px">
        <b>Country:</b>
        <select id="icCountry" style="width:220px">
          <option value="italy">🇮🇹 Italy (Puglia/Liguria)</option>
          <option value="spain">🇪🇸 Spain (Andalusia)</option>
        </select>
        <span class="muted" style="font-size:.82em">fills in transaction costs, rental tax, interest rate, down payment and upkeep costs for the selected country</span>
      </div>
      <div class="muted" style="font-size:.85em;margin-bottom:8px">Computed live. EUR/PLN ${fmt.num(eurpln, 3)} (from Market).
        Everything in € (PLN conversion alongside). Changes are saved in the browser.</div>
      <div id="icInputs" style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px"></div>
      <div id="icOut" class="mt"></div>
    </div>

    <div class="card mt">
      <h3>Comparison — ranking by your criteria</h3>
      <div class="muted" style="margin-bottom:8px;font-size:.85em">Criteria weights:
        ${a.criteria.map((c) => `${c.label} ×${c.weight}`).join(" · ")}. Scored 1–5 (● filled).</div>
      <div style="overflow-x:auto">
      <table>
        <thead><tr><th>Location</th><th style="text-align:center">Score</th>${critHead}<th style="text-align:right">€/m²</th></tr></thead>
        <tbody>
        ${ranked.map((l, i) => `<tr>
          <td><b>${i === 0 ? "🏆 " : ""}${l.name}</b><div class="muted" style="font-size:.8em">${l.region}</div></td>
          <td style="text-align:center"><b class="${l.total >= 85 ? "pos" : l.total >= 70 ? "" : "muted"}">${l.total}</b></td>
          ${a.criteria.map((c) => `<td style="text-align:center" class="${scoreColor(l.scores[c.key])}">${dots(l.scores[c.key])}</td>`).join("")}
          <td style="text-align:right;white-space:nowrap">${l.price_m2}</td>
        </tr>`).join("")}
        </tbody>
      </table>
      </div>
    </div>

    <div class="grid cols-2 mt">
      ${ranked.map((l) => `<div class="card" ${l.verdict.startsWith("★") ? 'style="border-left:4px solid #3ecf8e"' : ""}>
        <h3 style="margin-top:0">${l.name} <span class="muted" style="font-weight:normal;font-size:.7em">${l.region}</span></h3>
        <div style="font-size:.92em"><b>🌊 Sea:</b> ${l.water}</div>
        ${l.house ? `<div class="mt" style="font-size:.92em"><b>🏡 House+plot:</b> ${l.house}</div>` : ""}
        ${l.solar ? `<div class="mt" style="font-size:.92em"><b>☀️ Sun/PV:</b> ${l.solar}</div>` : ""}
        <div class="mt" style="font-size:.92em"><b>📅 Rental:</b> ${l.rental}</div>
        <div class="mt" style="font-size:.92em"><b>💶 Entry:</b> ${l.entry}</div>
        <div class="mt" style="font-size:.9em;padding:6px 10px;background:#00000022;border-radius:6px">
          <b>${l.verdict}</b></div>
      </div>`).join("")}
    </div>

    ${a.house_vs_apartment ? `<div class="card mt" style="border-left:4px solid #3ecf8e">
      <h3 style="margin-top:0">🏡 House with a plot vs apartment</h3>
      <div style="font-size:1.0em"><b>${a.house_vs_apartment.headline}</b></div>
      <ul style="padding-left:18px">${a.house_vs_apartment.points.map((p) => `<li class="mt" style="font-size:.92em">${p}</li>`).join("")}</ul>
    </div>` : ""}

    ${a.energy_pv ? `<div class="card mt" style="border-left:4px solid #ffd166">
      <h3 style="margin-top:0">☀️ Solar, battery, wallbox — energy independence</h3>
      <div style="font-size:1.0em"><b>${a.energy_pv.headline}</b></div>
      <ul style="padding-left:18px">${a.energy_pv.points.map((p) => `<li class="mt" style="font-size:.92em">${p}</li>`).join("")}</ul>
    </div>` : ""}

    ${a.budget_realism ? `<div class="card mt" style="border-left:4px solid #4c8dff">
      <h3 style="margin-top:0">💶 Is €400,000 a realistic budget?</h3>
      <div style="font-size:1.02em"><b>${a.budget_realism.headline}</b></div>
      <ul style="padding-left:18px">${a.budget_realism.points.map((p) => `<li class="mt" style="font-size:.92em">${p}</li>`).join("")}</ul>
      <div class="mt" style="font-size:.9em;padding:8px 12px;background:#00000022;border-radius:6px">
        ⚠️ ${a.budget_realism.cash_warning}</div>
    </div>` : ""}

    <div class="card mt" style="border-left:4px solid #ffd166">
      <h3 style="margin-top:0">✅ Recommendation: ${a.recommendation.pick}</h3>
      <ul style="padding-left:18px">${a.recommendation.why.map((w) => `<li class="mt">${w}</li>`).join("")}</ul>
      <div class="mt muted"><b>Runner-up:</b> ${a.recommendation.runner_up}</div>
    </div>

    <div class="grid cols-2 mt">
      <div class="card">
        <h3>💶 Financing — plan for ${fmt.eur ? fmt.eur(a.budget_eur) : "€" + fmt.grouped(a.budget_eur)}</h3>
        <table>${Object.entries({
          "Price": a.financing.plan_400k.cena,
          "Down payment 50%": a.financing.plan_400k.wklad_50pct,
          "EUR loan": a.financing.plan_400k.kredyt_eur,
          "Installment": a.financing.plan_400k.rata_ok,
          "Additional costs": a.financing.plan_400k.koszty_dod,
        }).map(([k, v]) => `<tr><td>${k}</td><td><b>${v}</b></td></tr>`).join("")}</table>
        <div class="muted mt" style="font-size:.82em">${a.financing.note}</div>
        ${a.financing.cash_vs_equity_capacity ? `<div class="mt" style="font-size:.86em;padding:8px 12px;background:#00000022;border-radius:6px">
          <b>💡 Borrowing capacity vs 50% cash:</b> ${a.financing.cash_vs_equity_capacity}</div>` : ""}
      </div>
      <div class="card">
        <h3>🧭 Next steps</h3>
        <ol style="padding-left:18px">${a.next_steps.map((s) => `<li class="mt" style="font-size:.92em">${s}</li>`).join("")}</ol>
      </div>
    </div>

    <div class="card mt muted" style="font-size:.8em">
      Analysis from market research (prices, yields, loan terms, marinas) — a snapshot, not computed automatically.
      To refresh: ask Claude to "refresh the Italy analysis".
      Sources: ${a.sources.map((u, i) => `<a href="${u}" target="_blank">[${i + 1}]</a>`).join(" ")}
    </div>`;

  // ---- purchase calculator ----
  const FIELDS = [
    ["price", "House price (€)", 400000], ["down", "Down payment (%)", 50],
    ["rate", "EUR interest (%)", 3.4], ["years", "Term (years)", 20],
    ["rentGross", "Gross rent (€/yr)", 8000], ["rentTax", "Rental tax (%)", 21],
    ["he", "HomeExchange (€/yr)", 2500], ["energy", "PV savings (€/yr)", 1500],
    ["costs", "Annual costs (€)", 6000], ["pv", "PV+battery install (€)", 20000],
    ["trans", "Transaction costs (%)", 11], ["mgmt", "Rental management (%)", 15],
  ];
  // country presets — transaction costs, rental tax, interest rate, down payment, upkeep costs
  const PRESETS = {
    italy: { trans: 11, rentTax: 21, rate: 3.4, down: 50, costs: 6000 },
    spain: { trans: 11, rentTax: 19, rate: 3.1, down: 35, costs: 5000 },
  };
  const saved = JSON.parse(localStorage.getItem("italyCalc") || "{}");
  const savedCountry = localStorage.getItem("italyCalcCountry") || "italy";
  document.getElementById("icCountry").value = savedCountry;
  const inputsEl = document.getElementById("icInputs");
  inputsEl.innerHTML = FIELDS.map(([k, label, def]) =>
    `<label class="muted" style="font-size:.82em">${label}<br>
      <input data-num data-ic="${k}" value="${fmt.grouped(saved[k] != null ? saved[k] : def)}" style="width:100%"></label>`).join("");

  document.getElementById("icCountry").addEventListener("change", (e) => {
    const p = PRESETS[e.target.value] || PRESETS.italy;
    localStorage.setItem("italyCalcCountry", e.target.value);
    Object.entries(p).forEach(([k, v]) => {
      const inp = inputsEl.querySelector(`[data-ic="${k}"]`);
      if (inp) inp.value = fmt.grouped(v);
    });
    compute();
  });

  const goalTarget = italyGoal ? italyGoal.target_amount : 0;
  const pln = (e) => fmt.pln(Math.round(e * eurpln));

  function compute() {
    const v = {};
    FIELDS.forEach(([k]) => { v[k] = parseNum(inputsEl.querySelector(`[data-ic="${k}"]`)) || 0; });
    localStorage.setItem("italyCalc", JSON.stringify(v));
    const loan = v.price * (1 - v.down / 100);
    const r = v.rate / 100 / 12, n = v.years * 12;
    const rata = r > 0 ? loan * r / (1 - Math.pow(1 + r, -n)) : loan / n;
    const transaction = v.price * v.trans / 100;
    const cashStart = v.price * v.down / 100 + transaction + v.pv;
    const mgmtCost = v.rentGross * v.mgmt / 100;
    const rentNet = v.rentGross * (1 - v.rentTax / 100) - mgmtCost;
    const annualIn = rentNet + v.he + v.energy;
    const annualOut = rata * 12 + v.costs;
    const net = annualIn - annualOut;
    const yieldBrutto = v.price ? v.rentGross / v.price * 100 : 0;
    const yieldNetto = v.price ? rentNet / v.price * 100 : 0;
    const cashStartPln = Math.round(cashStart * eurpln);

    const line = (k, val, cls) => `<tr><td>${k}</td><td style="text-align:right" class="${cls || ""}"><b>${val}</b></td></tr>`;
    document.getElementById("icOut").innerHTML = `
      <div class="grid cols-2">
        <div class="card" style="margin:0">
          <h4 style="margin:0 0 6px">Loan and cash at the start</h4>
          <table>
            ${line("EUR loan", "€" + fmt.grouped(Math.round(loan)) + " · " + pln(loan))}
            ${line("Monthly installment", "€" + fmt.grouped(Math.round(rata)) + " · " + pln(rata))}
            ${line("Transaction costs", "€" + fmt.grouped(Math.round(transaction)))}
            ${line("Cash at the start (down payment+costs+PV)", "€" + fmt.grouped(Math.round(cashStart)) + " · " + fmt.pln(cashStartPln), "neg")}
          </table>
          <div class="muted mt" style="font-size:.82em">Down-payment goal in the app: ${fmt.pln(goalTarget)} (covers the 50% down payment only).
            Realistically you need ${fmt.pln(cashStartPln)} at the start — the ${fmt.pln(cashStartPln - goalTarget)} difference is transaction costs + PV.</div>
        </div>
        <div class="card" style="margin:0">
          <h4 style="margin:0 0 6px">Annual balance (after all income)</h4>
          <table>
            ${line("Net rent (after tax and management)", "€" + fmt.grouped(Math.round(rentNet)), "pos")}
            ${line("+ HomeExchange (avoided lodging)", "€" + fmt.grouped(Math.round(v.he)), "pos")}
            ${line("+ Energy savings (PV)", "€" + fmt.grouped(Math.round(v.energy)), "pos")}
            ${line("− Annual installments", "€" + fmt.grouped(Math.round(rata * 12)), "neg")}
            ${line("− Upkeep costs", "€" + fmt.grouped(Math.round(v.costs)), "neg")}
            ${line(net >= 0 ? "= The house EARNS per year" : "= The house COSTS per year",
              "€" + fmt.grouped(Math.abs(Math.round(net))) + " · " + pln(Math.abs(net)), net >= 0 ? "pos" : "neg")}
          </table>
          <div class="muted mt" style="font-size:.82em">
            ${net >= 0 ? "The house nets out positive — it pays for itself." :
              "Real cost of ownership: " + pln(Math.abs(net) / 12) + "/mo (after rent, HE and PV)."}
            Gross yield ${fmt.num(yieldBrutto, 1)}% · net ${fmt.num(yieldNetto, 1)}%.
          </div>
        </div>
      </div>
      <div class="muted mt" style="font-size:.82em">${document.getElementById("icCountry").value === "spain"
        ? "🇪🇸 Andalusia: 19% rental tax (EU, with deductions), 35% down payment (LTV up to 65%), rate ~3.1%, cheaper upkeep (~16% less than Italy). 7% ITP included in transaction costs."
        : "🇮🇹 Italy: 21% rental tax (cedolare), 50% down payment (LTV 50–60%), rate ~3.4%, ~9% purchase tax in transaction costs."}</div>`;
  }
  inputsEl.querySelectorAll("[data-ic]").forEach((i) => i.addEventListener("input", compute));
  compute();
}
