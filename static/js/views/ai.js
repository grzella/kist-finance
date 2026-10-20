// Control Center → AI improvement tab: AI mode and questions, memory (RAG), ratings, lessons
// and the step list from ai_improve.py. Split out of control.js so the AI has one home.
// 👍/👎 on a logged AI answer; clicking the active one again clears it
function rateBtns(id, rating) {
  if (!id) return "";
  const b = (v, ic) => `<button class="aiRate" data-id="${id}" data-v="${v}" style="font-size:.78em;margin-top:4px;${rating === v ? "outline:2px solid var(--accent)" : "opacity:.7"}">${ic}</button>`;
  return b(1, "👍") + " " + b(-1, "👎");
}

function bindRate(root) {
  root.querySelectorAll(".aiRate").forEach((btn) => btn.addEventListener("click", async () => {
    const v = Number(btn.dataset.v);
    const wasOn = btn.style.outline !== "";
    await api.post(`/api/llm/log/${btn.dataset.id}/rating`, { rating: wasOn ? 0 : v });
    root.querySelectorAll(`.aiRate[data-id="${btn.dataset.id}"]`).forEach((o) => {
      const on = !wasOn && Number(o.dataset.v) === v;
      o.style.outline = on ? "2px solid var(--accent)" : ""; o.style.opacity = on ? "1" : ".7";
    });
  }));
}

// one tinted badge for every state/status chip on this tab
const tint = (text, color) => `<span class="badge" style="background:${color}22;color:${color}">${text}</span>`;
const STATE = { error: ["🔴 broken", "var(--neg)"], todo: ["🟡 to do", "var(--warn)"], auto: ["🟢 runs itself", "var(--pos)"], ok: ["🟢 OK", "var(--pos)"] };

function roadmapHtml(roadmap) {
  const PH = { done: "✅ Done", "1": "Phase 1: measurement foundation", "2": "Phase 2: retrieval and context", "3": "Phase 3: engine (model, llama.cpp)", "4": "Phase 4: decisions and confidence", "P": "Price forecasts", "⏸": "Conditional (with a threshold to revisit)", "X": "Rejected after research (so we don't come back)" };
  const ST = { done: ["✅ done", "var(--pos)"], idea: ["🟠 idea", "var(--warn)"], conditional: ["⏸ conditional", "var(--muted)"], rejected: ["❌ rejected", "var(--neg)"] };
  const groups = Object.keys(PH).map((k) => [k, roadmap.filter((r) => r.phase === k)]).filter(([, rs]) => rs.length);
  return `<details class="mt" style="font-size:.85em"><summary>🗺️ Improvement roadmap: ${roadmap.filter((r) => r.status === "idea").length} ideas, ${roadmap.filter((r) => r.status === "done").length} done, ${roadmap.filter((r) => r.status === "rejected").length} rejected</summary>
    <div class="muted mt" style="font-size:.9em;max-width:90ch">Directions from a research pass (2026-10-06: inference stack, RAG and memory, evals and decisions, forecasts, a separate red team), not tasks for today. Phase order matters: without a larger gold set (R1) no later change can be measured. Each item carries its reason with evidence and the criterion that tells you it worked.</div>
    ${groups.map(([k, rs]) => `<div class="mt" style="font-weight:600">${PH[k]}</div>
    <table style="font-size:.95em"><tbody>${rs.map((r) => `<tr>
      <td style="white-space:nowrap;vertical-align:top;width:110px">${tint(...ST[r.status])}<div class="muted" style="font-size:.8em;margin-top:2px">${esc(r.id)}${r.hours ? ` · ~${r.hours} h` : ""}${r.where ? ` · ${esc(r.where)}` : ""}</div></td>
      <td style="vertical-align:top"><b>${esc(r.title)}</b><div class="muted" style="font-size:.9em;line-height:1.45">${esc(r.why)}${r.criterion ? `<br>Criterion: ${esc(r.criterion)}` : ""}</div></td></tr>`).join("")}</tbody></table>`).join("")}
  </details>`;
}

async function renderAi(el) {
  const [ai, aiLog, exp, imp] = await Promise.all([
    api.get("/api/llm/config").catch(() => null),
    api.get("/api/llm/log").catch(() => null),
    api.get("/api/experiences").catch(() => null),
    api.get("/api/ai/improve").catch(() => null),
  ]);
  el.innerHTML = `
    <h2>🛠️ Control Center</h2>
    ${ctrlTabs("ai")}
    <div class="muted" style="margin-bottom:12px">One place for the AI: mode and questions, memory, answer ratings and the list of things that make the next answers better.</div>

    ${ai ? `<div class="card mt" style="border-left:4px solid ${ai.ai_mode === "both" ? "#b78cff" : TOKENS.pos}">
      <h3>🤖 AI mode
        <span class="badge" style="background:${ai.ai_mode === "both" ? "#b78cff22;color:#b78cff" : "var(--pos)22;color:var(--pos)"}">${ai.ai_mode === "both" ? "local + cloud" : "local only"}</span></h3>
      <div class="muted" style="font-size:.85em;margin-bottom:8px">This mode governs <b>every AI feature in the app</b>:
        the "AI second opinion" on Recommendations, forecast narration and questions typed below. The default is local only —
        nothing leaves your machine. "Local + cloud" asks BOTH engines and synthesizes one verdict (usually the best result),
        but <b class="neg">the cloud sends your question + snippets of your data to Anthropic</b>, so enable it deliberately.</div>
      <div class="row" style="gap:16px;flex-wrap:wrap">
        <label style="cursor:pointer"><input type="radio" name="aiMode" value="local" ${ai.ai_mode !== "both" ? "checked" : ""}>
          🔒 Local only <span class="muted" style="font-size:.85em">(${ai.local.online ? "🟢 " + ai.local.model : "🔴 offline — " + (ai.local.hint || "")})</span></label>
        <label style="cursor:pointer"><input type="radio" name="aiMode" value="both" ${ai.ai_mode === "both" ? "checked" : ""} ${ai.cloud.online ? "" : "disabled"}>
          🔒+☁️ Local + Claude <span class="muted" style="font-size:.85em">(${ai.cloud.online ? "🟢 " + ai.cloud.model : "🔴 no key — " + (ai.cloud.hint || "")})</span></label>
      </div>
      <div class="row mt" style="gap:8px">
        <input id="aiPrompt" placeholder="ask a question… (e.g. overpay the mortgage or invest?)" style="flex:1">
        <button class="primary" id="aiAsk">Ask</button>
      </div>
      <div id="aiOut" class="mt"></div>
    </div>` : ""}

    ${imp ? `<div class="card mt" style="border-left:4px solid ${imp.errors ? TOKENS.neg : imp.todo ? TOKENS.warn : TOKENS.pos}">
      <h3 style="margin-top:0">🎓 AI improvement
        <span class="badge" style="background:${imp.errors ? "var(--neg)22;color:var(--neg)" : imp.todo ? "var(--warn)22;color:var(--warn)" : "var(--pos)22;color:var(--pos)"}">${imp.errors ? imp.errors + " broken" + (imp.todo ? " · " + imp.todo + " to do" : "") : imp.todo ? imp.todo + " to do" : "all OK"}</span></h3>
      <details style="font-size:.85em"><summary class="muted">How it works: the model stays the same, what it gets changes</summary>
        <ol class="muted mt" style="padding-left:20px;line-height:1.55;max-width:80ch">
          <li><b>Data.</b> Fresh numbers land in the memory (RAG) and the AI gets them as context for the question.</li>
          <li><b>Ratings.</b> Two buttons sit under every answer. 👍 means the answer was right and used your numbers. 👎 means it was wrong, made something up or dodged the question. A rating does not change the answer; it is counted against the lessons that were in that answer's context, so after a few 👎 you can see which lesson hurts.
            <br>💡 “Learn from this” is a different thing from 👍: the model boils a good answer down to one general rule (without your numbers), stores it as a lesson and adds it to the context of similar questions later. Use it rarely, only when the answer contains a method worth reusing.</li>
          <li><b>Measurement.</b> A quality eval, fixed questions with your own facts, before and after a model, prompt or RAG change. Without it “seems better” is a guess.</li>
        </ol>
        <div class="muted">Price forecasts calibrate themselves, daily. Nothing to do there.</div></details>
      <table class="mt" style="font-size:.88em"><tbody>${imp.steps.map((st) => `<tr>
        <td style="width:120px;white-space:nowrap">${tint(...STATE[st.state])}</td>
        <td><b>${esc(st.title)}</b><div class="muted" style="font-size:.9em">${esc(st.detail)}</div>
          ${st.action && st.action.kind === "cmd" ? `<code style="display:block;white-space:pre-wrap;word-break:break-all;font-size:.8em;margin-top:4px">${esc(st.action.cmd)}</code>` : ""}</td>
        <td style="white-space:nowrap;text-align:right">${!st.action ? "" :
          st.action.kind === "reindex" ? `<button class="impReindex" style="${st.state === "auto" ? "opacity:.75" : ""}">${st.state === "auto" ? "optional: " : ""}${esc(st.action.label)}</button>` :
          st.action.kind === "scroll" ? `<button class="impScroll" data-target="${st.action.target}">${esc(st.action.label)}</button>` :
          st.action.kind === "link" ? `<a href="${st.action.href}">${esc(st.action.label)} →</a>` :
          st.action.kind === "cmd" ? `<button class="impCopy" data-cmd="${encodeURIComponent(st.action.cmd)}">Copy</button>` :
          `<span class="muted" style="font-size:.85em;white-space:normal;display:inline-block;max-width:260px">${esc(st.action.label)}</span>`}</td></tr>`).join("")}</tbody></table>
      ${imp.roadmap ? roadmapHtml(imp.roadmap) : ""}
      ${imp.progress && imp.progress.eval && imp.progress.eval.length ? `<div class="muted mt" style="font-size:.85em">📈 Quality eval over time:
        ${imp.progress.eval.map((e) => `<b>${e.passed}/${e.total}</b> <span style="font-size:.85em">(${esc(e.ts.slice(0, 10))})</span>`).join(" → ")}</div>` : ""}
      <div class="muted" style="font-size:.82em;margin-top:6px">Colours as in a RAG status report (Red / Amber / Green): 🔴 broken, fix first · 🟡 to do, waits for you · 🟢 OK or runs by itself (the button only if you want it now). Rows sorted by urgency. Ask questions in the “AI mode” card above.</div>
      ${aiLog && aiLog.stats.total ? `<details class="mt" id="aiLogBox" style="font-size:.85em">
        <summary>📊 AI prompt log (${aiLog.stats.total}) — ${aiLog.stats.rag_grounded} RAG-grounded · ${aiLog.stats.cloud_calls} cloud calls</summary>
        <div class="mt">${aiLog.recent.map((e) => { const ans = e.synthesis_text || e.cloud_text || e.local_text; return `<div style="border-top:1px solid #2a2f45;padding:6px 0">
          <div class="muted" style="font-size:.8em">${e.ts} · ${e.mode}${e.rag_used ? " · RAG" : ""}${e.rating == null ? ` · ${tint("unrated", "var(--warn)")}` : ""}</div>
          <div><b>${esc(e.prompt)}</b></div>
          <div style="white-space:pre-wrap;color:#c9cee0">${esc(ans)}</div>
          ${ans ? `${rateBtns(e.id, e.rating)} <button class="expLearn" style="font-size:.78em;margin-top:4px" data-id="${e.id}" data-q="${encodeURIComponent(e.prompt || "")}" data-a="${encodeURIComponent(ans)}">💡 Learn from this</button> <span class="expMsg muted" style="font-size:.78em"></span>` : ""}</div>`; }).join("")}</div>
      </details>` : ""}

      <details class="mt" id="expBox" style="font-size:.85em" ${exp && exp.experiences.length ? "open" : ""}>
        <summary>🧠 Learned experiences (${(exp && exp.experiences.length) || 0})</summary>
        <div class="muted mt" style="font-size:.82em">Lessons distilled from answers you marked as good. They're indexed into the AI's memory (RAG) and injected as guidance on similar questions — so the assistant improves without retraining. Prune any that don't hold up: "used" counts the answers a lesson was in, 👍/👎 are your ratings of those answers.</div>
        <div class="mt">${(exp && exp.experiences.length) ? exp.experiences.map((x) => `<div style="border-top:1px solid #2a2f45;padding:6px 0;display:flex;gap:8px;align-items:flex-start">
          <div style="flex:1"><div style="white-space:pre-wrap;color:#c9cee0;line-height:1.5;max-width:80ch">${esc(x.lesson)}</div>
            <div class="muted" style="font-size:.75em">${x.created_at}${x.question ? " · from: " + esc(x.question) : ""}
              · used ${x.used || 0}× · 👍 ${x.up || 0} · 👎 ${x.down || 0}${x.bad ? ' · <span class="neg">rated worse than it helps — consider removing</span>' : ""}</div></div>
          <button class="expDel danger" style="font-size:.75em" data-id="${x.id}">✕</button></div>`).join("")
          : `<div class="muted" style="font-size:.82em">Nothing yet — ask the AI something, then click <b>💡 Learn from this</b> on a good answer above.</div>`}</div>
      </details>
    </div>` : ""}
`;

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
          <div style="white-space:pre-wrap;font-size:.9em">${res.ok ? esc(res.text) : '<span class="neg">offline / no answer</span>'}</div></div>` : "";
        const syn = r.synthesis && r.synthesis.ok ? `<div class="card" style="border-left:4px solid var(--warn);margin:0 0 10px">
          <div style="font-weight:600;font-size:.85em">🧭 Verdict — synthesis of both models <span class="muted">(${r.synthesis.by === "cloud" ? "Claude" : "local"})</span></div>
          <div style="white-space:pre-wrap;font-size:.9em">${esc(r.synthesis.text)}</div></div>` : "";
        out.innerHTML = syn + `<div class="grid ${r.cloud ? "cols-2" : ""}">
          ${card("🔒 " + (r.local.label || "local"), r.local, TOKENS.pos)}
          ${r.cloud ? card("☁️ " + (r.cloud.label || "Claude"), r.cloud, "#b78cff") : ""}</div>
          ${r.log_id && r.best ? `<div class="mt" style="font-size:.85em">Was this answer good? ${rateBtns(r.log_id, null)}</div>` : ""}`;
        bindRate(out);
      } catch (e) { out.innerHTML = `<div class="neg">Error: ${e.message}</div>`; }
      finally { aiAsk.disabled = false; }
    });
  }
  bindRate(document);
  const reindexNow = async (b) => {
    b.disabled = true; b.textContent = "Indexing… (embedding new chunks, carrying the rest over)";
    try {
      const r = await api.post("/api/rag/reindex", {});
      b.textContent = `✅ ${r.chunks} chunks, ${r.embedded} embedded, ${r.reused} unchanged, ${r.seconds} s`;
      setTimeout(route, 2500);
    } catch (e) { b.textContent = "❌ " + e.message; b.disabled = false; }
  };
  document.querySelectorAll(".impReindex").forEach((b) => b.addEventListener("click", () => reindexNow(b)));
  document.querySelectorAll(".impCopy").forEach((b) => b.addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(decodeURIComponent(b.dataset.cmd)); b.textContent = "✅ Copied"; }
    catch (e) { b.textContent = "select by hand"; }
  }));
  document.querySelectorAll(".impScroll").forEach((b) => b.addEventListener("click", () => {
    const t = document.getElementById(b.dataset.target);
    if (t) { t.open = true; t.scrollIntoView({ behavior: "smooth", block: "start" }); }
  }));
  // experience distillation: "learn from this" on a good answer, and pruning
  document.querySelectorAll(".expLearn").forEach((b) => b.addEventListener("click", async () => {
    const msg = b.nextElementSibling;
    b.disabled = true; if (msg) msg.textContent = "distilling…";
    try {
      const r = await api.post("/api/experience", {
        question: decodeURIComponent(b.dataset.q), answer: decodeURIComponent(b.dataset.a), log_id: b.dataset.id });
      if (r.ok) { if (msg) msg.textContent = "✅ learned"; setTimeout(route, 700); }
      else { if (msg) msg.textContent = "no transferable lesson"; b.disabled = false; }
    } catch (e) {
      // show the reason instead of a bare "error" — a 404 usually means a stale
      // server (endpoint added after ./run.sh started → restart the app)
      if (msg) msg.textContent = /404/.test(e.message) ? "error: restart the app (new endpoint)" : "error: " + e.message;
      b.disabled = false;
    }
  }));
  document.querySelectorAll(".expDel").forEach((b) => b.addEventListener("click", async () => {
    await api.del("/api/experiences/" + b.dataset.id); route();
  }));
}
