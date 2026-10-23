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
        The metric to watch over time is <b>% ≥ current</b>: only when several in a row clearly beat the package has the market "outgrown" you.</div>
    </div>` : "";
  el.innerHTML = `
    <h2>💼 Career — offers, market, growth</h2>
    ${CAREER_TAB_INFO}
    <div style="margin-bottom:10px">
      <a href="#career" class="pill pos">🧭 Long-term career analysis →</a>
      <a href="#commits" class="pill pos" style="margin-left:6px">
        🧑‍💻 Committing${gh ? ` — today ${gh.today}, streak ${gh.streak}🔥` : ""} →</a>
      <a href="#ailearn" class="pill pos" style="margin-left:6px">🧠 AI learning →</a></div>
    ${statsBar}
    <div class="muted" style="margin:6px 0 12px;font-size:.88em">Reference point (auto): <b>${s ? fmt.pln(s.current) : "—"}</b>/mo —
      current gross total (base + bonus + RSU + cash vest, computed dynamically from the RSU stock price). Offer deltas and goal impact are computed against this.</div>
    <div class="card" id="baroCard">
      <h3 style="margin:0">📈 Market barometer</h3>
      <div class="muted" style="font-size:.85em;margin:6px 0 8px" id="baroDesc">Postings for your roles (index, first month = 100) and bars of your inbound.
        ${help(`<b>🧭 Job market</b> is one series per role: the sum of postings across all checked services. Each service is a month-end snapshot:
          🏢 watchlist (your roles in Europe at companies with a public ATS, ⚙️), 🗂️ No Fluff Jobs (role keyword, region from config), 💼 Just Join IT and 🚀 Rocket Jobs (your roles in Poland or remote, from the active-offer sitemaps).
          The index compares each service with its own previous snapshot, so adding a service grows the market without a jump; a month with no such comparison stays empty. The same posting can appear on two services.<br>
          <b>Market range</b>: the mean of the services' medians, each weighing the same: upper bounds of Just Join IT / Rocket Jobs offers that publish one, and 💰 levels.fyi (median total compensation /12, pasted by hand because its terms forbid automated access).<br>
          <b>Background</b>: 📈 Google Trends (who searches for the title, mostly candidates) and 🌍 Indeed Hiring Lab (IT postings in GB/DE/FR, the whole sector). They are not postings, so they are not in the sum.<br>
          <b>Bars</b>: your inbound. If inbound falls with the market, it's the market; if alone, it's your visibility.`, "how to read this")}</div>
      <details class="mt"><summary class="pill" style="font-size:.78em">⚙️ roles / geography</summary><div id="baroCfgBox" class="mt"></div></details>
      <div id="baroFilter" class="row mt" style="gap:12px;flex-wrap:wrap;font-size:.85em"></div>
      <canvas id="baroChart" height="95" class="mt"></canvas>
      <h4 style="margin:16px 0 0">💶 Ranges: your offers and the market (per month)</h4>
      <div class="muted" style="font-size:.85em;margin:4px 0 6px">Upper bounds from your inbound and the services' medians, against your package (dashed).
        ${help(`<b>Your offers</b>: the average upper bound of inbound offers that disclosed a range; offers without numbers don't drag it down, a month without any stays empty.<br>
          <b>Market range</b>: the mean of the services' medians (hover a point to see the parts), held until the next measurement.<br>
          <b>Your package</b>: base, bonus, shares and cash-vest that applied in each month, at today's price, stepping at raises and new grant starts (3 months ahead).`, "how to read this")}</div>
      <canvas id="compChart" height="60"></canvas>
      <div id="levelsBox" class="mt"></div>
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
        gi.new_months == null ? "" : `<tr><td>${esc(gi.goal)}</td>
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
  // hidden services drop out of the market definition server-side (total, index, ranges)
  const MARKET_ALL = ["watchlist", "boards", "jjit", "rocketjobs"];
  // everything is shown by default, background included; hide with the checkboxes
  let hidden = new Set();
  try { const h = localStorage.getItem("kist.baroHidden"); if (h) hidden = new Set(JSON.parse(h)); } catch (e) { /* no storage */ }
  const sel = [...MARKET_ALL, "levels"].filter((st) => !hidden.has(st)).join(",");
  const baro = await api.get("/api/market-barometer?sources=" + sel).catch(() => ({ points: [], roles: [], series: {}, geo: [] }));
  // Gap guard: the last FULL month must have a 'trends' point; if not, say so
  // (with the collector's last error) instead of silently drawing a shorter line.
  {
    const t = new Date(); const lf = new Date(t.getFullYear(), t.getMonth() - 1, 1);
    const lastFull = `${lf.getFullYear()}-${String(lf.getMonth() + 1).padStart(2, "0")}`;
    const trendMonths = (baro.points || []).filter((p) => p.stream === "trends").map((p) => p.month);
    if (!trendMonths.includes(lastFull)) {
      const sched = await api.get("/api/schedules").catch(() => null);
      const task = sched && sched.tasks.find((x) => x.id === "barometer_collect");
      const err = task && task.last_error ? ` Last attempt ${esc(task.last_error.at)}: <i>${esc(task.last_error.error)}</i>.` : "";
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
    <input id="baroGeo" value="${esc((baro.geo || []).join(", "))}" style="width:100%;margin-top:6px" placeholder="Remote, US, UK">
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
  roleColor.it_eu = CHART_COLORS[4];  // not [2]: warn is the inbound bar colour
  roleColor.it_broad = CHART_COLORS[5];
  const hlLabel = { it_eu: "Indeed: software (EU)", it_broad: "Indeed: IT (EU)" };
  const srcIcon = { watchlist: "🏢", boards: "🗂️", jjit: "💼", rocketjobs: "🚀", levels: "💰", trends: "📈", hiringlab: "🌍", openings: "🎯" };
  const srcName = { watchlist: "watchlist", boards: "No Fluff Jobs", jjit: "Just Join IT", rocketjobs: "Rocket Jobs",
                    levels: "levels.fyi", trends: "Trends", hiringlab: "Hiring Lab", openings: "JSearch" };
  const src = (st) => `${srcIcon[st] || ""} ${srcName[st] || st}`;
  const mkt = baro.market || {}, mpay = baro.market_pay || {}, levels = baro.levels || [];
  const mSrc = baro.market_sources || [];

  // filter: which services make up the market definition (posting counts and ranges) and which background is shown
  const box = (st) => `<label style="cursor:pointer"><input type="checkbox" data-src="${st}" ${hidden.has(st) ? "" : "checked"}> ${src(st)}</label>`;
  const fbox = document.getElementById("baroFilter");
  fbox.innerHTML = `<span class="muted">Market made of:</span> ${MARKET_ALL.map(box).join("")}
    <span class="muted" style="margin-left:10px">+ ranges:</span> ${box("levels")}
    <span class="muted" style="margin-left:10px">background:</span> ${["trends", "hiringlab"].map(box).join("")}`;
  fbox.querySelectorAll("[data-src]").forEach((cb) => cb.addEventListener("change", () => {
    cb.checked ? hidden.delete(cb.dataset.src) : hidden.add(cb.dataset.src);
    try { localStorage.setItem("kist.baroHidden", JSON.stringify([...hidden])); } catch (e) { /* no storage */ }
    route();
  }));
  const shown = (st) => !hidden.has(st);
  const lastVal = (arr) => { for (let i = (arr || []).length - 1; i >= 0; i--) if (arr[i] != null) return [i, arr[i]]; return [-1, null]; };
  const partsTxt = (parts, f = (v) => fmt.grouped(v)) => Object.entries(parts || {}).map(([st, v]) => `${srcIcon[st] || st} ${f(v)}`).join(" · ");

  if (bpts.length) {
    // now: the sum of each service's latest snapshot (snapshots are taken on different days of the month)
    const snaps = mSrc.map((st) => bpts.filter((p) => p.stream === st).pop()).filter(Boolean);
    if (snaps.length) document.getElementById("baroChart").insertAdjacentHTML("beforebegin",
      `<div class="mt" style="font-size:.92em">🧭 <b>Job market now:</b> ` +
      broles.map((r) => {
        const n = snaps.reduce((a, p) => a + (p.counts[r.key] || 0), 0);
        const [, pay] = lastVal((mpay[r.key] || {}).values);
        const parts = snaps.map((p) => `${srcName[p.stream]} ${fmt.grouped(p.counts[r.key] || 0)} (${p.as_of || p.month})`).join(", ");
        return `<span style="margin-right:16px" title="${esc(parts)}"><b style="color:${roleColor[r.key]}">${esc(r.label)}</b> ${fmt.grouped(n)}` +
          (pay ? ` <span class="muted">· range ~${fmt.pln(pay)}</span>` : "") + "</span>";
      }).join("") + "</div>");

    // tiles: market per role + background
    const tiles = [...Object.values(mkt).map((m) => ({ ...m, _label: (broles.find((x) => x.key === m.role) || {}).label, _sub: "job market: " + mSrc.map((st) => srcIcon[st]).join(" ") })),
      ...Object.values(bser).filter((s) => ["trends", "hiringlab"].includes(s.stream) && shown(s.stream)).map((s) => ({ ...s,
        _label: s.stream === "hiringlab" ? hlLabel[s.role] || s.role : (broles.find((x) => x.key === s.role) || {}).label, _sub: src(s.stream) }))]
      .filter((s) => s.reading).map((s) => {
        const dash = s.stream === "market" ? "solid" : s.stream === "hiringlab" ? "dotted" : "dashed";
        const pct = s.q_pct != null ? `${s.q_pct > 0 ? "+" : ""}${fmt.num(s.q_pct, 1)}%` : "—";
        return `<div style="padding:8px 12px;border-radius:8px;background:rgba(127,127,127,.08)">
          <div style="display:flex;align-items:center;gap:8px"><span style="width:18px;border-top:3px ${dash} ${roleColor[s.role]}"></span>
            <b style="font-size:.92em">${esc(s._label || s.role)}</b></div>
          <div class="muted" style="font-size:.78em;margin:2px 0 4px 26px">${esc(s._sub)}</div>
          <div style="margin-left:26px"><b class="${readCls(s.reading)}" style="font-size:1.15em">${pct}</b>
            <span class="${readCls(s.reading)}" style="font-size:.85em"> ${esc(s.reading)}</span>
            <span class="muted" style="font-size:.78em"> · 3 mo</span></div></div>`;
      }).join("");

    // raw snapshots per service: folded away, they are material to check, not the market reading
    const rows = bpts.filter((p) => shown(p.stream));
    btbl.innerHTML = (tiles ? `<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:8px;margin-bottom:12px">${tiles}</div>` : "") +
      `<details><summary class="pill" style="font-size:.78em">🔎 raw snapshots per service (${rows.length})</summary>
      <div style="overflow-x:auto" class="mt"><table><thead><tr><th>Month</th><th>Service</th>` +
      broles.map((r) => `<th style="text-align:right" title="query: ${esc(r.query || r.label)}. In the Google Trends row this is a 0–100 interest index, elsewhere a posting count.">${esc(r.label)}</th>`).join("") +
      `<th style="text-align:right">Your inbound</th><th>Source</th><th></th></tr></thead><tbody>` +
      rows.reverse().map((p) => `<tr><td>${esc(p.month)}</td><td class="muted" style="font-size:.85em">${src(p.stream)}</td>` +
        broles.map((r) => `<td style="text-align:right">${p.counts[r.key] != null ? fmt.grouped(p.counts[r.key]) : "—"}</td>`).join("") +
        `<td style="text-align:right">${esc(p.my_inbound)}</td>
        <td class="muted" style="font-size:.82em" title="${p.geo ? "geo: " + esc(p.geo) + " · " : ""}${p.as_of ? "as of " + esc(p.as_of) : ""}">${esc(p.sources || "—")}</td>
        <td><button class="danger" data-bdel="${p.id}">✕</button></td></tr>`).join("") + "</tbody></table></div>" +
      mSrc.map((st) => { const last = bpts.filter((p) => p.stream === st).pop();
        return last && last.note ? `<details class="mt"><summary class="pill" style="font-size:.78em">${src(st)}: offer list (${esc(last.month)})</summary>
          <pre class="muted mt" style="font-size:.8em;white-space:pre-wrap">${esc(last.note)}</pre></details>` : ""; }).join("") + "</details>";
    btbl.querySelectorAll("[data-bdel]").forEach((b) =>
      b.addEventListener("click", async () => { await api.del("/api/market-barometer/" + b.dataset.bdel); route(); }));

    // chart: job market (solid) against Trends (dashed) and Hiring Lab (dotted); a one-point series is 100 by definition, so from two
    const enough = (s) => (s.index || []).filter((v) => v != null).length >= 2;
    const lines = [
      ...Object.values(mkt).filter(enough).map((m) => ({ type: "line", label: (broles.find((x) => x.key === m.role) || {}).label,
        data: m.index, _raw: m.counts, _parts: m.parts, borderColor: roleColor[m.role], backgroundColor: "transparent",
        yAxisID: "y", tension: 0.25, borderWidth: 3, spanGaps: true, pointRadius: 3 })),
      ...Object.values(bser).filter((s) => ["trends", "hiringlab"].includes(s.stream) && shown(s.stream) && enough(s)).map((s) => ({ type: "line",
        label: s.stream === "hiringlab" ? `🌍 ${hlLabel[s.role] || s.role}` : `📈 ${(broles.find((x) => x.key === s.role) || {}).label}: Trends`,
        data: s.index, _raw: s.counts, borderColor: roleColor[s.role], backgroundColor: "transparent", yAxisID: "y",
        borderDash: s.stream === "hiringlab" ? [2, 3] : [6, 4], tension: 0.25, borderWidth: 1.5, spanGaps: true, pointRadius: 2 })),
    ];
    // without a market line the checkboxes only change the row above; without this note it looked like a broken filter
    if (!Object.values(mkt).some(enough)) document.getElementById("baroChart").insertAdjacentHTML("beforebegin",
      `<div class="muted" style="font-size:.82em;margin-top:4px">The market line appears on the chart after the first month in which a service has a previous snapshot to compare with (next collection: the 28th). Until then, checking services changes the total and range above, and the chart shows only the background.</div>`);
    trackChart(new Chart(document.getElementById("baroChart"), {
      data: {
        labels: months,
        datasets: [
          { type: "bar", label: "Your inbound", data: baro.inbound || [],
            backgroundColor: "rgba(255,209,102,0.55)", yAxisID: "y1", order: 9, barPercentage: 0.5, categoryPercentage: 0.6 },
          ...lines,
        ],
      },
      options: {
        interaction: { mode: "index", intersect: false },
        plugins: { tooltip: { callbacks: { label: (ctx) => {
          if (ctx.dataset.yAxisID === "y1") return `${ctx.dataset.label}: ${ctx.parsed.y}`;
          const raw = (ctx.dataset._raw || [])[ctx.dataIndex];
          const parts = (ctx.dataset._parts || [])[ctx.dataIndex];
          return `${ctx.dataset.label}: ${ctx.parsed.y}` + (raw != null ? ` (${parts ? fmt.grouped(raw) + " postings: " + partsTxt(parts) : raw})` : "");
        } } } },
        scales: {
          y: { position: "left", beginAtZero: false, title: { display: true, text: "index (base 100)" } },
          y1: { position: "right", beginAtZero: true, suggestedMax: 6, grid: { drawOnChartArea: false },
            ticks: { stepSize: 1 }, title: { display: true, text: "Your inbound" } },
        },
      },
    }));
  } else {
    btbl.innerHTML = '<div class="empty">No barometer data yet. The job-market services (watchlist, No Fluff Jobs, Just Join IT, Rocket Jobs), Google Trends and Indeed Hiring Lab are collected monthly by the app itself (Control Center → Data → Schedules). External collectors can still <code>POST /api/market-barometer</code>. Set roles/geography/watchlist with ⚙️.</div>';
  }

  const cur = s ? s.current : null;
  const cmonths = baro.comp_months || months;
  // per-month package (raises, new grants); the old flat line only when the API doesn't send it
  const curLine = baro.comp_current && baro.comp_current.some((v) => v != null)
    ? baro.comp_current : (cur ? cmonths.map(() => cur) : null);
  // The market range is a snapshot: it holds from one measurement to the next, so a stepped line
  // carries the last value to the end of the axis (like your package). A lone point blended into inbound.
  const carry = (arr) => { let last = null; return arr.map((v) => (v != null ? (last = v) : last)); };
  const payLines = broles.filter((r) => (mpay[r.key] || {}).values && mpay[r.key].values.some((v) => v != null)).map((r) => ({
    type: "line", label: `market: ${r.label}`, data: carry(mpay[r.key].values), _parts: carry(mpay[r.key].parts),
    _measured: mpay[r.key].values.map((v) => v != null), borderColor: roleColor[r.key], backgroundColor: roleColor[r.key],
    borderWidth: 3, stepped: true, pointStyle: "rectRot",
    pointRadius: mpay[r.key].values.map((v) => (v != null ? 6 : 0)) }));
  trackChart(new Chart(document.getElementById("compChart"), {
    data: {
      labels: cmonths,
      datasets: [
        { type: "line", label: "Your offers (inbound)", data: baro.comp_avg || [], borderColor: CHART_COLORS[2],
          backgroundColor: "transparent", tension: 0.25, borderWidth: 3, pointRadius: 4, spanGaps: true },
        ...(curLine ? [{ type: "line", label: "Your package", data: curLine, borderColor: CHART_COLORS[3],
          backgroundColor: "transparent", borderDash: [6, 4], borderWidth: 2, pointRadius: 0, stepped: true }] : []),
        ...payLines,
      ],
    },
    options: {
      interaction: { mode: "index", intersect: false },
      plugins: { tooltip: { callbacks: { label: (ctx) => {
        const parts = (ctx.dataset._parts || [])[ctx.dataIndex];
        if (parts) {
          const at = ctx.dataset._measured.lastIndexOf(true, ctx.dataIndex);
          return `${ctx.dataset.label}: ${fmt.pln(ctx.parsed.y)} (${partsTxt(parts, fmt.pln)}; measured ${cmonths[at]})`;
        }
        if (ctx.datasetIndex !== 0) return `${ctx.dataset.label}: ${fmt.pln(ctx.parsed.y)}`;
        const n = (baro.comp_n || [])[ctx.dataIndex];
        return `Your offers: ${fmt.pln(ctx.parsed.y)} (of ${n} ${n === 1 ? "offer" : "offers"})`;
      } } } },
      scales: { y: { beginAtZero: true, ticks: { callback: (v) => fmt.grouped(v) } } },
    },
  }));

  // levels.fyi: by hand only (its terms forbid automated access); the raw paste is kept in the data dir
  const lbox = document.getElementById("levelsBox");
  const pm = (v) => (v != null ? fmt.pln(Math.round(v / 12)) : "—");
  lbox.innerHTML = `<details><summary class="pill" style="font-size:.78em">💰 levels.fyi samples (${levels.length})</summary>
    <div class="muted mt" style="font-size:.82em">Open the levels.fyi page for your role and location with <code>.md</code> appended
      (<code>levels.fyi/t/&lt;job-family&gt;/locations/&lt;country&gt;.md</code>, see <a href="https://www.levels.fyi/t" target="_blank" rel="noopener">levels.fyi/t</a>)
      or a company page ending in <code>/locations/&lt;country&gt;.md</code>, select all, copy and paste below. Amounts must be in your base currency.
      The role says which market role the median feeds. Amounts are yearly total compensation (base, stock, bonus), divided by 12 on the chart. Data source: Levels.fyi (https://www.levels.fyi).</div>
    <div class="row mt"><input id="lvLabel" placeholder="label, e.g. Senior, Berlin" style="width:200px">
      <select id="lvRole" title="which market role this sample feeds">${broles.map((r) => `<option value="${esc(r.key)}">${esc(r.label)}</option>`).join("")}</select></div>
    <textarea id="lvText" rows="5" style="width:100%;margin-top:6px" placeholder="paste a levels.fyi summary"></textarea>
    <button class="primary mt" id="lvAdd" style="font-size:.85em">Import sample</button>
    ${levels.length ? `<div style="overflow-x:auto" class="mt"><table><thead><tr><th>Sample of</th><th>Label</th><th>Role</th><th style="text-align:right">p25</th><th style="text-align:right">median</th><th style="text-align:right">p75</th><th style="text-align:right">p90</th><th style="text-align:right">reports</th><th>Levels</th><th></th></tr></thead><tbody>` +
      [...levels].reverse().map((l) => `<tr><td>${esc(l.as_of)}</td>
        <td>${l.url ? `<a href="${esc(safeUrl(l.url))}" target="_blank" rel="noopener">${esc(l.label)}</a>` : esc(l.label)}</td>
        <td>${esc((broles.find((r) => r.key === l.role) || {}).label || l.role || "")}</td>
        <td style="text-align:right">${pm(l.p25)}</td><td style="text-align:right"><b>${pm(l.median)}</b></td>
        <td style="text-align:right">${pm(l.p75)}</td><td style="text-align:right">${pm(l.p90)}</td>
        <td style="text-align:right">${l.n != null ? esc(l.n) : "—"}</td>
        <td class="muted" style="font-size:.85em">${Object.entries(l.levels || {}).map(([k, v]) => `${esc(k)} ${pm(v)}`).join(", ") || "—"}</td>
        <td><button class="danger" data-lvdel="${l.id}">✕</button></td></tr>`).join("") +
      `</tbody></table><div class="muted" style="font-size:.78em">monthly amounts (TC/12)</div></div>` : ""}</details>`;
  document.getElementById("lvAdd").addEventListener("click", async () => {
    const text = document.getElementById("lvText").value;
    if (!text.trim()) return;
    try {
      await api.post("/api/market-barometer/levels", { text, label: document.getElementById("lvLabel").value.trim(), role: document.getElementById("lvRole").value });
      route();
    } catch (e) { alert("Import failed: " + (e.message || e)); }
  });
  lbox.querySelectorAll("[data-lvdel]").forEach((b) =>
    b.addEventListener("click", async () => { await api.del("/api/market-barometer/" + b.dataset.lvdel); route(); }));

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
