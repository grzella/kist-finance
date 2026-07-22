function marketBriefHtml(b, controls) {
  if (!b || !b.headline) {
    return `<div class="card"><div class="row" style="align-items:center;gap:8px;flex-wrap:wrap"><h3 style="margin:0">🧭 Market brief</h3>${controls || ""}</div>
      <div class="muted">No saved brief yet — key moves, macro context and a per-position stance,
        authored by you or any AI assistant. Fill it with the box below.</div>
      <details class="mt"><summary style="cursor:pointer"><b>➕ Fill it now</b> (paste JSON from any AI assistant)</summary>
        <div class="muted mt" style="font-size:.85em">1) <b>Copy AI prompt</b> → paste into any assistant. 2) Paste the returned JSON below. 3) Save.</div>
        <div class="row mt" style="gap:8px"><button data-copyprompt="analysis_market_brief">📋 Copy AI prompt</button><span class="muted" data-copied style="font-size:.8em"></span></div>
        <textarea data-paste="analysis_market_brief" rows="5" class="mt" style="width:100%"></textarea>
        <button class="primary mt" data-savejson="analysis_market_brief">Save</button>
      </details></div>`;
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
        <h3 style="margin:0">🧭 Market brief</h3>${controls || ""}
        <span class="muted" style="font-size:.82em">quotes through <b>${b.data_through || "?"}</b> · analysis: ${b.as_of || "—"}${b.generated_by ? ` · ${b.generated_by}` : ""}${b.data_through && b.data_through < new Date().toISOString().slice(0,10) ? ' <span title="the price collector has not written today\'s session yet — insights are computed from the last available close">⏳</span>' : ""}</span>
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
  const [wl, briefs, radar] = await Promise.all([
    api.get("/api/watchlist"),
    api.get("/api/market/brief").catch(() => ({})),
    api.get("/api/risk-radar").catch(() => null),
  ]);
  el.innerHTML = `
    <h2>Market</h2>
    ${radar ? `<div class="card mt" style="border-left:4px solid ${radar.score >= 4 ? "#ff5c5c" : radar.score >= 2 ? "#ffd166" : "#3ecf8e"}">
      <div class="row" style="justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px">
        <h3 style="margin:0">🌍 Risk Radar <span class="badge" title="sum of the 4 component scores (0–2 each) — max ${radar.max_score}. E.g. 3/8 = three fear points total, not 3 of 8 components">${radar.state} · ${radar.score}/${radar.max_score} pts ⓘ</span></h3>
      </div>
      <div class="muted" style="font-size:.85em;margin:4px 0 8px">Is the world nervous today? Measurable fear proxies the market already prices — instead of meme "pizza indexes" 🍕.</div>
      <div style="overflow-x:auto"><table>
        <thead><tr><th>Component</th><th style="text-align:right" title="current indicator/price value — unit next to the number, meaning in the row tooltip">Level ⓘ</th><th style="text-align:right" title="percentage change vs the previous close (prior trading day)">Δ 1d ⓘ</th><th style="text-align:center" title="component contribution: 0 🟢 calm · 1 🟡 elevated · 2 🔴 hot (thresholds in the row tooltip)">Score 0–2 ⓘ</th></tr></thead>
        <tbody>${radar.components.map((c) => `<tr title="${c.what} • Thresholds: ${c.rule}">
          <td>${c.label} <span class="muted" style="font-size:.8em">${c.ticker}</span></td>
          <td style="text-align:right">${c.level != null ? c.level + (c.unit ? " " + c.unit : "") : "<span class=muted>no data</span>"}</td>
          <td style="text-align:right" class="${(c.chg_1d || 0) > 0 ? "pos" : (c.chg_1d || 0) < 0 ? "neg" : "muted"}">${c.chg_1d != null ? c.chg_1d + "%" : "—"}</td>
          <td style="text-align:center">${c.score == null ? "—" : ["🟢","🟡","🔴"][c.score]}</td>
        </tr>`).join("")}</tbody></table></div>
      ${radar.note ? `<div class="muted mt" style="font-size:.82em">⚠️ ${radar.note}</div>` : ""}
      ${radar.history && radar.history.length
        ? `<div class="mt"><canvas id="radarChart" height="50"></canvas>
           ${radar.history[radar.history.length-1].comment ? `<div class="muted mt" style="font-size:.85em">🤖 Comment (local AI): ${radar.history[radar.history.length-1].comment}</div>` : ""}</div>`
        : `<div class="muted mt" style="font-size:.82em">No readings yet — the radar stores the first one on the next daily cycle (or once the nightly sync delivers quotes).</div>`}
      <div class="muted mt" style="font-size:.78em">The reading = the sum of component scores (each 0🟢/1🟡/2🔴, max 8 total). The radar predicts nothing — it contextualizes. Hover rows/columns for explanations.</div>
    </div>` : ""}

    ${(() => {
      const view = localStorage.getItem("brief_view") || "daily";
      const b = (briefs || {})[view];
      const controls = `
        <button data-briefview="daily" class="${view === "daily" ? "primary" : ""}" style="font-size:.85em">Daily</button>
        <button data-briefview="weekly" class="${view === "weekly" ? "primary" : ""}" style="font-size:.85em">Weekly</button>
        ${view === "daily" ? `<button id="briefRefresh" style="font-size:.85em" title="pull fresh quotes and regenerate">🔄 Fetch latest</button>` : ""}`;
      if (b && b.headline) return marketBriefHtml(b, controls);
      return `<div class="card"><div class="row" style="align-items:center;gap:8px;flex-wrap:wrap">
        <h3 style="margin:0">🧭 Market brief</h3>${controls}</div>
        <div class="muted mt" id="briefEmptyMsg">No ${view} brief yet — generating it now from your cached quotes…
          (needs a running AI and at least one ticker; daily regenerates each morning, weekly on Mondays — Data → Schedules)</div>
      </div>`;
    })()}
    <h3 class="mt">Watchlist</h3>
    <div class="muted" style="font-size:.82em;margin:2px 0 6px">Quotes come from your local cache. The 🌍 Risk Radar fetches its four tickers by itself (keyless Yahoo); everything else needs your own sync — see README › Connecting your own services.</div>
    <div class="card">
      <div class="row">
        <input id="wlTicker" placeholder="ticker e.g. AAPL" style="width:140px">
        <button class="primary" id="wlAdd">Add</button>
        <button id="wlRefresh">Refresh from cloud</button>
        <span class="muted">last sync: ${wl.last_sync || "never"}</span>
      </div>
    </div>
    <div class="card mt"><div id="wlTable"><div class="empty">Loading…</div></div></div>
    <div class="card mt">
      <div class="row" style="align-items:center;gap:8px;flex-wrap:wrap">
        <h3 id="chartTitle" style="margin:0">Pick a ticker from the table</h3>
        <span id="chartRange" style="display:none;gap:4px" class="row">
          ${["1M", "6M", "1Y", "Max"].map((r) => `<button data-range="${r}" style="font-size:.8em">${r}</button>`).join("")}
        </span>
      </div>
      <div id="chartMeta" class="muted" style="font-size:.78em;margin:2px 0"></div>
      <canvas id="priceChart"></canvas>
      <canvas id="rsiChart" height="70" style="display:none;margin-top:6px"></canvas>
    </div>
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


  const TICKER_NAMES_EXTRA = {
    "^VIX": "VIX — S&P 500 volatility index (the market's 'fear gauge')",
    "^GSPC": "S&P 500 index (500 largest US companies)",
    "^IXIC": "NASDAQ Composite index (US tech-heavy)",
    "GC=F": "Gold — futures price per troy ounce (USD)",
    "SI=F": "Silver — futures price per troy ounce (USD)",
    "CL=F": "WTI crude oil — futures price per barrel (USD)",
    "EURUSD=X": "EUR/USD — euro priced in US dollars",
    "EURPLN=X": "EUR/PLN — euro priced in Polish zloty",
    "USDPLN=X": "USD/PLN — US dollar priced in Polish zloty",
    "VWCE.DE": "Vanguard FTSE All-World ETF (Xetra) — the whole world market",
    "BTC-USD": "Bitcoin in US dollars",
  };
  const tickerDesc = (t) => TICKER_NAMES[t] || TICKER_NAMES_EXTRA[t] || (
    t.endsWith("=F") ? "commodity futures contract" :
    t.endsWith("=X") ? "currency pair (FX)" :
    t.startsWith("^") ? "market index" :
    /\.DE$/.test(t) ? "ETF/share listed on Xetra (Frankfurt)" :
    /\.L$/.test(t) ? "ETF/share listed in London" :
    /\.AS$/.test(t) ? "ETF/share listed in Amsterdam" : "");
  const tickerShort = (t) => { const d = tickerDesc(t); return d ? d.split(" — ")[0].slice(0, 34) : ""; };
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
      ${hint("RSI14", "Relative Strength Index (14 sessions), 0–100: >70 overbought (stretched up), <30 oversold (stretched down), ~50 neutral. Works even on short history — useful where SMA50/200 has no data yet.")}
      ${hint("Off 52w high", "How many % the price is below the one-year maximum (drawdown). −5% = near the top; −40% = a deep sell-off.")}
      ${hint("Target", "YOUR price target — enter it manually (e.g. analyst consensus or a sell/buy-more price). Saves automatically.")}
      ${hint("Upside", "How many % from the price to your target. Negative = price already above the target — revise the target or take profit.")}
      <th></th>
    </tr></thead><tbody>` + rows.map((a) => { const t = esc(a.ticker); return a.error
      ? `<tr><td>${t}</td><td colspan="8" class="muted">no data — refresh from cloud</td>
         <td><button class="danger" data-rm="${t}">✕</button></td></tr>`
      : `<tr data-t="${t}" style="cursor:pointer">
        <td><b><span class="hint" title="${esc(tickerDesc(a.ticker) || a.ticker)}">${t}</span></b>${tickerShort(a.ticker) ? `<div class="muted" style="font-size:.72em;line-height:1.2">${esc(tickerShort(a.ticker))}</div>` : ""}</td>
        <td>${fmt.num(a.last_close)} ${a.currency}</td>
        <td class="${a.change_1d_pct >= 0 ? "pos" : "neg"}">${fmt.pct(a.change_1d_pct)}</td>
        <td class="${a.change_30d_pct >= 0 ? "pos" : "neg"}">${fmt.pct(a.change_30d_pct)}</td>
        <td>${a.sma50 == null ? `<span class="muted hint" title="fewer than 50 sessions in cache — click the row: the chart fetches deeper history from Yahoo and this fills in">—</span>` : `<span class="badge ${a.last_close > a.sma50 ? "up" : "down"}">${a.last_close > a.sma50 ? "above" : "below"} ${fmt.num(a.sma50, 0)}</span>`}</td>
        <td>${a.rsi14 == null ? '<span class="muted">—</span>' : `<span class="${a.rsi14 > 70 ? "neg" : a.rsi14 < 30 ? "pos" : "muted"}">${a.rsi14}</span>`}</td>
        <td class="neg">${fmt.pct(a.drawdown_from_high_pct)}</td>
        <td><input type="number" value="${a.analyst_target || ""}" data-target="${t}" style="width:80px"></td>
        <td class="${a.target_upside_pct >= 0 ? "pos" : "neg"}">${fmt.pct(a.target_upside_pct)}</td>
        <td><button class="danger" data-rm="${t}">✕</button></td>
      </tr>`; }).join("") + "</tbody></table>";

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

  let chart, rsiChart, curTicker;
  const RANGE_DAYS = { "1M": 22, "6M": 128, "1Y": 252, "Max": 100000 };
  async function drawChart(ticker, range) {
    curTicker = ticker;
    range = range || localStorage.getItem("chart_range") || "1Y";
    localStorage.setItem("chart_range", range);
    let hist = await api.get(`/api/market/prices/${ticker}?days=100000`);
    // deepen thin tickers (radar commodities/FX only get a shallow backfill) so
    // a real 1-year view — and the 50/200 averages — become available
    const wantDays = RANGE_DAYS[range];
    if (hist.length < Math.min(wantDays, 240) && !window[`_deep_${ticker}`]) {
      window[`_deep_${ticker}`] = true;
      document.getElementById("chartMeta").textContent = "fetching more history…";
      await api.post(`/api/market/deepen/${encodeURIComponent(ticker)}`, { range: "2y" }).catch(() => {});
      hist = await api.get(`/api/market/prices/${ticker}?days=100000`);
    }
    if (!hist.length) return;
    const shown = range === "Max" ? hist : hist.slice(-wantDays);
    const closes = shown.map((h) => h.close);
    const full = hist.map((h) => h.close);
    // SMAs computed on the FULL series so the line is correct at the left edge
    const offset = hist.length - shown.length;
    const smaFull = (n) => full.map((_, i) =>
      i + 1 >= n ? full.slice(i + 1 - n, i + 1).reduce((a, b) => a + b, 0) / n : null);
    const smaShown = (n) => smaFull(n).slice(offset);
    // Bollinger(20) on the full series, then sliced to the view
    const bands = full.map((_, i) => {
      if (i + 1 < 20) return [null, null];
      const w = full.slice(i - 19, i + 1);
      const m = w.reduce((a, b) => a + b, 0) / 20;
      const sd = Math.sqrt(w.reduce((a, b) => a + (b - m) ** 2, 0) / 20);
      return [m - 2 * sd, m + 2 * sd];
    });
    const bLow = bands.map((x) => x[0]).slice(offset);
    const bUp = bands.map((x) => x[1]).slice(offset);

    document.getElementById("chartTitle").textContent = ticker;
    document.getElementById("chartRange").style.display = "inline-flex";
    document.querySelectorAll("[data-range]").forEach((b) =>
      b.classList.toggle("primary", b.dataset.range === range));
    const span = shown.length ? `${shown[0].date} → ${shown[shown.length - 1].date}` : "";
    const thin = range !== "Max" && shown.length < wantDays * 0.8;
    document.getElementById("chartMeta").innerHTML =
      `${shown.length} sessions · ${span}` +
      (thin ? ` · <span style="color:#e0a458">only ${shown.length} in cache for this window — the sync/Yahoo has no more yet</span>` : "") +
      ` · <span class="hint" title="Bollinger Bands: SMA20 ± 2σ. Price hugging the upper band = stretched high; lower = stretched low; wide bands = high volatility.">Bollinger 20</span> shown`;

    if (chart) chart.destroy();
    chart = trackChart(new Chart(document.getElementById("priceChart"), {
      type: "line",
      data: {
        labels: shown.map((h) => h.date),
        datasets: [
          { label: "Bollinger upper", data: bUp, borderColor: "#3ecf8e55", borderDash: [2, 3], pointRadius: 0, fill: false },
          { label: "Bollinger lower", data: bLow, borderColor: "#3ecf8e55", borderDash: [2, 3], pointRadius: 0, fill: "-1", backgroundColor: "#3ecf8e12" },
          { label: ticker, data: closes, borderColor: "#4c8dff", tension: 0.2, pointRadius: 0 },
          { label: "SMA50", data: smaShown(50), borderColor: "#ffd166", borderDash: [4, 4], pointRadius: 0 },
          { label: "SMA200", data: smaShown(200), borderColor: "#b78cff", borderDash: [4, 4], pointRadius: 0 },
        ],
      },
      options: { interaction: { mode: "index", intersect: false },
        plugins: { legend: { labels: { filter: (i) => !/Bollinger lower/.test(i.text) } } } },
    }));

    // RSI(14) sub-chart with 30/70 guide lines
    const rsi = full.map((_, i) => {
      if (i < 14) return null;
      let g = 0, l = 0;
      for (let k = i - 13; k <= i; k++) { const d = full[k] - full[k - 1]; if (d > 0) g += d; else l -= d; }
      if (l === 0) return 100;
      return 100 - 100 / (1 + (g / 14) / (l / 14));
    }).slice(offset);
    const rsiEl = document.getElementById("rsiChart");
    rsiEl.style.display = "block";
    if (rsiChart) rsiChart.destroy();
    rsiChart = trackChart(new Chart(rsiEl, {
      type: "line",
      data: { labels: shown.map((h) => h.date), datasets: [
        { label: "RSI(14)", data: rsi, borderColor: "#e0a458", pointRadius: 0, tension: 0.2 },
        { label: "70", data: shown.map(() => 70), borderColor: "#ff5c5c33", borderDash: [3, 3], pointRadius: 0 },
        { label: "30", data: shown.map(() => 30), borderColor: "#3ecf8e33", borderDash: [3, 3], pointRadius: 0 },
      ] },
      options: { interaction: { mode: "index", intersect: false }, scales: { y: { min: 0, max: 100 } },
        plugins: { legend: { labels: { filter: (i) => i.text === "RSI(14)" } } } },
    }));
  }

  document.querySelectorAll("[data-range]").forEach((b) =>
    b.addEventListener("click", () => { if (curTicker) drawChart(curTicker, b.dataset.range); }));

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

  const PROMPTS = {
    analysis_market_brief: `Write a short market brief for my portfolio and return ONLY valid JSON: {"headline": str, "as_of": "YYYY-MM-DD", "highlights": [{"icon": "emoji", "title": str, "text": str}], "geopolitics": [{"title": str, "text": str}], "positions": [{"ticker": str, "stance": "hold|add|trim", "note": str}]}. Ask me for my tickers first.`,
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

  el.querySelectorAll("[data-briefview]").forEach((b) => b.addEventListener("click", () => {
    localStorage.setItem("brief_view", b.dataset.briefview); route();
  }));
  {
    const view = localStorage.getItem("brief_view") || "daily";
    if (!((briefs || {})[view] || {}).headline && !window._briefAutoTried) {
      window._briefAutoTried = true;
      api.post("/api/market/brief/refresh", { kind: view }).then((r) => {
        if (r && r.ok) route();
        else { const m = document.getElementById("briefEmptyMsg"); if (m) m.textContent = (r && r.error) || "generation failed — check AI mode in Control"; }
      }).catch((e) => { const m = document.getElementById("briefEmptyMsg"); if (m) m.textContent = e.message; });
    }
  }
  const br = document.getElementById("briefRefresh");
  if (br) br.addEventListener("click", async () => {
    br.disabled = true; br.textContent = "🔄 generating…";
    const r = await api.post("/api/market/brief/refresh", { kind: "daily" }).catch((e) => ({ ok: false, error: e.message }));
    if (r && r.ok) { route(); } else { br.disabled = false; br.textContent = "🔄 Fetch latest"; alert(r && r.error || "failed"); }
  });
}
