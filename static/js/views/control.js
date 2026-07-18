function securityReviewHtml(rev) {
  if (!rev || !rev.verdict) {
    return `<div class="muted">Jeszcze nie uruchomiono. Kliknij „Uruchom security &amp; testy”,
      żeby zrobić pełny skan (wycieki w repo i historii gita, analiza kodu pod kątem kontrybutorów,
      audyt danych osobowych, konfiguracja połączeń, testy funkcjonalne).</div>`;
  }
  const SEV = {
    critical: "#ff5c5c", high: "#ff8f3f", medium: "#ffd166", low: "#4c8dff", info: "#8a90a6",
  };
  const STAT = { pass: ["✓", "#3ecf8e"], warn: ["!", "#ffd166"], fail: ["✗", "#ff5c5c"] };
  const row = (i) => {
    const [ic, col] = STAT[i.status] || ["·", "#8a90a6"];
    return `<tr>
      <td style="color:${col};font-weight:700;text-align:center">${ic}</td>
      <td><span class="badge" style="background:${SEV[i.severity]}22;color:${SEV[i.severity]}">${i.severity}</span></td>
      <td><b>${i.title}</b>${i.status !== "pass" && i.detail ? `<div class="muted" style="font-size:.82em">${i.detail}</div>` : ""}
        ${i.status !== "pass" && i.fix ? `<div style="font-size:.82em;color:#ffd166">🔧 ${i.fix}</div>` : ""}</td>
    </tr>`;
  };
  const area = (a) => `<div class="mt"><div style="font-weight:600;margin-bottom:4px">${a.area}</div>
    <div style="overflow-x:auto"><table>
      <tbody>${a.items.map(row).join("")}</tbody></table></div></div>`;
  return `<div class="row" style="justify-content:space-between;align-items:baseline;flex-wrap:wrap">
      <div>${rev.summary}</div>
      <div class="muted" style="font-size:.82em">ostatni run: ${rev.generated_at}</div>
    </div>
    ${(rev.areas || []).map(area).join("")}`;
}

async function renderControl(el) {
  const [d, rev] = await Promise.all([
    api.get("/api/health"),
    api.get("/api/security-review").catch(() => ({})),
  ]);
  const s = d.summary;
  const vColor = { ok: "#3ecf8e", warn: "#ffd166", error: "#ff5c5c" };
  const secColor = vColor[rev && rev.verdict] || "#8a90a6";
  const badge = (st) => {
    const m = { ok: ["✅", "pos"], warn: ["⚠️", ""], error: ["🛑", "neg"], info: ["ℹ️", "muted"] };
    const [ic, cls] = m[st] || ["·", "muted"];
    return `<span class="badge ${cls}">${ic} ${st}</span>`;
  };
  el.innerHTML = `
    <h2>🛠️ Control Center</h2>
    <div class="row" style="gap:8px;margin-bottom:12px">
      <a href="#control" style="text-decoration:none;padding:5px 12px;border-radius:6px;background:${CHART_COLORS[0]};color:#fff">🛠️ Automatyzacje &amp; health</a>
      <a href="#reminders" style="text-decoration:none;padding:5px 12px;border-radius:6px;border:1px solid #4a4f66;color:#e8e8ee">🔔 Przypomnienia</a>
      <a href="#data" style="text-decoration:none;padding:5px 12px;border-radius:6px;border:1px solid #4a4f66;color:#e8e8ee">📊 Dane w aplikacji</a>
    </div>
    <div class="muted" style="margin-bottom:12px">Wszystko, co ma się dziać automatycznie: częstotliwość, ostatni update (data+godzina) i status.
      Sprawdzono: ${d.checked_at}.</div>

    <div class="grid cols-4">
      <div class="card kpi"><div class="label">Zadania OK</div><div class="value pos">${s.ok}</div><div class="sub">z ${s.total}</div></div>
      <div class="card kpi"><div class="label">Ostrzeżenia</div><div class="value ${s.warn ? "" : "muted"}">${s.warn}</div><div class="sub">nieświeże / offline</div></div>
      <div class="card kpi"><div class="label">Błędy</div><div class="value ${s.error ? "neg" : "muted"}">${s.error}</div><div class="sub">wymagają akcji</div></div>
      <div class="card kpi"><div class="label">Odśwież</div>
        <div class="value"><button class="primary" id="hRefresh" style="font-size:.5em;padding:8px 14px">Sprawdź teraz</button></div></div>
    </div>

    <div class="grid cols-2 mt">
      <div class="card" style="border-left:4px solid #ffd166;margin:0">
        <h3 style="margin-top:0">🔬 Tryb demo</h3>
        <div class="row" style="align-items:center;gap:12px">
          <button class="${demoOn() ? "danger" : "primary"}" id="demoToggle">${demoOn() ? "Wyłącz tryb demo" : "Włącz tryb demo"}</button>
          <span class="muted" style="font-size:.85em">Maskuje kwoty wzorem 0-1 (np. „010 101 zł") — do screenshotów bez ujawniania liczb.
            Status: <b class="${demoOn() ? "neg" : "pos"}">${demoOn() ? "WŁĄCZONY" : "wyłączony"}</b>. Także przez <code>?demo</code>.</span>
        </div>
      </div>
      <div class="card" style="border-left:4px solid #4c8dff;margin:0">
        <h3 style="margin-top:0">🌐 Język / Language</h3>
        <div class="row" style="align-items:center;gap:8px">
          <button class="${langGet() === "pl" ? "primary" : ""}" id="langPl">🇵🇱 Polski</button>
          <button class="${langGet() === "en" ? "primary" : ""}" id="langEn">🇬🇧 English</button>
          <span class="muted" style="font-size:.85em">Tłumaczy interfejs (nawigacja, Control, wspólne etykiety).
            Także przez <code>?lang=en</code>.</span>
        </div>
      </div>
    </div>

    <div class="card mt" style="border-left:4px solid ${secColor}">
      <div class="row" style="justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px">
        <h3 style="margin:0">🔐 Bezpieczeństwo &amp; testy
          ${rev && rev.verdict ? `<span class="badge" style="background:${secColor}22;color:${secColor}">score ${rev.score}/100</span>` : ""}</h3>
        <button class="primary" id="secRun">🔐 Uruchom security &amp; testy</button>
      </div>
      <div class="muted" style="font-size:.85em;margin:6px 0 4px">Pełny pentest + testy funkcjonalne: wycieki sekretów w drzewie
        <b>i w historii gita</b> (kluczowe dla repo publicznego), audyt danych osobowych maintainera, analiza kodu pod kątem kontrybutorów
        (eval/exec, shell, SQL injection, debug, bind 0.0.0.0), higiena konfiguracji/połączeń i smoke-testy endpointów.
        Automatycznie co tydzień (GitHub Actions na PR-ach) albo ręcznie tym przyciskiem.</div>
      <div id="secBody">${securityReviewHtml(rev)}</div>
    </div>

    <div class="card mt">
      <div style="overflow-x:auto"><table>
        <thead><tr><th>Zadanie</th><th>Częstotliwość</th><th>Ostatni update</th><th>Status</th><th>Szczegóły</th></tr></thead>
        <tbody>${d.tasks.map((t) => `<tr>
          <td><b>${t.name}</b></td>
          <td class="muted" style="font-size:.88em">${t.freq}</td>
          <td style="white-space:nowrap">${t.last}</td>
          <td>${badge(t.status)}</td>
          <td class="muted" style="font-size:.88em">${t.detail}</td>
        </tr>`).join("")}</tbody>
      </table></div>
    </div>

    <div class="card mt muted" style="font-size:.85em">
      <b>Jak to działa:</b> kursy i marketing pobiera n8n do Supabase (publiczne dane); predykcje RSU i barometr
      utrzymuje Claude/aplikacja lokalnie; backup danych szyfrowany na Google Drive. „Audyt danych wrażliwych"
      sprawdza, czy do gita nie trafiło nic z <code>private/ .finance/ doc-raw/ *.env</code> — powinien być zawsze ✅.
      Alert e-mail/Telegram przy nieświeżych danych: gotowy workflow n8n w <code>integrations/n8n/</code> (import + Telegram bot).
      Dalej do dobudowania: auto-test spójności danych po imporcie, monitoring czy Google Drive zamontowany.
    </div>`;

  document.getElementById("hRefresh").addEventListener("click", () => route());
  document.getElementById("demoToggle").addEventListener("click", () => toggleDemo(!demoOn()));
  document.getElementById("langPl").addEventListener("click", () => langSet("pl"));
  document.getElementById("langEn").addEventListener("click", () => langSet("en"));
  document.getElementById("secRun").addEventListener("click", async (e) => {
    const btn = e.target;
    btn.disabled = true;
    btn.textContent = "⏳ Skanuję repo, historię, kod i endpointy…";
    const body = document.getElementById("secBody");
    body.innerHTML = '<div class="muted">Trwa pełny skan (może potrwać kilkanaście sekund — przeszukuję historię gita)…</div>';
    try {
      const fresh = await api.post("/api/security-review/run");
      body.innerHTML = securityReviewHtml(fresh);
      const card = btn.closest(".card");
      const col = { ok: "#3ecf8e", warn: "#ffd166", error: "#ff5c5c" }[fresh.verdict] || "#8a90a6";
      if (card) card.style.borderLeftColor = col;
    } catch (err) {
      body.innerHTML = `<div class="neg">Błąd skanu: ${err.message}</div>`;
    } finally {
      btn.disabled = false;
      btn.innerHTML = "🔐 Uruchom security &amp; testy";
    }
  });
}
