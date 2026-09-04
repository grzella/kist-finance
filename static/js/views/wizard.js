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

      <div class="card" style="border-left:4px solid var(--accent)">
        <h3 style="margin-top:0">1 · Which areas do you want to track?</h3>
        <div class="muted" style="font-size:.85em;margin-bottom:10px">Core (dashboard, cash-flow, wealth,
          goals, forecasts) is always on. Toggle the rest — you can change this later.</div>
        <div class="grid cols-2" style="gap:10px">
          ${(cfg.registry || []).map(moduleRow).join("")}
        </div>
      </div>

      <div class="card mt" style="border-left:4px solid var(--warn)">
        <h3 style="margin-top:0">2 · Start with data</h3>
        ${cfg.has_data ? `
          <div class="muted">You already have data in the local database — skipping this step.</div>
          <input type="hidden" id="wzData" value="keep">` : `
          <label style="display:block;cursor:pointer;margin-bottom:8px">
            <input type="radio" name="wzData" value="sample" checked>
            <b>Load sample data</b> <span class="muted">(fake persona "Alex Demo" — see how everything looks,
            clear it later with one click in Control Center → 🧨 Wipe all data)</span>
          </label>
          <label style="display:block;cursor:pointer;margin-bottom:8px">
            <input type="radio" name="wzData" value="empty">
            <b>Start empty</b> <span class="muted">(add your own numbers in Wealth / Loans / Goals tabs)</span>
          </label>
          <label style="display:block;cursor:pointer">
            <input type="radio" name="wzData" value="ai">
            <b>Set it up with an AI assistant</b> <span class="muted">(get a ready-made prompt that interviews you and tells you exactly what to enter where)</span>
          </label>
          <div id="wzAiBox" style="display:none;margin:10px 0 0 24px;padding:10px 12px;background:var(--accent)14;border-radius:8px;font-size:.88em">
            <div style="padding:6px 10px;background:var(--warn)22;border-radius:6px;margin-bottom:8px">⚠️ <b>Privacy note:</b> the app itself runs 100% on localhost, but anything you paste into a <b>cloud</b> assistant (ChatGPT, Claude web…) leaves your machine and is processed by that provider. For full privacy use a <b>local model</b> (Control Center → AI mode) or enter the numbers yourself.</div>
            How it works: 1) click the button and paste the prompt into any AI assistant · 2) answer its questions ·
            3) it hands you a tab-by-tab checklist (and ready JSON for the analysis boxes) · 4) finish this wizard with "Start empty" behavior and type the values in.
            <div class="row mt" style="gap:8px;align-items:center">
              <button type="button" id="wzAiCopy">📋 Copy AI onboarding prompt</button>
              <span class="muted" id="wzAiCopied" style="font-size:.85em"></span>
            </div>
          </div>`}
      </div>

      <div class="card mt" style="border-left:4px solid var(--pos)">
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

            <div class="card mt" style="border-left:4px solid var(--accent)">
        <h3 style="margin-top:0">💱 Base currency</h3>
        <div class="row" style="align-items:center;gap:10px">
          <select id="wzCur">${["PLN","EUR","USD","GBP","CHF"].map((c) => `<option ${c === (cfg.currency || "PLN") ? "selected" : ""}>${c}</option>`).join("")}</select>
          <span class="muted" style="font-size:.85em">Used everywhere amounts are shown. Change later in Control Center.</span>
        </div>
      </div>

<div class="row mt" style="justify-content:flex-end;gap:10px">
        <button id="wzFinish" class="primary" style="padding:10px 22px">Finish setup →</button>
      </div>
      <div id="wzStatus" class="muted mt" style="text-align:right"></div>
    </div>`;

  const AI_PROMPT = `You are helping me set up "Kist", a local-first personal-finance app I run on localhost. Interview me step by step (one topic at a time, short questions), then output a tab-by-tab checklist of exactly what to enter, using my base currency. Topics and the fields the app expects:
1. Cash-flow tab: annual net income, fixed monthly costs, optional annual bonus (net) and its month.
2. Wealth tab: each asset as name / type (cash, ETF, stock, property, vehicle, other) / owner / current value.
3. Loans tab: each loan as name / balance / annual rate % / monthly payment / months left (and fixed-rate end date if any).
4. Goals tab: each goal as name / target amount / amount saved so far / monthly pace.
5. Taxes tab: capital-gains %, rental %, business income %, social-security monthly amount.
6. RSU tab (if I have stock compensation): ticker, grant value, vesting schedule.
7. Business tab (if I have a company): monthly revenue, monthly costs, tax rate.
8. Market tab: 3-8 tickers for my watchlist.
9. Career tab: my current role and a realistic target role set.
For the analysis boxes (Career analysis, Property purchase, Market brief) produce ready-to-paste JSON — I will show you each box's exact schema by pasting its "Copy AI prompt" text when we get there.
Finish with the checklist formatted as: TAB → field → value, in the order above. Ask before assuming anything.`;
  const aiBox = document.getElementById("wzAiBox");
  el.querySelectorAll('input[name="wzData"]').forEach((r) => r.addEventListener("change", () => {
    if (aiBox) aiBox.style.display = r.value === "ai" && r.checked ? "block" : "none";
  }));
  const aiCopy = document.getElementById("wzAiCopy");
  if (aiCopy) aiCopy.addEventListener("click", async () => {
    await navigator.clipboard.writeText(AI_PROMPT);
    document.getElementById("wzAiCopied").textContent = "copied ✓ — paste it into your assistant";
  });

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
      await api.post("/api/app-config", { modules, wizard_completed: true, base_currency: (document.getElementById("wzCur") || {}).value });
      location.hash = "#dashboard";
      location.reload();
    } catch (err) {
      status.textContent = "Error: " + err.message;
      btn.disabled = false;
    }
  });
}
