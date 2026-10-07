"""planner_career — Career: job offers (stats vs current), job-market barometer.

Split out of planner.py on 2026-09-05 (code moved 1:1; other modules are reached through `P`).
"""
import uuid
from datetime import date

import engine_bridge as eb
from planner_proxy import P

# ---------- job offers ----------

def _current_total_monthly(today=None):
    """GROSS monthly total in offer units (base + bonus + RSU + cash vest); monthly_equivalent is net."""
    base = P._num(P.get_setting("tax_salary_gross_annual"))
    if not base:
        return None
    x = P._annual_extras(today)
    bonus = x["bonus_net"] / x["payroll_net_factor"]  # the bonus goes through payroll like the cash vest
    return round((base + bonus + x["rsu_annual_gross"] + x["cash_vest_annual_gross"]) / 12)


def _package_by_month(months):
    """GROSS monthly package per month, in the same units as `_current_total_monthly`, but
    with what applied in that month: base salary from `salary_history`
    ([{"from": "YYYY-MM", "annual": N}], missing = today's salary everywhere), shares and
    cash-vest from grants active from their first_vest. Today's price and FX, so the steps
    show package changes, not price swings."""
    base_now = P._num(P.get_setting("tax_salary_gross_annual"))
    if not base_now:
        return [None] * len(months)
    hist = sorted(P.get_json_setting("salary_history") or [], key=lambda h: h["from"])
    x = P._annual_extras()
    bonus = x["bonus_net"] / x["payroll_net_factor"]
    try:
        import market
        r = market.get_rsu()
    except Exception:
        r = {}
    px, fx, vpy = r.get("last_close") or 0, r.get("usdpln") or 0, r.get("vests_per_year") or 4
    legacy, legacy_until = r.get("legacy_shares_per_vest") or 0, r.get("legacy_until")
    # the schedule starts legacy grants at the NEXT vest; past months need the flat tranche instead
    grants = [g for g in r.get("vest_sources") or [] if g["label"] != "legacy grants" and g.get("first_vest")]
    out = []
    for m in months:
        prior = [h for h in hist if h["from"] <= m]
        base = P._num(prior[-1]["annual"]) if prior else (P._num(hist[0]["annual"]) if hist else base_now)
        live = [g for g in grants if g["first_vest"] <= m <= (g.get("last_vest") or m)]
        shares = (legacy if not legacy_until or m <= legacy_until else 0) + sum(g["per_vest"] for g in live)
        cash = sum(g.get("cash_per_vest_usd") or 0 for g in live)
        out.append(round((base + bonus + (shares * px + cash) * fx * vpy) / 12))
    return out


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
        "ge_current_pct": round(100 * len(ge) / len(quantified)) if quantified and current else None,
        "current": current,
    }


def _offer_value(k, v):
    if k in ("total_monthly", "base_monthly", "bonus_pct"):
        return P._num(v)  # text in a REAL column broke GET /api/offers
    if k == "tier":
        return int(v) if v not in (None, "") else None
    return v


def add_offer(data):
    offer_id = str(uuid.uuid4())
    eb._exec(
        "insert into job_offers (id, company, role, recruiter, total_monthly, "
        "base_monthly, bonus_pct, work_model, status, received_at, notes, tier, created_at) "
        "values (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (offer_id, data["company"], data.get("role", ""), data.get("recruiter", ""),
         _offer_value("total_monthly", data["total_monthly"]),
         P._num(data.get("base_monthly")), P._num(data.get("bonus_pct")),
         data.get("work_model", ""), data.get("status", "new"),
         data.get("received_at") or date.today().isoformat(),
         data.get("notes", ""),
         _offer_value("tier", data.get("tier")), P._now()))
    P._audit("offer", offer_id, "add", data)
    return offer_id


def update_offer(offer_id, data):
    row = eb._rows("select notes from job_offers where id = ?", (offer_id,))
    if not row:
        return None
    if data.get("notes_append"):
        # notes is the only log of a recruiter thread; a PUT of notes alone wiped earlier rounds
        base = data.get("notes", row[0]["notes"]) or ""
        data = {**data, "notes": (base + "\n\n" + data["notes_append"]).strip()}
    cols, params = [], []
    for k in ("company", "role", "recruiter", "total_monthly", "base_monthly",
              "bonus_pct", "work_model", "status", "received_at", "notes", "tier"):
        if k in data:
            cols.append(k); params.append(_offer_value(k, data[k]))
    if cols:
        params.append(offer_id)
        eb._exec(eb.update_sql("job_offers", cols), tuple(params))
        P._audit("offer", offer_id, "update", data)
    return len(cols)


def delete_offer(offer_id):
    P._audit("offer", offer_id, "delete")
    eb._exec("delete from job_offers where id = ?", (offer_id,))


# ---------- market barometer (demand for the roles you track — configurable) ----------

def barometer_config():
    """Configurable roles + geography for the barometer. Defaults roles from the
    career_role_a/b settings (the two roles you already track); geography is
    user-set (empty until configured). The n8n collector uses each role's
    `query` (title-match string) to count postings on job boards."""
    cfg = P.get_json_setting("barometer_config")
    if cfg and cfg.get("roles"):
        cfg.setdefault("geo", [])
        cfg.setdefault("watchlist", DEFAULT_WATCHLIST)
        return cfg
    a = P.get_setting("career_role_a") or "Senior / Staff Engineer"
    b = P.get_setting("career_role_b") or "Engineering Manager / Head"
    return {"geo": [], "roles": [
        {"key": "a", "label": a, "query": a},
        {"key": "b", "label": b, "query": b}], "watchlist": DEFAULT_WATCHLIST}


# Companies with a public job board and engineering teams in Europe (checked 2026-10:
# every board answered and had at least 5 European postings). Format "ats:slug";
# edit via ⚙️ on the Career tab.
DEFAULT_WATCHLIST = [
    "greenhouse:adyen", "greenhouse:affirm", "greenhouse:airbnb", "greenhouse:algolia",
    "greenhouse:anthropic", "greenhouse:asana", "greenhouse:celonis", "greenhouse:cloudflare",
    "greenhouse:cognite", "greenhouse:coinbase", "greenhouse:contentful", "greenhouse:databricks",
    "greenhouse:datadog", "greenhouse:dataiku", "greenhouse:discord", "greenhouse:doctolib",
    "greenhouse:dropbox", "greenhouse:elastic", "greenhouse:fastly", "greenhouse:figma",
    "greenhouse:fivetran", "greenhouse:getyourguide", "greenhouse:gitlab", "greenhouse:gocardless",
    "greenhouse:grafanalabs", "greenhouse:gusto", "greenhouse:helsing", "greenhouse:hightouch",
    "greenhouse:instacart", "greenhouse:intercom", "greenhouse:launchdarkly", "greenhouse:mirakl",
    "greenhouse:mixpanel", "greenhouse:mongodb", "greenhouse:monzo", "greenhouse:n26",
    "greenhouse:newrelic", "greenhouse:okta", "greenhouse:pinterest", "greenhouse:planetscale",
    "greenhouse:realtimeboardglobal", "greenhouse:reddit", "greenhouse:robinhood",
    "greenhouse:roblox", "greenhouse:samsara", "greenhouse:scaleai", "greenhouse:squarespace",
    "greenhouse:stripe", "greenhouse:sumup", "greenhouse:tailscale", "greenhouse:tide",
    "greenhouse:toast", "greenhouse:twilio", "greenhouse:typeform", "greenhouse:vercel",
    "greenhouse:veriff", "greenhouse:webflow", "greenhouse:wise", "greenhouse:wolt",
    "greenhouse:xai", "greenhouse:zscaler", "lever:contentsquare", "lever:palantir",
    "lever:pipedrive", "lever:spotify", "lever:swile", "ashby:1password", "ashby:alan",
    "ashby:amplitude", "ashby:backmarket", "ashby:clickhouse", "ashby:cohere", "ashby:cursor",
    "ashby:deepl", "ashby:docker", "ashby:docplanner", "ashby:elevenlabs", "ashby:kong",
    "ashby:ledger", "ashby:linear", "ashby:modal", "ashby:mollie", "ashby:multiverse", "ashby:n8n",
    "ashby:notion", "ashby:openai", "ashby:paddle", "ashby:perplexity", "ashby:plaid",
    "ashby:pleo", "ashby:posthog", "ashby:qonto", "ashby:ramp", "ashby:redis", "ashby:render",
    "ashby:sentry", "ashby:snowflake", "ashby:supabase", "ashby:synthesia", "ashby:temporal",
    "ashby:vanta", "ashby:wayve", "ashby:xero",
]


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


_STREAM_LABEL = {"trends": "interest (Google Trends)", "openings": "openings (JSearch)",
                 "watchlist": "open roles (watchlist)", "hiringlab": "IT postings in Europe (Indeed Hiring Lab)", "boards": "postings on IT job boards (No Fluff Jobs)"}


def list_barometer():
    """Barometer points + a computed INDEX (base 100 at the first month with data)
    per role × STREAM (trends = Google Trends demand proxy with history / openings =
    real posting counts from job boards, from now on), month-over-month and 3-month
    % change and a direction reading — because this tab is about the TREND in
    demand against your inbound, not a falsely precise absolute count."""
    import json as _json
    cfg = barometer_config()
    role_keys = [r["key"] for r in cfg["roles"]]
    rows = eb._rows("select * from market_barometer order by month asc")
    offers = eb._rows("select received_at, total_monthly from job_offers")
    inbound, comp = {}, {}
    for o in offers:
        m = (o.get("received_at") or "")[:7]
        if m:
            inbound[m] = inbound.get(m, 0) + 1
            if o.get("total_monthly"):
                comp.setdefault(m, []).append(o["total_monthly"])

    # Hiring Lab series are sector-wide, not per configured role: kept out of points
    # and the table, and turned into their own series below.
    points, hiringlab = [], {}
    for r in rows:
        if (r.get("stream") or "trends") == "hiringlab":
            try:
                for key, v in _json.loads(r["counts"] or "{}").items():
                    hiringlab.setdefault(key, {})[r["month"]] = P._num(v)
            except ValueError:
                pass
            continue
        points.append({
            "id": r["id"], "month": r["month"], "counts": _baro_counts(r, role_keys),
            "stream": r.get("stream") or "trends",
            "my_inbound": inbound.get(r["month"], 0),
            "sources": r.get("sources") or r.get("note") or "",
            "geo": r.get("geo") or r.get("region") or "",
            "as_of": r.get("as_of") or "", "note": r.get("note") or "",
        })

    months = sorted({p["month"] for p in points} | {m for hl in hiringlab.values() for m in hl})
    streams = sorted({p["stream"] for p in points}, key=lambda s: (s != "trends", s))
    inbound_series = [inbound.get(m, 0) for m in months]
    # a handful of inquiries a month is noise; a 3-month average shows the direction
    inbound_ma3 = [round(sum(inbound_series[max(0, i - 2):i + 1]) / len(inbound_series[max(0, i - 2):i + 1]), 1)
                   for i in range(len(inbound_series))]
    # average only over offers that disclosed a range; a month without any = None, not 0
    comp_avg = [round(sum(comp[m]) / len(comp[m])) if m in comp else None for m in months]
    comp_n = [len(comp.get(m, [])) for m in months]
    # the range chart's axis runs 3 months ahead so announced package steps show up
    t = date.today()
    comp_months = list(months)
    y, mo = (int(comp_months[-1][:4]), int(comp_months[-1][5:7])) if comp_months else (t.year, t.month - 1)
    horizon = f"{t.year + (t.month + 2) // 12:04d}-{(t.month + 2) % 12 + 1:02d}"
    while True:
        y, mo = (y + 1, 1) if mo == 12 else (y, mo + 1)
        if f"{y:04d}-{mo:02d}" > horizon:
            break
        comp_months.append(f"{y:04d}-{mo:02d}")

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
            # Trends measures searches (mostly candidates), not vacancies: "shrinking"
            # read like a shrinking market next to a flat Hiring Lab line.
            down = "falling" if st == "trends" else "shrinking"
            reading = None if drv is None else (down if drv < -10 else "growing" if drv > 10 else "steady")
            series[f"{k}|{st}"] = {"role": k, "stream": st, "stream_label": _STREAM_LABEL.get(st, st),
                                   "counts": raw, "index": index, "mom_pct": mom, "q_pct": q,
                                   "reading": reading, "last": last}

    for key, hl in hiringlab.items():
        raw = [hl.get(m) for m in months]
        base = next((v for v in raw if v), None)
        present = [v for v in raw if v is not None]
        q = _pct(present[-1], present[-4]) if len(present) >= 4 else None
        series[f"{key}|hiringlab"] = {"role": key, "stream": "hiringlab", "stream_label": _STREAM_LABEL["hiringlab"],
                                      "counts": raw, "index": [round(100 * v / base, 1) if v and base else None for v in raw],
                                      "q_pct": q, "last": present[-1] if present else None,
                                      "reading": None if q is None else ("shrinking" if q < -10 else "growing" if q > 10 else "steady")}

    wl = [p for p in points if p["stream"] == "watchlist"]
    return {"points": points, "roles": cfg["roles"], "geo": cfg["geo"],
            "watchlist": cfg.get("watchlist") or [], "watchlist_latest": wl[-1] if wl else None,
            "months": months, "streams": streams, "inbound": inbound_series, "inbound_ma3": inbound_ma3,
            "comp_avg": comp_avg, "comp_n": comp_n, "series": series,
            "comp_months": comp_months, "comp_current": _package_by_month(comp_months)}


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
