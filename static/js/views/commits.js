async function renderCommits(el) {
  const [gh, c] = await Promise.all([
    api.get("/api/github-activity").catch(() => null),
    api.get("/api/analysis/contributions").catch(() => ({}))]);

  const diffCls = (d) => /łatwe/.test(d) ? "pos" : /trudne/.test(d) ? "neg" : "";

  el.innerHTML = `
    <div class="muted" style="margin-bottom:4px"><a href="#offers" style="text-decoration:none">← Career</a></div>
    <h2>🧑‍💻 Committing — coding activity and open source</h2>

    ${gh ? `<div class="card" style="border-left:4px solid #3ecf8e">
      <div class="muted" style="font-size:.85em;margin-bottom:8px">Your commits from local repos (${gh.repos}) over ${gh.days} days.
        Goal: coding activity every day — builds an AI-native, "I code with AI" profile. Status also in Control → Automation.</div>
      <div class="grid cols-4">
        <div class="card kpi"><div class="label">Today</div><div class="value ${gh.today > 0 ? "pos" : ""}">${gh.today}</div><div class="sub">commits</div></div>
        <div class="card kpi"><div class="label">Streak</div><div class="value ${gh.streak >= 3 ? "pos" : ""}">${gh.streak} 🔥</div><div class="sub">days in a row · record ${gh.best_streak}</div></div>
        <div class="card kpi"><div class="label">This week</div><div class="value">${gh.week}</div><div class="sub">commits</div></div>
        <div class="card kpi"><div class="label">Active days</div><div class="value">${gh.active_pct}%</div><div class="sub">${gh.active_days}/${gh.days} days · ${gh.total} commits</div></div>
      </div>
      <canvas id="ghChart" height="60" class="mt"></canvas>
      <div class="muted mt" style="font-size:.82em">${gh.today > 0 ? "✅ You already committed today — the streak lives." : "⚠️ Still 0 commits today — a small commit will keep the streak alive."}
        Avg ${gh.avg_per_active} commits/active day. Even a tiny daily commit keeps the streak and the green square on GitHub.</div>
    </div>` : ""}

    ${c && c.goal ? `
    <div class="card mt" style="border-left:4px solid #4c8dff">
      <h3 style="margin-top:0">🎯 Where to contribute (open source for the business)</h3>
      <div style="font-size:1.0em"><b>${c.goal}</b></div>
      <div class="muted mt" style="font-size:.85em">${c.method}</div>
      <div style="overflow-x:auto" class="mt"><table>
        <thead><tr><th>Repo</th><th>Activity</th><th>Language</th><th>Difficulty</th><th>Why / first PR</th></tr></thead>
        <tbody>${c.repos.map((r) => `<tr>
          <td><b><a href="${r.url}" target="_blank">${r.name} ↗</a></b></td>
          <td class="${/bardzo/.test(r.activity) ? "pos" : ""}" style="font-size:.85em">${r.activity}</td>
          <td class="muted" style="font-size:.85em">${r.lang}</td>
          <td><span class="badge ${diffCls(r.difficulty)}">${r.difficulty}</span></td>
          <td style="font-size:.88em">${r.why}</td>
        </tr>`).join("")}</tbody>
      </table></div>
    </div>

    <div class="grid cols-2 mt">
      <div class="card">
        <h3>🏆 Badges to earn</h3>
        <table><tbody>${c.badges.map((b) => `<tr>
          <td><b>${b.name}</b><div class="muted" style="font-size:.82em">${b.how}</div></td>
          <td style="text-align:right"><span class="badge ${/instant|łatwe/.test(b.status) ? "pos" : ""}">${b.status}</span></td>
        </tr>`).join("")}</tbody></table>
        <div class="muted mt" style="font-size:.82em">You already have: Pull Shark, Pair Extraordinaire, Quickdraw, YOLO.</div>
      </div>
      <div class="card">
        <h3>✅ Playbook (first PR)</h3>
        <ol style="padding-left:18px">${c.playbook.map((p) => `<li class="mt" style="font-size:.9em">${p}</li>`).join("")}</ol>
      </div>
    </div>` : `<div class="card mt muted">No contribution research — ask Claude to "refresh the contribution research".</div>`}`;

  if (gh && document.getElementById("ghChart")) {
    const last = gh.series.slice(-60);
    trackChart(new Chart(document.getElementById("ghChart"), {
      type: "bar",
      data: {
        labels: last.map((d) => d.date.slice(5)),
        datasets: [{ label: "commits/day", data: last.map((d) => d.count),
          backgroundColor: last.map((d) => d.count > 0 ? "#3ecf8e" : "#2c3040") }],
      },
      options: {
        plugins: { legend: { display: false },
          tooltip: { callbacks: { title: (i) => i[0].label, label: (x) => `${x.parsed.y} commits` } } },
        scales: { x: { ticks: { maxTicksLimit: 12 } }, y: { ticks: { stepSize: 2 } } },
      },
    }));
  }
}
