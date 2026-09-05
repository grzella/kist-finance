"""planner_career — Career: job offers (stats vs current), job-market barometer.

Split out of planner.py on 2026-09-05 (code moved 1:1; other modules are reached through `P`).
"""
import uuid
from datetime import date

import engine_bridge as eb
from planner_proxy import P

# ---------- job offers ----------

def _current_total_monthly():
    """Auto: current monthly total = base/12 + (bonus + RSU)/12. Dynamic (RSU tracks the company price)."""
    base = (P._num(P.get_setting("tax_salary_gross_annual")) or 120000) / 12.0
    extras = P._annual_extras().get("monthly_equivalent", 0) or 0
    return round(base + extras)


def list_offers():
    offers = eb._rows("select * from job_offers order by received_at desc, created_at desc")
    cfg = P.settings()
    goals = P.list_goals()
    current = _current_total_monthly()
    cfg["current_total_monthly"] = current
    savings = cfg.get("monthly_savings")
    for o in offers:
        o["delta_monthly"] = (o["total_monthly"] - current) if current else None
        o["goal_impact"] = []
        if current and savings and savings > 0:
            for g in goals:
                if g["status"] != "active":
                    continue
                remaining = (g["target_amount"] or 0) - (g["current_amount"] or 0)
                if remaining <= 0:
                    continue
                base_pace = g["monthly_contribution"] or savings
                base_months = remaining / base_pace
                # assumption: comp delta flows fully into savings for this goal
                new_pace = base_pace + (o["total_monthly"] - current)
                new_months = remaining / new_pace if new_pace > 0 else None
                o["goal_impact"].append({
                    "goal": g["name"],
                    "base_months": round(base_months, 1),
                    "new_months": round(new_months, 1) if new_months else None,
                    "months_saved": round(base_months - new_months, 1) if new_months else None,
                })
    roles = {"a": P.get_setting("career_role_a") or "IC roles (Senior / Staff Engineer)",
             "b": P.get_setting("career_role_b") or "Leadership roles (Tech Lead / EM / Head)"}
    return {"offers": offers, "settings": cfg, "stats": _offers_stats(offers, current),
            "roles": roles}


def _offers_stats(offers, current):
    """Market-signal stats for inbound offers (all unsolicited)."""
    if not offers:
        return None
    # timespan in months from earliest received_at to today
    dates = sorted(o["received_at"] for o in offers if o.get("received_at"))
    span_months = 1.0
    if dates:
        try:
            y0, m0 = int(dates[0][:4]), int(dates[0][5:7])
            today = date.today()
            span_months = max(1.0, (today.year - y0) * 12 + (today.month - m0) + 1)
        except (ValueError, IndexError):
            pass
    tier1 = [o for o in offers if o.get("tier") == 1]
    quantified = [o for o in offers if o.get("total_monthly")]
    vals = sorted(o["total_monthly"] for o in quantified)
    median = None
    if vals:
        n = len(vals)
        median = vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2
    ge = [o for o in quantified if current and o["total_monthly"] >= current]
    return {
        "total": len(offers),
        "span_months": round(span_months, 1),
        "tier1_count": len(tier1),
        "tier1_per_month": round(len(tier1) / span_months, 2),
        "per_month": round(len(offers) / span_months, 2),
        "quantified_count": len(quantified),
        "median_comp": round(median, 0) if median is not None else None,
        "range_low": vals[0] if vals else None,
        "range_high": vals[-1] if vals else None,
        "ge_current_count": len(ge),
        "ge_current_pct": round(100 * len(ge) / len(quantified)) if quantified else None,
        "current": current,
    }


def add_offer(data):
    offer_id = str(uuid.uuid4())
    eb._exec(
        "insert into job_offers (id, company, role, recruiter, total_monthly, "
        "base_monthly, bonus_pct, work_model, status, received_at, notes, tier, created_at) "
        "values (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (offer_id, data["company"], data.get("role", ""), data.get("recruiter", ""),
         float(data["total_monthly"]),
         P._num(data.get("base_monthly")), P._num(data.get("bonus_pct")),
         data.get("work_model", ""), data.get("status", "new"),
         data.get("received_at") or date.today().isoformat(),
         data.get("notes", ""),
         int(data["tier"]) if data.get("tier") not in (None, "") else None, P._now()))
    P._audit("offer", offer_id, "add", data)
    return offer_id


def update_offer(offer_id, data):
    cols, params = [], []
    for k in ("company", "role", "recruiter", "total_monthly", "base_monthly",
              "bonus_pct", "work_model", "status", "received_at", "notes", "tier"):
        if k in data:
            cols.append(k); params.append(data[k])
    if cols:
        params.append(offer_id)
        eb._exec(eb.update_sql("job_offers", cols), tuple(params))
        P._audit("offer", offer_id, "update", data)


def delete_offer(offer_id):
    P._audit("offer", offer_id, "delete")
    eb._exec("delete from job_offers where id = ?", (offer_id,))


# ---------- market barometer (demand for the roles you track — configurable) ----------

def barometer_config():
    """Configurable roles + geography for the barometer. Defaults roles from the
    career_role_a/b settings (the two roles you already track); geography is
    user-set (empty until configured). The n8n collector uses each role's
    `query` (title-match string) to count postings on job boards."""
    import json as _json
    raw = P.get_setting("barometer_config")
    if raw:
        try:
            cfg = _json.loads(raw)
            if cfg.get("roles"):
                cfg.setdefault("geo", [])
                return cfg
        except ValueError:
            pass
    a = P.get_setting("career_role_a") or "Senior / Staff Engineer"
    b = P.get_setting("career_role_b") or "Engineering Manager / Head"
    return {"geo": [], "roles": [
        {"key": "a", "label": a, "query": a},
        {"key": "b", "label": b, "query": b}]}


def _baro_counts(row, role_keys):
    """Per-role counts for a row — from the `counts` JSON, or, when absent,
    back-compat from legacy em_openings/head_openings (first two roles)."""
    import json as _json
    if row.get("counts"):
        try:
            c = _json.loads(row["counts"])
            return {k: P._num(c.get(k)) for k in role_keys}
        except ValueError:
            pass
    legacy = [row.get("em_openings"), row.get("head_openings")]
    return {k: (P._num(legacy[i]) if i < 2 else None) for i, k in enumerate(role_keys)}


def _pct(cur, prev):
    if cur is None or prev in (None, 0):
        return None
    return round((cur / prev - 1) * 100, 1)


_STREAM_LABEL = {"trends": "demand (Google Trends)", "openings": "openings (JSearch)"}


def list_barometer():
    """Barometer points + a computed INDEX (base 100 at the first month with data)
    per role × STREAM (trends = Google Trends demand proxy with history / openings =
    real posting counts from job boards, from now on), month-over-month and 3-month
    % change and a direction reading — because this tab is about the TREND in
    demand against your inbound, not a falsely precise absolute count."""
    cfg = barometer_config()
    role_keys = [r["key"] for r in cfg["roles"]]
    rows = eb._rows("select * from market_barometer order by month asc")
    offers = eb._rows("select received_at from job_offers")
    inbound = {}
    for o in offers:
        m = (o.get("received_at") or "")[:7]
        if m:
            inbound[m] = inbound.get(m, 0) + 1

    points = []
    for r in rows:
        points.append({
            "id": r["id"], "month": r["month"], "counts": _baro_counts(r, role_keys),
            "stream": r.get("stream") or "trends",
            "my_inbound": inbound.get(r["month"], 0),
            "sources": r.get("sources") or r.get("note") or "",
            "geo": r.get("geo") or r.get("region") or "",
            "as_of": r.get("as_of") or "", "note": r.get("note") or "",
        })

    months = sorted({p["month"] for p in points})
    streams = sorted({p["stream"] for p in points}, key=lambda s: (s != "trends", s))
    inbound_series = [inbound.get(m, 0) for m in months]

    # per role × stream: series aligned to the month axis, index (base 100), trend
    series = {}
    for k in role_keys:
        for st in streams:
            by_month = {p["month"]: p["counts"].get(k) for p in points if p["stream"] == st}
            raw = [by_month.get(m) for m in months]
            base = next((v for v in raw if v not in (None, 0)), None)
            index = [round(100 * v / base, 1) if (v is not None and base) else None for v in raw]
            present = [v for v in raw if v is not None]
            last = present[-1] if present else None
            prev = present[-2] if len(present) >= 2 else None
            prevq = present[-4] if len(present) >= 4 else None
            mom = _pct(last, prev)
            q = _pct(last, prevq)
            drv = q if q is not None else mom
            reading = None if drv is None else ("shrinking" if drv < -10 else "growing" if drv > 10 else "steady")
            series[f"{k}|{st}"] = {"role": k, "stream": st, "stream_label": _STREAM_LABEL.get(st, st),
                                   "counts": raw, "index": index, "mom_pct": mom, "q_pct": q,
                                   "reading": reading, "last": last}

    return {"points": points, "roles": cfg["roles"], "geo": cfg["geo"],
            "months": months, "streams": streams, "inbound": inbound_series, "series": series}


def add_barometer_point(data):
    """Add a point. New shape (n8n collector): month + counts{role:count} + sources
    + geo + as_of. Old shape (em_openings/head_openings) still works."""
    import json as _json
    bid = str(uuid.uuid4())
    counts = data.get("counts")
    counts_json = _json.dumps(counts) if isinstance(counts, dict) else None
    em = P._num(data.get("em_openings"))
    head = P._num(data.get("head_openings"))
    if counts and em is None and head is None:
        vals = list(counts.values())
        em = P._num(vals[0]) if len(vals) > 0 else None
        head = P._num(vals[1]) if len(vals) > 1 else None
    eb._exec(
        "insert into market_barometer (id, month, em_openings, head_openings, "
        "region, note, counts, sources, geo, as_of, stream, created_at) "
        "values (?,?,?,?,?,?,?,?,?,?,?,?)",
        (bid, data["month"], em, head,
         data.get("region", "Europe (remote)"), data.get("note", ""),
         counts_json, data.get("sources", ""), data.get("geo", ""),
         data.get("as_of", ""), data.get("stream", "trends"), P._now()))
    P._audit("barometer", bid, "add", data)
    return bid


def delete_barometer_point(bid):
    P._audit("barometer", bid, "delete")
    eb._exec("delete from market_barometer where id=?", (bid,))
