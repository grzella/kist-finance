async function renderMetrics(el) {
  el.innerHTML = '<div class="empty">Computing ratios…</div>';
  const [m, traj] = await Promise.all([api.get("/api/metrics"), api.get("/api/trajectory?months=12").catch(() => null)]);
  const cur = m.current, hist = m.history || [], pts = m.points || [];
  // one point per month (the last one): daily points showed mid-month states, e.g. shares
  // already sold while the loan they pay off is still open
  const monthly = Object.values(pts.reduce((acc, p) => { acc[p.date.slice(0, 7)] = p; return acc; }, {}));
  const icon = (l) => ({ green: "🟢", amber: "🟡", red: "🔴" }[l] || "⚪");
  const cls = (l) => l === "green" ? "pos" : l === "amber" ? "warn" : l === "red" ? "neg" : "muted";
  const col = (l) => l === "green" ? TOKENS.pos : l === "amber" ? TOKENS.warn : l === "red" ? TOKENS.neg : TOKENS.muted;
  const val = (i) => i.value == null ? "—" : `${fmt.num(i.value, 1)}${i.unit === "%" ? "%" : " " + i.unit}`;
  const keys = cur.items.map((i) => i.key);
  const label = Object.fromEntries(cur.items.map((i) => [i.key, i.label]));
  const bad = cur.items.filter((i) => i.light === "red");
  const amber = cur.items.filter((i) => i.light === "amber");

  el.innerHTML = `
    <h2>📐 Ratios — personal finance as a series</h2>
    <div class="muted" style="margin-bottom:12px">As of ${cur.as_of}. A wealth point is stored weekly (schedule in Control) and on
      "recompute derived"; this month's ratios are overwritten by the latest recompute, so history is one row per month.</div>
    <div class="card" style="border-left:4px solid ${bad.length ? TOKENS.neg : amber.length ? TOKENS.warn : TOKENS.pos}">
      <b>${bad.length ? `🔴 ${bad.length} off target: ${bad.map((i) => i.label).join(", ")}` : amber.length ? `🟡 ${amber.length} to improve: ${amber.map((i) => i.label).join(", ")}` : "🟢 All ratios on target"}</b>
      <div class="muted mt" style="font-size:.85em">Estimated net income ${fmt.pln(cur.facts.net_income_est)}/mo = surplus ${fmt.pln(cur.facts.surplus)} + fixed expenses ${fmt.pln(cur.facts.expenses)} + loan payments ${fmt.pln(cur.facts.debt_service)} · liquid ${fmt.pln(cur.facts.liquid)} · invested ${fmt.pln(cur.facts.invested)} · debt incl. reserve ${fmt.pln(cur.facts.debt_total)}</div>
    <div class="muted mt" style="font-size:.9em">Every card has a "what & how" fold-out with the numbers used in the calculation; the full legend is at the bottom of the page.</div>
    </div>
    <div class="grid cols-4 mt">
      ${cur.items.map((i) => `<div class="card kpi" style="margin:0;border-left:4px solid ${col(i.light)}" title="${esc(i.note)}">
        <div class="label">${icon(i.light)} ${i.label}</div>
        <div class="value ${cls(i.light)}" style="font-size:28px">${val(i)}</div>
        <div class="sub">target ${i.target}</div>
        ${i.explain ? help(`<b>What it means:</b> ${i.explain.what}<br><b>How it is computed:</b> ${i.explain.how}<br><b>Why it matters:</b> ${i.explain.why}`, "what & how") : ""}
      </div>`).join("")}
    </div>

    <div class="card mt">
      <div class="row" style="justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px">
        <h3 style="margin:0">Net-worth trajectory <span class="muted" style="font-weight:normal;font-size:.75em">(${monthly.length} months of history, last state of each month${traj ? "; dashed: 12-month forecast, median and p10–p90 band from Forecasts" : ""})</span></h3>
        <button id="mSnap">Store a point now</button>
      </div>
      ${monthly.length ? `<canvas id="nwPoints" height="80" class="mt"></canvas>` : `<div class="muted mt">No points yet — click "Store a point now".</div>`}
    </div>

    <div class="card mt">
      <h3>Ratio history (one row per month)</h3>
      ${hist.length ? `<div style="overflow-x:auto"><table style="font-size:.9em"><thead><tr><th>Month</th>${keys.map((k) => `<th style="text-align:right">${label[k]}</th>`).join("")}</tr></thead>
        <tbody>${hist.slice().reverse().map((h) => `<tr><td><b>${h.month}</b></td>${keys.map((k) => `<td style="text-align:right">${h[k] == null ? "—" : fmt.num(h[k], 1)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`
        : `<div class="muted">The first row appears after storing a point (button above) or at the next scheduled run.</div>`}
    </div>

    <details class="card mt"><summary><b>Definitions and thresholds</b></summary>
      <table class="mt" style="font-size:.9em"><tbody>${cur.items.map((i) => `<tr><td><b>${i.label}</b></td><td class="muted">${i.note}${i.explain ? `<div class="mt" style="font-size:.93em"><b>What it means:</b> ${i.explain.what}<br><b>How it is computed:</b> ${i.explain.how}<br><b>Why it matters:</b> ${i.explain.why}</div>` : ""}</td><td style="white-space:nowrap">target ${i.target}</td></tr>`).join("")}</tbody></table>
    </details>`;

  document.getElementById("mSnap").addEventListener("click", async () => {
    await api.post("/api/metrics/snapshot", {});
    renderMetrics(el);
  });

  if (monthly.length && document.getElementById("nwPoints")) {
    // the forecast starts at the last history month; months already in the history are skipped
    const lastM = monthly[monthly.length - 1].date.slice(0, 7);
    const fIdx = traj ? traj.labels.map((l, i) => [l, i]).filter(([l]) => l > lastM).map(([, i]) => i) : [];
    if (traj) ["p10", "p50", "p90"].forEach((k) => { traj[k] = fIdx.map((i) => traj[k][i]); });
    const fLabels = traj ? fIdx.map((i) => traj.labels[i]) : [];
    const hPad = monthly.slice(0, -1).map(() => null), last = monthly[monthly.length - 1].net_worth;
    trackChart(new Chart(document.getElementById("nwPoints"), {
      type: "line",
      data: {
        labels: [...monthly.map((p) => p.date.slice(0, 7)), ...fLabels],
        datasets: [
          ...(traj ? [
            { label: "forecast (median)", data: [...hPad, last, ...traj.p50], borderColor: TOKENS.pos, borderDash: [6, 4], backgroundColor: "transparent", borderWidth: 2, pointRadius: 0, tension: 0.2 },
            { label: "p90", data: [...hPad, last, ...traj.p90], borderColor: "transparent", backgroundColor: "rgba(127,127,127,.15)", pointRadius: 0, fill: "+1", tension: 0.2 },
            { label: "p10", data: [...hPad, last, ...traj.p10], borderColor: "transparent", backgroundColor: "transparent", pointRadius: 0, tension: 0.2 },
          ] : []),
          { label: "net worth", data: monthly.map((p) => p.net_worth), borderColor: TOKENS.pos, backgroundColor: "transparent", borderWidth: 3, pointRadius: 3, tension: 0.2 },
          { label: "liquid incl. investments", data: monthly.map((p) => p.liquid), borderColor: TOKENS.accent, backgroundColor: "transparent", borderWidth: 2, pointRadius: 3, tension: 0.2, spanGaps: true },
          { label: "debt", data: monthly.map((p) => p.debt), borderColor: TOKENS.neg, backgroundColor: "transparent", borderWidth: 1, borderDash: [5, 4], pointRadius: 0, tension: 0.2, spanGaps: true },
        ],
      },
      options: { interaction: { mode: "index", intersect: false },
        plugins: { legend: { labels: { filter: (i) => !/^p\d0$/.test(i.text) } },
          tooltip: { callbacks: { label: (c) => c.parsed.y == null ? null : `${c.dataset.label}: ${fmt.pln(c.parsed.y)}` } } },
        scales: { y: { ticks: { callback: (v) => (v / 1000000).toFixed(2) + " M" } } } },
    }));
  }
}
