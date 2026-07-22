"""Monthly market-barometer collector from Google Trends.

Search interest for the English role titles (worldwide) = a real monthly demand
history: free, keyless, already an index (0-100). Ideal for remote roles searched
in English. Run by the `barometer_collect` task in Schedules — it appends the
LAST FULL month, idempotently (skips a month already in the DB). Historical
backfill is done once on setup (see the barometer README).

Requires `pytrends` (in requirements). The current, partial month is not
collected — Trends would give a deflated average; it lands on the next run.
"""
from datetime import date

GEO = ""  # worldwide — the best signal for English remote role titles
_SOURCE = "Google Trends (search interest)"
_GEO_LABEL = "global (remote proxy)"


def _last_full_month():
    t = date.today()
    y, m = (t.year, t.month - 1) if t.month > 1 else (t.year - 1, 12)
    return f"{y:04d}-{m:02d}"


def collect():
    """Appends the last full month for the configured roles. Best-effort — Trends
    rate-limits; on error it returns ok:False without breaking anything."""
    import planner
    try:
        from pytrends.request import TrendReq
    except Exception:
        return {"ok": False, "error": "pytrends not installed (pip install pytrends)"}

    cfg = planner.barometer_config()
    roles = cfg["roles"]
    queries = [r["query"] for r in roles][:5]  # Trends: max 5 terms at once
    target = _last_full_month()
    if target in {p["month"] for p in planner.list_barometer()["points"]}:
        return {"ok": True, "skipped": target}

    try:
        tr = TrendReq(hl="en-US", tz=0)
        tr.build_payload(queries, timeframe=f"2026-01-01 {date.today().isoformat()}", geo=GEO)
        df = tr.interest_over_time()
        if "isPartial" in df:
            df = df.drop(columns=["isPartial"])
        monthly = df.resample("MS").mean().round(1)
        row = monthly[monthly.index.strftime("%Y-%m") == target]
        if row.empty:
            return {"ok": False, "error": f"no Trends data for {target}"}
        counts = {roles[i]["key"]: float(row[queries[i]].iloc[0]) for i in range(len(roles))}
        planner.add_barometer_point({
            "month": target, "counts": counts, "stream": "trends",
            "sources": _SOURCE, "geo": _GEO_LABEL, "as_of": date.today().isoformat()})
        return {"ok": True, "added": target, "counts": counts}
    except Exception as e:
        return {"ok": False, "error": str(e)[:140]}


def collect_openings():
    """Monthly collector of REAL postings (the 'openings' stream) from JSearch
    (Google for Jobs: LinkedIn/Indeed/Glassdoor aggregate). Needs a RapidAPI key in
    env RAPIDAPI_JSEARCH_KEY (or the 'rapidapi_jsearch_key' setting). Without a key
    it's a no-op with a clear message. Fixed method: PAGES pages per role — the raw
    count is a proxy, the app turns it into an index (comparable month to month)."""
    import os
    import json as _json
    import urllib.request
    import urllib.parse
    import planner
    key = os.environ.get("RAPIDAPI_JSEARCH_KEY") or planner.get_setting("rapidapi_jsearch_key")
    if not key:
        return {"ok": False, "error": "no key — set RAPIDAPI_JSEARCH_KEY (rapidapi.com → JSearch)"}
    PAGES = 3  # fixed depth — do NOT change (it breaks index comparability)
    cfg = planner.barometer_config()
    roles = cfg["roles"]
    geo = ", ".join(cfg.get("geo") or []) or "Remote"
    target = _last_full_month()
    already = [p for p in planner.list_barometer()["points"]
               if p["month"] == target and p["stream"] == "openings"]
    if already:
        return {"ok": True, "skipped": target}
    counts = {}
    try:
        for r in roles:
            n = 0
            for pg in range(1, PAGES + 1):
                qs = urllib.parse.urlencode({"query": f"{r['query']} in {geo}", "page": pg, "num_pages": 1})
                req = urllib.request.Request(
                    "https://jsearch.p.rapidapi.com/search?" + qs,
                    headers={"X-RapidAPI-Key": key, "X-RapidAPI-Host": "jsearch.p.rapidapi.com"})
                data = _json.loads(urllib.request.urlopen(req, timeout=20).read())
                n += len(data.get("data") or [])
            counts[r["key"]] = n
    except Exception as e:
        return {"ok": False, "error": str(e)[:140]}
    planner.add_barometer_point({
        "month": target, "counts": counts, "stream": "openings",
        "sources": f"JSearch/Google-for-Jobs ({PAGES} pages)", "geo": geo,
        "as_of": date.today().isoformat()})
    return {"ok": True, "added": target, "counts": counts}


def backfill(replace=True):
    """One-off backfill of history from 2026-01 to the last full month for the
    configured roles (Google Trends, worldwide). `replace` removes existing
    estimates / old Trends points so nothing is duplicated. Run once: python -c
    'import config; config.setup(); import barometer_collect as b; print(b.backfill())'."""
    import planner
    try:
        from pytrends.request import TrendReq
    except Exception:
        return {"ok": False, "error": "pytrends not installed"}
    cfg = planner.barometer_config()
    roles = cfg["roles"]
    queries = [r["query"] for r in roles][:5]
    try:
        tr = TrendReq(hl="en-US", tz=0)
        tr.build_payload(queries, timeframe=f"2026-01-01 {date.today().isoformat()}", geo=GEO)
        df = tr.interest_over_time()
        if "isPartial" in df:
            df = df.drop(columns=["isPartial"])
        monthly = df.resample("MS").mean().round(1)
    except Exception as e:
        return {"ok": False, "error": str(e)[:140]}
    if replace:
        for p in planner.list_barometer()["points"]:
            src = (p.get("sources") or p.get("note") or "").lower()
            if "estimat" in src or "trends" in src:
                planner.delete_barometer_point(p["id"])
    this_month = date.today().strftime("%Y-%m")
    added = []
    for ts, row in monthly.iterrows():
        month = ts.strftime("%Y-%m")
        if month >= this_month:  # full months only
            continue
        counts = {roles[i]["key"]: float(row[queries[i]].iloc[0]) for i in range(len(roles))}
        planner.add_barometer_point({"month": month, "counts": counts, "stream": "trends",
            "sources": _SOURCE, "geo": _GEO_LABEL, "as_of": date.today().isoformat()})
        added.append(month)
    return {"ok": True, "added": added, "skipped_current": this_month}
