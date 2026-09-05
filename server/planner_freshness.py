"""planner_freshness — Data freshness: update bar, reminders (auto + manual), recompute derived.

Split out of planner.py on 2026-09-05 (code moved 1:1; other modules are reached through `P`).
"""
import uuid
from datetime import date, datetime

import engine_bridge as eb
from planner_proxy import P

def refresh_derived():
    """After a manual data entry: recompute derived layers — this month's net
    worth and FIRE snapshots (replace, not ensure), a risk-radar snapshot and
    the RSU prediction tracker. Called after a freshness-strip save."""
    out = {}
    month = date.today().strftime("%Y-%m")
    try:
        eb._exec("delete from snapshots where type='net_worth' and date like ?",
                 (month + "%",))
        eb._exec("delete from fire_snapshots where month=?", (month,))
        P.ensure_monthly_snapshot()
        P.record_fire_snapshot()
        out["snapshots"] = "ok"
    except Exception as e:
        out["snapshots"] = str(e)[:80]
    try:
        import metrics as _metrics
        _metrics.record_point()
        _metrics.record_month()
        out["metrics"] = "ok"
    except Exception as e:
        out["metrics"] = str(e)[:80]
    try:
        import risk_radar
        risk_radar.snapshot()
        out["risk_radar"] = "ok"
    except Exception as e:
        out["risk_radar"] = str(e)[:80]
    try:
        import market as _mkt
        _mkt.rsu_accuracy()
        out["rsu_tracker"] = "ok"
    except Exception as e:
        out["rsu_tracker"] = str(e)[:80]
    return out


def freshness():
    """What needs a refresh NOW — derived from data timestamps, not from a
    calendar in the user's head. Feeds the dashboard strip, the guided
    update flow and the reminders view. Cadences: cash/investments monthly,
    real estate / car quarterly (valuations do not move monthly), income
    items event-driven (never nag), RSU after each vest month, debts a
    quarterly statement reconciliation (installments auto-post)."""
    from datetime import date as _date
    import market as _mkt
    today = _date.today()
    iso = today.isoformat()

    def age(d):
        try:
            y, m, dd = map(int, d[:10].split("-"))
            return (today - _date(y, m, dd)).days
        except Exception:
            return None

    due, ok = [], []

    def put(stale, **e):
        e["status"] = "due" if stale else "ok"
        (due if stale else ok).append(e)

    for it in P.wealth_summary()["items"]:
        n = (it.get("name") or "").lower()
        # event-driven: income (rent/salary are fixed) and deposits — they
        # change only when tenants/contracts change, not monthly
        if it.get("kind") == "income" or "kaucj" in n or "deposit" in n:
            continue
        if it.get("live"):
            continue  # valued from the quote — refreshes itself, never nags
        cls = P._alloc_class(it.get("name", "")) or ""
        need = 3 if cls in ("real_estate", "car") else 1
        last = it.get("latest_date")
        stale = last is None or P._months_between(last, iso) >= need
        put(stale, key="wealth:" + it["id"], label=it["name"], group="Wealth",
            last=last, days=age(last or ""), minutes=1,
            cadence="quarterly" if need == 3 else "monthly",
            value_hint=it.get("value_ccy", it.get("latest_value")),
            currency=it.get("currency"),
            action={"type": "wealth_value", "item_id": it["id"], "view": "wealth"})

    # RSU: a simple monthly "how many shares do you hold" — the app infers vest
    # inflows vs sales from the delta and the vest calendar (rsu_shares_history)
    try:
        import json as _json
        p = _mkt._rsu_path()
        g = _json.loads(p.read_text()) if p.exists() else {}
        log = _mkt.rsu_shares_history(g)
        last = (log[-1]["month"] + "-01") if log else None
        stale = last is None or P._months_between(last, iso) >= 1
        put(stale, key="rsu_shares", label="RSU: shares held right now",
            group="RSU", last=last, days=age(last or ""), minutes=1,
            cadence="monthly", value_hint=g.get("shares_held"), always_show=True,
            action={"type": "rsu_shares", "view": "rsu"})
    except Exception:
        pass

    try:
        for g in eb._rows("select id, name, current_amount, "
                          "substr(updated_at,1,10) d from goals "
                          "where coalesce(status,'') != 'done'"):
            last = g.get("d")
            stale = last is None or P._months_between(last, iso) >= 1
            put(stale, key="goal:" + g["id"], label=f"Goal: {g['name']} — saved so far",
                group="Goals", last=last, days=age(last or ""), minutes=1,
                cadence="monthly", value_hint=g.get("current_amount"),
                action={"type": "goal_amount", "goal_id": g["id"], "view": "goals"})
    except Exception:
        pass

    try:
        r = eb._rows("select max(substr(created_at,1,10)) d from biz_entries")
        last = r[0]["d"] if r and r[0]["d"] else None
        stale = last is None or P._months_between(last, iso) >= 1
        put(stale, key="business", label="Business: this month's income/costs",
            group="Business", last=last, days=age(last or ""), minutes=2,
            cadence="monthly", action={"type": "biz_month", "view": "business"})
    except Exception:
        pass

    try:
        for d in P.list_debts()["debts"]:
            hist = [h for h in (d.get("history") or [])
                    if "auto" not in (h.get("note") or "")]
            last = (hist[-1]["month"] + "-01") if hist else None
            stale = last is None or P._months_between(last, iso) >= 1
            put(stale, key="debt:" + d["id"],
                label=f"{d['name']}: current balance per the bank",
                group="Debts", last=last, days=age(last or ""), minutes=1,
                cadence="monthly", value_hint=d.get("balance"),
                action={"type": "debt_balance", "debt_id": d["id"], "view": "debts"})
    except Exception:
        pass

    due.sort(key=lambda e: -(e.get("days") if e.get("days") is not None else 10**6))
    return {"month": iso[:7], "due": due, "ok": ok, "complete": not due,
            "total_minutes": sum(e.get("minutes", 1) for e in due)}


# ---------- reminders ----------

def _auto_reminders():
    """Derive upcoming events from live data (not stored)."""
    from datetime import date
    import market as _mkt
    today = date.today()
    out = []

    def days_to(ds):
        try:
            y, m, d = map(int, ds.split("-"))
            return (date(y, m, d) - today).days
        except Exception:
            return None

    # next vest + bonus
    try:
        rsu = _mkt.get_rsu()
        vm = sorted(rsu.get("vest_months") or [2, 5, 8, 11])
        nvm = next((x for x in vm if x > today.month), None)
        vy = today.year if nvm else today.year + 1
        nvm = nvm or vm[0]
        vdate = f"{vy:04d}-{nvm:02d}-15"
        val = rsu.get("next_vest_value_pln")
        out.append({"title": f"RSU vest ({rsu.get('shares_next_vest')} shares"
                    + (f", ≈{P._zl(val)}" if val else "") + ") — review your sell/hold plan",
                    "due_date": vdate, "auto": True, "kind": "RSU"})
    except Exception:
        pass
    # recommendations resolved without a recorded outcome (>7 days) → review
    try:
        pend = [p for p in P.rec_review()["pending"]
                if (days_to(p["resolved"]) or 0) <= -7]
        if pend:
            out.append({"title": f"Recommendation review: {len(pend)} resolved without a recorded outcome "
                                 f"(Recommendations → outcome: done / rejected / obsolete)",
                        "due_date": today.isoformat(), "auto": True, "kind": "review"})
    except Exception:
        pass
    # annual bonus — only when configured (amount + month come from settings)
    try:
        _bonus = P._num(P.get_setting("annual_bonus_net"))
        _bm = int(P._num(P.get_setting("cf_bonus_month")) or 0)
        if _bonus and 1 <= _bm <= 12:
            by = today.year if today.month <= _bm else today.year + 1
            out.append({"title": f"Annual bonus (~{P._zl(_bonus)}) — plan its use",
                        "due_date": f"{by:04d}-{_bm:02d}-28", "auto": True, "kind": "Income"})
    except Exception:
        pass
    # kredyt hipoteczny fixed-rate end → aneks
    try:
        for d in P.list_debts()["debts"]:
            fu = d.get("fixed_until")
            if fu and days_to(fu) is not None:
                out.append({"title": f"{d['name']}: fixed rate ends — time for an annex/refinancing",
                            "due_date": fu, "auto": True, "kind": "Loan"})
    except Exception:
        pass
    # cushion: cash < 3 months of FULL costs (monthly_expenses setting + live
    # debt service) — the threshold shrinks by itself as debts get paid off
    try:
        expenses = float(P.get_setting("monthly_expenses") or 0)
        if expenses > 0:
            w = P.wealth_summary()
            cash = sum((it.get("latest_value") or 0) for it in w["items"]
                       if P._alloc_class(it.get("name", "")) == "cash"
                       and (it.get("latest_value") or 0) > 0)
            service = sum((d.get("monthly_cost_total") or 0)
                          for d in P.list_debts()["debts"])
            burn = expenses + service
            months = cash / burn if burn else None
            if months is not None and months < 3:
                out.append({"title": f"Cushion: {months:.1f} months of full costs "
                            f"({P._zl(cash)} / {P._zl(burn)}/mo) — below the 3-month target",
                            "due_date": today.isoformat(), "auto": True,
                            "kind": "Cushion"})
    except Exception:
        pass
    # monthly data refresh (freshness engine) — one aggregate entry
    try:
        fr = freshness()
        if fr["due"]:
            out.append({"title": f"Data refresh: {len(fr['due'])} items "
                        f"(~{fr['total_minutes']} min) — see the dashboard strip",
                        "due_date": today.isoformat(), "auto": True, "kind": "Data"})
    except Exception:
        pass
    # RSU stock near/above target
    try:
        _tk = (_mkt.get_rsu() or {}).get("ticker") or "AAPL"
        an = _mkt.analytics(_tk)
        tgt = an.get("analyst_target"); last = an.get("last_close")
        if tgt and last and last >= tgt * 0.95:
            out.append({"title": f"{_tk} ${last} near/above the ${tgt} target — consider selling held shares",
                        "due_date": today.isoformat(), "auto": True, "kind": "Market"})
    except Exception:
        pass
    # weekly: security review (also runs in CI / on schedule — this is a visibility nudge)
    from datetime import timedelta as _td
    nextweek = (today + _td(days=7 - today.weekday() if today.weekday() < 7 else 7)).isoformat()
    out.append({"title": "🔒 Run the security review (Control Center button — also automated)",
                "due_date": nextweek, "auto": True, "kind": "Security"})
    # next month's 1st, reused for monthly tasks
    by, bm = (today.year, today.month + 1) if today.month < 12 else (today.year + 1, 1)
    # monthly market barometer update (Claude task)
    out.append({"title": "📈 Update the market barometer (the roles you track) — you or any AI assistant",
                "due_date": f"{by:04d}-{bm:02d}-05", "auto": True, "kind": "Barometer"})
    # monthly market brief refresh (Claude task) — Markets tab
    out.append({"title": "🧭 Refresh the market brief — authored by you or any AI assistant",
                "due_date": f"{by:04d}-{bm:02d}-05", "auto": True, "kind": "Market"})
    # monthly: verify backups exist (snapshots are automated via Schedules)
    out.append({"title": "💾 Verify backups (Control Center — snapshots run on a schedule)",
                "due_date": f"{by:04d}-{bm:02d}-01", "auto": True, "kind": "Backup"})
    # quarterly review
    q_month = ((today.month - 1) // 3 + 1) * 3 + 1
    qy = today.year + (1 if q_month > 12 else 0)
    q_month = q_month if q_month <= 12 else q_month - 12
    out.append({"title": "Quarterly portfolio review (allocation, concentration, rebalancing)",
                "due_date": f"{qy:04d}-{q_month:02d}-01", "auto": True, "kind": "Review"})

    for r in out:
        r["days"] = days_to(r["due_date"])
    return out


def list_reminders():
    manual = eb._rows("select * from reminders where done=0 order by "
                      "coalesce(due_date,'9999') asc, created_at asc")
    from datetime import date
    today = date.today()
    for r in manual:
        r["auto"] = False
        try:
            y, m, d = map(int, (r["due_date"] or "9999-12-31").split("-"))
            r["days"] = (date(y, m, d) - today).days
        except Exception:
            r["days"] = None
    combined = _auto_reminders() + manual
    combined.sort(key=lambda r: (r.get("days") if r.get("days") is not None else 99999))
    return {"reminders": combined,
            "done_count": (eb._rows("select count(*) c from reminders where done=1") or [{"c": 0}])[0]["c"]}


def add_reminder(data):
    rid = str(uuid.uuid4())
    eb._exec("insert into reminders (id, title, due_date, note, created_at) values (?,?,?,?,?)",
             (rid, data["title"], data.get("due_date"), data.get("note", ""), P._now()))
    P._audit("reminder", rid, "add", data)
    return rid


def update_reminder(rid, data):
    if "done" in data:
        eb._exec("update reminders set done=? where id=?", (1 if data["done"] else 0, rid))
    P._audit("reminder", rid, "update", data)


def delete_reminder(rid):
    P._audit("reminder", rid, "delete")
    eb._exec("delete from reminders where id=?", (rid,))
