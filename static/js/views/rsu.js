async function renderRsu(el) {
  const [r, debtsData, deep, adv] = await Promise.all([
    api.get("/api/rsu"), api.get("/api/debts"),
    api.get("/api/rsu/analysis").catch(() => ({})),
    api.get("/api/rsu/advanced").catch(() => ({}))]);
  const bands = await api.get("/api/forecast/bands/" + encodeURIComponent(r.ticker || "")).catch(() => null);
  const nextVestPln = r.next_vest_value_pln;
  const topDebt = debtsData.debts
    .filter((d) => d.balance > 0)
    .sort((a, b) => (b.effective_rate || 0) - (a.effective_rate || 0))[0];
  const rec = (() => {
    if (!r.last_close) return "No price — add your company ticker and USDPLN=X to the watchlist.";
    const parts = [];
    if (nextVestPln) {
      parts.push(`In the ${r.next_vest_month} window ${fmt.num(r.shares_next_vest, 0)} shares vest ≈ ${fmt.pln(nextVestPln)} at the current price.`);
    }
    const loan = debtsData.debts.find((d) => ["mortgage","loan","home","house"].some((k) => d.name.toLowerCase().includes(k)) && d.balance > 0);
    if (loan && nextVestPln) {
      parts.push(
        `sell the vest right away and pay down the loan — balance ${fmt.pln(loan.balance)}, ` +
        `i.e. ~${Math.ceil(loan.balance / nextVestPln)} vests to close the loan. Every vest into the loan is a guaranteed ` +
        `${fmt.pct(loan.effective_rate, 2)} + frees up ${fmt.pln(loan.monthly_cost_total)}/mo and boosts borrowing ` +
        `capacity for the goal. After the loan is paid off, vests go toward the down payment (the mortgage rate you fix via an annex, not capital).`);
    } else if (topDebt && topDebt.effective_rate > 6.5 && nextVestPln) {
      parts.push(
        `The ${topDebt.name} loan costs ${fmt.pct(topDebt.effective_rate, 2)} effective — selling the vest and overpaying ` +
        `is a guaranteed, untaxed return, more certain than a bet on a single stock rebounding.`);
    } else {
      parts.push(
        "The standard RSU rule: sell at vest — tax-wise holding " +
        "gains you nothing (the 19% capital gains tax applies to the gain AFTER vest), and by holding you concentrate " +
        "employer risk (salary + bonus + shares in one company).");
    }
    if (r.last_close < 100) {
      parts.push(
        `Nuance: ${r.ticker} ~$${r.last_close} is near multi-year lows — selling EVERYTHING now ` +
        "means realizing the bottom. Compromise: sell current vests right away (for overpayment), " +
        "hold the existing " + fmt.num(r.shares_held, 0) + " shares for a rebound — the cushion allows it.");
    }
    return parts.join(" ");
  })();

  el.innerHTML = `
    <h2>RSU — ${r.ticker}</h2>
    <div class="grid cols-4">
      <div class="card kpi"><div class="label">Shares held</div>
        <div class="value">${fmt.num(r.shares_held, 0)}</div>
        <div class="sub">${r.held_value_pln ? "≈ " + fmt.pln(r.held_value_pln) + " (" + fmt.usd(r.held_value_usd) + ")" : ""}</div></div>
      <div class="card kpi"><div class="label">Next vest (${r.next_vest_month})</div>
        <div class="value">+${fmt.num(r.shares_next_vest, 0)}</div>
        <div class="sub">${nextVestPln ? "≈ " + fmt.pln(nextVestPln) + " at $" + r.last_close : ""}</div></div>
      <div class="card kpi"><div class="label">Total after vest</div>
        <div class="value">${fmt.num(r.shares_after_vest, 0)}</div>
        <div class="sub">${r.after_vest_value_pln ? "≈ " + fmt.pln(r.after_vest_value_pln) : ""}</div></div>
      <div class="card kpi"><div class="label">Price / USDPLN</div>
        <div class="value">${r.last_close ? "$" + r.last_close : "—"}</div>
        <div class="sub">close ${r.last_close_date || "—"} · USD/PLN ${r.usdpln ? fmt.num(r.usdpln, 3) : "—"} (${r.usdpln_date || "—"})<br>
          new quotes daily ~22:35 (n8n) · sync: ${r.cache_synced ? r.cache_synced.slice(0, 16).replace("T", " ") : "—"}</div></div>
    </div>
    <div class="card mt" style="border-left:4px solid #ffd166">
      <h3 style="margin-top:0">💡 Recommendation</h3>
      <div>${rec}</div>
    </div>
    ${deep.headline ? `<div class="card mt" style="border-left:4px solid #4c8dff">
      <h3 style="margin-top:0">🔬 Deep-dive analysis — ${deep.vest_month} vest
        <span class="muted" style="font-weight:normal;font-size:.75em">(as of ${deep.as_of}, price $${deep.price})</span></h3>
      <div><b>${deep.headline}</b></div>
      ${(deep.sections || []).map((s) => `<details class="mt" ${s === deep.sections[0] ? "open" : ""}>
        <summary style="cursor:pointer"><b>${s.title}</b></summary>
        <div class="mt" style="font-size:.93em">${s.text}</div>
      </details>`).join("")}
      <div class="muted mt" style="font-size:.8em">A research snapshot (earnings, guidance, analyst targets) —
        not computed automatically. To refresh: ask Claude to "refresh the vest analysis".
        ${(deep.sources || []).length ? `Sources: ${deep.sources.map((u, i) => `<a href="${u}" target="_blank">[${i + 1}]</a>`).join(" ")}` : ""}</div>
    </div>` : ""}
    ${bands && bands.horizons ? `<div class="card mt" style="border-left:4px solid #4c8dff">
      <h3 style="margin-top:0">📏 Short horizon — range, not direction
        <span class="muted" style="font-weight:normal;font-size:.7em">(a single stock's direction cannot be predicted — we manage risk, not timing)</span></h3>
      <table><thead><tr><th>Window</th><th>Pessimistic (p10)</th><th>Middle</th><th>Optimistic (p90)</th><th>Model</th></tr></thead>
      <tbody>${bands.horizons.map((h) => `<tr>
        <td>${h.days === 5 ? "1 week" : h.days === 21 ? "1 month" : "3 months"}</td>
        <td class="neg">$${fmt.num(h.p10, 2)}</td><td><b>$${fmt.num(h.p50, 2)}</b></td>
        <td class="pos">$${fmt.num(h.p90, 2)}</td>
        <td class="muted" style="font-size:.8em">${h.calibrated ? "🧠 " : ""}${h.source}</td>
      </tr>`).join("")}</tbody></table>
      <div class="muted mt" style="font-size:.82em">EWMA (λ=0.94) + quantiles of actual moves; 🧠 = band calibrated
        on the model's own scored forecasts (self-learning).
        ${bands.coverage ? `Historical 1M band coverage: <b>${bands.coverage.band_coverage_pct}%</b> (target ~80%).` : ""}</div>
    </div>` : ""}
    ${adv && !adv.error ? `<div class="card mt">
      <h3 style="margin-top:0">📈 Probabilistic prediction — Monte Carlo (${fmt.grouped(adv.sims)} paths)</h3>
      <div class="grid cols-4">
        <div class="card kpi"><div class="label">Annual volatility</div>
          <div class="value">${adv.vol_annual_pct}%</div>
          <div class="sub">from actual quotes (400 sessions) · hist. drift ${adv.hist_drift_annual_pct != null ? adv.hist_drift_annual_pct + "%" : "—"}</div></div>
        <div class="card kpi"><div class="label">Position in the 52w range</div>
          <div class="value">${adv.pos_in_52w_pct}%</div>
          <div class="sub">$${adv.low_52w}–$${adv.high_52w} · ${adv.trend}</div></div>
        <div class="card kpi"><div class="label">P(price ≥ today in a year)</div>
          <div class="value ${adv.prob_above_current_1y_pct >= 50 ? "pos" : "neg"}">${adv.prob_above_current_1y_pct}%</div>
          <div class="sub">at ${adv.drift_annual_pct}%/yr drift and this volatility</div></div>
        <div class="card kpi"><div class="label">Analyst consensus</div>
          <div class="value">$${adv.analyst.mid}</div>
          <div class="sub">range $${adv.analyst.bear}–$${adv.analyst.bull} · today $${adv.last_close}</div></div>
      </div>
      <canvas id="rsuCone" height="110" class="mt"></canvas>
      <div class="muted mt" style="font-size:.85em">Band = the distribution of the value of held + vested shares (base, not counting growing grants)
        from ${fmt.grouped(adv.sims)} simulations of the price path (GBM on actual ${adv.vol_annual_pct}% volatility). The dark line = the median (p50);
        the band = p10–p90. Dashed = the path to the analyst consensus $${adv.analyst.mid} (fundamental view, 12 mo).
        USD/PLN ${fmt.num(adv.usdpln, 2)}. Gross values — 19% capital gains tax on the gain after vest (≈0 when selling right away).</div>
      <table class="mt"><thead><tr><th>Window</th><th>Shares (base)</th>
        <th>Pess. p10</th><th>Median p50</th><th>Opt. p90</th><th>Analyst consensus</th></tr></thead>
      <tbody>${adv.projection.map((p) => `<tr>
        <td>${p.month}</td><td>${fmt.num(p.shares_base, 0)}</td>
        <td class="neg">${fmt.pln(p.p10)} <span class="muted">($${p.p10_price})</span></td>
        <td><b>${fmt.pln(p.p50)}</b> <span class="muted">($${p.p50_price})</span></td>
        <td class="pos">${fmt.pln(p.p90)} <span class="muted">($${p.p90_price})</span></td>
        <td class="muted">${fmt.pln(p.mid_analyst)}</td>
      </tr>`).join("")}</tbody></table>
    </div>

    ${adv.accuracy && adv.accuracy.backtest && adv.accuracy.backtest.h21 ? (() => {
      const bt = adv.accuracy.backtest, lv = adv.accuracy.live;
      const covCls = (c) => c >= 72 ? "pos" : c >= 55 ? "" : "neg";
      const btRow = (h) => h ? `<tr><td>${h.horizon_days === 21 ? "~1 mo" : "~3 mo"}</td>
        <td class="${covCls(h.band_coverage_pct)}"><b>${h.band_coverage_pct}%</b> <span class="muted">(ideal ~80%)</span></td>
        <td>${h.directional_pct}%</td><td>${h.median_abs_err_pct}%</td><td class="muted">${h.n}</td></tr>` : "";
      return `<div class="card mt" style="border-left:4px solid #ffd166">
      <h3 style="margin-top:0">🎯 How accurate my predictions are (learning from data)</h3>
      <div class="muted" style="font-size:.88em;margin-bottom:8px">Every day the stock price is fetched and the bands are scored.
        \"Calibration\" = how often the actual price fell inside my p10–p90 band (ideal ~80%).
        At ${adv.vol_annual_pct}% volatility the short-term move is almost random — so the honest measure is calibration, not \"hitting the price\".</div>
      <table><thead><tr><th>Horizon</th><th>Band calibration</th><th>Direction OK</th><th>Median error</th><th>Samples</th></tr></thead>
        <tbody>${btRow(bt.h21)}${btRow(bt.h63)}</tbody></table>
      <div class="mt" style="font-size:.9em;padding:8px 12px;background:#00000022;border-radius:6px">
        <b>Backtest takeaway (${bt.source}):</b> the bands hit ${bt.h21.band_coverage_pct}% instead of ~80% —
        i.e. <b>too narrow</b>; actual price moves were bigger. Realized drift in that period: <b class="neg">${bt.realized_drift_pct}%/yr</b>
        vs the assumed <b>+${bt.assumed_drift_pct}%</b> — the price was falling hard, so the median direction was often wrong.
        <b>Treat the p10–p90 band as optimistic (narrower than the real risk).</b> This reinforces the recommendation: sell at vest, do not bet on a rebound.</div>
      <div class="muted mt" style="font-size:.82em">📡 Live track record:
        ${lv.scored ? `${lv.scored} scored since ${lv.tracked_since} — calibration ${lv.band_coverage_pct}%, direction ${lv.directional_pct}%.`
          : `collecting since ${lv.tracked_since || "today"} (${lv.predictions_made} forecasts recorded, first scores in ~1 week).`}</div>
    </div>`; })() : ""}

` : ""}
    <div class="card mt">
      <h3>New grant ${r.grant_month} (pricing: ${r.pricing_window} average)</h3>
      <div class="row">
        <span class="muted">Window average (${r.window_days_counted} sessions):</span>
        <b>${r.window_running_average ? fmt.usd(r.window_running_average) : "no data yet"}</b>
        <span class="muted">· projected shares from the ${fmt.usd(r.grant_value_usd)} grant:</span>
        <b>${r.projected_shares ?? (r.estimate_from_last_close ? "~" + r.estimate_from_last_close : "—")}</b>
        <span class="muted">· quarterly tranche: ${r.shares_per_vest ?? "—"} shares</span>
      </div>
    </div>
    <div class="card mt">
      <h3>Parameters</h3>
      <div class="row">
        <input type="number" id="rHeld" value="${r.shares_held}" title="shares held" style="width:110px">
        <input type="number" id="rNext" value="${r.shares_next_vest}" title="shares in the next vest" style="width:110px">
        <input data-num id="rGrant" value="${fmt.grouped(r.grant_value_usd)}" title="grant value USD">
        <input id="rWindow" value="${r.pricing_window}" title="pricing window YYYY-MM" style="width:110px">
        <button class="primary" id="rSave">Save</button>
      </div>
      <div class="muted mt">held · next vest · grant value USD · pricing window.
        After each vest update "held" (and the RSU shares item in Wealth).</div>
    </div>`;

  if (adv && !adv.error && document.getElementById("rsuCone")) {
    const pj = adv.projection;
    trackChart(new Chart(document.getElementById("rsuCone"), {
      type: "line",
      data: {
        labels: pj.map((p) => p.month),
        datasets: [
          { label: "p90 (optimistic)", data: pj.map((p) => p.p90),
            borderColor: "transparent", backgroundColor: "rgba(62,207,142,0.13)",
            fill: "+1", pointRadius: 0, tension: 0.2 },
          { label: "p10 (pessimistic)", data: pj.map((p) => p.p10),
            borderColor: "transparent", backgroundColor: "transparent",
            fill: false, pointRadius: 0, tension: 0.2 },
          { label: "Median (p50)", data: pj.map((p) => p.p50),
            borderColor: CHART_COLORS[0], backgroundColor: "transparent",
            borderWidth: 3, pointRadius: 3, tension: 0.2 },
          { label: "Analyst consensus ($" + adv.analyst.mid + ")", data: pj.map((p) => p.mid_analyst),
            borderColor: CHART_COLORS[1], backgroundColor: "transparent",
            borderDash: [6, 4], pointRadius: 0, tension: 0.2 },
        ],
      },
      options: { plugins: { legend: { labels: { filter: (i) => !i.text.startsWith("p10") } } },
        scales: { y: { ticks: { callback: (v) => (v / 1000) + "k" } } } },
    }));
  }

  document.getElementById("rSave").addEventListener("click", async () => {
    await api.put("/api/rsu", {
      shares_held: +document.getElementById("rHeld").value,
      shares_next_vest: +document.getElementById("rNext").value,
      grant_value_usd: parseNum(document.getElementById("rGrant")),
      pricing_window: document.getElementById("rWindow").value,
    });
    route();
  });
}
