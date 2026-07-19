async function renderOffers(el) {
  const data = await api.get("/api/offers");
  const gh = await api.get("/api/github-activity").catch(() => null);
  const cfg = data.settings;
  const OFFER_STATUS = { new: "New", interviewing: "Interviewing", offer: "Offer", rejected: "Rejected", accepted: "Accepted" };
  const s = data.stats;
  const statsBar = s ? `
    <div class="card" style="padding:10px 16px">
      <div class="row" style="gap:22px;flex-wrap:wrap;align-items:baseline">
        <span title="A known company + scope ≥ yours + range ≥ current. The most important market signal.">
          🏆 Tier-1: <b>${s.tier1_count}</b> <span class="muted">(${fmt.num(s.tier1_per_month, 1)}/mo)</span></span>
        <span title="All inbound, no applying.">📥 Total: <b>${s.total}</b>
          <span class="muted">(${fmt.num(s.per_month, 1)}/mo over ${s.span_months} mo)</span></span>
        <span title="Median of offers that disclosed a range.">💶 Median range:
          <b>${s.median_comp ? fmt.pln(s.median_comp) : "—"}</b>
          ${s.range_low ? `<span class="muted">(${fmt.grouped(s.range_low)}–${fmt.grouped(s.range_high)}, of ${s.quantified_count})</span>` : ""}</span>
        <span title="The most important indicator: whether the market prices you above your current package.">
          📈 ≥ current (${fmt.grouped(s.current)}): <b class="${s.ge_current_pct >= 50 ? "pos" : ""}">${s.ge_current_pct != null ? s.ge_current_pct + "%" : "—"}</b>
          <span class="muted">(${s.ge_current_count} of ${s.quantified_count})</span></span>
      </div>
      <div class="muted mt" style="font-size:.8em">A healthy result with zero applying: ~1 tier-1/mo.
        The key long-term metric is <b>% ≥ current</b> — only when several in a row clearly beat the package has the market "outgrown" you.</div>
    </div>` : "";
  el.innerHTML = `
    <h2>💼 Career — offers, market, growth</h2>
    <details style="margin:6px 0 12px;padding:8px 12px;background:#4c8dff14;border-radius:8px">
      <summary style="cursor:pointer;font-size:.9em"><b>👀 What this tab is (and is not)</b> — market monitoring, not job hunting</summary>
      <div class="muted" style="font-size:.87em;margin-top:6px">This tab watches the <b>job market as a signal</b>, the same way the Market tab watches stock prices:
        what is the sentiment around your role, how many offers reach you <i>without applying anywhere</i>, and how demand shifts over time —
        especially as AI reshapes engineering roles. Tracking inbound offers measures your market value and the health of your niche;
        it is not a sign of looking for a new job. Think of it as a personal labor-market index.</div>
    </details>
    <div style="margin-bottom:10px">
      <a href="#career" style="text-decoration:none;display:inline-block;padding:6px 12px;
        border:1px solid ${CHART_COLORS[1]};border-radius:6px;color:${CHART_COLORS[1]};font-size:.9em">
        🧭 Long-term career analysis →</a>
      <a href="#commits" style="text-decoration:none;display:inline-block;padding:6px 12px;margin-left:6px;
        border:1px solid #3ecf8e;border-radius:6px;color:#3ecf8e;font-size:.9em">
        🧑‍💻 Committing${gh ? ` — today ${gh.today}, streak ${gh.streak}🔥` : ""} →</a></div>
    ${statsBar}
    <div class="muted" style="margin:6px 0 12px;font-size:.88em">Reference point (auto): <b>${s ? fmt.pln(s.current) : "—"}</b>/mo —
      current total (base + bonus + RSU, computed dynamically from the RSU stock price). Offer deltas and goal impact are computed against this.</div>
    <div class="card" id="baroCard">
      <h3>📈 Market barometer — demand for ${data.roles.a} / ${data.roles.b} roles (+ your inbound)</h3>
      <div class="muted" style="font-size:.85em;margin-bottom:8px">Total open roles on your market for the two roles you track (rename them in Settings: career_role_a / career_role_b) — a monthly trend against your inbound (bars).
        Shows whether the growing number of inquiries to you is your brand or market growth (and whether AI is shrinking it).
        <b>Updated by Claude monthly</b> (research across board aggregates: Glassdoor / Indeed / Remote Rocketship) — you compute nothing by hand.</div>
      <canvas id="baroChart" height="95" class="mt"></canvas>
      <div id="baroTable" class="mt"></div>
    </div>
    <div class="card mt">
      <h3>Add an offer</h3>
      <div class="row">
        <input id="oCompany" placeholder="company" style="width:160px">
        <input id="oRole" placeholder="role" style="flex:1">
        <input data-num id="oTotal" placeholder="monthly total PLN">
        <input id="oModel" placeholder="work model" style="width:140px">
        <input type="date" id="oDate" value="${new Date().toISOString().slice(0, 10)}">
        <button class="primary" id="oAdd">Add</button>
      </div>
    </div>
    <div id="oList" class="mt"></div>`;

  const list = document.getElementById("oList");
  if (!data.offers.length) {
    list.innerHTML = '<div class="empty">No offers — add the first one above</div>';
  } else {
    list.innerHTML = data.offers.map((o) => {
      const noComp = !o.total_monthly;
      const delta = noComp ? null : o.delta_monthly;
      const deltaTxt = noComp ? "range not disclosed"
        : delta == null ? "set your current total above"
        : `${delta >= 0 ? "+" : ""}${fmt.pln(delta)}/mo vs current job`;
      const impact = (o.goal_impact || []).map((gi) =>
        gi.new_months == null ? "" : `<tr><td>${gi.goal}</td>
          <td>${fmt.num(gi.base_months, 1)} mo</td>
          <td>${fmt.num(gi.new_months, 1)} mo</td>
          <td class="${gi.months_saved > 0 ? "pos" : "neg"}">${gi.months_saved > 0 ? "−" : "+"}${fmt.num(Math.abs(gi.months_saved), 1)} mo</td>
        </tr>`).join("");
      return `<div class="card mt">
        <div class="row" style="justify-content:space-between">
          <h3 style="margin:0">${o.company}${o.role ? " — " + o.role : ""}</h3>
          <span class="badge">${OFFER_STATUS[o.status] || o.status}</span>
        </div>
        <div class="row mt">
          <b>${noComp ? "—" : fmt.pln(o.total_monthly) + "/mo"}</b>
          <span class="${delta > 0 ? "pos" : delta < 0 ? "neg" : "muted"}">${deltaTxt}</span>
          <span class="muted">${o.work_model || ""} · ${o.received_at || ""}</span>
        </div>
        ${impact ? `<table class="mt"><thead><tr>
            <th>Goal</th><th>Now</th><th>With this offer</th><th>Difference</th>
          </tr></thead><tbody>${impact}</tbody></table>
          <div class="muted">Assumption: the entire pay surplus goes toward the goal.</div>` : ""}
        ${o.notes ? `<div class="muted mt">${o.notes}</div>` : ""}
        <div class="row mt">
          <select data-ost="${o.id}">
            ${["new", "interviewing", "offer", "rejected", "accepted"].map((s) =>
              `<option value="${s}" ${o.status === s ? "selected" : ""}>${OFFER_STATUS[s]}</option>`).join("")}
          </select>
          <button data-osave="${o.id}">Save status</button>
          <button class="danger" data-odel="${o.id}">Delete</button>
        </div>
      </div>`;
    }).join("");
  }

  // --- market barometer ---
  const baro = await api.get("/api/market-barometer").catch(() => ({ points: [] }));
  const bpts = baro.points || [];
  const btbl = document.getElementById("baroTable");
  if (bpts.length) {
    btbl.innerHTML = `<table><thead><tr><th>Month</th><th style="text-align:right">EM openings</th>
      <th style="text-align:right">${data.roles.b}</th><th style="text-align:right">Your inbound</th><th>Source</th><th></th></tr></thead><tbody>` +
      [...bpts].reverse().map((p) => `<tr><td>${p.month}</td>
        <td style="text-align:right">${p.em_openings != null ? fmt.grouped(p.em_openings) : "—"}</td>
        <td style="text-align:right">${p.head_openings != null ? fmt.grouped(p.head_openings) : "—"}</td>
        <td style="text-align:right">${p.my_inbound}</td>
        <td class="muted" style="font-size:.82em">${/szacun/i.test(p.note || "") ? "⚠️ estimate" : (p.note ? p.note : "LinkedIn")}</td>
        <td><button class="danger" data-bdel="${p.id}">✕</button></td></tr>`).join("") + "</tbody></table>";
    btbl.querySelectorAll("[data-bdel]").forEach((b) =>
      b.addEventListener("click", async () => { await api.del("/api/market-barometer/" + b.dataset.bdel); route(); }));
    trackChart(new Chart(document.getElementById("baroChart"), {
      data: {
        labels: bpts.map((p) => p.month),
        datasets: [
          { type: "bar", label: "Your inbound (offers to you)", data: bpts.map((p) => p.my_inbound),
            backgroundColor: "rgba(255,209,102,0.55)", yAxisID: "y1", order: 3, barPercentage: 0.5, categoryPercentage: 0.6 },
          { type: "line", label: "Market: " + data.roles.a, data: bpts.map((p) => p.em_openings),
            borderColor: CHART_COLORS[0], backgroundColor: "transparent", yAxisID: "y", tension: 0.25, borderWidth: 3, pointRadius: 3, order: 1 },
          { type: "line", label: "Market: " + data.roles.b, data: bpts.map((p) => p.head_openings),
            borderColor: CHART_COLORS[1], backgroundColor: "transparent", yAxisID: "y", tension: 0.25, borderWidth: 3, pointRadius: 3, order: 2 },
        ],
      },
      options: {
        interaction: { mode: "index", intersect: false },
        scales: {
          y: { position: "left", beginAtZero: true, title: { display: true, text: "openings on the market" } },
          y1: { position: "right", beginAtZero: true, suggestedMax: 6, grid: { drawOnChartArea: false },
            ticks: { stepSize: 1 }, title: { display: true, text: "Your inbound" } },
        },
      },
    }));
  } else {
    btbl.innerHTML = '<div class="empty">No data yet — ask your AI assistant to research this month openings for your two role groups and insert the first row (see the note above).</div>';
  }

  document.getElementById("oAdd").addEventListener("click", async () => {
    const company = document.getElementById("oCompany").value.trim();
    const total = parseNum(document.getElementById("oTotal"));
    if (!company || !total) { alert("Enter the company and monthly total"); return; }
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
      if (!confirm("Delete this offer?")) return;
      await api.del("/api/offers/" + b.dataset.odel);
      route();
    }));
}
