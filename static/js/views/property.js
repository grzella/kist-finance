async function renderProperty(el) {
  const [a, goals, fxRes] = await Promise.all([
    api.get("/api/analysis/property").catch(() => ({})),
    api.get("/api/goals").catch(() => []),
    api.get("/api/market/analytics/EURPLN=X").catch(() => ({}))]);
  const fx = fxRes.last_close || 4.34;

  const propertyGoal = (goals || []).find((g) =>
    /propert|house|home|apartment|flat|down.?payment|mortgage/i.test(g.name));

  // The rich comparison view (a.headline, a.locations, …) is optional research
  // saved into app_settings. When it's absent, the purchase calculator below
  // still works standalone — a generic buy-to-own / buy-to-let model.
  const hasAnalysis = !!a.headline;

  const dots = (n) => '<span style="letter-spacing:2px">'
    + "●".repeat(n) + '<span class="muted">' + "○".repeat(5 - n) + "</span></span>";
  const scoreColor = (n) => n >= 5 ? "pos" : n >= 4 ? "" : n >= 3 ? "muted" : "neg";
  const weighted = (loc) => {
    let sum = 0, w = 0;
    a.criteria.forEach((c) => { sum += (loc.scores[c.key] || 0) * c.weight; w += c.weight * 5; });
    return Math.round((sum / w) * 100);
  };
  const ranked = hasAnalysis
    ? [...a.locations].map((l) => ({ ...l, total: weighted(l) })).sort((x, y) => y.total - x.total)
    : [];

  el.innerHTML = `
    <div class="muted" style="margin-bottom:4px"><a href="#goals" style="text-decoration:none">← Goals</a></div>
    <h2>🏡 Property purchase — analysis &amp; calculator</h2>

    ${hasAnalysis ? `<div class="card" style="border-left:4px solid var(--pos)">
      <div style="font-size:1.05em"><b>${a.headline}</b></div>
      <div class="muted mt" style="font-size:.85em">As of ${a.as_of}${a.budget_eur ? ` · budget ${fmt.eur ? fmt.eur(a.budget_eur) : "€" + fmt.grouped(a.budget_eur)}` : ""}
        ${propertyGoal ? ` · goal progress: ${fmt.pln(propertyGoal.current_amount)} / ${fmt.pln(propertyGoal.target_amount)}` : ""}</div>
    </div>` : `<div class="card">
      <div class="muted">No saved location research yet — the calculator below works standalone.
      To add a ranked location comparison, use the box below.</div>
      <details class="mt"><summary style="cursor:pointer"><b>➕ Fill it now</b> (paste JSON from any AI assistant)</summary>
        <div class="muted mt" style="font-size:.85em">1) Click <b>Copy AI prompt</b> and paste it into any assistant (ChatGPT, Claude, the local model…). 2) Paste the JSON it returns below. 3) Save.</div>
        <div class="row mt" style="gap:8px">
          <button data-copyprompt="analysis_property">📋 Copy AI prompt</button>
          <span class="muted" data-copied style="font-size:.8em"></span>
        </div>
        <textarea data-paste="analysis_property" rows="5" class="mt" style="width:100%" placeholder='{"headline": "...", ...}'></textarea>
        <button class="primary mt" data-savejson="analysis_property">Save</button>
      </details>
    </div>`}

    <div class="card mt" style="border-left:4px solid var(--accent)">
      <h3 style="margin-top:0">🧮 Purchase calculator — real cost and balance</h3>
      <div class="muted" style="font-size:.85em;margin-bottom:8px">Computed live. Amounts in € with a local-currency
        conversion alongside (EUR/PLN ${fmt.num(fx, 3)}, from Market). Inputs are saved in your browser.</div>
      <div id="pcInputs" style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px"></div>
      <div id="pcOut" class="mt"></div>
    </div>

    ${hasAnalysis && ranked.length ? `<div class="card mt">
      <h3>Location comparison — ranked by your criteria</h3>
      <div class="muted" style="margin-bottom:8px;font-size:.85em">Criteria weights:
        ${a.criteria.map((c) => `${c.label} ×${c.weight}`).join(" · ")}. Scored 1–5 (● filled).</div>
      <div style="overflow-x:auto"><table>
        <thead><tr><th>Location</th><th style="text-align:center">Score</th>
          ${a.criteria.map((c) => `<th style="text-align:center">${c.label}</th>`).join("")}
          <th style="text-align:right">€/m²</th></tr></thead>
        <tbody>${ranked.map((l, i) => `<tr>
          <td><b>${i === 0 ? "🏆 " : ""}${l.name}</b><div class="muted" style="font-size:.8em">${l.region || ""}</div></td>
          <td style="text-align:center"><b class="${l.total >= 85 ? "pos" : l.total >= 70 ? "" : "muted"}">${l.total}</b></td>
          ${a.criteria.map((c) => `<td style="text-align:center" class="${scoreColor(l.scores[c.key])}">${dots(l.scores[c.key])}</td>`).join("")}
          <td style="text-align:right;white-space:nowrap">${l.price_m2 || "—"}</td>
        </tr>`).join("")}</tbody>
      </table></div>
    </div>` : ""}

    ${hasAnalysis && a.recommendation ? `<div class="card mt" style="border-left:4px solid var(--warn)">
      <h3 style="margin-top:0">✅ Recommendation: ${a.recommendation.pick}</h3>
      <ul style="padding-left:18px">${(a.recommendation.why || []).map((w) => `<li class="mt">${w}</li>`).join("")}</ul>
      ${a.recommendation.runner_up ? `<div class="mt muted"><b>Runner-up:</b> ${a.recommendation.runner_up}</div>` : ""}
    </div>` : ""}`;

  // ---- purchase calculator (generic buy-to-own / buy-to-let) ----
  const FIELDS = [
    ["price", "Property price (€)", 300000], ["down", "Down payment (%)", 30],
    ["rate", "Interest rate (%)", 3.5], ["years", "Term (years)", 25],
    ["rentGross", "Gross rent (€/yr)", 9000], ["rentTax", "Rental tax (%)", 19],
    ["other", "Other income (€/yr)", 0], ["upkeep", "Annual upkeep (€)", 3000],
    ["trans", "Transaction costs (%)", 8], ["mgmt", "Rental management (%)", 10],
    ["improve", "Upfront improvements (€)", 0],
  ];
  const saved = JSON.parse(localStorage.getItem("propertyCalc") || "{}");
  const inputsEl = document.getElementById("pcInputs");
  inputsEl.innerHTML = FIELDS.map(([k, label, def]) =>
    `<label class="muted" style="font-size:.82em">${label}<br>
      <input data-num data-pc="${k}" value="${fmt.grouped(saved[k] != null ? saved[k] : def)}" style="width:100%"></label>`).join("");

  const goalTarget = propertyGoal ? propertyGoal.target_amount : 0;
  const pln = (e) => fmt.pln(Math.round(e * fx));

  function compute() {
    const v = {};
    FIELDS.forEach(([k]) => { v[k] = parseNum(inputsEl.querySelector(`[data-pc="${k}"]`)) || 0; });
    localStorage.setItem("propertyCalc", JSON.stringify(v));
    const loan = v.price * (1 - v.down / 100);
    const r = v.rate / 100 / 12, n = v.years * 12;
    const rata = r > 0 ? loan * r / (1 - Math.pow(1 + r, -n)) : loan / n;
    const transaction = v.price * v.trans / 100;
    const cashStart = v.price * v.down / 100 + transaction + v.improve;
    const mgmtCost = v.rentGross * v.mgmt / 100;
    const rentNet = v.rentGross * (1 - v.rentTax / 100) - mgmtCost;
    const annualIn = rentNet + v.other;
    const annualOut = rata * 12 + v.upkeep;
    const net = annualIn - annualOut;
    const yieldBrutto = v.price ? v.rentGross / v.price * 100 : 0;
    const yieldNetto = v.price ? rentNet / v.price * 100 : 0;
    const cashStartPln = Math.round(cashStart * fx);

    const line = (k, val, cls) => `<tr><td>${k}</td><td style="text-align:right" class="${cls || ""}"><b>${val}</b></td></tr>`;
    document.getElementById("pcOut").innerHTML = `
      <div class="grid cols-2">
        <div class="card" style="margin:0">
          <h4 style="margin:0 0 6px">Loan and cash at the start</h4>
          <table>
            ${line("Loan", "€" + fmt.grouped(Math.round(loan)) + " · " + pln(loan))}
            ${line("Monthly installment", "€" + fmt.grouped(Math.round(rata)) + " · " + pln(rata))}
            ${line("Transaction costs", "€" + fmt.grouped(Math.round(transaction)))}
            ${line("Cash at the start (down payment+costs+improvements)", "€" + fmt.grouped(Math.round(cashStart)) + " · " + fmt.pln(cashStartPln), "neg")}
          </table>
          ${goalTarget ? `<div class="muted mt" style="font-size:.82em">Down-payment goal in the app: ${fmt.pln(goalTarget)}.
            Realistically you need ${fmt.pln(cashStartPln)} at the start — the ${fmt.pln(cashStartPln - goalTarget)} difference is transaction costs + improvements.</div>` : ""}
        </div>
        <div class="card" style="margin:0">
          <h4 style="margin:0 0 6px">Annual balance (after all income)</h4>
          <table>
            ${line("Net rent (after tax and management)", "€" + fmt.grouped(Math.round(rentNet)), "pos")}
            ${line("+ Other income", "€" + fmt.grouped(Math.round(v.other)), "pos")}
            ${line("− Annual installments", "€" + fmt.grouped(Math.round(rata * 12)), "neg")}
            ${line("− Upkeep costs", "€" + fmt.grouped(Math.round(v.upkeep)), "neg")}
            ${line(net >= 0 ? "= The property EARNS per year" : "= The property COSTS per year",
              "€" + fmt.grouped(Math.abs(Math.round(net))) + " · " + pln(Math.abs(net)), net >= 0 ? "pos" : "neg")}
          </table>
          <div class="muted mt" style="font-size:.82em">
            ${net >= 0 ? "The property nets out positive — it pays for itself." :
              "Real cost of ownership: " + pln(Math.abs(net) / 12) + "/mo (after rent and other income)."}
            Gross yield ${fmt.num(yieldBrutto, 1)}% · net ${fmt.num(yieldNetto, 1)}%.
          </div>
        </div>
      </div>`;
  }
  inputsEl.querySelectorAll("[data-pc]").forEach((i) => i.addEventListener("input", compute));
  compute();

  const PROMPTS = {
    analysis_property: `Research property-purchase locations for me and return ONLY valid JSON (no prose) with this shape: {"headline": str, "as_of": "YYYY-MM-DD", "budget_eur": number, "criteria": [{"key": str, "label": str, "weight": 1-3}], "locations": [{"name": str, "region": str, "price_m2": str, "scores": {criteriaKey: 1-5}}], "recommendation": {"pick": str, "why": [str], "runner_up": str}}. Ask me clarifying questions first if you need my constraints.`,
    analysis_market_brief: `Write a short market brief for my portfolio and return ONLY valid JSON: {"headline": str, "as_of": "YYYY-MM-DD", "highlights": [{"icon": "emoji", "title": str, "text": str}], "geopolitics": [{"title": str, "text": str}], "positions": [{"ticker": str, "stance": "hold|add|trim", "note": str}]}. Ask me for my tickers first.`,
    analysis_career: `Prepare a long-term career analysis for me and return ONLY valid JSON: {"headline": str, "as_of": "YYYY-MM-DD", "target_role": str, "comp_levels": [{"role": str, "comp": str, "you": bool}], "money_paths": [{"tag": "A|B|C", "title": str, "verdict": str, "text": str}], "head_of_eng": str, "ai_impact": [str], "skills": [{"skill": str, "why": str}], "skills_note": str}. Interview me about my situation first.`,
  };
  el.querySelectorAll("[data-copyprompt]").forEach((b) => b.addEventListener("click", async () => {
    await navigator.clipboard.writeText(PROMPTS[b.dataset.copyprompt] || "");
    const hint = b.parentElement.querySelector("[data-copied]"); if (hint) hint.textContent = "copied ✓";
  }));
  el.querySelectorAll("[data-savejson]").forEach((b) => b.addEventListener("click", async () => {
    const key = b.dataset.savejson;
    const raw = el.querySelector(`[data-paste="${key}"]`).value.trim();
    try { JSON.parse(raw); } catch (e) { alert("That is not valid JSON: " + e.message); return; }
    await api.put("/api/settings", { [key]: raw });
    route();
  }));
}
