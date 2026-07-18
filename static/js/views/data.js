async function renderData(el) {
  const d = await api.get("/api/data-inventory");
  const s = d.summary;

  const MODE = {
    auto: ["🟢 auto", "#3ecf8e"],
    derived: ["🔵 liczone", "#4c8dff"],
    claude: ["🟣 Claude", "#b78cff"],
    manual: ["🟡 ręcznie", "#ffd166"],
  };
  const modeBadge = (m) => {
    const [label, color] = MODE[m] || ["·", "#9aa"];
    return `<span class="badge" style="background:${color}22;color:${color};white-space:nowrap">${label}</span>`;
  };
  const lvl = (v) => v === "wysoki" ? "pos" : v === "niski" ? "muted" : "";

  const groupCard = (g) => `
    <div class="card mt">
      <h3 style="margin-top:0">${g.title}</h3>
      <div class="muted" style="margin:-4px 0 10px;font-size:.9em">${g.note}</div>
      <div style="overflow-x:auto"><table>
        <thead><tr><th>Dane</th><th>Tryb</th><th>Źródło</th><th>Częstotliwość</th>
          <th>Ostatnia akt.</th><th style="text-align:right">Rek.</th><th style="text-align:right">min/mies</th></tr></thead>
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
      <a href="#control" style="text-decoration:none;padding:5px 12px;border-radius:6px;border:1px solid #4a4f66;color:#e8e8ee">🛠️ Automatyzacje &amp; health</a>
      <a href="#reminders" style="text-decoration:none;padding:5px 12px;border-radius:6px;border:1px solid #4a4f66;color:#e8e8ee">🔔 Przypomnienia</a>
      <a href="#data" style="text-decoration:none;padding:5px 12px;border-radius:6px;background:${CHART_COLORS[0]};color:#fff">📊 Dane w aplikacji</a>
    </div>
    <div class="muted" style="margin-bottom:12px">Co jest zaciągane automatycznie, a co musisz wpisać sam i jak często.
      Cel: jak najwięcej w pełni zautomatyzowane, a ręcznie tylko absolutne minimum co miesiąc. Stan: ${d.generated_at}.</div>

    <div class="grid cols-4">
      <div class="card kpi"><div class="label">Źródła bez pracy</div><div class="value pos">${s.auto}</div>
        <div class="sub">auto + liczone przez apkę</div></div>
      <div class="card kpi"><div class="label">Utrzymuje Claude</div><div class="value" style="color:#b78cff">${s.claude}</div>
        <div class="sub">miesięcznie / na żądanie</div></div>
      <div class="card kpi"><div class="label">Ręczne punkty / mies.</div><div class="value" style="color:#ffd166">${s.manual_touchpoints}</div>
        <div class="sub">+ ${s.manual_rare} rzadkich/zdarzeniowych</div></div>
      <div class="card kpi"><div class="label">Czas ręczny / mies.</div><div class="value">~${s.manual_minutes} min</div>
        <div class="sub">cel po automatyzacji: ~3 min</div></div>
    </div>

    ${d.groups.map(groupCard).join("")}

    <div class="card mt" style="border-left:4px solid #ffd166">
      <h3 style="margin-top:0">🚀 Roadmapa automatyzacji — jak zejść do minimum</h3>
      <div class="muted" style="margin:-4px 0 10px;font-size:.9em">Priorytet: usunąć comiesięczne wpisywanie.
        Kolejność wg stosunku efektu do nakładu.</div>
      <div style="overflow-x:auto"><table>
        <thead><tr><th>Usprawnienie</th><th>Efekt</th><th>Nakład</th><th>Zysk</th><th>Jak</th></tr></thead>
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
      <b>Kierunek docelowy:</b> jedyny nieautomatyzowalny „za darmo” punkt to salda kont —
      i to też znika po podpięciu darmowego PSD2 (Open Banking) przez n8n. Po realizacji roadmapy
      wpisujesz ręcznie tylko rzeczy zdarzeniowe (nowa oferta, zakup ETF, zmiana raty), a nie nic cyklicznego.
    </div>`;
}
