function marketBriefHtml(b) {
  if (!b || !b.headline) {
    return `<div class="card"><h3 style="margin-top:0">🧭 Market brief</h3>
      <div class="muted">No saved brief. Authored offline (Claude/own notes) and stored under the
        <code>analysis_market_brief</code> setting — key moves, macro context, and a per-position stance.</div></div>`;
  }
  const hi = (b.highlights || []).map((h) => `<div class="card" style="margin:0">
      <div style="font-size:1.4em">${h.icon || "•"}</div>
      <div style="font-weight:600;margin:2px 0">${h.title}</div>
      <div class="muted" style="font-size:.9em">${h.text}</div></div>`).join("");
  const geo = (b.geopolitics || []).map((g) => `<details class="mt">
      <summary style="cursor:pointer;font-weight:600">${g.title}</summary>
      <div class="muted mt" style="font-size:.92em">${g.text}</div></details>`).join("");
  const stanceColor = (s) => /sell/i.test(s) ? "#3ecf8e" : /hold|core/i.test(s) ? "#4c8dff"
    : /accumulate|dca|buduj|stopniowo/i.test(s) ? "#ffd166" : "#9aa";
  const pos = (b.positions || []).map((p) => `<tr>
      <td><b>${p.ticker}</b></td>
      <td><span class="badge" style="background:${stanceColor(p.stance)}22;color:${stanceColor(p.stance)}">${p.stance}</span></td>
      <td class="muted" style="font-size:.9em">${p.text}</td></tr>`).join("");
  return `
    <div class="card" style="border-left:4px solid #4c8dff">
      <div class="row" style="justify-content:space-between;align-items:baseline">
        <h3 style="margin:0">🧭 Market brief</h3>
        <span class="muted" style="font-size:.82em">as of ${b.as_of || "—"}</span>
      </div>
      ${b.regime ? `<div class="mt" style="font-weight:600;color:#ffd166">${b.regime}</div>` : ""}
      <div class="mt">${b.headline}</div>
    </div>
    ${hi ? `<div class="grid cols-4 mt">${hi}</div>` : ""}
    ${geo ? `<div class="card mt"><h3 style="margin-top:0">🌍 Context — what drives the moves</h3>${geo}</div>` : ""}
    ${pos ? `<div class="card mt"><h3 style="margin-top:0">🎯 What to do about it — per position</h3>
      <table><thead><tr><th>Ticker</th><th>Stance</th><th>Rationale</th></tr></thead>
      <tbody>${pos}</tbody></table>
      ${b.fx_note ? `<div class="muted mt" style="border-left:3px solid #e0a458;padding-left:8px">💱 ${b.fx_note}</div>` : ""}</div>` : ""}
    ${b.method_note ? `<div class="muted mt" style="font-size:.8em">${b.method_note}</div>` : ""}`;
}

async function renderMarket(el) {
  const [wl, brief, radar] = await Promise.all([
    api.get("/api/watchlist"),
    api.get("/api/analysis/market_brief").catch(() => ({})),
    api.get("/api/risk-radar").catch(() => null),
  ]);
  el.innerHTML = `
    <h2>Market</h2>
    ${radar ? `<div class="card mt" style="border-left:4px solid ${radar.score >= 4 ? "#ff5c5c" : radar.score >= 2 ? "#ffd166" : "#3ecf8e"}">
      <div class="row" style="justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px">
        <h3 style="margin:0">🌍 Risk Radar <span class="badge">${radar.state} · ${radar.score}/${radar.max_score}</span></h3>
      </div>
      <div class="muted" style="font-size:.85em;margin:4px 0 8px">Is the world nervous today? Measurable fear proxies the market already prices — instead of meme "pizza indexes" 🍕.</div>
      <div style="overflow-x:auto"><table>
        <thead><tr><th>Component</th><th style="text-align:right">Level</th><th style="text-align:right">Δ 1d</th><th style="text-align:center">Score</th></tr></thead>
        <tbody>${radar.components.map((c) => `<tr title="${c.rule}">
          <td>${c.label} <span class="muted" style="font-size:.8em">${c.ticker}</span></td>
          <td style="text-align:right">${c.level ?? "<span class=muted>no data</span>"}</td>
          <td style="text-align:right" class="${(c.chg_1d || 0) > 0 ? "pos" : (c.chg_1d || 0) < 0 ? "neg" : "muted"}">${c.chg_1d != null ? c.chg_1d + "%" : "—"}</td>
          <td style="text-align:center">${c.score == null ? "—" : ["🟢","🟡","🔴"][c.score]}</td>
        </tr>`).join("")}</tbody></table></div>
      ${radar.note ? `<div class="muted mt" style="font-size:.82em">⚠️ ${radar.note}</div>` : ""}
      ${radar.history && radar.history.length
        ? `<div class="mt"><canvas id="radarChart" height="50"></canvas>
           ${radar.history[radar.history.length-1].comment ? `<div class="muted mt" style="font-size:.85em">🤖 Comment (local AI): ${radar.history[radar.history.length-1].comment}</div>` : ""}</div>`
        : `<div class="muted mt" style="font-size:.82em">No readings yet — the radar stores the first one on the next daily cycle (or once the nightly sync delivers quotes).</div>`}
      <div class="muted mt" style="font-size:.78em">The radar predicts nothing — it contextualizes. Thresholds are explicit (hover a component).</div>
    </div>` : ""}

    ${marketBriefHtml(brief)}
    <h3 class="mt">Watchlist</h3>
    <div class="card">
      <div class="row">
        <input id="wlTicker" placeholder="ticker e.g. AAPL" style="width:140px">
        <button class="primary" id="wlAdd">Add</button>
        <button id="wlRefresh">Refresh from cloud</button>
        <span class="muted">last sync: ${wl.last_sync || "never"}</span>
      </div>
    </div>
    <div class="card mt"><div id="wlTable"><div class="empty">Loading…</div></div></div>
    <div class="card mt"><h3 id="chartTitle">Pick a ticker from the table</h3><canvas id="priceChart"></canvas></div>
    `;
  if (radar && radar.history && radar.history.length && document.getElementById("radarChart")) {
    trackChart(new Chart(document.getElementById("radarChart"), {
      type: "line",
      data: { labels: radar.history.map((h) => h.date.slice(5)),
        datasets: [{ label: "score", data: radar.history.map((h) => h.score),
          borderColor: "#ffd166", backgroundColor: "transparent", tension: 0.3, pointRadius: 2 },
          { label: "trend (7d)", data: radar.history.map((_, i, a) => {
              const w = a.slice(Math.max(0, i - 6), i + 1);
              return +(w.reduce((x, h) => x + h.score, 0) / w.length).toFixed(2);
            }), borderColor: "#4c8dff", backgroundColor: "transparent",
            tension: 0.35, pointRadius: 0, borderDash: [5, 4] }] },
      options: { plugins: { legend: { display: false } },
        scales: { y: { min: 0, max: radar.max_score } } },
    }));
  }


  const TICKER_NAMES = {
    "AAPL": "RSU stock (set the ticker in RSU)",
    "GOOGL": "Alphabet Inc. (Google) — shares from brokerage",
    "AMZN": "Amazon.com Inc. — shares from brokerage",
    "NVDA": "NVIDIA Corporation — shares from brokerage",
    "V": "Visa Inc. — card payments operator, shares from brokerage",
    "IWDA.AS": "iShares Core MSCI World ETF (Amsterdam) — broad world market",
    "SXR8.DE": "iShares Core S&P 500 ETF (Xetra)",
    "CNDX.L": "iShares NASDAQ 100 ETF (London)",
    "USDPLN=X": "US dollar to Polish zloty rate",
    "EURPLN=X": "Euro to Polish zloty rate",
    "EURUSD=X": "Euro to US dollar rate",
  };

  async function loadTable() {
    const tickers = (await api.get("/api/watchlist")).tickers;
    if (!tickers.length) {
      document.getElementById("wlTable").innerHTML =
        '<div class="empty">Empty watchlist — add a ticker above</div>';
      return;
    }
    const rows = await Promise.all(tickers.map((t) =>
      api.get("/api/market/analytics/" + encodeURIComponent(t.ticker)).catch(() => ({ ticker: t.ticker, error: "?" }))));
    const hint = (label, tip) => `<th><span class="hint" title="${tip}">${label}</span></th>`;
    document.getElementById("wlTable").innerHTML = `<table><thead><tr>
      ${hint("Ticker", "Exchange symbol of the instrument — hover over the symbol in the table to see the full name")}
      ${hint("Price", "Last daily close (n8n fetches daily ~22:30; the app pulls it in the morning)")}
      ${hint("1D", "Price change vs the previous session")}
      ${hint("30D", "Price change over the last 30 days")}
      ${hint("SMA50", "Average price over the last 50 sessions (~2.5 mo). ABOVE = price above the average, uptrend; BELOW = downtrend. A classic momentum filter. Number = the average value.")}
      ${hint("Off 52w high", "How many % the price is below the one-year maximum (drawdown). −5% = near the top; −40% = a deep sell-off.")}
      ${hint("Target", "YOUR price target — enter it manually (e.g. analyst consensus or a sell/buy-more price). Saves automatically.")}
      ${hint("Upside", "How many % from the price to your target. Negative = price already above the target — revise the target or take profit.")}
      <th></th>
    </tr></thead><tbody>` + rows.map((a) => a.error
      ? `<tr><td>${a.ticker}</td><td colspan="7" class="muted">no data — refresh from cloud</td>
         <td><button class="danger" data-rm="${a.ticker}">✕</button></td></tr>`
      : `<tr data-t="${a.ticker}" style="cursor:pointer">
        <td><b><span class="hint" title="${TICKER_NAMES[a.ticker] || a.ticker}">${a.ticker}</span></b></td>
        <td>${fmt.num(a.last_close)} ${a.currency}</td>
        <td class="${a.change_1d_pct >= 0 ? "pos" : "neg"}">${fmt.pct(a.change_1d_pct)}</td>
        <td class="${a.change_30d_pct >= 0 ? "pos" : "neg"}">${fmt.pct(a.change_30d_pct)}</td>
        <td><span class="badge ${a.last_close > a.sma50 ? "up" : "down"}">${a.last_close > a.sma50 ? "above" : "below"} ${fmt.num(a.sma50, 0)}</span></td>
        <td class="neg">${fmt.pct(a.drawdown_from_high_pct)}</td>
        <td><input type="number" value="${a.analyst_target || ""}" data-target="${a.ticker}" style="width:80px"></td>
        <td class="${a.target_upside_pct >= 0 ? "pos" : "neg"}">${fmt.pct(a.target_upside_pct)}</td>
        <td><button class="danger" data-rm="${a.ticker}">✕</button></td>
      </tr>`).join("") + "</tbody></table>";

    document.querySelectorAll("[data-rm]").forEach((b) =>
      b.addEventListener("click", async (e) => {
        e.stopPropagation();
        await api.del("/api/watchlist/" + b.dataset.rm);
        loadTable();
      }));
    document.querySelectorAll("[data-target]").forEach((inp) =>
      inp.addEventListener("change", () =>
        api.put("/api/market/target/" + inp.dataset.target, { target: parseFloat(inp.value) })));
    document.querySelectorAll("tr[data-t]").forEach((tr) =>
      tr.addEventListener("click", () => drawChart(tr.dataset.t)));
  }

  let chart;
  async function drawChart(ticker) {
    const hist = await api.get(`/api/market/prices/${ticker}?days=365`);
    if (!hist.length) return;
    document.getElementById("chartTitle").textContent = ticker + " — 12 months";
    const closes = hist.map((h) => h.close);
    const sma = (n) => closes.map((_, i) =>
      i + 1 >= n ? closes.slice(i + 1 - n, i + 1).reduce((a, b) => a + b, 0) / n : null);
    if (chart) chart.destroy();
    chart = trackChart(new Chart(document.getElementById("priceChart"), {
      type: "line",
      data: {
        labels: hist.map((h) => h.date),
        datasets: [
          { label: ticker, data: closes, borderColor: "#4c8dff", tension: 0.2, pointRadius: 0 },
          { label: "SMA50", data: sma(50), borderColor: "#ffd166", borderDash: [4, 4], pointRadius: 0 },
          { label: "SMA200", data: sma(200), borderColor: "#b78cff", borderDash: [4, 4], pointRadius: 0 },
        ],
      },
      options: { interaction: { mode: "index", intersect: false } },
    }));
  }

  document.getElementById("wlAdd").addEventListener("click", async () => {
    const t = document.getElementById("wlTicker").value.trim().toUpperCase();
    if (!t) return;
    await api.post("/api/watchlist/" + encodeURIComponent(t));
    document.getElementById("wlTicker").value = "";
    loadTable();
  });
  document.getElementById("wlRefresh").addEventListener("click", async () => {
    const r = await api.post("/api/market/refresh");
    alert(`Synced ${r.rows} quotes`);
    route();
  });

  await loadTable();
}
