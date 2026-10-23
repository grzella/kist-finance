// Career → AI learning: where you stand on a 0-5 scale, a skill map with statuses you set,
// courses by priority, what to follow and a progress log. The assessment (analysis_ai_learning)
// is scored from your repositories ("Score from my repos": evidence, statuses and the level are
// computed in code, the local model only writes the text) or pasted from any AI assistant; the
// statuses and the log are yours and live apart from it (ai_learning_state), so a new
// assessment never wipes your progress.
const AL_PROMPT = `Assess my AI skills and return ONLY valid JSON: {"as_of": "YYYY-MM-DD", "score": 0-5, "target": number, "score_label": str, "scale": [{"lvl": 0-5, "name": str, "desc": str}], "verdict": str, "projects": [{"name": str, "grade": str, "what": str, "gap": str}], "skills": [{"id": str, "area": str, "name": str, "status": "have|partial|missing", "how": str, "link": str}], "certs": [{"id": str, "name": str, "provider": str, "cost": str, "time": str, "format": "online|in person|hybrid", "priority": "high|medium|low|skip", "why": str, "link": str}], "sources": {"method": str, "daily": [{"name": str, "link": str, "what": str}], "weekly": [], "quarterly": [], "services": []}, "routine": [str], "plan_12m": [str]}. Interview me about my work first.`;

// the server answers errors as `400 {"error": "..."}`
const alErr = (e) => { const m = String(e.message || e).replace(/^\d+ /, ""); try { return JSON.parse(m).error || m; } catch (_) { return m; } };

function alScorePanel(rp, a, hist) {
  const gen = a.generated || {};
  const last = hist.length ? hist[hist.length - 1] : null;
  return `<div class="card" id="alScore" style="border-left:4px solid var(--accent)">
    <h3>Score from my repos</h3>
    <div class="muted" style="font-size:.9em">Reads your local repositories (<code>git</code>) and your GitHub account (<code>gh</code>): dependencies, folder names, recent commit subjects and the README are matched against a fixed rubric.
      Statuses, the 0-5 level and the project grades are computed in code; the <b>local</b> model only writes the sentences. Nothing leaves this machine, and each run adds a point to the history.</div>
    <details class="mt" ${(rp.repos || []).length ? "" : "open"}><summary><b>Repositories</b> <span class="muted">(${(rp.repos || []).length} connected)</span></summary>
      <div class="muted mt" style="font-size:.85em">One absolute path per line, git repositories only (max 20). The same list feeds the Committing tab. Optional author filter for commit subjects, e.g. your name.</div>
      <textarea id="alRepos" rows="4" class="mt" style="width:100%" placeholder="/Users/you/code/my-project">${esc((rp.repos || []).join("\n"))}</textarea>
      <div class="row mt" style="gap:8px"><input id="alAuthor" maxlength="100" value="${esc(rp.author || "")}" placeholder="git author filter (optional)" style="width:260px"><button id="alSaveRepos">Save repositories</button><span class="muted" id="alRepoMsg" style="font-size:.9em"></span></div>
    </details>
    <div class="row mt" style="gap:10px;align-items:center"><button class="primary" id="alScoreBtn">Score from my repos</button>
      <span class="muted" id="alScoreMsg" style="font-size:.9em">${gen.by === "repos" ? `Last run ${esc(a.as_of)}, text by ${esc(gen.narration)}.` : last ? `Last run ${esc(last.date)}.` : "Takes up to a couple of minutes when the local model writes the text."}</span></div>
  </div>`;
}

function alBindScore(rerender) {
  const msg = (id, t) => { const n = document.getElementById(id); if (n) n.textContent = t; };
  document.getElementById("alSaveRepos").addEventListener("click", async () => {
    try {
      const repos = document.getElementById("alRepos").value.split("\n").map((x) => x.trim()).filter(Boolean);
      const r = await api.put("/api/ai-learning/repos", { repos, author: document.getElementById("alAuthor").value });
      if (r.ok === false) return;
      document.getElementById("alRepos").value = (r.repos || []).join("\n");
      msg("alRepoMsg", `Saved ${(r.repos || []).length}.` + (r.rejected && r.rejected.length ? " Skipped: " + r.rejected.map((j) => `${j.path} (${j.reason})`).join("; ") : ""));
    } catch (e) { msg("alRepoMsg", alErr(e)); }
  });
  const btn = document.getElementById("alScoreBtn");
  btn.addEventListener("click", async () => {
    btn.disabled = true; msg("alScoreMsg", "Scoring… reading repositories, then the local model writes the text.");
    try {
      const r = await api.post("/api/ai-learning/score");
      if (r.ok === false) { msg("alScoreMsg", r.error || "Not saved."); return; }
      await rerender();
    } catch (e) { msg("alScoreMsg", alErr(e)); }
    finally { btn.disabled = false; }
  });
}

async function renderAiLearn(el) {
  const [d, rp] = await Promise.all([api.get("/api/ai-learning"), api.get("/api/ai-learning/repos").catch(() => ({ repos: [], author: "" }))]);
  const a = d.content || {}; const st = d.state || {};
  const hist = Array.isArray(d.history) ? d.history : [];
  st.skills = st.skills || {}; st.certs = st.certs || {}; st.log = st.log || [];
  const rerender = () => renderAiLearn(el);
  if (!Array.isArray(a.scale)) {
    el.innerHTML = `<div class="muted" style="margin-bottom:4px"><a href="#offers" style="text-decoration:none">← Career</a></div>
      <h2>🧠 AI learning</h2>
      <div class="muted" style="margin-bottom:10px">No assessment yet. Connect your repositories and score them, or paste one written by any AI assistant with the box below.</div>
      ${alScorePanel(rp, a, hist)}
      <div class="card mt"><h3>Or paste an assessment</h3>${aiJsonBox("analysis_ai_learning", AL_PROMPT)}</div>`;
    alBindScore(rerender);
    return;
  }
  a.projects = a.projects || []; a.skills = a.skills || []; a.certs = a.certs || [];
  a.sources = a.sources || {}; a.routine = a.routine || []; a.plan_12m = a.plan_12m || [];
  ["daily", "weekly", "quarterly", "services"].forEach((k) => { a.sources[k] = a.sources[k] || []; });
  const save = () => api.put("/api/ai-learning/state", st);
  const skillStatus = (s) => st.skills[s.id] || s.status;
  const stCls = { have: "pos", partial: "warn", missing: "neg" };
  const SKILL_LABEL = { have: "have", partial: "partial", missing: "missing" };
  const prRank = (p) => /skip/.test(p) ? 3 : /high/.test(p) ? 0 : /medium/.test(p) ? 1 : 2;
  const certsSorted = [...a.certs].sort((x, y) => prRank(x.priority) - prRank(y.priority));
  const FMT = ["all", "online", "in person", "hybrid"];
  const certFilter = (c) => {
    const f = window._alFmt || "all"; const fm = String(c.format || "online").toLowerCase();
    if (f === "all") return true;
    if (f === "online") return fm.startsWith("online");
    if (f === "hybrid") return fm.includes("hybrid");
    return !fm.startsWith("online") && !fm.includes("hybrid");
  };
  const areas = [...new Set(a.skills.map((s) => s.area))];

  // fragments are repainted IN PLACE (no route()), so the page does not jump to the top
  const kpisHtml = () => {
    const counts = { have: 0, partial: 0, missing: 0 };
    a.skills.forEach((s) => { counts[skillStatus(s)] = (counts[skillStatus(s)] || 0) + 1; });
    const certDone = a.certs.filter((c) => st.certs[c.id] === "done").length;
    const certPlan = a.certs.filter((c) => st.certs[c.id] === "planned" || st.certs[c.id] === "in progress").length;
    return `
      <div class="card kpi"><div class="label">Level today</div><div class="value">${esc(a.score)} <span class="muted" style="font-size:.5em">/ ${esc(a.target)}</span></div><div class="sub">${esc(a.score_label)}</div></div>
      <div class="card kpi"><div class="label">Skills</div><div class="value"><span class="pos">${counts.have}</span> · <span class="warn">${counts.partial}</span> · <span class="neg">${counts.missing}</span></div><div class="sub">have · partial · missing (of ${a.skills.length})</div></div>
      <div class="card kpi"><div class="label">Courses &amp; certificates</div><div class="value">${certDone} <span class="muted" style="font-size:.6em">done</span></div><div class="sub">${certPlan} planned or in progress, of ${a.certs.length} suggested</div></div>
      <div class="card kpi"><div class="label">Progress log</div><div class="value">${st.log.length}</div><div class="sub">entries · latest ${st.log.length ? esc(st.log[st.log.length - 1].date) : "—"}</div></div>`;
  };
  const certsHtml = () => {
    const list = certsSorted.filter(certFilter);
    return `
      <div class="row" style="gap:6px;margin-bottom:10px;flex-wrap:wrap">${FMT.map((f) => `<button data-fmt="${f}" class="${(window._alFmt || "all") === f ? "primary" : ""}" style="font-size:.9em">${f}</button>`).join("")}
        <span class="muted" style="font-size:.9em">${list.length} of ${a.certs.length}</span></div>
      ${a.format_note ? `<div class="muted" style="font-size:.9em;margin-bottom:12px;padding:10px 12px;border-radius:8px;background:var(--inset)">ℹ️ ${esc(a.format_note)}</div>` : ""}
      <div style="display:grid;gap:10px">${list.map((c) => `<div style="display:grid;grid-template-columns:170px minmax(0,1fr);gap:14px;padding:12px 14px;border-radius:10px;background:var(--panel2);border:1px solid var(--hairline)">
        <div style="display:flex;flex-direction:column;gap:8px">
          <select data-cert="${esc(c.id)}" style="font-size:.9em">${["—", "planned", "in progress", "done"].map((o) => `<option ${(st.certs[c.id] || "—") === o ? "selected" : ""}>${o}</option>`).join("")}</select>
          <span class="badge ${/high/.test(c.priority) ? "pos" : /skip/.test(c.priority) ? "neg" : ""}" style="white-space:normal;text-align:center">${esc(c.priority)}</span>
          <span class="badge" style="white-space:normal;text-align:center">${esc(c.format || "online")}</span>
        </div>
        <div style="min-width:0">
          <div><a href="${esc(safeUrl(c.link))}" target="_blank" rel="noopener noreferrer" style="text-decoration:none"><b>${esc(c.name)}</b> ↗</a></div>
          <div class="muted" style="font-size:.92em;margin-top:3px">${esc(c.provider)} · <b style="color:var(--text)">${esc(c.cost)}</b> · ${esc(c.time)}</div>
          <div style="font-size:.95em;margin-top:6px">${esc(c.why)}</div>
        </div>
      </div>`).join("")}</div>`;
  };
  const logHtml = () => `
      <div class="row"><input id="alDate" type="date" value="${new Date().toISOString().slice(0, 10)}" style="width:160px"><input id="alText" maxlength="500" placeholder="e.g. hybrid BM25 + embeddings: recall@5 0.61 → 0.74 on my gold set; adopting" style="flex:1;min-width:260px"><button class="primary" id="alAdd">Add entry</button></div>
      ${st.log.length ? `<table class="mt"><tbody>${[...st.log].reverse().slice(0, 30).map((e, i) => `<tr><td class="muted" style="width:120px">${esc(e.date)}</td><td>${esc(e.text)}</td><td style="width:40px"><button class="danger" data-aldel="${st.log.length - 1 - i}">✕</button></td></tr>`).join("")}</tbody></table>` : '<div class="empty">Your first entry goes here after your first experiment.</div>'}
      <div class="muted mt" style="font-size:.88em">To re-rate your level: change the statuses above, and at the quarterly review press <b>Score from my repos</b> again.</div>`;

  el.innerHTML = `
    <div class="muted" style="margin-bottom:4px"><a href="#offers" style="text-decoration:none">← Career</a></div>
    <h2>🧠 AI learning: from user to architect</h2>
    ${alScorePanel(rp, a, hist)}
    <div class="grid cols-4 mt" id="alKpis">${kpisHtml()}</div>
    <div class="card mt" style="border-left:4px solid var(--violet)">
      <h3>Scale and verdict <span class="muted" style="font-weight:normal;font-size:.8em">(as of ${esc(a.as_of)})</span></h3>
      <div class="row" style="gap:6px;flex-wrap:wrap;margin-bottom:10px">${a.scale.map((l) => `<span class="badge ${l.lvl <= Math.floor(a.score) ? "pos" : ""}" title="${esc(l.desc)}" style="${Math.floor(a.score) === l.lvl ? "border-color:var(--accent);color:var(--accent)" : ""}">${esc(l.lvl)} · ${esc(l.name)}</span>`).join("")}</div>
      <div>${esc(a.verdict)}</div>
    </div>
    ${hist.length ? `<div class="card mt">
      <h3>Score history <span class="muted" style="font-weight:normal;font-size:.8em">(one point per run)</span></h3>
      <table><thead><tr><th>Date</th><th style="width:40%">Level</th><th>have · partial · missing</th><th>Repos</th><th>Text by</th></tr></thead>
        <tbody>${[...hist].reverse().slice(0, 12).map((h) => `<tr><td class="muted">${esc(h.date)}</td>
          <td><div style="display:flex;align-items:center;gap:8px"><div style="height:6px;border-radius:3px;background:var(--accent);width:${Math.max(2, Math.min(100, Number(h.score) * 20))}%"></div><b>${Number(h.score).toFixed(1)}</b></div></td>
          <td>${Number(h.have)} · ${Number(h.partial)} · ${Number(h.missing)}</td><td>${Number(h.repos)}</td><td class="muted">${esc(h.narration)}</td></tr>`).join("")}</tbody></table>
    </div>` : ""}
    ${a.projects.length ? `<div class="card mt">
      <h3>Your projects, graded</h3>
      <div style="display:grid;gap:10px">${a.projects.map((r) => `<div style="display:grid;grid-template-columns:minmax(160px,240px) 70px minmax(0,1fr) minmax(0,1fr);gap:14px;padding:10px 12px;border-radius:10px;background:var(--panel2)">
        <div><b>${esc(r.name)}</b></div><div><b>${esc(r.grade)}</b></div>
        <div class="muted" style="font-size:.9em">${esc(r.what)}</div><div style="font-size:.9em">${esc(r.gap)}</div></div>`).join("")}</div>
    </div>` : ""}
    <div class="card mt">
      <h3>Skill map <span class="muted" style="font-weight:normal;font-size:.8em">(pick a status, it saves right away)</span></h3>
      ${areas.map((ar) => `<h4 class="mt">${esc(ar)}</h4>
      <div style="display:grid;gap:8px">${a.skills.filter((s) => s.area === ar).map((s) => `<div style="display:grid;grid-template-columns:130px minmax(180px,1fr) minmax(0,2fr);gap:12px;align-items:start;padding:8px 10px;border-radius:8px;background:var(--panel2)">
          <select data-skill="${esc(s.id)}" class="${stCls[skillStatus(s)] || ""}" style="font-size:.9em">${Object.keys(SKILL_LABEL).map((o) => `<option ${skillStatus(s) === o ? "selected" : ""}>${o}</option>`).join("")}</select>
          <b>${esc(s.name)}</b>
          <div style="font-size:.92em">${esc(s.how)}${s.link ? ` <a href="${esc(safeUrl(s.link))}" target="_blank" rel="noopener noreferrer">↗</a>` : ""}
            ${Array.isArray(s.evidence) && s.evidence.length ? `<div class="muted" style="font-size:.85em;margin-top:4px">Evidence: ${s.evidence.map((ev) => esc(ev)).join(" · ")}</div>` : ""}</div></div>`).join("")}</div>`).join("")}
    </div>
    <div class="card mt" style="border-left:4px solid var(--warn)">
      <h3>Courses and certificates <span class="muted" style="font-weight:normal;font-size:.8em">(by priority)</span></h3>
      <div id="alCerts">${certsHtml()}</div>
    </div>
    <div class="grid cols-2 mt">
      <div class="card">
        <h3>How to know what's new: three layers</h3>
        <div class="muted" style="font-size:.92em;margin-bottom:8px">${esc(a.sources.method || "")}</div>
        ${[["Daily (5 min)", a.sources.daily], ["Weekly (45 min)", a.sources.weekly], ["Quarterly (2 h)", a.sources.quarterly]].map(([t, list]) => `<h4 class="mt">${t}</h4>
          <ul style="padding-left:18px;margin:0">${list.map((x) => `<li style="font-size:.92em"><a href="${esc(safeUrl(x.link))}" target="_blank" rel="noopener noreferrer"><b>${esc(x.name)}</b></a>: ${esc(x.what)}</li>`).join("")}</ul>`).join("")}
      </div>
      <div class="card">
        <h3>Services that do the watching for you</h3>
        <ul style="padding-left:18px;margin:0">${a.sources.services.map((x) => `<li class="mt" style="font-size:.92em"><a href="${esc(safeUrl(x.link))}" target="_blank" rel="noopener noreferrer"><b>${esc(x.name)}</b></a>: ${esc(x.what)}</li>`).join("")}</ul>
        <h4 class="mt">A rhythm that produces progress</h4>
        <ul style="padding-left:18px;margin:0">${a.routine.map((x) => `<li class="mt" style="font-size:.92em">${esc(x)}</li>`).join("")}</ul>
        <h4 class="mt">12-month plan</h4>
        <ol style="padding-left:18px;margin:0">${a.plan_12m.map((x) => `<li class="mt" style="font-size:.92em">${esc(x)}</li>`).join("")}</ol>
      </div>
    </div>
    <div class="card mt" style="border-left:4px solid var(--pos)">
      <h3>Progress log: what I tried, what I'm adopting</h3>
      <div id="alLog">${logHtml()}</div>
    </div>`;

  const paint = (id, html, bind) => { const box = document.getElementById(id); box.innerHTML = html; bind && bind(); };
  const bindCerts = () => {
    document.querySelectorAll("#alCerts [data-fmt]").forEach((b) => b.addEventListener("click", () => { window._alFmt = b.dataset.fmt; paint("alCerts", certsHtml(), bindCerts); }));
    document.querySelectorAll("#alCerts [data-cert]").forEach((sel) => sel.addEventListener("change", async () => {
      if (sel.value === "—") delete st.certs[sel.dataset.cert]; else st.certs[sel.dataset.cert] = sel.value;
      await save(); paint("alKpis", kpisHtml());
    }));
  };
  const bindLog = () => {
    document.getElementById("alAdd").addEventListener("click", async () => {
      const text = document.getElementById("alText").value.trim(); if (!text) return;
      st.log.push({ date: document.getElementById("alDate").value, text }); await save();
      paint("alLog", logHtml(), bindLog); paint("alKpis", kpisHtml());
    });
    document.querySelectorAll("#alLog [data-aldel]").forEach((b) => b.addEventListener("click", async () => {
      st.log.splice(+b.dataset.aldel, 1); await save(); paint("alLog", logHtml(), bindLog); paint("alKpis", kpisHtml());
    }));
  };
  bindCerts(); bindLog(); alBindScore(rerender);
  el.querySelectorAll("[data-skill]").forEach((sel) => sel.addEventListener("change", async () => {
    st.skills[sel.dataset.skill] = sel.value; await save();
    sel.className = stCls[sel.value] || ""; paint("alKpis", kpisHtml());
  }));
}
