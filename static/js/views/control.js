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
  const [d, rev, ai, ragStatus, bk, aiLog] = await Promise.all([
    api.get("/api/health"),
    api.get("/api/security-review").catch(() => ({})),
    api.get("/api/llm/config").catch(() => null),
    api.get("/api/rag/status").catch(() => null),
    api.get("/api/backup/status").catch(() => null),
    api.get("/api/llm/log").catch(() => null),
  ]);
  const esc = (s) => (s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
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

    ${ai ? `<div class="card mt" style="border-left:4px solid ${ai.ai_mode === "both" ? "#b78cff" : "#3ecf8e"}">
      <h3 style="margin-top:0">🤖 AI mode
        <span class="badge" style="background:${ai.ai_mode === "both" ? "#b78cff22;color:#b78cff" : "#3ecf8e22;color:#3ecf8e"}">${ai.ai_mode === "both" ? "local + cloud" : "local only"}</span></h3>
      <div class="muted" style="font-size:.85em;margin-bottom:8px">How the app answers AI questions. Default is the local model only (fully private).
        "Local + cloud" asks BOTH and shows the answers side by side — best result from the comparison, but
        <b class="neg">the cloud sends your prompt to Anthropic</b>, so enable it deliberately (not for sensitive figures).</div>
      <div class="row" style="gap:16px;flex-wrap:wrap">
        <label style="cursor:pointer"><input type="radio" name="aiMode" value="local" ${ai.ai_mode !== "both" ? "checked" : ""}>
          🔒 Local only <span class="muted" style="font-size:.85em">(${ai.local.online ? "🟢 " + ai.local.model : "🔴 offline — " + (ai.local.hint || "")})</span></label>
        <label style="cursor:pointer"><input type="radio" name="aiMode" value="both" ${ai.ai_mode === "both" ? "checked" : ""} ${ai.cloud.online ? "" : "disabled"}>
          🔒+☁️ Local + Claude <span class="muted" style="font-size:.85em">(${ai.cloud.online ? "🟢 " + ai.cloud.model : "🔴 no key — " + (ai.cloud.hint || "")})</span></label>
      </div>
      <div class="row mt" style="gap:8px">
        <input id="aiPrompt" placeholder="ask both models… (e.g. categorize: WHOLE FOODS 187)" style="flex:1">
        <button class="primary" id="aiAsk">Ask</button>
      </div>
      <div id="aiOut" class="mt"></div>
      ${ragStatus ? `<div class="row mt" style="gap:10px;align-items:center;font-size:.85em;padding-top:8px;border-top:1px solid #2a2f45">
        <span>🔎 Local RAG: <b>${ragStatus.chunks}</b> chunks <span class="muted">(${ragStatus.engine})</span></span>
        <button id="ragReindex">Reindex</button>
        <span class="muted">${ragStatus.hint || "AI questions are automatically grounded in your own data"}</span></div>` : ""}
      ${aiLog && aiLog.stats.total ? `<details class="mt" style="font-size:.85em">
        <summary style="cursor:pointer">📊 AI prompt log (${aiLog.stats.total}) — ${aiLog.stats.rag_grounded} RAG-grounded · ${aiLog.stats.cloud_calls} cloud calls</summary>
        <div class="mt">${aiLog.recent.slice(0, 8).map((e) => `<div style="border-top:1px solid #2a2f45;padding:6px 0">
          <div class="muted" style="font-size:.8em">${e.ts} · ${e.mode}${e.rag_used ? " · RAG" : ""}</div>
          <div><b>${esc(e.prompt)}</b></div>
          <div style="white-space:pre-wrap;color:#c9cee0">${esc(e.synthesis_text || e.cloud_text || e.local_text)}</div></div>`).join("")}</div>
      </details>` : ""}
    </div>` : ""}

    ${bk ? `<div class="card mt" style="border-left:4px solid #4c8dff">
      <h3 style="margin-top:0">💾 Data backup
        <span class="badge" style="background:${bk.configured ? "#3ecf8e22;color:#3ecf8e" : "#ffd16622;color:#ffd166"}">${bk.configured ? "configured" : "not set"}</span></h3>
      <div class="muted" style="font-size:.85em;margin-bottom:8px">Writes a consistent snapshot of the database into a folder your
        Google Drive / Dropbox / iCloud client already syncs. No API keys — your desktop client pushes the file to the cloud.</div>
      <div class="row" style="gap:8px;align-items:center;flex-wrap:wrap">
        <select id="bkDest" style="min-width:300px">
          <option value="">— choose a synced folder —</option>
          ${bk.destinations.map((dd) => `<option value="${dd.path}" ${bk.dir === dd.path ? "selected" : ""}>${dd.label} — ${dd.path}</option>`).join("")}
          ${bk.dir && !bk.destinations.some((dd) => dd.path === bk.dir) ? `<option value="${bk.dir}" selected>${bk.dir}</option>` : ""}
        </select>
        <button class="primary" id="bkRun" ${bk.configured ? "" : "disabled"}>Back up now</button>
      </div>
      <div class="muted mt" style="font-size:.82em">
        ${bk.last ? `Last: <b>${bk.last.name}</b> (${bk.last.when}) · ${bk.count} total` : "No backups yet."}
        ${bk.encryption.on ? " · 🔒 encrypted" : bk.encryption.lib ? " · set BACKUP_KEY in .env to encrypt" : " · " + bk.encryption.hint}
      </div>
      <div id="bkOut" class="mt"></div>
    </div>` : ""}

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
  document.querySelectorAll('input[name="aiMode"]').forEach((r) =>
    r.addEventListener("change", (e) =>
      api.post("/api/llm/config", { ai_mode: e.target.value }).then(() => route())));
  const aiAsk = document.getElementById("aiAsk");
  if (aiAsk) {
    aiAsk.addEventListener("click", async () => {
      const prompt = document.getElementById("aiPrompt").value.trim();
      if (!prompt) return;
      const out = document.getElementById("aiOut");
      aiAsk.disabled = true; out.innerHTML = '<div class="muted">Asking…</div>';
      try {
        const r = await api.post("/api/llm/ask", { prompt });
        const card = (label, res, col) => res ? `<div class="card" style="border-left:3px solid ${col};margin:0">
          <div style="font-weight:600;font-size:.85em">${label}</div>
          <div style="white-space:pre-wrap;font-size:.9em">${res.ok ? res.text : '<span class="neg">offline / no answer</span>'}</div></div>` : "";
        const syn = r.synthesis && r.synthesis.ok ? `<div class="card" style="border-left:4px solid #ffd166;margin:0 0 10px">
          <div style="font-weight:600;font-size:.85em">🧭 Verdict — synthesis of both models <span class="muted">(${r.synthesis.by === "cloud" ? "Claude" : "local"})</span></div>
          <div style="white-space:pre-wrap;font-size:.9em">${r.synthesis.text}</div></div>` : "";
        out.innerHTML = syn + `<div class="grid ${r.cloud ? "cols-2" : ""}">
          ${card("🔒 " + (r.local.label || "local"), r.local, "#3ecf8e")}
          ${r.cloud ? card("☁️ " + (r.cloud.label || "Claude"), r.cloud, "#b78cff") : ""}</div>`;
      } catch (e) { out.innerHTML = `<div class="neg">Error: ${e.message}</div>`; }
      finally { aiAsk.disabled = false; }
    });
  }
  const ragBtn = document.getElementById("ragReindex");
  if (ragBtn) {
    ragBtn.addEventListener("click", async () => {
      ragBtn.disabled = true; ragBtn.textContent = "Indexing…";
      try { await api.post("/api/rag/reindex", {}); } finally { route(); }
    });
  }
  const bkDest = document.getElementById("bkDest");
  if (bkDest) {
    bkDest.addEventListener("change", async (e) => {
      await api.post("/api/backup/config", { dir: e.target.value }); route();
    });
  }
  const bkRun = document.getElementById("bkRun");
  if (bkRun) {
    bkRun.addEventListener("click", async () => {
      bkRun.disabled = true;
      const o = document.getElementById("bkOut");
      o.innerHTML = '<div class="muted">Backing up…</div>';
      try {
        const r = await api.post("/api/backup/run", {});
        o.innerHTML = r.ok
          ? `<div class="pos">✅ ${r.file} (${r.size_kb} KB${r.encrypted ? ", 🔒 encrypted" : ""}) → ${r.dir}</div>`
          : `<div class="neg">${r.error}</div>`;
      } catch (e) { o.innerHTML = `<div class="neg">${e.message}</div>`; }
      finally { bkRun.disabled = false; }
    });
  }
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
