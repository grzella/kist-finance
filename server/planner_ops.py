"""planner_ops — Ops: health / Control Center, data inventory, git, GitHub activity, secrets scan.

Split out of planner.py on 2026-09-05 (code moved 1:1; other modules are reached through `P`).
"""
from datetime import date, datetime

import engine_bridge as eb
from planner_proxy import P

# ---------- control center / health ----------

def _days_since(dstr):
    from datetime import date
    try:
        parts = dstr[:10].split("-")
        d = date(int(parts[0]), int(parts[1]), int(parts[2]))
        return (date.today() - d).days
    except Exception:
        return None


def health():
    import os, subprocess
    from datetime import datetime
    from pathlib import Path
    import market as _mkt

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    repo = _mkt._finance_dir().parent
    tasks = []

    def task(name, freq, last, status, detail):
        tasks.append({"name": name, "freq": freq, "last": last,
                      "status": status, "detail": detail})

    # 1. kursy rynkowe (n8n → Supabase, dziennie 22:35)
    try:
        sync = _mkt.last_sync()
        _htk = (_mkt.get_rsu() or {}).get("ticker") or "AAPL"
        hist = _mkt.prices(_htk, days=5)
        lastd = hist[-1]["date"] if hist else None
        d = _days_since(lastd) if lastd else None
        st = "ok" if (d is not None and d <= 4) else "warn"
        task("Market rates (stocks/FX)", "daily ~22:35",
             (sync or lastd or "—"), st,
             f"last quote {lastd} ({d} days ago)" if lastd else "no data")
    except Exception as e:
        task("Market rates (stocks/FX)", "daily ~22:35", "—", "error", str(e)[:80])

    # 2. RSU prediction tracking (daily when RSU opens)
    try:
        r = eb._rows("select max(made_on) m, count(*) c from rsu_predictions")
        lastm = r[0]["m"] if r else None
        d = _days_since(lastm) if lastm else None
        st = "ok" if (d is not None and d <= 2) else ("warn" if lastm else "info")
        task("RSU prediction tracking", "daily", lastm or "—", st,
             f"{r[0]['c']} forecasts; last one {d} days ago" if lastm else "none yet")
    except Exception as e:
        task("RSU prediction tracking", "daily", "—", "error", str(e)[:80])

    # 2b. self-learning forecast journal (short-term bands, whole watchlist)
    try:
        ss = _mkt.forecast_selfscore()
        h21 = next((h for h in ss["horizons"] if h["days"] == 21), None)
        st = "ok" if (h21 and h21["coverage_pct"] and 70 <= h21["coverage_pct"] <= 92) else ("info" if ss["total_scored"] < 100 else "warn")
        task("Forecast self-learning (bands)", "daily after sync",
             f"{ss['total_scored']} scored", st,
             f"1M coverage: {h21['coverage_pct']}% (target ~80%)" if h21 else "the journal is building up")
    except Exception as e:
        task("Forecast self-learning (bands)", "daily after sync", "—", "warn", str(e)[:60])

    # 2c. optional local LLM — online + exposure
    try:
        import os as _os, llm_local
        st = llm_local.status()
        if not st.get("online"):
            task("Local LLM (optional)", "on demand", "—", "info",
                 "off — zero attack surface; to enable: " + st.get("hint", ""))
        else:
            protected = bool(_os.environ.get("LOCAL_LLM_KEY"))
            task("Local LLM (optional)", "when running",
                 st.get("model", "?"), "ok" if protected else "warn",
                 f"{st.get('url')} — {'key-protected' if protected else 'no API key (run llama-server --api-key, set LOCAL_LLM_KEY)'}")
    except Exception as e:
        task("Local LLM (optional)", "on demand", "—", "info", str(e)[:60])

    # 3. marketing (ads-analyst, tygodniowo pon ~07:00)
    try:
        rep = _mkt._supabase_get("analysis_reports?select=week_end&order=week_end.desc&limit=1", service=True)
        we = rep[0]["week_end"] if rep else None
        d = _days_since(we) if we else None
        st = "ok" if (d is not None and d <= 9) else ("warn" if we else "info")
        task("Business marketing (ads reports)", "weekly Mon ~07:00", we or "—", st,
             f"last report for the week ending {we} ({d} days ago)" if we else "none/offline")
    except Exception as e:
        task("Business marketing (ads reports)", "weekly Mon ~07:00", "—", "warn",
             "offline/no Supabase")

    # 4. job-market barometer (Claude, monthly)
    try:
        r = eb._rows("select max(month) m, count(*) c from market_barometer")
        lastm = (r[0]["m"] + "-15") if r and r[0]["m"] else None
        d = _days_since(lastm) if lastm else None
        st = "ok" if (d is not None and d <= 40) else ("warn" if lastm else "info")
        task("Market barometer (EM/Head openings)", "monthly (Claude)",
             (r[0]["m"] if r and r[0]["m"] else "—"), st,
             f"{r[0]['c']} points; last {r[0]['m']}" if r and r[0]["m"] else "none — to fill in")
    except Exception as e:
        task("Market barometer (EM/Head openings)", "monthly (Claude)", "—", "error", str(e)[:80])

    # 5. data backup (monthly)
    try:
        bdir = repo / "backups"
        enc = sorted(bdir.glob("finance-*.db.enc"), key=lambda p: p.stat().st_mtime) if bdir.exists() else []
        if enc:
            mt = datetime.fromtimestamp(enc[-1].stat().st_mtime)
            d = (datetime.now() - mt).days
            st = "ok" if d <= 35 else "warn"
            task("Data backup (encrypted)", "monthly", mt.strftime("%Y-%m-%d %H:%M"), st,
                 f"{len(enc)} copies; last one {d} days ago")
        else:
            task("Data backup (encrypted)", "monthly", "—", "error", "no copies — run backup.sh")
    except Exception as e:
        task("Data backup (encrypted)", "monthly", "—", "error", str(e)[:80])

    # 6. sensitive-data audit in git
    try:
        out = subprocess.run(["git", "-C", str(repo), "ls-files"],
                             capture_output=True, text=True, timeout=10)
        tracked = out.stdout.splitlines()
        bad = [f for f in tracked if any(s in f.lower() for s in
               ("private/", ".finance/", "doc-raw/", "compensation", "finanse/", "psyche/", ".env"))
               and not f.endswith(".env.example")]
        if bad:
            task("Audit: sensitive data in git", "on every push / monthly",
                 now, "error", f"🚨 tracked sensitive files: {', '.join(bad[:3])}")
        else:
            task("Audit: sensitive data in git", "on every push / monthly",
                 now, "ok", f"clean — {len(tracked)} tracked files, zero sensitive")
    except Exception as e:
        task("Audit: sensitive data in git", "on every push", "—", "warn", "git unavailable: " + str(e)[:60])

    # 7. database — integrity
    try:
        chk = eb._rows("pragma integrity_check")
        okc = chk and (chk[0].get("integrity_check") == "ok" or list(chk[0].values())[0] == "ok")
        size = (repo / ".finance" / "finance.db").stat().st_size // 1024 if (repo / ".finance" / "finance.db").exists() else 0
        task("Database (SQLite)", "continuous", now, "ok" if okc else "error",
             f"integrity OK · {size} KB")
    except Exception as e:
        task("Database (SQLite)", "continuous", now, "warn", str(e)[:80])

    # 8. synchronizacja z GitHub
    try:
        gs = git_status(do_fetch=True)
        detail = gs["summary"]
        if gs.get("remote", "").startswith("http"):
            detail += f" · last commit: {gs.get('last_commit_date', '')}"
        task("GitHub sync", "after code changes (Claude)",
             gs.get("last_commit_date") or "—", gs["status"], detail)
    except Exception as e:
        task("GitHub sync", "after code changes", "—", "warn", str(e)[:80])

    # 9b. repo security scan (weekly)
    try:
        sc = security_scan()
        task("Repo security scan (secrets)", "weekly", now, sc["status"], sc["summary"])
    except Exception as e:
        task("Repo security scan (secrets)", "weekly", "—", "warn", str(e)[:70])

    # 9. commit activity (goal: daily)
    try:
        ga = github_activity(days=30)
        if not ga.get("configured"):
            st = "info"; detail = ("not set up — connect it: run `gh auth login` or set "
                                   "`commit_repos` in Data → Settings to track your own activity")
        elif ga["today"] > 0:
            st = "ok"; detail = f"today {ga['today']} commits · streak {ga['streak']} days 🔥 (record {ga['best_streak']})"
        elif ga["streak"] > 0:
            st = "warn"; detail = f"still 0 today · streak {ga['streak']} days — a small commit will keep it alive"
        else:
            st = "warn"; detail = f"0 today, streak broken · {ga['active_days']}/30 days active recently"
        task("Commit activity (GitHub)", "daily (goal)", now, st, detail)
    except Exception as e:
        task("Commit activity (GitHub)", "daily", "—", "warn", str(e)[:60])

    errors = sum(1 for t in tasks if t["status"] == "error")
    warns = sum(1 for t in tasks if t["status"] == "warn")
    return {"tasks": tasks, "checked_at": now,
            "summary": {"ok": sum(1 for t in tasks if t["status"] == "ok"),
                        "warn": warns, "error": errors, "total": len(tasks)}}


# ---------- inwentarz danych: co auto / claude / recznie ----------

def data_inventory():
    """Mapa wszystkich zrodel danych w aplikacji: tryb (auto/derived/claude/
    manual), zrodlo, czestotliwosc, ostatnia aktualizacja, liczba rekordow i
    szacowany reczny wysilek/mies. Cel: zminimalizowac reczne wprowadzanie."""
    from datetime import datetime
    import json as _json

    def one(q):
        try:
            r = eb._rows(q)
            return r[0] if r else {}
        except Exception:
            return {}

    def cnt_last(table, tcol=None):
        sel = "count(*) c" + (f", max({tcol}) m" if tcol else "")
        r = one(f"select {sel} from {table}")
        return r.get("c", 0), (r.get("m") if tcol else None)

    def setting_asof(key, field="as_of"):
        raw = P.get_setting(key)
        if not raw:
            return None, False
        try:
            return _json.loads(raw).get(field), True
        except Exception:
            return None, True

    acc_c, acc_last = cnt_last("accounts", "updated_at")
    wv_c, wv_last = cnt_last("wealth_values", "created_at")
    wi_c, _ = cnt_last("wealth_items")
    debt_c, debt_last = cnt_last("debts", "updated_at")
    dv_c, dv_last = cnt_last("debt_values", "created_at")
    goal_c, goal_last = cnt_last("goals", "updated_at")
    tx_c, tx_last = cnt_last("transactions", "created_at")
    off_c, off_last = cnt_last("job_offers", "created_at")
    biz_c, biz_last = cnt_last("biz_entries", "created_at")
    px_c, px_last = cnt_last("market_prices_cache", "date")
    bar_c, bar_last = cnt_last("market_barometer", "month")
    pred_c, pred_last = cnt_last("rsu_predictions", "made_on")
    snap_c, snap_last = cnt_last("snapshots", "date")
    fire_c, fire_last = cnt_last("fire_snapshots", "month")
    ins_c, _ = cnt_last("insurance_policies")
    brief_asof, brief_has = setting_asof("analysis_market_brief")
    vest_asof, vest_has = setting_asof("rsu_vest_analysis", "vest_month")
    prop_asof, prop_has = setting_asof("analysis_property")
    try:
        import market as _mkt
        sync = _mkt.last_sync()
    except Exception:
        sync = None

    def item(name, mode, source, freq, last, count=None, minutes=0, note="", suggest=""):
        return {"name": name, "mode": mode, "source": source, "freq": freq,
                "last": last or "\u2014", "count": count, "minutes": minutes,
                "note": note, "suggest": suggest}

    groups = [
        {"key": "auto", "title": "\U0001F7E2 Fully automatic \u2014 zero effort",
         "note": "Pulled by n8n/Supabase/git or computed by the app. You enter nothing.",
         "items": [
            item("Stock + FX rates", "auto", "n8n \u2192 Supabase \u2192 cache",
                 "daily", sync or px_last, px_c,
                 note=f"{px_c} quotes in cache; latest {px_last}"),
            item("Marketing/ads reports", "auto", "n8n \u2192 Supabase (analysis_reports)",
                 "weekly", None, note="read from Supabase; offline when there is no connection"),
            item("Commit activity (GitHub)", "auto", "local repos (git log)",
                 "on demand / daily", None, note="computed from git, you enter nothing"),
            item("Sensitive-data audit", "auto", "git ls-files + secret scan",
                 "on push / weekly", None, note="makes sure .finance/.env never lands in git"),
         ]},
        {"key": "derived", "title": "\U0001F535 Derived from other data \u2014 zero effort",
         "note": "The app computes these itself from what you already have. Also nothing to enter.",
         "items": [
            item("Wealth snapshot (monthly)", "derived", "auto from wealth items",
                 "1x/mo (auto)", snap_last, snap_c, note="one net point per month for the wealth chart"),
            item("FIRE snapshot (plan vs actual)", "derived", "auto from liquidity",
                 "1x/mo (auto)", fire_last, fire_c, note="feeds the work-optional projection"),
            item("Automatic reminders", "derived", "from data (vests, fixed-rate end...)",
                 "continuous", None, note="derived from data \u2014 not stored manually"),
            item("Prediction-accuracy tracking", "derived", "auto when RSU opens",
                 "daily", pred_last, pred_c, note=f"{pred_c} forecasts for the backtest"),
            item("Loan balance (model)", "derived", "installment \u2212 interest each month",
                 "monthly (auto)", debt_last, debt_c,
                 note="the balance drops by itself; a per-bank correction only occasionally (below)"),
         ]},
        {"key": "claude", "title": "🟣 AI research notes (optional) — monthly/on demand",
         "note": "Deep-dive snapshots authored by you or any AI assistant (Claude Code, the built-in local AI, or plain notes). The app only reads them — empty is fine.",
         "items": [
            item("Market brief", "claude", "app_settings: analysis_market_brief",
                 "monthly", brief_asof, note="moves + macro context + per-position recommendations" if brief_has else "none \u2014 to generate"),
            item("Job-market barometer", "claude", "market_barometer",
                 "monthly", bar_last, bar_c, note=f"{bar_c} role-demand points"),
            item("Vest analysis (RSU)", "claude", "app_settings: rsu_vest_analysis",
                 "per vest (~quarterly)", vest_asof, note="earnings, guidance, targets" if vest_has else "none"),
            item("Goal analysis (e.g. property)", "claude", "app_settings: analysis_property",
                 "on demand / rarely", prop_asof, note="deep analysis" if prop_has else "none"),
         ]},
        {"key": "manual_reg", "title": "\U0001F7E1 Manual \u2014 regular (what we want to reduce)",
         "note": "The only things you actually enter each month. Goal: bring this down to the minimum.",
         "items": [
            item("Portfolio value (broker/ETF)", "manual", "you (portfolio setting + wealth items)",
                 "monthly / on trade", wv_last, wi_c, minutes=3,
                 note="today you enter the VALUE by hand",
                 suggest="store only the NUMBER of units; the value computes itself from cached rates \u2014 update only on purchase"),
            item("Goal progress (saved)", "manual", "you (Goals tab)",
                 "monthly", goal_last, goal_c, minutes=1,
                 note="how much is saved",
                 suggest="derive it from liquid assets (accounts \u2212 buffer) instead of typing it in"),
            item("Business revenue/costs", "manual", "you (Business tab)",
                 "monthly", biz_last, biz_c, minutes=2,
                 note="business result",
                 suggest="if sales data lives in Supabase \u2014 auto-pull revenue from the pipeline"),
            item("Loan-balance correction per bank", "manual", "you (Loans tab)",
                 "occasionally (the model computes itself)", dv_last, dv_c, minutes=1,
                 note="only when you want to match the statement to the penny",
                 suggest="import 1 number from the bank statement (PSD2) instead of a manual correction"),
         ]},
        {"key": "manual_rare", "title": "\u26AA Manual \u2014 rare / event-driven (setup)",
         "note": "Entered once or only when something actually changes \u2014 no monthly burden.",
         "items": [
            item("Job offers", "manual", "you (Offers tab)",
                 "as they arrive (event-driven)", off_last, off_c, minutes=0,
                 note="not recurring \u2014 you add one when a recruiter writes"),
            item("Fixed costs / budget plan", "manual", "Fixed Expenses tab",
                 "rarely (when it changes)", None, minutes=0, note="installments, rent, subscriptions \u2014 stable"),
            item("Tax data", "manual", "settings: tax_*",
                 "~yearly", None, minutes=0, note="changes once in a while"),
            item("RSU configuration (ticker, vests, shares)", "manual", "market_meta / RSU",
                 "rarely", None, minutes=0, note="updated on grant/vest"),
            item("Watchlist + price targets", "manual", "you (Market tab)",
                 "occasionally", None, minutes=0, note="you add a ticker/target when you want to track it"),
            item("Insurance", "manual", "insurance_policies",
                 "rarely", None, ins_c, minutes=0, note="policies \u2014 change on renewal"),
         ]},
    ]

    manual_reg = next(g for g in groups if g["key"] == "manual_reg")["items"]
    minutes = sum(i["minutes"] for g in groups for i in g["items"])
    counts = {g["key"]: len(g["items"]) for g in groups}

    roadmap = [
        {"title": "Portfolio: store the number of units, not the value",
         "impact": "high", "effort": "low",
         "saves": "~3 min/mo + always current",
         "how": "You already have rates in the cache. Store only how many units you hold; value = units x last price. "
                "An entry only on purchase, not every month."},
        {"title": "Goal progress derived from liquidity",
         "impact": "medium", "effort": "low",
         "saves": "~1 min/mo + consistency",
         "how": "Compute the saved amount from (liquid accounts \u2212 safety buffer) instead of a separate field. "
                "One source of truth instead of two."},
        {"title": "Business revenue auto-pulled from the pipeline",
         "impact": "medium", "effort": "medium",
         "saves": "~2 min/mo",
         "how": "If sales data lives in Supabase, auto-fill revenue instead of typing the result by hand."},
        {"title": "Alert on stale data \u2705 done",
         "impact": "low", "effort": "done",
         "saves": "peace of mind \u2014 you catch a broken sync yourself",
         "how": "A ready n8n \u2192 Telegram workflow in integrations/n8n/ (daily freshness check of "
                "market_prices in Supabase, alert when > threshold days). Import into n8n per the README; extensible."},
    ]

    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "groups": groups,
        "roadmap": roadmap,
        "summary": {
            "auto": counts.get("auto", 0) + counts.get("derived", 0),
            "claude": counts.get("claude", 0),
            "manual_regular": len(manual_reg),
            "manual_rare": counts.get("manual_rare", 0),
            "manual_minutes": minutes,
            "manual_touchpoints": sum(1 for i in manual_reg if i["minutes"] > 0),
        },
    }


# ---------- git / GitHub sync status ----------

def git_status(do_fetch=True):
    import subprocess
    from pathlib import Path
    import market as _mkt
    repo = str(_mkt._finance_dir().parent)

    def g(args, timeout=10):
        try:
            r = subprocess.run(["git", "-C", repo] + args, capture_output=True,
                               text=True, timeout=timeout)
            return r.stdout.strip()
        except Exception:
            return ""

    out = {"repo": repo}
    out["branch"] = g(["rev-parse", "--abbrev-ref", "HEAD"]) or "?"
    out["remote"] = g(["remote", "get-url", "origin"]) or "no remote"
    fetched = False
    if do_fetch and out["remote"] != "no remote":
        try:
            import subprocess as _sp
            _sp.run(["git", "-C", repo, "fetch", "--quiet", "origin"],
                    capture_output=True, timeout=20)
            fetched = True
        except Exception:
            fetched = False
    out["fetched"] = fetched
    porcelain = g(["status", "--porcelain"])
    out["uncommitted"] = len([l for l in porcelain.splitlines() if l.strip()])
    ahead = g(["rev-list", "--count", "origin/main..HEAD"])
    behind = g(["rev-list", "--count", "HEAD..origin/main"])
    out["ahead"] = int(ahead) if ahead.isdigit() else 0
    out["behind"] = int(behind) if behind.isdigit() else 0
    out["last_commit"] = g(["log", "-1", "--format=%h %s"])
    out["last_commit_date"] = g(["log", "-1", "--format=%cd", "--date=format:%Y-%m-%d %H:%M"])
    out["total_commits"] = g(["rev-list", "--count", "HEAD"]) or "?"
    unpushed = g(["log", "origin/main..HEAD", "--format=%h %s"])
    out["unpushed_list"] = [l for l in unpushed.splitlines() if l.strip()][:15]
    uncommitted_files = [l[3:] for l in porcelain.splitlines() if l.strip()][:15]
    out["uncommitted_files"] = uncommitted_files
    out["synced"] = (out["uncommitted"] == 0 and out["ahead"] == 0 and out["behind"] == 0)
    if out["synced"]:
        out["status"] = "ok"; out["summary"] = "In sync with GitHub ✓"
    elif out["behind"] > 0:
        out["status"] = "warn"; out["summary"] = f"GitHub has {out['behind']} commits you do not have locally"
    elif out["uncommitted"] or out["ahead"]:
        parts = []
        if out["uncommitted"]:
            parts.append(f"{out['uncommitted']} uncommitted changes")
        if out["ahead"]:
            parts.append(f"{out['ahead']} commits ahead of GitHub")
        out["status"] = "warn"; out["summary"] = "To push: " + ", ".join(parts)
    else:
        out["status"] = "ok"; out["summary"] = "In sync"
    return out


# ---------- GitHub / commit activity ----------

def _github_contribution_calendar(days=90):
    """Full GitHub-wide activity (the profile's green graph: commits, PRs,
    issues, reviews — across all repos, including merged contributions to other
    people's projects) via the GraphQL contributionsCollection. Invoked through
    the `gh` CLI (logged in locally); cached 6h in app_settings. Returns None
    when gh is unavailable/offline — the tracker then stays local-only."""
    import json as _json
    import subprocess
    from datetime import datetime, timedelta, timezone
    cache_raw = P.get_setting("gh_activity_cache")
    if cache_raw:
        try:
            cache = _json.loads(cache_raw)
            age_h = (datetime.now() - datetime.fromisoformat(cache["at"])).total_seconds() / 3600
            if age_h < 6 and cache.get("days") == days:
                return cache
        except Exception:
            pass
    now = datetime.now(timezone.utc)
    frm = (now - timedelta(days=days)).strftime("%Y-%m-%dT00:00:00Z")
    to = now.strftime("%Y-%m-%dT23:59:59Z")
    query = (
        'query { viewer { login contributionsCollection(from: "%s", to: "%s") {'
        ' totalCommitContributions totalPullRequestContributions'
        ' totalIssueContributions totalPullRequestReviewContributions'
        ' contributionCalendar { weeks { contributionDays { date contributionCount } } }'
        ' pullRequestContributions(first: 100, orderBy: {direction: DESC}) { nodes { occurredAt'
        ' pullRequest { title url state merged mergedAt repository { nameWithOwner } } } }'
        ' } } }' % (frm, to))
    try:
        out = subprocess.run(["gh", "api", "graphql", "-f", f"query={query}"],
                             capture_output=True, text=True, timeout=15)
        viewer = _json.loads(out.stdout)["data"]["viewer"]
        data = viewer["contributionsCollection"]
    except Exception:
        return None
    counts = {}
    for week in data["contributionCalendar"]["weeks"]:
        for d in week["contributionDays"]:
            counts[d["date"]] = d["contributionCount"]
    # PRs separately: per day (chart) + list (repo, title, state) for the view
    prs_by_day, pr_list = {}, []
    for n in (data.get("pullRequestContributions") or {}).get("nodes") or []:
        pr = n.get("pullRequest") or {}
        day = (n.get("occurredAt") or "")[:10]
        if day:
            prs_by_day[day] = prs_by_day.get(day, 0) + 1
        pr_list.append({"date": day, "title": pr.get("title"), "url": pr.get("url"),
                        "state": "merged" if pr.get("merged") else (pr.get("state") or "").lower(),
                        "merged_at": (pr.get("mergedAt") or "")[:10], "repo": (pr.get("repository") or {}).get("nameWithOwner")})
    cache = {"at": datetime.now().isoformat(timespec="seconds"), "days": days,
             "prs_by_day": prs_by_day, "pr_list": pr_list,
             "counts": counts,
             "totals": {"login": viewer.get("login"),
                        "commits": data["totalCommitContributions"],
                        "prs": data["totalPullRequestContributions"],
                        "issues": data["totalIssueContributions"],
                        "reviews": data["totalPullRequestReviewContributions"]}}
    try:
        P.set_settings({"gh_activity_cache": _json.dumps(cache)})
    except Exception:
        pass
    return cache


def _commit_streak(counts, today):
    """Consecutive days with ≥1 commit ending today. GitHub-style grace: while
    you haven't committed today yet, the streak is still alive and counts from
    yesterday — a missing commit today doesn't zero yesterday's streak (only an
    empty yesterday+today breaks it). `counts` = {'YYYY-MM-DD': n}, `today` = date."""
    from datetime import timedelta
    streak = 0
    i = 0 if counts.get(today.isoformat(), 0) > 0 else 1
    while counts.get((today - timedelta(days=i)).isoformat(), 0) > 0:
        streak += 1
        i += 1
    return streak


def github_activity(days=90):
    """Daily commit activity across local git repos. Configure which repos and
    author to count via settings `commit_repos` (comma-separated absolute paths)
    and `commit_author` (git --author filter; blank = all authors).
    When the `gh` CLI is logged in, the local counts are merged with the full
    GitHub contribution calendar (max per day)."""
    import os
    import subprocess
    from datetime import date, timedelta
    from pathlib import Path
    repos = set()
    configured = (P.get_setting("commit_repos") or os.environ.get("COMMIT_REPOS", "")).strip()
    if configured:
        for p in configured.split(","):
            if (Path(p.strip()) / ".git").exists():
                repos.add(p.strip())
    # NOTE: no home-directory auto-scan. On a fresh clone that would count
    # commits from whatever repos happen to live in ~/ (and every author) —
    # i.e. someone else's numbers. The tracker stays empty until the user
    # points it at their repos (`commit_repos`) or logs in with `gh`.
    author = (P.get_setting("commit_author") or os.environ.get("COMMIT_AUTHOR", "")).strip()

    counts = {}
    for repo in repos:
        try:
            cmd = ["git", "-C", repo, "log", f"--since={days} days ago",
                   "--format=%cd", "--date=short"]
            if author:
                cmd.insert(4, f"--author={author}")
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=12).stdout
            for line in out.splitlines():
                dd = line.strip()
                if dd:
                    counts[dd] = counts.get(dd, 0) + 1
        except Exception:
            pass

    # full GitHub-wide activity (commits+PRs+issues+reviews, incl. merged
    # contributions to other repos). Per day take max(local, GitHub): local
    # catches unpushed work, GitHub catches everything server-side.
    gh_cal = _github_contribution_calendar(days)
    if gh_cal:
        for dd, n in gh_cal["counts"].items():
            counts[dd] = max(counts.get(dd, 0), n)

    today = date.today()
    # nothing wired up yet: no repos configured and no gh account connected.
    # Return an explicit "not configured" state so the UI shows setup steps
    # instead of a wall of zeros (or, worse, someone else's numbers).
    if not configured and not gh_cal:
        return {
            "configured": False, "days": days, "repos": 0,
            "series": [{"date": (today - timedelta(days=i)).isoformat(), "count": 0}
                       for i in range(days - 1, -1, -1)],
            "today": 0, "week": 0, "total": 0, "active_days": 0,
            "streak": 0, "best_streak": 0, "avg_per_active": 0, "active_pct": 0,
            "github": {"connected": False},
        }
    prs_by_day = (gh_cal or {}).get("prs_by_day") or {}
    series = []
    for i in range(days - 1, -1, -1):
        dd = (today - timedelta(days=i)).isoformat()
        series.append({"date": dd, "count": counts.get(dd, 0), "prs": prs_by_day.get(dd, 0)})
    total = sum(c["count"] for c in series)
    active_days = sum(1 for c in series if c["count"] > 0)
    streak = _commit_streak(counts, today)
    # longest streak in the window
    best = cur = 0
    for c in series:
        if c["count"] > 0:
            cur += 1; best = max(best, cur)
        else:
            cur = 0
    week = sum(counts.get((today - timedelta(days=i)).isoformat(), 0) for i in range(7))
    return {
        "configured": True,
        "series": series, "days": days, "repos": len(repos),
        "today": counts.get(today.isoformat(), 0),
        "week": week, "total": total, "active_days": active_days,
        "streak": streak, "best_streak": best,
        "avg_per_active": round(total / active_days, 1) if active_days else 0,
        "active_pct": round(100 * active_days / days),
        "github": ({"connected": True, **gh_cal["totals"], "pr_list": gh_cal.get("pr_list") or []} if gh_cal
                   else {"connected": False}),
    }


# ---------- security scan (sekrety w repo) ----------

def security_scan():
    import subprocess, re
    from pathlib import Path
    from datetime import datetime
    import market as _mkt
    repo = str(_mkt._finance_dir().parent)
    findings = []

    def g(args, timeout=20):
        try:
            return subprocess.run(["git", "-C", repo] + args, capture_output=True, text=True, timeout=timeout)
        except Exception:
            return None

    ls = g(["ls-files"])
    tracked = ls.stdout.splitlines() if ls else []

    # 1. tracked secret files
    bad = [f for f in tracked if re.search(r"(^|/)\.env($|\.)(?!example)|\.pem$|\.key$|id_rsa|\.p12$|secret", f, re.I)]
    if bad:
        findings.append({"sev": "high", "what": "Tracked secret files", "detail": ", ".join(bad[:5])})

    # 2. sensitive paths not git-ignored
    for p in ("private", ".finance", "doc-raw", "backups"):
        ci = g(["check-ignore", p + "/"])
        leaked = [f for f in tracked if f.startswith(p + "/")]
        if leaked:
            findings.append({"sev": "high", "what": f"Tracked files in {p}/", "detail": ", ".join(leaked[:3])})

    # 3. leak-check: real .env values in tracked files
    env = Path(repo) / ".env"
    checked = 0
    if env.exists():
        for line in env.read_text().splitlines():
            line = line.strip()
            if "=" not in line or line.startswith("#"):
                continue
            k, _, v = line.partition("=")
            v = v.strip().strip('"').strip("'")
            if len(v) < 12:  # skip short ones (PORT etc.)
                continue
            checked += 1
            r = g(["grep", "-F", v, "--", "."])
            if r and r.stdout.strip():
                findings.append({"sev": "critical", "what": f"LEAK of the {k.strip()} value", "detail": "a value from .env found in a tracked file!"})

    # 4. secret patterns (excluding base64/blogs). Literals split so the scanner doesn't match itself.
    pat = "|".join([
        "eyJ" + "hbGciOiJ",                       # JWT header
        r"https://[a-z0-9]{15,}\.supabase\.co",   # realny URL Supabase
        r"/webhook/[a-f0-9-]{36}",                # webhook n8n
        "sk" + r"-[A-Za-z0-9]{20,}",              # OpenAI-style
        "ghp" + r"_[A-Za-z0-9]{20,}",             # GitHub token
        "AKI" + r"A[0-9A-Z]{16}",                 # AWS
        "-----" + "BEGIN (RSA |OPENSSH |EC )?PRIVATE",
    ])
    r = g(["grep", "-nIE", pat,
           "--", ".", ":(exclude)posts/*", ":(exclude)*.html", ":(exclude)doc-raw/*"])
    if r and r.stdout.strip():
        for ln in r.stdout.strip().splitlines()[:5]:
            findings.append({"sev": "high", "what": "Secret pattern", "detail": ln[:100]})

    crit = sum(1 for f in findings if f["sev"] == "critical")
    high = sum(1 for f in findings if f["sev"] == "high")
    status = "error" if (crit or high) else "ok"
    return {"status": status, "findings": findings, "tracked_files": len(tracked),
            "secrets_checked": checked, "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "summary": ("🚨 " + str(crit + high) + " findings — check!") if findings else f"Clean — {len(tracked)} files, {checked} .env values verified, zero leaks"}
