/* First-run setup wizard: pick modules, choose sample data or empty start,
   learn about optional integrations. Re-run anytime via #wizard. */
async function renderWizard(el) {
  const cfg = await api.get("/api/app-config");
  const mods = cfg.modules || {};

  const moduleRow = (m) => `
    <label class="card" style="display:flex;gap:12px;align-items:flex-start;cursor:pointer;margin:0">
      <input type="checkbox" data-mod="${m.id}" ${mods[m.id] ? "checked" : ""} style="margin-top:4px">
      <div>
        <div style="font-weight:600">${m.icon} ${m.label}</div>
        <div class="muted" style="font-size:.85em">${m.desc}</div>
      </div>
    </label>`;

  el.innerHTML = `
    <div style="max-width:820px;margin:0 auto">
      <h2 style="margin-bottom:4px">👋 Welcome — let's set up your finance cockpit</h2>
      <div class="muted" style="margin-bottom:16px">Three quick steps. Everything runs locally —
        your data stays in one file on this machine (<code>.finance/finance.db</code>).
        You can re-run this anytime by opening <code>#wizard</code>.</div>

      <div class="card" style="border-left:4px solid #4c8dff">
        <h3 style="margin-top:0">1 · Which areas do you want to track?</h3>
        <div class="muted" style="font-size:.85em;margin-bottom:10px">Core (dashboard, cash-flow, wealth,
          goals, forecasts) is always on. Toggle the rest — you can change this later.</div>
        <div class="grid cols-2" style="gap:10px">
          ${(cfg.registry || []).map(moduleRow).join("")}
        </div>
      </div>

      <div class="card mt" style="border-left:4px solid #ffd166">
        <h3 style="margin-top:0">2 · Start with data</h3>
        ${cfg.has_data ? `
          <div class="muted">You already have data in the local database — skipping this step.</div>
          <input type="hidden" id="wzData" value="keep">` : `
          <label style="display:block;cursor:pointer;margin-bottom:8px">
            <input type="radio" name="wzData" value="sample" checked>
            <b>Load sample data</b> <span class="muted">(fake persona "Alex Demo" — see how everything looks,
            wipe later by deleting <code>.finance/</code>)</span>
          </label>
          <label style="display:block;cursor:pointer">
            <input type="radio" name="wzData" value="empty">
            <b>Start empty</b> <span class="muted">(add your own numbers in Wealth / Loans / Goals tabs)</span>
          </label>`}
      </div>

      <div class="card mt" style="border-left:4px solid #3ecf8e">
        <h3 style="margin-top:0">3 · Optional integrations <span class="muted" style="font-weight:normal;font-size:.7em">— skip freely, the app is fully functional offline</span></h3>
        <div style="font-size:.9em">
          <p><b>📈 Live market data (Supabase)</b> — the Markets/FX/RSU tabs read daily quotes from a free
          <a href="https://supabase.com" target="_blank">Supabase</a> table. Create a project, add
          <code>SUPABASE_URL</code> + <code>SUPABASE_ANON_KEY</code> to <code>.env</code>, and feed it daily
          (e.g. with <a href="https://n8n.io" target="_blank">n8n</a>). Full guide in the README.</p>
          <p><b>🔔 Telegram alerts (n8n)</b> — an importable workflow in <code>integrations/n8n/</code>
          pings you when the data pipeline goes stale. Setup guide included.</p>
          <p class="muted">Without these, market views simply show "no data" — everything else works.</p>
        </div>
      </div>

      <div class="row mt" style="justify-content:flex-end;gap:10px">
        <button id="wzFinish" class="primary" style="padding:10px 22px">Finish setup →</button>
      </div>
      <div id="wzStatus" class="muted mt" style="text-align:right"></div>
    </div>`;

  document.getElementById("wzFinish").addEventListener("click", async (e) => {
    const btn = e.target;
    btn.disabled = true;
    const status = document.getElementById("wzStatus");
    const modules = {};
    el.querySelectorAll("[data-mod]").forEach((c) => { modules[c.dataset.mod] = c.checked; });
    const dataChoice = cfg.has_data ? "keep"
      : (el.querySelector('input[name="wzData"]:checked') || {}).value || "empty";
    try {
      if (dataChoice === "sample") {
        status.textContent = "Loading sample data…";
        await api.post("/api/sample-data");
      }
      status.textContent = "Saving configuration…";
      await api.post("/api/app-config", { modules, wizard_completed: true });
      location.hash = "#dashboard";
      location.reload();
    } catch (err) {
      status.textContent = "Error: " + err.message;
      btn.disabled = false;
    }
  });
}
