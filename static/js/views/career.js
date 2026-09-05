async function renderCareer(el) {
  const [a, em0] = await Promise.all([api.get("/api/analysis/career").catch(() => ({})), api.get("/api/em").catch(() => null)]);
  if (!a.headline) {
    el.innerHTML = `<div class="card"><h2>Career</h2>
    <details style="margin:6px 0 12px;padding:8px 12px;background:var(--accent)14;border-radius:8px">
      <summary style="cursor:pointer;font-size:.9em"><b>👀 What this tab is (and is not)</b> — market monitoring, not job hunting <span class="muted" style="font-weight:normal">· click for details</span></summary>
      <div class="muted" style="font-size:.87em;margin-top:6px">This tab watches the <b>job market as a signal</b>, the same way the Market tab watches stock prices:
        what is the sentiment around your role, how many offers reach you <i>without applying anywhere</i>, and how demand shifts over time —
        especially as AI reshapes engineering roles. Tracking inbound offers measures your market value and the health of your niche;
        it is not a sign of looking for a new job. Think of it as a personal labor-market index.</div>
    </details>
    <div class="muted">No career analysis yet — a comp-ladder snapshot, growth paths and skill bets, authored by you or any AI assistant. Fill it with the box below.</div>
    <details class="mt"><summary style="cursor:pointer"><b>➕ Fill it now</b> (paste JSON from any AI assistant)</summary>
      <div class="muted mt" style="font-size:.85em">1) Click <b>Copy AI prompt</b> and paste it into any assistant (ChatGPT, Claude, the local model…). 2) Paste the JSON it returns below. 3) Save.</div>
      <div class="row mt" style="gap:8px">
        <button data-copyprompt>📋 Copy AI prompt</button>
        <span class="muted" data-copied style="font-size:.8em"></span>
      </div>
      <textarea data-paste rows="5" class="mt" style="width:100%" placeholder='{"headline": "...", ...}'></textarea>
      <button class="primary mt" data-savejson>Save</button>
    </details></div>`;
    const PROMPT = `Prepare a long-term career analysis for me and return ONLY valid JSON: {"headline": str, "as_of": "YYYY-MM-DD", "target_role": str, "comp_levels": [{"role": str, "comp": str, "you": bool}], "money_paths": [{"tag": "A|B|C", "title": str, "verdict": str, "text": str}], "head_of_eng": str, "ai_impact": [str], "skills": [{"skill": str, "why": str}], "skills_note": str}. Interview me about my situation first.`;
    el.querySelector("[data-copyprompt]").addEventListener("click", async (e) => {
      await navigator.clipboard.writeText(PROMPT);
      el.querySelector("[data-copied]").textContent = "copied ✓";
    });
    el.querySelector("[data-savejson]").addEventListener("click", async () => {
      const raw = el.querySelector("[data-paste]").value.trim();
      try { JSON.parse(raw); } catch (err) { alert("That is not valid JSON: " + err.message); return; }
      await api.put("/api/settings", { analysis_career: raw });
      route();
    });
    return;
  }
  el.innerHTML = `
    <div class="muted" style="margin-bottom:4px"><a href="#offers" style="text-decoration:none">← Career (offers and market)</a></div>
    <h2>🧭 Career — long-term growth analysis</h2>
    ${em0 ? `<div class="card mt" style="border-left:4px solid var(--pos)" id="emCard"></div>` : ""}
    <details style="margin:6px 0 12px;padding:8px 12px;background:var(--accent)14;border-radius:8px">
      <summary style="cursor:pointer;font-size:.9em"><b>👀 What this tab is (and is not)</b> — market monitoring, not job hunting <span class="muted" style="font-weight:normal">· click for details</span></summary>
      <div class="muted" style="font-size:.87em;margin-top:6px">This tab watches the <b>job market as a signal</b>, the same way the Market tab watches stock prices:
        what is the sentiment around your role, how many offers reach you <i>without applying anywhere</i>, and how demand shifts over time —
        especially as AI reshapes engineering roles. Tracking inbound offers measures your market value and the health of your niche;
        it is not a sign of looking for a new job. Think of it as a personal labor-market index.</div>
    </details>
    <div class="card" style="border-left:4px solid var(--pos)">
      <div style="font-size:1.05em"><b>${a.headline}</b></div>
      <div class="muted mt" style="font-size:.82em">As of ${a.as_of}.</div>
    </div>

    <div class="card mt">
      <h3>Where you sit on the comp ladder (your market)</h3>
      <div style="overflow-x:auto"><table>
        <thead><tr><th>Level / role</th><th style="text-align:right">Compensation/yr</th></tr></thead>
        <tbody>${a.comp_levels.map((c) => `<tr style="${c.you ? "background:rgba(62,207,142,0.12)" : ""}">
          <td>${c.you ? "⭐ " : ""}<b>${c.role}</b></td>
          <td style="text-align:right" class="${c.you ? "pos" : ""}"><b>${c.comp}</b></td>
        </tr>`).join("")}</tbody>
      </table></div>
    </div>

    <div class="card mt">
      <h3>Where MORE money realistically comes from — 3 paths</h3>
      <div class="grid cols-3">
        ${a.money_paths.map((p) => `<div class="card" style="margin:0;border-left:3px solid ${p.tag === "A" ? TOKENS.pos : p.tag === "B" ? TOKENS.accent : TOKENS.warn}">
          <h4 style="margin:0 0 4px">${p.tag}. ${p.title}</h4>
          <div class="pos" style="font-size:.85em;margin-bottom:6px">${p.verdict}</div>
          <div style="font-size:.9em">${p.text}</div>
        </div>`).join("")}
      </div>
    </div>

    <div class="card mt" style="border-left:4px solid var(--amber)">
      <h3 style="margin-top:0">🎯 ${a.target_role || "Your target role"} — should you aim for it?</h3>
      <div style="font-size:.95em">${a.head_of_eng}</div>
    </div>

    <div class="card mt">
      <h3>🤖 AI — taking jobs or not?</h3>
      <ul style="padding-left:18px">${a.ai_impact.map((x) => `<li class="mt" style="font-size:.92em">${x}</li>`).join("")}</ul>
    </div>

    <div class="card mt">
      <h3>📚 What to train in and why</h3>
      <div style="overflow-x:auto"><table>
        <thead><tr><th>Skill</th><th>Why</th></tr></thead>
        <tbody>${a.skills.map((s) => `<tr><td><b>${s.skill}</b></td><td class="muted" style="font-size:.9em">${s.why}</td></tr>`).join("")}</tbody>
      </table></div>
      <div class="muted mt" style="font-size:.85em">${a.skills_note}</div>
    </div>

    ${a.trainings ? `<div class="card mt" style="border-left:4px solid var(--accent)">
      <h3 style="margin-top:0">🎓 Specific trainings — for a ${a.trainings.budget} budget</h3>
      <div class="muted" style="font-size:.88em;margin-bottom:10px">${a.trainings.strategy}</div>
      <div style="overflow-x:auto"><table>
        <thead><tr><th>Program</th><th>Where</th><th style="text-align:right">Cost</th><th>Priority</th><th>Why / how to pitch it to your boss</th></tr></thead>
        <tbody>${a.trainings.items.map((t) => `<tr>
          <td><b>${t.url ? `<a href="${t.url}" target="_blank">${t.name} ↗</a>` : t.name}</b></td>
          <td class="muted" style="font-size:.88em">${t.provider}<br><span style="font-size:.92em">${t.format}</span></td>
          <td style="text-align:right;white-space:nowrap">${t.cost}</td>
          <td><span class="badge ${/wysoki/.test(t.priority) ? "pos" : ""}">${t.priority}</span></td>
          <td style="font-size:.88em">${t.why}
            ${t.boss_pitch ? `<div class="mt" style="font-size:.9em;padding:4px 8px;background:rgba(62,207,142,0.1);border-radius:5px">🗣️ <b>To your boss:</b> <i>${t.boss_pitch}</i></div>` : ""}
            <div class="muted mt" style="font-size:.92em">🔗 ${t.linkedin}</div></td>
        </tr>`).join("")}</tbody>
      </table></div>
      <div class="mt" style="font-size:.92em;padding:8px 12px;background:var(--inset);border-radius:6px">
        <b>💡 Plan for this year:</b> ${a.trainings.recommended_year}</div>

      ${a.trainings.conferences ? `<h4 class="mt">🎤 Conferences — local (Warsaw)</h4>
      <div class="muted" style="font-size:.85em;margin-bottom:6px">${a.trainings.conferences_note}</div>
      <table><tbody>${a.trainings.conferences.map((c) => `<tr>
        <td><b>${c.url ? `<a href="${c.url}" target="_blank">${c.name} ↗</a>` : c.name}</b><div class="muted" style="font-size:.82em">${c.when}</div></td>
        <td style="font-size:.88em">${c.why}</td>
      </tr>`).join("")}</tbody></table>` : ""}
    </div>` : ""}

    <div class="card mt">
      <h3>🛣️ Long-term path</h3>
      ${a.roadmap.map((r) => `<div class="mt" style="display:flex;gap:12px">
        <div style="min-width:110px"><span class="badge">${r.period}</span></div>
        <div><b>${r.title}</b><div class="muted" style="font-size:.9em">${r.text}</div></div>
      </div>`).join("")}
    </div>

    <div class="card mt" style="border-left:4px solid var(--violet)">
      <h3 style="margin-top:0">Two philosophies — choose consciously</h3>
      <div class="grid cols-2">
        <div class="card" style="margin:0"><h4 style="margin:0 0 4px">🚀 ${a.philosophies.max.title}</h4><div style="font-size:.9em">${a.philosophies.max.text}</div></div>
        <div class="card" style="margin:0"><h4 style="margin:0 0 4px">🌊 ${a.philosophies.coast.title}</h4><div style="font-size:.9em">${a.philosophies.coast.text}</div></div>
      </div>
      <div class="mt" style="font-size:.92em;padding:8px 12px;background:var(--inset);border-radius:6px"><b>${a.philosophies.note}</b></div>
    </div>

    <div class="card mt" style="border-left:4px solid var(--pos)">
      <h3 style="margin-top:0">✅ Next steps</h3>
      <ol style="padding-left:18px">${a.next_steps.map((s) => `<li class="mt" style="font-size:.92em">${s}</li>`).join("")}</ol>
    </div>

    <div class="card mt muted" style="font-size:.8em">Analysis from market research — a snapshot. To refresh: "refresh the career analysis".
      Sources: ${a.sources.map((u, i) => `<a href="${u}" target="_blank">[${i + 1}]</a>`).join(" ")}</div>`;

  // ---- Evidence & rhythm: measuring growth as a leader (in place, no page jump)
  const plan90 = (a.market_2026 && a.market_2026.plan_90d) || a.plan_90d || [];
  const paintEm = (em) => {
    const card = document.getElementById("emCard");
    if (!card || !em) return;
    const wk = em.weeks.find((w) => w.week === em.this_week) || {};
    const st = em.plan || {};
    const done = plan90.filter((_, i) => (st[i] || {}).status === "done").length;
    const kindIcon = { impact: "🎯", visibility: "📣", scope: "🧭", feedback: "💬", learning: "📚" };
    const last8 = em.weeks.slice(-8);
    card.innerHTML = `
      <h3 style="margin-top:0">📒 Evidence & rhythm — measuring growth <span class="muted" style="font-weight:normal;font-size:.75em">(the analysis says "what", this says "how much")</span></h3>
      <div class="grid cols-2">
        <div>
          <h4 style="margin:0 0 6px">Week ${em.this_week} in 4 numbers</h4>
          <div class="row" style="gap:6px;flex-wrap:wrap">
            <input data-num id="emE" placeholder="energy 1–5" value="${wk.energy ?? ""}" style="width:110px">
            <input data-num id="emH" placeholder="deep-work hours" value="${wk.deep_hours ?? ""}" style="width:140px">
            <input data-num id="emO" placeholder="1:1s" value="${wk.one_on_ones ?? ""}" style="width:70px">
            <input data-num id="emD" placeholder="decisions" value="${wk.decisions ?? ""}" style="width:90px">
            <button class="primary" id="emWeekSave">Save week</button>
          </div>
          <input id="emN" placeholder="one sentence about the week" value="${esc(wk.note || "")}" style="width:100%;margin-top:6px">
          ${last8.length ? `<table class="mt" style="font-size:.85em"><thead><tr><th>Week</th><th style="text-align:right">⚡</th><th style="text-align:right">🧠 h</th><th style="text-align:right">1:1</th><th style="text-align:right">decisions</th></tr></thead>
            <tbody>${last8.map((w) => `<tr><td>${w.week.slice(5)}</td><td style="text-align:right">${w.energy ?? "—"}</td><td style="text-align:right">${w.deep_hours ?? "—"}</td><td style="text-align:right">${w.one_on_ones ?? "—"}</td><td style="text-align:right">${w.decisions ?? "—"}</td></tr>`).join("")}</tbody></table>` : `<div class="muted mt" style="font-size:.85em">The first entry shows up here as a row; after 4 weeks a trend appears.</div>`}
        </div>
        <div>
          <h4 style="margin:0 0 6px">90-day plan <span class="muted" style="font-weight:normal">${plan90.length ? `${done}/${plan90.length} ✓` : ""}</span></h4>
          ${plan90.length ? `<div style="height:6px;background:var(--inset);border-radius:3px;margin-bottom:8px"><div style="height:6px;width:${Math.round(done / plan90.length * 100)}%;background:${TOKENS.pos};border-radius:3px"></div></div>
          ${plan90.map((p, i) => { const it = st[i] || {}; return `<div class="row" style="gap:6px;align-items:flex-start;margin-top:6px;font-size:.88em">
            <select data-plan="${i}" style="font-size:.85em">${["todo", "doing", "done"].map((x) => `<option value="${x}" ${(it.status || "todo") === x ? "selected" : ""}>${{ todo: "☐", doing: "◐", done: "☑" }[x]}</option>`).join("")}</select>
            <div style="${it.status === "done" ? "opacity:.6;text-decoration:line-through" : ""}">${p}${it.at ? ` <span class="muted" style="font-size:.85em">(${it.at})</span>` : ""}</div></div>`; }).join("")}`
          : `<div class="muted" style="font-size:.85em">The 90-day plan comes from the career analysis JSON (key <code>plan_90d</code>: a list of steps). Add it there and the checklist appears here.</div>`}
        </div>
      </div>
      <h4 class="mt">Evidence log <span class="muted" style="font-weight:normal">(${em.log.length}: ${em.kinds.map((k) => `${kindIcon[k]} ${em.counts[k] || 0}`).join(" · ")})</span></h4>
      <div class="row" style="gap:6px;flex-wrap:wrap">
        <input type="date" id="emDate" value="${new Date().toISOString().slice(0, 10)}" style="width:150px">
        <select id="emKind">${em.kinds.map((k) => `<option value="${k}">${kindIcon[k]} ${k}</option>`).join("")}</select>
        <input id="emText" placeholder="what happened (with a number, if there is one)" style="flex:1;min-width:260px">
        <input id="emMetric" placeholder="metric" style="width:120px">
        <input data-num id="emValue" placeholder="value" style="width:90px">
        <input id="emLink" placeholder="link / proof" style="width:160px">
        <button class="primary" id="emAdd">Add</button>
      </div>
      ${em.log.length ? `<table class="mt" style="font-size:.88em"><tbody>${em.log.slice(0, 30).map((r) => `<tr>
        <td style="white-space:nowrap" class="muted">${r.date}</td><td>${kindIcon[r.kind] || ""} <span class="badge">${r.kind}</span></td>
        <td>${esc(r.text)}${r.metric ? ` <span class="muted">· ${esc(r.metric)}${r.value != null ? ` = <b>${fmt.num(r.value, 0)}</b>` : ""}</span>` : ""}${r.link ? ` <a href="${esc(r.link)}" target="_blank">↗</a>` : ""}</td>
        <td><button class="danger" data-emdel="${r.id}" title="delete">✕</button></td></tr>`).join("")}</tbody></table>` : `<div class="muted mt" style="font-size:.85em">Empty. One entry a week is enough: a decision with its result, a talk, a merged PR, feedback from a VP.</div>`}`;
    const refresh = async () => paintEm(await api.get("/api/em").catch(() => null));
    document.getElementById("emWeekSave").addEventListener("click", async () => {
      await api.put("/api/em/week", { energy: parseNum(document.getElementById("emE")), deep_hours: parseNum(document.getElementById("emH")),
        one_on_ones: parseNum(document.getElementById("emO")), decisions: parseNum(document.getElementById("emD")), note: document.getElementById("emN").value });
      refresh();
    });
    document.getElementById("emAdd").addEventListener("click", async () => {
      const text = document.getElementById("emText").value.trim();
      if (!text) { alert("Write what happened"); return; }
      await api.post("/api/em/log", { date: document.getElementById("emDate").value, kind: document.getElementById("emKind").value, text,
        metric: document.getElementById("emMetric").value, value: parseNum(document.getElementById("emValue")), link: document.getElementById("emLink").value });
      refresh();
    });
    card.querySelectorAll("[data-emdel]").forEach((b) => b.addEventListener("click", async () => { await api.del("/api/em/log/" + b.dataset.emdel); refresh(); }));
    card.querySelectorAll("[data-plan]").forEach((sel) => sel.addEventListener("change", async () => { await api.put("/api/em/plan", { idx: +sel.dataset.plan, status: sel.value }); refresh(); }));
  };
  paintEm(em0);
}
