function marketBriefHtml(b) {
  if (!b || !b.headline) {
    return `<div class="card"><h3 style="margin-top:0">🧭 Brief rynkowy</h3>
      <div class="muted">Brak zapisanego briefu. Authored offline (Claude/own notes) and stored under the
        <code>analysis_market_brief</code> setting — key moves, macro context, and a per-position stance.</div></div>`;
  }
  const hi = (b.highlights || []).map((h) => `<div class="card" style="margin:0">
      <div style="font-size:1.4em">${h.icon || "•"}</div>
      <div style="font-weight:600;margin:2px 0">${h.title}</div>
      <div class="muted" style="font-size:.9em">${h.text}</div></div>`).join("");
  const geo = (b.geopolitics || []).map((g) => `<details class="mt">
      <summary style="cursor:pointer;font-weight:600">${g.title}</summary>
      <div class="muted mt" style="font-size:.92em">${g.text}</div></details>`).join("");
  const stanceColor = (s) => /sell|sprzedaj/i.test(s) ? "#3ecf8e" : /hold|trzymaj|core|rdzeń/i.test(s) ? "#4c8dff"
    : /accumulate|dca|buduj|stopniowo/i.test(s) ? "#ffd166" : "#9aa";
  const pos = (b.positions || []).map((p) => `<tr>
      <td><b>${p.ticker}</b></td>
      <td><span class="badge" style="background:${stanceColor(p.stance)}22;color:${stanceColor(p.stance)}">${p.stance}</span></td>
      <td class="muted" style="font-size:.9em">${p.text}</td></tr>`).join("");
  return `
    <div class="card" style="border-left:4px solid #4c8dff">
      <div class="row" style="justify-content:space-between;align-items:baseline">
        <h3 style="margin:0">🧭 Brief rynkowy</h3>
        <span class="muted" style="font-size:.82em">stan na ${b.as_of || "—"}</span>
      </div>
      ${b.regime ? `<div class="mt" style="font-weight:600;color:#ffd166">${b.regime}</div>` : ""}
      <div class="mt">${b.headline}</div>
    </div>
    ${hi ? `<div class="grid cols-4 mt">${hi}</div>` : ""}
    ${geo ? `<div class="card mt"><h3 style="margin-top:0">🌍 Kontekst — co napędza ruchy</h3>${geo}</div>` : ""}
    ${pos ? `<div class="card mt"><h3 style="margin-top:0">🎯 Co z tym zrobić — per pozycja</h3>
      <table><thead><tr><th>Ticker</th><th>Nastawienie</th><th>Uzasadnienie</th></tr></thead>
      <tbody>${pos}</tbody></table>
      ${b.fx_note ? `<div class="muted mt" style="border-left:3px solid #e0a458;padding-left:8px">💱 ${b.fx_note}</div>` : ""}</div>` : ""}
    ${b.method_note ? `<div class="muted mt" style="font-size:.8em">${b.method_note}</div>` : ""}`;
}

async function renderMarket(el) {
  const [wl, brief] = await Promise.all([
    api.get("/api/watchlist"),
    api.get("/api/analysis/market_brief").catch(() => ({})),
  ]);
  el.innerHTML = `
    <h2>Rynek</h2>
    ${marketBriefHtml(brief)}
    <h3 class="mt">Watchlista</h3>
    <div class="card">
      <div class="row">
        <input id="wlTicker" placeholder="ticker np. AAPL" style="width:140px">
        <button class="primary" id="wlAdd">Dodaj</button>
        <button id="wlRefresh">Odśwież z chmury</button>
        <span class="muted">ostatnia synchronizacja: ${wl.last_sync || "nigdy"}</span>
      </div>
    </div>
    <div class="card mt"><div id="wlTable"><div class="empty">Ładowanie…</div></div></div>
    <div class="card mt"><h3 id="chartTitle">Wybierz ticker z tabeli</h3><canvas id="priceChart"></canvas></div>
    `;

  const TICKER_NAMES = {
    "TEAM": "RSU stock (ustaw ticker w RSU)",
    "GOOGL": "Alphabet Inc. (Google) — akcje z XTB",
    "AMZN": "Amazon.com Inc. — akcje z XTB",
    "NVDA": "NVIDIA Corporation — akcje z XTB",
    "V": "Visa Inc. — operator kart płatniczych, akcje z XTB",
    "IWDA.AS": "iShares Core MSCI World ETF (Amsterdam) — szeroki rynek świata",
    "SXR8.DE": "iShares Core S&P 500 ETF (Xetra)",
    "CNDX.L": "iShares NASDAQ 100 ETF (Londyn)",
    "USDPLN=X": "Kurs dolara do złotego",
    "EURPLN=X": "Kurs euro do złotego",
    "EURUSD=X": "Kurs euro do dolara",
  };

  async function loadTable() {
    const tickers = (await api.get("/api/watchlist")).tickers;
    if (!tickers.length) {
      document.getElementById("wlTable").innerHTML =
        '<div class="empty">Pusta watchlista — dodaj ticker powyżej</div>';
      return;
    }
    const rows = await Promise.all(tickers.map((t) =>
      api.get("/api/market/analytics/" + encodeURIComponent(t.ticker)).catch(() => ({ ticker: t.ticker, error: "?" }))));
    const hint = (label, tip) => `<th><span class="hint" title="${tip}">${label}</span></th>`;
    document.getElementById("wlTable").innerHTML = `<table><thead><tr>
      ${hint("Ticker", "Symbol giełdowy instrumentu — najedź na symbol w tabeli, żeby zobaczyć pełną nazwę")}
      ${hint("Kurs", "Ostatnie zamknięcie dzienne (n8n pobiera codziennie ~22:30; apka dociąga rano)")}
      ${hint("1D", "Zmiana kursu vs poprzednia sesja")}
      ${hint("30D", "Zmiana kursu przez ostatnie 30 dni")}
      ${hint("SMA50", "Średnia kursu z ostatnich 50 sesji (~2,5 mies.). NAD = kurs powyżej średniej → trend wzrostowy; POD = poniżej → spadkowy. Klasyczny filtr momentum. Liczba = wartość średniej.")}
      ${hint("Od szczytu 52w", "Ile % kurs jest poniżej maksimum z ostatniego roku (drawdown). −5% = blisko szczytu; −40% = głęboka przecena.")}
      ${hint("Target", "TWÓJ cel cenowy — wpisz ręcznie (np. konsensus analityków albo cena sprzedaży/dokupienia). Zapisuje się sam.")}
      ${hint("Upside", "Ile % brakuje od kursu do Twojego targetu. Ujemny = kurs już powyżej celu → rewizja targetu albo realizacja zysku.")}
      <th></th>
    </tr></thead><tbody>` + rows.map((a) => a.error
      ? `<tr><td>${a.ticker}</td><td colspan="7" class="muted">brak danych — odśwież z chmury</td>
         <td><button class="danger" data-rm="${a.ticker}">✕</button></td></tr>`
      : `<tr data-t="${a.ticker}" style="cursor:pointer">
        <td><b><span class="hint" title="${TICKER_NAMES[a.ticker] || a.ticker}">${a.ticker}</span></b></td>
        <td>${fmt.num(a.last_close)} ${a.currency}</td>
        <td class="${a.change_1d_pct >= 0 ? "pos" : "neg"}">${fmt.pct(a.change_1d_pct)}</td>
        <td class="${a.change_30d_pct >= 0 ? "pos" : "neg"}">${fmt.pct(a.change_30d_pct)}</td>
        <td><span class="badge ${a.last_close > a.sma50 ? "up" : "down"}">${a.last_close > a.sma50 ? "nad" : "pod"} ${fmt.num(a.sma50, 0)}</span></td>
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
    document.getElementById("chartTitle").textContent = ticker + " — 12 miesięcy";
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
    alert(`Zsynchronizowano ${r.rows} notowań`);
    route();
  });

  await loadTable();
}
