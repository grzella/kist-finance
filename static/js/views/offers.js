async function renderOffers(el) {
  const data = await api.get("/api/offers");
  const gh = await api.get("/api/github-activity").catch(() => null);
  const cfg = data.settings;
  const OFFER_STATUS = { new: "New", interviewing: "Interviewing", offer: "Offer", rejected: "Rejected", accepted: "Accepted" };
  const s = data.stats;
  const statsBar = s ? `
    <div class="card" style="padding:10px 16px">
      <div class="row" style="gap:22px;flex-wrap:wrap;align-items:baseline">
        <span title="A known company + scope ≥ yours + range ≥ current.">
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
    ${CAREER_TAB_INFO}
    <div style="margin-bottom:10px">
      <a href="#career" class="pill pos">🧭 Long-term career analysis →</a>
      <a href="#commits" class="pill pos" style="margin-left:6px">
        🧑‍💻 Committing${gh ? ` — today ${gh.today}, streak ${gh.streak}🔥` : ""} →</a></div>
    ${statsBar}
    <div class="muted" style="margin:6px 0 12px;font-size:.88em">Reference point (auto): <b>${s ? fmt.pln(s.current) : "—"}</b>/mo —
      current gross total (base + bonus + RSU + cash vest, computed dynamically from the RSU stock price). Offer deltas and goal impact are computed against this.</div>
    <div class="card" id="baroCard">
      <h3 style="margin:0">📈 Market barometer — your roles (index + your inbound)</h3>
      <div class="muted" style="font-size:.85em;margin:6px 0 8px" id="baroDesc">Is the market for your roles growing, set against the offers you receive. All series as an index (first month = 100).
        ${help(`<b>🏢 open roles</b>: postings for your roles in Europe at watchlist companies (⚙️), a snapshot at month end.<br>
          <b>🌍 Indeed</b>: history of IT posting volume in GB/DE/FR (Software Development and IT broad); the whole sector.<br>
          <b>📈 interest</b>: Google Trends, i.e. who searches for the role title (mostly candidates); sentiment, not demand.<br>
          <b>Bars</b>: your inbound, line = 3-month average. If inbound falls with the market, it's the market; if alone, it's your visibility.`, "how to read this")}</div>
      <details class="mt"><summary class="pill" style="font-size:.78em">⚙️ roles / geography</summary><div id="baroCfgBox" class="mt"></div></details>
      <canvas id="baroChart" height="95" class="mt"></canvas>
      <h4 style="margin:16px 0 0">💶 Average offered range (total/mo)</h4>
      <div class="muted" style="font-size:.85em;margin:4px 0 6px">Average of the offers that disclosed a range, against your package (dashed line): base, bonus, shares and cash-vest that applied in each month, at today's price, stepping at raises and new grant starts (3 months ahead).
        Offers without numbers don't drag the average down; a month without any range stays empty.</div>
      <canvas id="compChart" height="60"></canvas>
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
          <h3 style="margin:0">${esc(o.company)}${o.role ? " — " + esc(o.role) : ""}</h3>
          <span class="badge">${esc(OFFER_STATUS[o.status] || o.status)}</span>
        </div>
        <div class="row mt">
          <b>${noComp ? "—" : fmt.pln(o.total_monthly) + "/mo"}</b>
          <span class="${delta > 0 ? "pos" : delta < 0 ? "neg" : "muted"}">${deltaTxt}</span>
          <span class="muted">${esc(o.work_model || "")} · ${esc(o.received_at || "")}</span>
        </div>
        ${impact ? `<table class="mt"><thead><tr>
            <th>Goal</th><th>Now</th><th>With this offer</th><th>Difference</th>
          </tr></thead><tbody>${impact}</tbody></table>
          <div class="muted">Assumption: the entire pay surplus goes toward the goal.</div>` : ""}
        ${o.notes ? `<div class="muted mt">${esc(o.notes)}</div>` : ""}
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

  // --- market barometer (index + trend, roles from config) ---
  const baro = await api.get("/api/market-barometer").catch(() => ({ points: [], roles: [], series: {}, geo: [] }));
  // Gap guard: the last FULL month must have a 'trends' point; if not, say so
  // (with the collector's last error) instead of silently drawing a shorter line.
  {
    const t = new Date(); const lf = new Date(t.getFullYear(), t.getMonth() - 1, 1);
    const lastFull = `${lf.getFullYear()}-${String(lf.getMonth() + 1).padStart(2, "0")}`;
    const trendMonths = (baro.points || []).filter((p) => p.stream === "trends").map((p) => p.month);
    if (!trendMonths.includes(lastFull)) {
      const sched = await api.get("/api/schedules").catch(() => null);
      const task = sched && sched.tasks.find((x) => x.id === "barometer_collect");
      const err = task && task.last_error ? ` Last attempt ${task.last_error.at}: <i>${esc(task.last_error.error)}</i>.` : "";
      const box = document.getElementById("baroDesc");
      if (box) box.insertAdjacentHTML("beforebegin", `<div class="mt" style="padding:6px 10px;border-radius:6px;background:rgba(255,107,107,0.15);font-size:.88em">
        ⚠️ <b>No demand point for ${lastFull}</b> (last full month).${err} The collector retries on the next app open; see Control Center → Data → Schedules.</div>`);
    }
  }
  const bpts = baro.points || [];
  const broles = baro.roles || [];
  const bser = baro.series || {};

  const cfgBox = document.getElementById("baroCfgBox");
  cfgBox.innerHTML = `<div class="muted" style="font-size:.82em">Geography (comma-separated) and roles (one per line, <code>Label = title query</code>). The n8n collector uses the <b>query</b> to count postings on job boards.</div>
    <input id="baroGeo" value="${(baro.geo || []).join(", ")}" style="width:100%;margin-top:6px" placeholder="Remote, US, UK">
    <textarea id="baroRoles" rows="3" style="width:100%;margin-top:6px" placeholder="Senior Engineer = senior software engineer">${esc(broles.map((r) => `${r.label} = ${r.query || r.label}`).join("\n"))}</textarea>
    <div class="muted mt" style="font-size:.82em">🏢 <b>Watchlist</b> (one company per line: <code>greenhouse:slug</code>, <code>lever:slug</code> or <code>ashby:slug</code>; the slug is the name in the job board URL, e.g. <code>boards.greenhouse.io/gitlab</code> → <code>greenhouse:gitlab</code>). A posting counts when its title contains a role's query, in Europe or remote without a restriction to another continent; sales / solutions / support engineering roles are skipped.</div>
    <textarea id="baroWatch" rows="6" style="width:100%;margin-top:6px">${esc((baro.watchlist || []).join("\n"))}</textarea>
    <button class="primary mt" id="baroSave" style="font-size:.85em">Save config</button>`;
  document.getElementById("baroSave").addEventListener("click", async () => {
    const geo = document.getElementById("baroGeo").value.split(",").map((s) => s.trim()).filter(Boolean);
    const roles = document.getElementById("baroRoles").value.split("\n").map((ln) => {
      const [label, query] = ln.split("=").map((s) => s.trim());
      if (!label) return null;
      return { key: label.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "") || "role",
               label, query: query || label };
    }).filter(Boolean);
    const watchlist = document.getElementById("baroWatch").value.split("\n").map((s) => s.trim()).filter(Boolean);
    await api.put("/api/settings", { barometer_config: JSON.stringify({ geo, roles, watchlist }) });
    route();
  });

  const btbl = document.getElementById("baroTable");
  const months = baro.months || [];
  const readCls = (r) => /shrink|fall/.test(r || "") ? "neg" : /grow/.test(r || "") ? "pos" : "muted";
  const roleColor = {}; broles.forEach((r, i) => { roleColor[r.key] = [CHART_COLORS[0], CHART_COLORS[1], CHART_COLORS[4], CHART_COLORS[3]][i % 4]; });
  const streamShort = { trends: "interest", openings: "openings", watchlist: "open roles", hiringlab: "IT postings" };
  const streamIcon = { trends: "📈", openings: "🎯", watchlist: "🏢", hiringlab: "🌍" };
  roleColor.it_eu = CHART_COLORS[4];  // not [2]: warn is the inbound bar colour
  roleColor.it_broad = CHART_COLORS[5];
  const hlLabel = { it_eu: "🌍 Indeed: Software Development (Europe)", it_broad: "🌍 Indeed: IT broad (Europe)" };
  if (bpts.length) {
    // readings per role×stream: one tile per series (marker as on the chart), direction and %/3m
    const srcName = { trends: "Google Trends · searches", watchlist: "watchlist · open roles",
                      openings: "JSearch · openings", hiringlab: "Indeed · postings GB/DE/FR" };
    const legend = Object.values(bser).filter((s) => s.reading).map((s) => {
      const r = broles.find((x) => x.key === s.role) || { label: (hlLabel[s.role] || s.role).replace(/^🌍 Indeed: /, "") };
      const dash = s.stream === "hiringlab" ? "dotted" : s.stream === "trends" ? "solid" : "dashed";
      const pct = s.q_pct != null ? `${s.q_pct > 0 ? "+" : ""}${fmt.num(s.q_pct, 1)}%` : "—";
      return `<div style="padding:8px 12px;border-radius:8px;background:rgba(127,127,127,.08)">
        <div style="display:flex;align-items:center;gap:8px">
          <span style="width:18px;border-top:3px ${dash} ${roleColor[s.role]}"></span>
          <b style="font-size:.92em">${esc(r.label)}</b></div>
        <div class="muted" style="font-size:.78em;margin:2px 0 4px 26px">${srcName[s.stream] || s.stream}</div>
        <div style="margin-left:26px"><b class="${readCls(s.reading)}" style="font-size:1.15em">${pct}</b>
          <span class="${readCls(s.reading)}" style="font-size:.85em"> ${s.reading}</span>
          <span class="muted" style="font-size:.78em"> · 3 mo</span></div></div>`;
    }).join("");
    // table: ONE row per data point (month × stream), columns = roles
    btbl.innerHTML = (legend ? `<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:8px;margin-bottom:12px">${legend}</div>` : "") +
      `<div style="overflow-x:auto"><table><thead><tr><th>Month</th>` +
      `<th title="Where this row comes from. 📈 interest = Google Trends (who searches for the role title, index 0–100, not a posting count; has history). 🏢 open roles = real postings at watchlist companies (public Greenhouse/Lever/Ashby boards, a snapshot as of the collection day). 🎯 openings = JSearch (needs a key).">Stream ⓘ</th>` +
      broles.map((r) => `<th style="text-align:right" title="query: ${esc(r.query || r.label)}">${esc(r.label)}</th>`).join("") +
      `<th style="text-align:right">Your inbound</th><th>Source</th><th></th></tr></thead><tbody>` +
      [...bpts].reverse().map((p) => `<tr><td>${p.month}</td>
        <td class="muted" style="font-size:.85em">${streamIcon[p.stream] || "📈"} ${streamShort[p.stream] || esc(p.stream)}</td>` +
        broles.map((r) => `<td style="text-align:right">${p.counts[r.key] != null ? fmt.grouped(p.counts[r.key]) : "—"}</td>`).join("") +
        `<td style="text-align:right">${p.my_inbound}</td>
        <td class="muted" style="font-size:.82em" title="${p.geo ? "geo: " + esc(p.geo) + " · " : ""}${p.as_of ? "as of " + esc(p.as_of) : ""}">${esc(p.sources || "—")}</td>
        <td><button class="danger" data-bdel="${p.id}">✕</button></td></tr>`).join("") + "</tbody></table></div>";
    const wl = baro.watchlist_latest;
    if (wl && wl.note) btbl.insertAdjacentHTML("beforeend", `<details class="mt"><summary class="pill" style="font-size:.78em">🏢 open roles on the watchlist (${wl.month}, ${esc(wl.sources)})</summary>
      <pre class="muted mt" style="font-size:.8em;white-space:pre-wrap">${esc(wl.note)}</pre></details>`);
    btbl.querySelectorAll("[data-bdel]").forEach((b) =>
      b.addEventListener("click", async () => { await api.del("/api/market-barometer/" + b.dataset.bdel); route(); }));
    // chart: INDEX (base 100) — a line per role×stream (interest=solid, others=dashed, Hiring Lab=dotted) vs inbound (bars).
    // A single-point series is index 100 by definition and says nothing; the watchlist
    // numbers row above the chart covers the first snapshot.
    const lines = Object.values(bser).filter((s) => (s.index || []).filter((v) => v != null).length >= 2).map((s) => {
      const r = broles.find((x) => x.key === s.role) || { label: hlLabel[s.role] || s.role };
      const dashed = s.stream !== "trends";
      return { type: "line", label: s.stream === "hiringlab" ? r.label : `${r.label} · ${streamShort[s.stream] || s.stream}`,
        data: s.index || [], _raw: s.counts || [], borderColor: roleColor[s.role],
        backgroundColor: "transparent", borderDash: s.stream === "hiringlab" ? [2, 3] : dashed ? [6, 4] : [], yAxisID: "y",
        tension: 0.25, borderWidth: dashed ? 2 : 3, pointRadius: 3, spanGaps: true };
    });
    const wlPts = bpts.filter((p) => p.stream === "watchlist");
    const wlNow = wlPts[wlPts.length - 1], wlPrev = wlPts[wlPts.length - 2];
    if (wlNow) document.getElementById("baroChart").insertAdjacentHTML("beforebegin",
      `<div class="row mt" style="gap:18px;font-size:.92em">🏢 <b>Open roles at watchlist companies (${wlNow.month}):</b>` +
      broles.map((r) => {
        const v = wlNow.counts[r.key], pv = wlPrev && wlPrev.counts[r.key];
        const d = v != null && pv != null ? v - pv : null;
        return v == null ? "" : `<span><b style="color:${roleColor[r.key]}">${esc(r.label)}</b> ${fmt.grouped(v)}` +
          (d != null ? ` <span class="${d > 0 ? "pos" : d < 0 ? "neg" : "muted"}">(${d > 0 ? "+" : ""}${d} m/m)</span>` : "") + "</span>";
      }).join("") +
      (wlPrev ? "" : `<span class="muted">first snapshot; the chart line appears from the second one</span>`) + "</div>");
    trackChart(new Chart(document.getElementById("baroChart"), {
      data: {
        labels: months,
        datasets: [
          { type: "bar", label: "Your inbound", data: baro.inbound || [],
            backgroundColor: "rgba(255,209,102,0.55)", yAxisID: "y1", order: 9, barPercentage: 0.5, categoryPercentage: 0.6 },
          { type: "line", label: "inbound, 3-month average", data: baro.inbound_ma3 || [], borderColor: "rgba(255,209,102,0.9)",
            backgroundColor: "transparent", yAxisID: "y1", borderWidth: 1.5, pointRadius: 0, tension: 0.3, order: 8 },
          ...lines,
        ],
      },
      options: {
        interaction: { mode: "index", intersect: false },
        plugins: { tooltip: { callbacks: { label: (ctx) => {
          if (ctx.dataset.yAxisID === "y1") return `${ctx.dataset.label}: ${ctx.parsed.y}`;
          const raw = (ctx.dataset._raw || [])[ctx.dataIndex];
          return `${ctx.dataset.label}: ${ctx.parsed.y}` + (raw != null ? ` (${raw})` : "");
        } } } },
        scales: {
          y: { position: "left", beginAtZero: false, title: { display: true, text: "index (base 100)" } },
          y1: { position: "right", beginAtZero: true, suggestedMax: 6, grid: { drawOnChartArea: false },
            ticks: { stepSize: 1 }, title: { display: true, text: "Your inbound" } },
        },
      },
    }));
  } else {
    btbl.innerHTML = '<div class="empty">No barometer data yet. Interest (Google Trends), IT postings (Indeed Hiring Lab) and watchlist open roles are collected monthly by the app itself; real openings (JSearch) once you set <code>RAPIDAPI_JSEARCH_KEY</code>. External collectors can still <code>POST /api/market-barometer</code>. Set roles/geography/watchlist with ⚙️.</div>';
  }

  const cur = s ? s.current : null;
  const cmonths = baro.comp_months || months;
  // per-month package (raises, new grants); the old flat line only when the API doesn't send it
  const curLine = baro.comp_current && baro.comp_current.some((v) => v != null)
    ? baro.comp_current : (cur ? cmonths.map(() => cur) : null);
  trackChart(new Chart(document.getElementById("compChart"), {
    data: {
      labels: cmonths,
      datasets: [
        { type: "line", label: "Average range", data: baro.comp_avg || [], borderColor: CHART_COLORS[0],
          backgroundColor: "transparent", tension: 0.25, borderWidth: 3, pointRadius: 4, spanGaps: true },
        ...(curLine ? [{ type: "line", label: "Your package", data: curLine, borderColor: CHART_COLORS[3],
          backgroundColor: "transparent", borderDash: [6, 4], borderWidth: 2, pointRadius: 0, stepped: true }] : []),
      ],
    },
    options: {
      interaction: { mode: "index", intersect: false },
      plugins: { tooltip: { callbacks: { label: (ctx) => {
        if (ctx.datasetIndex !== 0) return `Your package: ${fmt.pln(ctx.parsed.y)}`;
        const n = (baro.comp_n || [])[ctx.dataIndex];
        return `Average: ${fmt.pln(ctx.parsed.y)} (of ${n} ${n === 1 ? "offer" : "offers"})`;
      } } } },
      scales: { y: { beginAtZero: true, ticks: { callback: (v) => fmt.grouped(v) } } },
    },
  }));

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
