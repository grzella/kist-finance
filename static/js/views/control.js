function securityReviewHtml(rev) {
  if (!rev || !rev.verdict) {
    return `<div class="muted">Not run yet. Click "Run security &amp; tests"
      to do a full scan (leaks in the repo and git history, code review from a contributor's perspective,
      personal-data audit, connection configuration, functional tests).</div>`;
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
      <div class="muted" style="font-size:.82em">last run: ${rev.generated_at}</div>
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
      <a href="#control" style="text-decoration:none;padding:5px 12px;border-radius:6px;background:${CHART_COLORS[0]};color:#fff">🛠️ Automation &amp; health</a>
      <a href="#reminders" style="text-decoration:none;padding:5px 12px;border-radius:6px;border:1px solid #4a4f66;color:#e8e8ee">🔔 Reminders</a>
      <a href="#data" style="text-decoration:none;padding:5px 12px;border-radius:6px;border:1px solid #4a4f66;color:#e8e8ee">📊 Data in the app</a>
    </div>
    <div class="muted" style="margin-bottom:12px">Everything that should happen automatically: frequency, last update (date+time) and status.
      Checked: ${d.checked_at}.</div>

    <div class="grid cols-4">
      <div class="card kpi"><div class="label">Tasks OK</div><div class="value pos">${s.ok}</div><div class="sub">of ${s.total}</div></div>
      <div class="card kpi"><div class="label">Warnings</div><div class="value ${s.warn ? "" : "muted"}">${s.warn}</div><div class="sub">stale / offline</div></div>
      <div class="card kpi"><div class="label">Errors</div><div class="value ${s.error ? "neg" : "muted"}">${s.error}</div><div class="sub">need action</div></div>
      <div class="card kpi"><div class="label">Refresh</div>
        <div class="value"><button class="primary" id="hRefresh" style="font-size:.5em;padding:8px 14px">Check now</button></div></div>
    </div>

    <div class="grid cols-2 mt">
      <div class="card" style="border-left:4px solid #ffd166;margin:0">
        <h3 style="margin-top:0">🔬 Demo mode</h3>
        <div class="row" style="align-items:center;gap:12px">
          <button class="${demoOn() ? "danger" : "primary"}" id="demoToggle">${demoOn() ? "Disable demo mode" : "Enable demo mode"}</button>
          <span class="muted" style="font-size:.85em">Masks amounts with a 0-1 pattern (e.g. "010 101 PLN") — for screenshots without revealing figures.
            Status: <b class="${demoOn() ? "neg" : "pos"}">${demoOn() ? "ON" : "off"}</b>. Also via <code>?demo</code>.</span>
        </div>
      </div>
      <div class="card" style="border-left:4px solid #4c8dff;margin:0">
        <h3 style="margin-top:0">🌐 Language</h3>
        <div class="row" style="align-items:center;gap:8px">
          <button class="${langGet() === "pl" ? "primary" : ""}" id="langPl">🇵🇱 Polski</button>
          <button class="${langGet() === "en" ? "primary" : ""}" id="langEn">🇬🇧 English</button>
          <span class="muted" style="font-size:.85em">English is the native UI language; the Polish option translates navigation, Control and common labels.
            Also via <code>?lang=pl</code>.</span>
        </div>
      </div>
    </div>

    <div class="card mt" style="border-left:4px solid ${secColor}">
      <div class="row" style="justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px">
        <h3 style="margin:0">🔐 Security &amp; tests
          ${rev && rev.verdict ? `<span class="badge" style="background:${secColor}22;color:${secColor}">score ${rev.score}/100</span>` : ""}</h3>
        <button class="primary" id="secRun">🔐 Run security &amp; tests</button>
      </div>
      <div class="muted" style="font-size:.85em;margin:6px 0 4px">Full pentest + functional tests: secret leaks in the working tree
        <b>and in git history</b> (crucial for a public repo), maintainer personal-data audit, code review from a contributor's perspective
        (eval/exec, shell, SQL injection, debug, bind 0.0.0.0), configuration/connection hygiene and endpoint smoke tests.
        Runs automatically weekly (GitHub Actions on PRs) or manually with this button.</div>
      <div id="secBody">${securityReviewHtml(rev)}</div>
    </div>

    <div class="card mt">
      <div style="overflow-x:auto"><table>
        <thead><tr><th>Task</th><th>Frequency</th><th>Last update</th><th>Status</th><th>Details</th></tr></thead>
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
      <b>How it works:</b> n8n pulls rates and marketing data into Supabase (public data); RSU predictions and the barometer
      are maintained by Claude/the app locally; data backup is encrypted on Google Drive. The "sensitive-data audit"
      checks that nothing from <code>private/ .finance/ doc-raw/ *.env</code> made it into git — it should always be ✅.
      E-mail/Telegram alert on stale data: a ready-made n8n workflow in <code>integrations/n8n/</code> (import + Telegram bot).
      Still to build: an automatic data-consistency test after import, monitoring whether Google Drive is mounted.
    </div>`;

  document.getElementById("hRefresh").addEventListener("click", () => route());
  document.getElementById("demoToggle").addEventListener("click", () => toggleDemo(!demoOn()));
  document.getElementById("langPl").addEventListener("click", () => langSet("pl"));
  document.getElementById("langEn").addEventListener("click", () => langSet("en"));
  document.getElementById("secRun").addEventListener("click", async (e) => {
    const btn = e.target;
    btn.disabled = true;
    btn.textContent = "⏳ Scanning repo, history, code and endpoints…";
    const body = document.getElementById("secBody");
    body.innerHTML = '<div class="muted">Full scan in progress (may take a dozen or so seconds — searching git history)…</div>';
    try {
      const fresh = await api.post("/api/security-review/run");
      body.innerHTML = securityReviewHtml(fresh);
      const card = btn.closest(".card");
      const col = { ok: "#3ecf8e", warn: "#ffd166", error: "#ff5c5c" }[fresh.verdict] || "#8a90a6";
      if (card) card.style.borderLeftColor = col;
    } catch (err) {
      body.innerHTML = `<div class="neg">Scan error: ${err.message}</div>`;
    } finally {
      btn.disabled = false;
      btn.innerHTML = "🔐 Run security &amp; tests";
    }
  });
}
