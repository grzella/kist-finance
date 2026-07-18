async function renderData(el) {
  const d = await api.get("/api/data-inventory");
  const s = d.summary;

  const MODE = {
    auto: ["🟢 auto", "#3ecf8e"],
    derived: ["🔵 derived", "#4c8dff"],
    claude: ["🟣 Claude", "#b78cff"],
    manual: ["🟡 manual", "#ffd166"],
  };
  const modeBadge = (m) => {
    const [label, color] = MODE[m] || ["·", "#9aa"];
    return `<span class="badge" style="background:${color}22;color:${color};white-space:nowrap">${label}</span>`;
  };
  const lvl = (v) => v === "wysoki" || v === "high" ? "pos" : v === "niski" || v === "low" ? "muted" : "";

  const groupCard = (g) => `
    <div class="card mt">
      <h3 style="margin-top:0">${g.title}</h3>
      <div class="muted" style="margin:-4px 0 10px;font-size:.9em">${g.note}</div>
      <div style="overflow-x:auto"><table>
        <thead><tr><th>Data</th><th>Mode</th><th>Source</th><th>Frequency</th>
          <th>Last upd.</th><th style="text-align:right">Recs</th><th style="text-align:right">min/mo</th></tr></thead>
        <tbody>${g.items.map((i) => `<tr>
          <td><b>${i.name}</b>${i.note ? `<div class="muted" style="font-size:.82em">${i.note}</div>` : ""}
            ${i.suggest ? `<div style="font-size:.82em;color:#ffd166">💡 ${i.suggest}</div>` : ""}</td>
          <td>${modeBadge(i.mode)}</td>
          <td class="muted" style="font-size:.85em">${i.source}</td>
          <td class="muted" style="font-size:.85em;white-space:nowrap">${i.freq}</td>
          <td style="white-space:nowrap;font-size:.88em">${i.last}</td>
          <td style="text-align:right" class="muted">${i.count != null ? i.count : "—"}</td>
          <td style="text-align:right" class="${i.minutes ? "" : "muted"}">${i.minutes ? "~" + i.minutes : "0"}</td>
        </tr>`).join("")}</tbody>
      </table></div>
    </div>`;

  el.innerHTML = `
    <h2>🛠️ Control Center</h2>
    <div class="row" style="gap:8px;margin-bottom:12px">
      <a href="#control" style="text-decoration:none;padding:5px 12px;border-radius:6px;border:1px solid #4a4f66;color:#e8e8ee">🛠️ Automation &amp; health</a>
      <a href="#reminders" style="text-decoration:none;padding:5px 12px;border-radius:6px;border:1px solid #4a4f66;color:#e8e8ee">🔔 Reminders</a>
      <a href="#data" style="text-decoration:none;padding:5px 12px;border-radius:6px;background:${CHART_COLORS[0]};color:#fff">📊 Data in the app</a>
    </div>
    <div class="muted" style="margin-bottom:12px">What is pulled in automatically, what you have to enter yourself and how often.
      Goal: as much as possible fully automated, with only the absolute monthly minimum done by hand. As of: ${d.generated_at}.</div>

    <div class="grid cols-4">
      <div class="card kpi"><div class="label">Zero-effort sources</div><div class="value pos">${s.auto}</div>
        <div class="sub">auto + derived by the app</div></div>
      <div class="card kpi"><div class="label">Maintained by Claude</div><div class="value" style="color:#b78cff">${s.claude}</div>
        <div class="sub">monthly / on demand</div></div>
      <div class="card kpi"><div class="label">Manual touchpoints / mo</div><div class="value" style="color:#ffd166">${s.manual_touchpoints}</div>
        <div class="sub">+ ${s.manual_rare} rare/event-driven</div></div>
      <div class="card kpi"><div class="label">Manual time / mo</div><div class="value">~${s.manual_minutes} min</div>
        <div class="sub">target after automation: ~3 min</div></div>
    </div>

    ${d.groups.map(groupCard).join("")}

    <div class="card mt" style="border-left:4px solid #ffd166">
      <h3 style="margin-top:0">🚀 Automation roadmap — getting down to the minimum</h3>
      <div class="muted" style="margin:-4px 0 10px;font-size:.9em">Priority: eliminate monthly data entry.
        Ordered by impact-to-effort ratio.</div>
      <div style="overflow-x:auto"><table>
        <thead><tr><th>Improvement</th><th>Impact</th><th>Effort</th><th>Payoff</th><th>How</th></tr></thead>
        <tbody>${d.roadmap.map((r) => `<tr>
          <td><b>${r.title}</b></td>
          <td class="${lvl(r.impact)}">${r.impact}</td>
          <td class="muted">${r.effort}</td>
          <td class="muted" style="font-size:.88em">${r.saves}</td>
          <td class="muted" style="font-size:.85em">${r.how}</td>
        </tr>`).join("")}</tbody>
      </table></div>
    </div>

    <div class="card mt muted" style="font-size:.85em">
      <b>End state:</b> the only point that can't be automated "for free" is account balances —
      and even that goes away once free PSD2 (Open Banking) is hooked up via n8n. Once the roadmap is done
      you only enter event-driven things by hand (a new offer, an ETF purchase, an installment change), nothing recurring.
    </div>`;
}
