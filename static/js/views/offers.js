async function renderOffers(el) {
  const data = await api.get("/api/offers");
  const gh = await api.get("/api/github-activity").catch(() => null);
  const cfg = data.settings;
  const s = data.stats;
  const statsBar = s ? `
    <div class="card" style="padding:10px 16px">
      <div class="row" style="gap:22px;flex-wrap:wrap;align-items:baseline">
        <span title="Znana firma + scope ≥ Twój (Senior EM / Head / Field CTO) + widełki ≥ obecne. Najważniejszy sygnał rynkowy.">
          🏆 Tier-1: <b>${s.tier1_count}</b> <span class="muted">(${fmt.num(s.tier1_per_month, 1)}/mies.)</span></span>
        <span title="Wszystkie inbound, bez aplikowania.">📥 Łącznie: <b>${s.total}</b>
          <span class="muted">(${fmt.num(s.per_month, 1)}/mies. przez ${s.span_months} mies.)</span></span>
        <span title="Mediana z ofert, które ujawniły widełki.">💶 Mediana widełek:
          <b>${s.median_comp ? fmt.pln(s.median_comp) : "—"}</b>
          ${s.range_low ? `<span class="muted">(${fmt.grouped(s.range_low)}–${fmt.grouped(s.range_high)}, z ${s.quantified_count})</span>` : ""}</span>
        <span title="Najważniejszy wskaźnik: czy rynek wycenia Cię powyżej obecnego pakietu.">
          📈 ≥ obecne (${fmt.grouped(s.current)}): <b class="${s.ge_current_pct >= 50 ? "pos" : ""}">${s.ge_current_pct != null ? s.ge_current_pct + "%" : "—"}</b>
          <span class="muted">(${s.ge_current_count} z ${s.quantified_count})</span></span>
      </div>
      <div class="muted mt" style="font-size:.8em">Zdrowy wynik przy zerowym aplikowaniu: ~1 tier-1/mies.
        Kluczowa metryka long-term to <b>% ≥ obecne</b> — dopiero gdy kilka z rzędu wyraźnie przebije pakiet, rynek Cię „przerósł".</div>
    </div>` : "";
  el.innerHTML = `
    <h2>💼 Kariera — oferty, rynek, rozwój</h2>
    <div style="margin-bottom:10px">
      <a href="#career" style="text-decoration:none;display:inline-block;padding:6px 12px;
        border:1px solid ${CHART_COLORS[1]};border-radius:6px;color:${CHART_COLORS[1]};font-size:.9em">
        🧭 Analiza kariery — rozwój do Director / Head of Eng →</a>
      <a href="#commits" style="text-decoration:none;display:inline-block;padding:6px 12px;margin-left:6px;
        border:1px solid #3ecf8e;border-radius:6px;color:#3ecf8e;font-size:.9em">
        🧑‍💻 Commitowanie${gh ? ` — dziś ${gh.today}, seria ${gh.streak}🔥` : ""} →</a></div>
    ${statsBar}
    <div class="muted" style="margin:6px 0 12px;font-size:.88em">Punkt odniesienia (auto): <b>${s ? fmt.pln(s.current) : "—"}</b>/mies. —
      obecny total (base + bonus + RSU, liczony dynamicznie z kursem akcji RSU). Delty ofert i wpływ na cele liczone względem tego.</div>
    <div class="card" id="baroCard">
      <h3>📈 Barometr rynku — popyt na role EM / Head of Engineering (+ Twój inbound)</h3>
      <div class="muted" style="font-size:.85em;margin-bottom:8px">Ile łącznie ofert (Europa, remote) jest na rynku dla ról EM / Head of Engineering — trend miesięczny na tle Twojego inbound (słupki).
        Pokazuje, czy rosnąca liczba zapytań do Ciebie to Twoja marka, czy wzrost rynku (i czy AI go nie kurczy).
        <b>Aktualizowane przez Claude co miesiąc</b> (research agregatu boardów: Glassdoor / Indeed / Remote Rocketship) — nie liczysz nic ręcznie.</div>
      <canvas id="baroChart" height="95" class="mt"></canvas>
      <div id="baroTable" class="mt"></div>
    </div>
    <div class="card mt">
      <h3>Dodaj ofertę</h3>
      <div class="row">
        <input id="oCompany" placeholder="firma" style="width:160px">
        <input id="oRole" placeholder="rola" style="flex:1">
        <input data-num id="oTotal" placeholder="total mies. PLN">
        <input id="oModel" placeholder="model pracy" style="width:140px">
        <input type="date" id="oDate" value="${new Date().toISOString().slice(0, 10)}">
        <button class="primary" id="oAdd">Dodaj</button>
      </div>
    </div>
    <div id="oList" class="mt"></div>`;

  const list = document.getElementById("oList");
  if (!data.offers.length) {
    list.innerHTML = '<div class="empty">Brak ofert — dodaj pierwszą powyżej</div>';
  } else {
    list.innerHTML = data.offers.map((o) => {
      const noComp = !o.total_monthly;
      const delta = noComp ? null : o.delta_monthly;
      const deltaTxt = noComp ? "widełki nieujawnione"
        : delta == null ? "ustaw obecny total powyżej"
        : `${delta >= 0 ? "+" : ""}${fmt.pln(delta)}/mies. vs obecna praca`;
      const impact = (o.goal_impact || []).map((gi) =>
        gi.new_months == null ? "" : `<tr><td>${gi.goal}</td>
          <td>${fmt.num(gi.base_months, 1)} mies.</td>
          <td>${fmt.num(gi.new_months, 1)} mies.</td>
          <td class="${gi.months_saved > 0 ? "pos" : "neg"}">${gi.months_saved > 0 ? "−" : "+"}${fmt.num(Math.abs(gi.months_saved), 1)} mies.</td>
        </tr>`).join("");
      return `<div class="card mt">
        <div class="row" style="justify-content:space-between">
          <h3 style="margin:0">${o.company}${o.role ? " — " + o.role : ""}</h3>
          <span class="badge">${o.status}</span>
        </div>
        <div class="row mt">
          <b>${noComp ? "—" : fmt.pln(o.total_monthly) + "/mies."}</b>
          <span class="${delta > 0 ? "pos" : delta < 0 ? "neg" : "muted"}">${deltaTxt}</span>
          <span class="muted">${o.work_model || ""} · ${o.received_at || ""}</span>
        </div>
        ${impact ? `<table class="mt"><thead><tr>
            <th>Cel</th><th>Teraz</th><th>Z tą ofertą</th><th>Różnica</th>
          </tr></thead><tbody>${impact}</tbody></table>
          <div class="muted">Założenie: cała nadwyżka wynagrodzenia idzie na cel.</div>` : ""}
        ${o.notes ? `<div class="muted mt">${o.notes}</div>` : ""}
        <div class="row mt">
          <select data-ost="${o.id}">
            ${["nowa", "rozmowy", "oferta", "odrzucona", "przyjęta"].map((s) =>
              `<option ${o.status === s ? "selected" : ""}>${s}</option>`).join("")}
          </select>
          <button data-osave="${o.id}">Zapisz status</button>
          <button class="danger" data-odel="${o.id}">Usuń</button>
        </div>
      </div>`;
    }).join("");
  }

  // --- barometr rynku ---
  const baro = await api.get("/api/market-barometer").catch(() => ({ points: [] }));
  const bpts = baro.points || [];
  const btbl = document.getElementById("baroTable");
  if (bpts.length) {
    btbl.innerHTML = `<table><thead><tr><th>Miesiąc</th><th style="text-align:right">Oferty EM</th>
      <th style="text-align:right">Head of Eng</th><th style="text-align:right">Twój inbound</th><th>Źródło</th><th></th></tr></thead><tbody>` +
      [...bpts].reverse().map((p) => `<tr><td>${p.month}</td>
        <td style="text-align:right">${p.em_openings != null ? fmt.grouped(p.em_openings) : "—"}</td>
        <td style="text-align:right">${p.head_openings != null ? fmt.grouped(p.head_openings) : "—"}</td>
        <td style="text-align:right">${p.my_inbound}</td>
        <td class="muted" style="font-size:.82em">${/szacun/i.test(p.note || "") ? "⚠️ szacunek" : (p.note ? p.note : "LinkedIn")}</td>
        <td><button class="danger" data-bdel="${p.id}">✕</button></td></tr>`).join("") + "</tbody></table>";
    btbl.querySelectorAll("[data-bdel]").forEach((b) =>
      b.addEventListener("click", async () => { await api.del("/api/market-barometer/" + b.dataset.bdel); route(); }));
    trackChart(new Chart(document.getElementById("baroChart"), {
      data: {
        labels: bpts.map((p) => p.month),
        datasets: [
          { type: "bar", label: "Twój inbound (oferty do Ciebie)", data: bpts.map((p) => p.my_inbound),
            backgroundColor: "rgba(255,209,102,0.55)", yAxisID: "y1", order: 3, barPercentage: 0.5, categoryPercentage: 0.6 },
          { type: "line", label: "Rynek: EM (Europa remote)", data: bpts.map((p) => p.em_openings),
            borderColor: CHART_COLORS[0], backgroundColor: "transparent", yAxisID: "y", tension: 0.25, borderWidth: 3, pointRadius: 3, order: 1 },
          { type: "line", label: "Rynek: Head of Eng", data: bpts.map((p) => p.head_openings),
            borderColor: CHART_COLORS[1], backgroundColor: "transparent", yAxisID: "y", tension: 0.25, borderWidth: 3, pointRadius: 3, order: 2 },
        ],
      },
      options: {
        interaction: { mode: "index", intersect: false },
        scales: {
          y: { position: "left", beginAtZero: true, title: { display: true, text: "oferty na rynku" } },
          y1: { position: "right", beginAtZero: true, suggestedMax: 6, grid: { drawOnChartArea: false },
            ticks: { stepSize: 1 }, title: { display: true, text: "Twój inbound" } },
        },
      },
    }));
  } else {
    btbl.innerHTML = '<div class="empty">Barometr uzupełni Claude przy najbliższej aktualizacji miesięcznej.</div>';
  }

  document.getElementById("oAdd").addEventListener("click", async () => {
    const company = document.getElementById("oCompany").value.trim();
    const total = parseNum(document.getElementById("oTotal"));
    if (!company || !total) { alert("Podaj firmę i total miesięczny"); return; }
    await api.post("/api/offers", {
      company,
      role: document.getElementById("oRole").value,
      total_monthly: total,
      work_model: document.getElementById("oModel").value,
      received_at: document.getElementById("oDate").value,
    });
    route();
  });
  list.querySelectorAll("[data-osave]").forEach((b) =>
    b.addEventListener("click", async () => {
      await api.put("/api/offers/" + b.dataset.osave,
        { status: list.querySelector(`[data-ost="${b.dataset.osave}"]`).value });
      route();
    }));
  list.querySelectorAll("[data-odel]").forEach((b) =>
    b.addEventListener("click", async () => {
      if (!confirm("Usunąć ofertę?")) return;
      await api.del("/api/offers/" + b.dataset.odel);
      route();
    }));
}
