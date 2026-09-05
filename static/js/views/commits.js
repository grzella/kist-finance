async function renderCommits(el) {
  const [gh, c] = await Promise.all([
    api.get("/api/github-activity").catch(() => null),
    api.get("/api/analysis/contributions").catch(() => ({}))]);

  // grouping: done/merged/closed at the bottom; fresh candidates on top
  const GROUP_LABEL = { now: "Do now — verified (dedup, open issue)", ai: "AI / dev-tooling — new direction", reserve: "Reserve / watch", done: "Done, merged or closed" };
  const grp = (r) => r.group || (/✅|MERGED|zmergowan|merged|zamknięt|closed/i.test(r.status || "") ? "done" : "now");
  const GROUP_ORDER = ["now", "ai", "reserve", "done"];
  const reposSorted = c && c.repos ? [...c.repos].sort((a, b) => GROUP_ORDER.indexOf(grp(a)) - GROUP_ORDER.indexOf(grp(b))) : [];
  const diffCls = (d) => /easy/i.test(d) ? "pos" : /hard/i.test(d) ? "neg" : "";

  el.innerHTML = `
    <div class="muted" style="margin-bottom:4px"><a href="#offers" style="text-decoration:none">← Career</a></div>
    <h2>🧑‍💻 Committing — coding activity and open source</h2>

    ${gh && !gh.configured ? `<div class="card" style="border-left:4px solid var(--accent)">
      <h3 style="margin-top:0">📊 Track your coding activity</h3>
      <div class="muted" style="font-size:.9em">Not set up yet — so nothing is counted. This tab turns daily commits into a streak and an "I code with AI" profile, once you point it at <b>your</b> data (two independent options, use either or both):</div>
      <ol style="padding-left:18px;font-size:.92em">
        <li class="mt"><b>Connect GitHub</b> — run <code>gh auth login</code> with your account. Pulls your full contribution calendar (commits + PRs + issues + reviews, all repos).</li>
        <li class="mt"><b>Point at local repos</b> — in <a href="#data">Data → Settings</a> set <code>commit_repos</code> (comma-separated absolute paths) and optionally <code>commit_author</code> (a git <code>--author</code> filter). Catches unpushed work too.</li>
      </ol>
      <div class="muted" style="font-size:.82em">Deliberately empty until then: a fresh clone must never show commits scraped from whatever repos happen to sit in your home folder.</div>
    </div>` : ""}

    ${gh && gh.configured ? `<div class="card" style="border-left:4px solid var(--pos)">
      <div class="muted" style="font-size:.85em;margin-bottom:8px">
        ${gh.github && gh.github.connected
          ? `<b class="pos">Full GitHub activity</b> (commits + PRs + issues + reviews, all repos — including merged contributions to other projects) merged with local repos (${gh.repos}) over ${gh.days} days. In window: ${gh.github.prs} PRs · ${gh.github.issues} issues · ${gh.github.reviews} reviews.`
          : `Your commits from local repos (${gh.repos}) over ${gh.days} days (GitHub offline — local only).`}
        <div style="font-size:.82em;margin:4px 0;padding:6px 10px;background:var(--accent)18;border-radius:6px">⚠️ Whose data is this? Activity found on <b>this machine</b>: local git repos scanned here${gh.github && gh.github.connected && gh.github.login ? ` + the gh CLI account (<a href="https://github.com/${gh.github.login}" target="_blank">@${gh.github.login}</a>)` : ""}. If you cloned this app, these may be someone else's numbers — switch to yours: run <code>gh auth login</code> with your account and set <code>commit_repos</code> / <code>commit_author</code> in the Data tab → Settings.</div>
        Goal: coding activity every day — builds an AI-native, "I code with AI" profile. Status also in Control → Automation.</div>
      <div class="grid cols-4">
        <div class="card kpi"><div class="label">Today</div><div class="value ${gh.today > 0 ? "pos" : ""}">${gh.today}</div><div class="sub">contributions</div></div>
        <div class="card kpi"><div class="label">Streak</div><div class="value ${gh.streak >= 3 ? "pos" : ""}">${gh.streak} 🔥</div><div class="sub">days in a row · record ${gh.best_streak}</div></div>
        <div class="card kpi"><div class="label">This week</div><div class="value">${gh.week}</div><div class="sub">contributions</div></div>
        <div class="card kpi"><div class="label">Active days</div><div class="value">${gh.active_pct}%</div><div class="sub">${gh.active_days}/${gh.days} days · ${gh.total} contributions</div></div>
      </div>
      <canvas id="ghChart" height="60" class="mt"></canvas>
      ${gh.github && gh.github.pr_list && gh.github.pr_list.length ? `<details class="mt"><summary class="muted" style="cursor:pointer">🟣 Pull requests in the window (${gh.github.pr_list.length}) — purple triangles above the bars</summary>
        <table class="mt"><tbody>${gh.github.pr_list.slice(0, 30).map((p) => `<tr><td class="muted" style="width:100px">${p.date}</td>
          <td><span class="badge ${p.state === "merged" ? "pos" : p.state === "open" ? "" : "neg"}">${p.state}</span></td>
          <td class="muted" style="font-size:.9em">${p.repo}</td><td><a href="${p.url}" target="_blank">${p.title}</a></td></tr>`).join("")}</tbody></table></details>` : ""}
      <div class="muted mt" style="font-size:.82em">${gh.today > 0 ? "✅ You already committed today — the streak lives." : "⚠️ Still 0 commits today — a small commit will keep the streak alive."}
        Avg ${gh.avg_per_active} commits/active day. Even a tiny daily commit keeps the streak and the green square on GitHub.</div>
    </div>` : ""}

    ${c && c.goal ? `
    <div class="card mt" style="border-left:4px solid var(--accent)">
      <h3 style="margin-top:0">🎯 Where to contribute (open source for the business)</h3>
      <div style="font-size:1.0em"><b>${c.goal}</b></div>
      <div class="muted mt" style="font-size:.85em">${c.method}</div>
      <div class="mt" style="display:grid;gap:10px">${reposSorted.map((r, i) => `
        ${(i === 0 || grp(reposSorted[i - 1]) !== grp(r)) ? `<div style="margin-top:${i === 0 ? 0 : 10}px"><span class="badge ${grp(r) === "done" ? "pos" : grp(r) === "now" ? "warn" : ""}">${GROUP_LABEL[grp(r)]}</span></div>` : ""}
        <div style="display:grid;grid-template-columns:minmax(260px,1.1fr) minmax(0,1.6fr);gap:14px;padding:12px 14px;border-radius:10px;background:var(--panel2);border:1px solid var(--hairline)">
          <div style="min-width:0">
            <div><b><a href="${r.url}" target="_blank">${r.name} ↗</a></b></div>
            ${r.tag ? `<div class="muted" style="font-size:.85em;margin-top:2px">${r.tag}</div>` : ""}
            <div class="row" style="gap:6px;margin-top:8px;flex-wrap:wrap">
              <span class="badge ${/bardzo|very/.test(r.activity) ? "pos" : ""}" title="Activity">${r.activity}</span>
              <span class="badge" title="Language">${r.lang}</span>
              <span class="badge ${diffCls(r.difficulty)}" title="Difficulty">${r.difficulty}</span>
            </div>
            <div class="${/✅/.test(r.status || "") ? "pos" : /✗/.test(r.status || "") ? "neg" : "muted"}" style="font-size:.88em;margin-top:8px" title="Your status">${r.status || "—"}</div>
          </div>
          <div style="font-size:.93em">${r.why}</div>
        </div>`).join("")}</div>
    </div>

    <div class="grid cols-2 mt">
      <div class="card">
        <h3>🏆 Badges to earn</h3>
        <table><tbody>${c.badges.map((b) => `<tr>
          <td><b>${b.name}</b><div class="muted" style="font-size:.82em">${b.how}</div></td>
          <td style="text-align:right"><span class="badge ${/instant|easy/i.test(b.status) ? "pos" : ""}">${b.status}</span></td>
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
    const maxY = Math.max(1, ...last.map((d) => d.count));
    trackChart(new Chart(document.getElementById("ghChart"), {
      type: "bar",
      data: {
        labels: last.map((d) => d.date.slice(5)),
        datasets: [
          { label: "contributions/day", data: last.map((d) => d.count),
            backgroundColor: last.map((d) => d.count >= 10 ? "#1f9d6a" : d.count >= 4 ? TOKENS.pos : d.count > 0 ? "#8fe3c2" : TOKENS.empty), order: 2 },
          { label: "pull requests", type: "line", showLine: false, data: last.map((d) => d.prs ? d.count + Math.max(2, maxY * 0.08) : null),
            pointStyle: "triangle", pointRadius: 8, pointHoverRadius: 10, backgroundColor: TOKENS.violet, borderColor: TOKENS.violet, order: 0,
            prCounts: last.map((d) => d.prs || 0) },
        ],
      },
      options: {
        plugins: { legend: { display: true },
          tooltip: { callbacks: { title: (i) => i[0].label, label: (x) => x.dataset.prCounts ? `${x.dataset.label}: ${x.dataset.prCounts[x.dataIndex]}` : `${x.dataset.label}: ${x.parsed.y}` } } },
        scales: { x: { ticks: { maxTicksLimit: 12 } }, y: { ticks: { stepSize: 2 } } },
      },
      options: {
        plugins: { legend: { display: false },
          tooltip: { callbacks: { title: (i) => i[0].label, label: (x) => `${x.parsed.y} commits` } } },
        scales: { x: { ticks: { maxTicksLimit: 12 } }, y: { ticks: { stepSize: 2 } } },
      },
    }));
  }
}
