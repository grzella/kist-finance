async function renderReminders(el) {
  const d = await api.get("/api/reminders");
  const rem = d.reminders;
  const urgency = (days) => days == null ? "muted"
    : days < 0 ? "neg" : days <= 14 ? "neg" : days <= 45 ? "" : "muted";
  const daysTxt = (days) => days == null ? "—"
    : days < 0 ? `${-days} dni temu` : days === 0 ? "dziś" : `za ${days} dni`;

  el.innerHTML = `
    <h2>🛠️ Control Center</h2>
    <div class="row" style="gap:8px;margin-bottom:12px">
      <a href="#control" style="text-decoration:none;padding:5px 12px;border-radius:6px;border:1px solid #4a4f66;color:#e8e8ee">🛠️ Automatyzacje &amp; health</a>
      <a href="#reminders" style="text-decoration:none;padding:5px 12px;border-radius:6px;background:${CHART_COLORS[0]};color:#fff">🔔 Przypomnienia</a>
      <a href="#data" style="text-decoration:none;padding:5px 12px;border-radius:6px;border:1px solid #4a4f66;color:#e8e8ee">📊 Dane w aplikacji</a>
    </div>
    <div class="muted" style="margin-bottom:12px">Automatyczne (z danych: vesty, bonus, koniec stałej stopy, targety, przeglądy)
      + Twoje własne. Sortowane wg terminu.</div>

    <div class="card">
      <h3>Dodaj przypomnienie</h3>
      <div class="row">
        <input id="rmTitle" placeholder="tytuł" style="flex:1">
        <input type="date" id="rmDate">
        <button class="primary" id="rmAdd">Dodaj</button>
      </div>
    </div>

    <div class="card mt">
      <div style="overflow-x:auto"><table>
        <thead><tr><th style="width:120px">Termin</th><th>Co</th><th style="width:90px">Typ</th><th style="width:60px"></th></tr></thead>
        <tbody>${rem.map((r) => `<tr>
          <td class="${urgency(r.days)}"><b>${daysTxt(r.days)}</b><div class="muted" style="font-size:.8em">${r.due_date || ""}</div></td>
          <td>${r.title}${r.note ? `<div class="muted" style="font-size:.82em">${r.note}</div>` : ""}</td>
          <td>${r.auto ? `<span class="badge">${r.kind || "auto"}</span>` : '<span class="badge">własne</span>'}</td>
          <td>${r.auto ? '<span class="muted" style="font-size:.8em">auto</span>'
            : `<button data-rdone="${r.id}" title="zrobione">✓</button> <button class="danger" data-rdel="${r.id}">✕</button>`}</td>
        </tr>`).join("")}</tbody>
      </table></div>
      ${d.done_count ? `<div class="muted mt" style="font-size:.85em">✅ Zrobione: ${d.done_count}</div>` : ""}
    </div>`;

  document.getElementById("rmAdd").addEventListener("click", async () => {
    const title = document.getElementById("rmTitle").value.trim();
    if (!title) { alert("Podaj tytuł"); return; }
    await api.post("/api/reminders", { title, due_date: document.getElementById("rmDate").value || null });
    route();
  });
  el.querySelectorAll("[data-rdone]").forEach((b) =>
    b.addEventListener("click", async () => {
      await api.put("/api/reminders/" + b.dataset.rdone, { done: true });
      route();
    }));
  el.querySelectorAll("[data-rdel]").forEach((b) =>
    b.addEventListener("click", async () => {
      await api.del("/api/reminders/" + b.dataset.rdel);
      route();
    }));
}
