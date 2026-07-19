async function renderRecs(el) {
  const [rec, xtb, acts, aiOp] = await Promise.all([
    api.get("/api/recommendation"),
    api.get("/api/recommendation/xtb"),
    api.get("/api/actions"),
    api.get("/api/recommendation/ai").catch(() => ({}))]);

  const STATUS_LABELS = { backlog: "backlog", "w trakcie": "in progress", zrobione: "done", odrzucone: "rejected" };
  const engineItems = [...rec.items, ...(xtb.items || []).map((i) => ({ ...i, area: "Portfolio: " + i.area }))];

  const byStatus = { "w trakcie": [], backlog: [], zrobione: [], odrzucone: [] };
  acts.actions.forEach((a) => (byStatus[a.status] || byStatus.backlog).push(a));

  const actionCard = (a) => `
    <div class="acard" data-act="${a.id}">
      <div class="row" style="justify-content:space-between;align-items:flex-start;gap:6px">
        <b style="font-size:.92em">${a.title}</b>
        <button class="danger" data-adel="${a.id}" title="delete">✕</button>
      </div>
      <div class="row" style="gap:6px;margin-top:4px;flex-wrap:wrap">
        ${a.area ? `<span class="badge">${a.area}</span>` : ""}
        <select data-ast="${a.id}" style="font-size:.85em">
          ${["backlog", "w trakcie", "zrobione", "odrzucone"].map((s) =>
            `<option value="${s}" ${a.status === s ? "selected" : ""}>${STATUS_LABELS[s]}</option>`).join("")}
        </select>
      </div>
      ${a.expected_impact ? `<div class="muted" style="margin-top:6px;font-size:.85em">Target: <b>${a.expected_impact}</b></div>` : ""}
      ${a.detail ? `<details style="margin-top:4px"><summary class="muted" style="font-size:.85em">details / instructions</summary>
        <pre style="white-space:pre-wrap;font-family:inherit;margin:6px 0 0;font-size:.85em">${a.detail}</pre></details>` : ""}
      ${a.status === "zrobione" ? `<div style="margin-top:6px">
        <div class="row" style="gap:4px">
          <input data-num data-aimp="${a.id}" placeholder="actual PLN/yr" value="${fmt.grouped(a.actual_impact_pln)}" style="width:120px;font-size:.85em">
          <button data-asave="${a.id}" style="font-size:.85em">Save</button>
          ${a.done_at ? `<span class="muted" style="font-size:.8em">✓ ${a.done_at.slice(0, 10)}</span>` : ""}
        </div>
        <input data-anote="${a.id}" placeholder="what it delivered / takeaway" value="${a.actual_note || ""}" style="width:100%;margin-top:4px;font-size:.85em">
      </div>` : ""}
    </div>`;

  const column = (title, list) => list.length ? `
    <div class="acol">
      <h4 style="margin:0 0 8px">${title} <span class="muted">(${list.length})</span></h4>
      ${list.map(actionCard).join("")}
    </div>` : "";

  el.innerHTML = `
    <h2>Recommendations — action plan</h2>
    <div class="card" style="padding:10px 16px">
      <div class="row" style="gap:20px;flex-wrap:wrap">
        <span>🔥 In progress: <b>${byStatus["w trakcie"].length}</b></span>
        <span>📋 Backlog: <b>${byStatus.backlog.length}</b></span>
        <span>✅ Done: <b>${acts.done_count}</b></span>
        <span>💰 Measured impact: <b class="pos">${fmt.pln(acts.total_actual_impact)}/yr</b></span>
      </div>
    </div>

        <div class="card mt">
      <h3>Recommendation engine (live)</h3>
      <div class="muted" style="margin-bottom:8px">Recomputed every time the tab is opened,
        from current data (balances, rates, portfolio).</div>
      <table>
        <thead><tr><th style="width:140px">Category</th><th>Recommendation</th><th style="width:110px"></th></tr></thead>
        <tbody>
        ${engineItems.map((r, i) => `<tr>
          <td><span class="badge">${r.area}</span></td>
          <td style="font-size:.92em">${r.text.length > 160
            ? `${r.text.slice(0, 160)}… <details style="display:inline"><summary class="muted" style="display:inline;cursor:pointer">more</summary><div class="mt">${r.text}</div></details>`
            : r.text}</td>
          <td><button data-eadd="${i}">→ backlog</button></td>
        </tr>`).join("")}
        </tbody>
      </table>
    </div>

    <div class="card mt" style="border-left:4px solid #b78cff">
      <div class="row" style="justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px">
        <h3 style="margin:0">🧠 AI review of the recommendations above</h3>
        <button class="primary" id="aiOpBtn">Ask for an opinion</button>
      </div>
      <div class="muted" style="font-size:.85em;margin-top:6px">The list above comes from the <b>rule engine</b> (deterministic code, not AI). Here the AI reviews it critically against your own data: what it agrees with, what it would change, and which recommendation is missing. AI engine per the Control Center mode (local, or local+Claude with a synthesized verdict).</div>
      <div id="aiOpOut" class="mt">${aiOp && aiOp.text ? `
        <div class="muted" style="font-size:.8em">${aiOp.at} · ${aiOp.by}${aiOp.rag_used ? " · grounded in your data" : ""}</div>
        <div style="white-space:pre-wrap;font-size:.92em">${aiOp.text}</div>` : '<div class="muted" style="font-size:.85em">Not asked yet.</div>'}</div>
    </div>


    <div class="card mt">
      <h3>Add an action manually</h3>
      <div class="row">
        <input id="aTitle" placeholder="action title" style="flex:1">
        <input id="aArea" placeholder="area" style="width:130px">
        <input id="aExp" placeholder="expected impact (e.g. 16k/yr)" style="width:200px">
        <button class="primary" id="aAdd">Add</button>
      </div>
      <textarea id="aDetail" placeholder="details / instructions / e-mail body…" rows="3" class="mt" style="width:100%"></textarea>
    </div>

    <div class="acols mt">
      ${column("🔥 In progress", byStatus["w trakcie"])}
      ${column("📋 Backlog", byStatus.backlog)}
      ${column("✅ Done — takeaways", byStatus.zrobione)}
      ${byStatus.odrzucone.length ? column("🚫 Rejected", byStatus.odrzucone) : ""}
    </div>`;

  document.getElementById("aiOpBtn").addEventListener("click", async (e) => {
    const btn = e.target; btn.disabled = true;
    const out = document.getElementById("aiOpOut");
    out.innerHTML = '<div class="muted">The AI is reviewing the recommendations against your data…</div>';
    try {
      const r = await api.post("/api/recommendation/ai", {});
      out.innerHTML = r.text
        ? `<div class="muted" style="font-size:.8em">${r.at} · ${r.by}${r.rag_used ? " · grounded in your data" : ""}</div>
           <div style="white-space:pre-wrap;font-size:.92em">${r.text}</div>`
        : `<div class="neg">${r.error || "no answer"}</div>`;
    } catch (err) { out.innerHTML = `<div class="neg">Error: ${err.message}</div>`; }
    finally { btn.disabled = false; }
  });
  el.querySelectorAll("[data-eadd]").forEach((b) =>
    b.addEventListener("click", async () => {
      const r = engineItems[+b.dataset.eadd];
      await api.post("/api/actions", { title: r.text.slice(0, 80), area: r.area, detail: r.text });
      route();
    }));
  document.getElementById("aAdd").addEventListener("click", async () => {
    const title = document.getElementById("aTitle").value.trim();
    if (!title) { alert("Enter a title"); return; }
    await api.post("/api/actions", {
      title, area: document.getElementById("aArea").value,
      expected_impact: document.getElementById("aExp").value,
      detail: document.getElementById("aDetail").value,
    });
    route();
  });
  el.querySelectorAll("[data-ast]").forEach((sel) =>
    sel.addEventListener("change", async () => {
      await api.put("/api/actions/" + sel.dataset.ast, { status: sel.value });
      route();
    }));
  el.querySelectorAll("[data-asave]").forEach((b) =>
    b.addEventListener("click", async () => {
      const id = b.dataset.asave;
      await api.put("/api/actions/" + id, {
        actual_impact_pln: parseNum(el.querySelector(`[data-aimp="${id}"]`)) || null,
        actual_note: el.querySelector(`[data-anote="${id}"]`).value,
      });
      route();
    }));
  el.querySelectorAll("[data-adel]").forEach((b) =>
    b.addEventListener("click", async () => {
      if (!confirm("Delete this action?")) return;
      await api.del("/api/actions/" + b.dataset.adel);
      route();
    }));
}
