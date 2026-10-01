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


HISTORY_START = "2026-01"  # first month of barometer history


def _last_full_month():
    t = date.today()
    y, m = (t.year, t.month - 1) if t.month > 1 else (t.year - 1, 12)
    return f"{y:04d}-{m:02d}"


def _full_months_since(start):
    """Months 'YYYY-MM' from `start` through the last FULL month, inclusive.

    The current month is always skipped — Trends would report a deflated average
    for it and opening counts would be partial. It lands on a run next month.
    """
    y, m = int(start[:4]), int(start[5:7])
    last = _last_full_month()
    out = []
    while f"{y:04d}-{m:02d}" <= last:
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def collect(force=False):
    """Fills in missing full months of the 'trends' stream and rewrites the WHOLE series.

    Google Trends scales every request to its own window (100 = the window's peak), so
    numbers from different requests are not comparable. Every run therefore stores all
    months since HISTORY_START from a single request; appending only the missing month
    once put a month ~20x too low and showed a false "-95%/3m". The same request also
    patches older gaps.

    Best-effort — on error it returns ok:False and changes nothing; the scheduler
    then does NOT record a run and retries (see schedules._succeeded).
    """
    import planner
    try:
        from pytrends.request import TrendReq
    except Exception:
        return {"ok": False, "error": "pytrends not installed (pip install pytrends)"}

    cfg = planner.barometer_config()
    roles = cfg["roles"]
    queries = [r["query"] for r in roles][:5]  # Trends: max 5 terms at once

    # Own stream only — an 'openings' point must not block a 'trends' write.
    old_ids = {}
    for p in planner.list_barometer()["points"]:
        if p.get("stream") == "trends":
            old_ids.setdefault(p["month"], []).append(p["id"])
    months = _full_months_since(HISTORY_START)
    if not force and all(m in old_ids for m in months):
        return {"ok": True, "added": [], "up_to_date": _last_full_month()}

    try:
        tr = TrendReq(hl="en-US", tz=0)
        tr.build_payload(queries, timeframe=f"{HISTORY_START}-01 {date.today().isoformat()}", geo=GEO)
        df = tr.interest_over_time()
        if "isPartial" in df:
            df = df.drop(columns=["isPartial"])
        monthly = df.resample("MS").mean().round(1)
    except Exception as e:
        return {"ok": False, "error": str(e)[:140]}

    added, missing = [], []
    for month in months:
        row = monthly[monthly.index.strftime("%Y-%m") == month]
        if row.empty:
            missing.append(month)
            continue
        for bid in old_ids.get(month, []):
            planner.delete_barometer_point(bid)
        counts = {roles[i]["key"]: float(row[queries[i]].iloc[0]) for i in range(len(roles))}
        planner.add_barometer_point({
            "month": month, "counts": counts, "stream": "trends",
            "sources": _SOURCE, "geo": _GEO_LABEL, "as_of": date.today().isoformat()})
        if month not in old_ids:
            added.append(month)

    # Success only if the last full month is now covered; otherwise stay ok:False
    # so the next app open retries within the same period.
    done = _last_full_month() in (set(old_ids) | set(added))
    out = {"ok": done, "added": added}
    if missing:
        out["no_trends_data"] = missing
    if not done:
        out["error"] = f"could not complete {_last_full_month()}"
    return out


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
        # No key = nothing to do (not a failure): mark the period done so it does not
        # raise a permanent warning; the key state is exposed as openings_key_set.
        return {"ok": True, "skipped": "no API key (RAPIDAPI_JSEARCH_KEY)"}
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


# ---------- watchlist: real open roles at companies in your target market ----------
#
# Google Trends measures who SEARCHES for a title (mostly candidates), not who is
# hiring, and JSearch caps out at 3 pages of 10. The watchlist counts real open roles
# on the public Greenhouse / Lever / Ashby boards (keyless) of companies you pick
# yourself (⚙️ on the Career tab), so it measures YOUR target market, not all of it.
import re

_ATS_URL = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{}/jobs?content=false",
    "lever": "https://api.lever.co/v0/postings/{}?mode=json",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{}",
}

# Title families: a role's `query` (or key) picks the family by what it names, so
# "Senior PM" also counts "Senior Product Manager" and "Engineering Manager / Head"
# catches Senior / Staff / Group EM. Head/Director share a family (VP is a separate
# league). A query that names none of them matches literally.
_FAMILIES = [
    (re.compile(r"head|director", re.I), re.compile(r"product", re.I),
     re.compile(r"head of product|director,? (of )?product|product director", re.I)),
    (re.compile(r"\bpm\b|product manager", re.I), None,
     re.compile(r"product manager|\bpm\b", re.I)),
    (re.compile(r"\bem\b|engineering manager", re.I), None,
     re.compile(r"engineering manager|manager,? (software |platform )?engineering", re.I)),
    (re.compile(r"head|director", re.I), None,
     re.compile(r"head of (software |platform )?engineering|director,? (of )?(software |platform )?engineering|engineering director", re.I)),
    (re.compile(r"senior|staff|principal", re.I), re.compile(r"engineer", re.I),
     re.compile(r"\b(senior|staff|principal) (software |backend |frontend |full[- ]?stack |platform )?engineer\b(?!ing)", re.I)),
]
_FAMILY = {"em": _FAMILIES[2][2], "head": _FAMILIES[3][2]}  # built-in private-style keys


def _family_for(role):
    if role["key"] in _FAMILY:
        return _FAMILY[role["key"]]
    q = role.get("query") or role.get("label") or role["key"]
    for names, also, fam in _FAMILIES:
        if names.search(q) and (also is None or also.search(q)):
            return fam
    return re.compile(re.escape(q), re.I)


# A Sales / Solutions / Support Engineering Manager is a different job.
_NOT_ENG = re.compile(r"\b(sales|solutions?|support|customer|field|partner|analytics?|analytical) engineering", re.I)
_EU = re.compile(r"poland|polska|warsaw|gda[nń]sk|krak[oó]w|wroc[lł]aw|europe|emea|london|berlin|amsterdam|dublin|paris|munich|"
                 r"stockholm|lisbon|madrid|barcelona|prague|zurich|vienna|oslo|copenhagen|helsinki|tallinn|bucharest|"
                 r"united kingdom|germany|netherlands|ireland|france|spain|portugal|sweden|denmark|norway|finland|"
                 r"czech|austria|switzerland|romania|estonia|italy", re.I)
_NON_EU = re.compile(r"united states|\bus\b|\busa\b|u\.s\.|north america|canada|india|australia|apac|latam|americas|brazil|mexico|singapore|japan|israel", re.I)


def _eu_location(loc):
    """A role counts when its location points to Europe, or it is remote without an
    explicit restriction to another continent ("Remote - US" is out)."""
    if _EU.search(loc):
        return True
    return "remote" in loc.lower() and not _NON_EU.search(loc)


def _board_jobs(ats, slug):
    """(title, location) pairs from one board; None on a network error / bad slug."""
    import json as _json
    import urllib.request
    try:
        req = urllib.request.Request(_ATS_URL[ats].format(slug), headers={"User-Agent": "kist-barometer"})
        d = _json.loads(urllib.request.urlopen(req, timeout=20).read())
    except Exception:
        return None
    if ats == "greenhouse":
        return [(j.get("title", ""), (j.get("location") or {}).get("name", "")) for j in d.get("jobs", [])]
    if ats == "lever":
        return [(j.get("text", ""), " ".join([(j.get("categories") or {}).get("location", "")]
                                          + ((j.get("categories") or {}).get("allLocations") or []))) for j in d]
    return [(j.get("title", ""), " ".join([j.get("location", "")]
                                        + [s.get("location", "") for s in (j.get("secondaryLocations") or [])]))
            for j in d.get("jobs", [])]


def count_watchlist(boards, roles, fetch=_board_jobs):
    """Counts roles per family across all boards. Returns (counts, hits, failed):
    hits = "company: title (location)" lines for the preview, failed = boards that
    did not answer."""
    import concurrent.futures as cf
    fams = [(r["key"], _family_for(r)) for r in roles]
    counts = {k: 0 for k, _ in fams}
    hits, failed = [], []
    with cf.ThreadPoolExecutor(8) as ex:
        results = list(ex.map(lambda b: (b, fetch(*b)), boards))
    for (ats, slug), jobs in results:
        if jobs is None:
            failed.append(f"{ats}:{slug}")
            continue
        seen = set()
        for title, loc in jobs:
            if _NOT_ENG.search(title) or not _eu_location(loc):
                continue
            # the same role posted once per country ("... | EMEA | (Remote, Spain)") counts once
            key = re.sub(r"\s*\|.*$|\s*\((remote|hybrid)[^)]*\)\s*$", "", title, flags=re.I).strip().lower()
            if key in seen:
                continue
            seen.add(key)
            for k, fam in fams:
                if fam.search(title):
                    counts[k] += 1
                    hits.append(f"{slug}: {title} ({loc.strip()})")
                    break
    return counts, hits, failed


def collect_watchlist(force=False):
    """Monthly snapshot of open roles at the watchlist companies ('watchlist' stream).
    Labelled with the current month (a snapshot as of the collection day), idempotent."""
    import planner
    cfg = planner.barometer_config()
    boards = []
    for item in cfg.get("watchlist") or []:
        ats, _, slug = item.partition(":")
        if ats in _ATS_URL and slug:
            boards.append((ats, slug))
    if not boards:
        return {"ok": True, "skipped": "empty watchlist"}
    month = date.today().isoformat()[:7]
    old = [p for p in planner.list_barometer()["points"] if p["stream"] == "watchlist" and p["month"] == month]
    if old and not force:
        return {"ok": True, "skipped": month}
    counts, hits, failed = count_watchlist(boards, cfg["roles"])
    if len(failed) > len(boards) // 2:
        return {"ok": False, "error": f"{len(failed)} of {len(boards)} boards did not answer"}
    for p in old:
        planner.delete_barometer_point(p["id"])
    planner.add_barometer_point({
        "month": month, "counts": counts, "stream": "watchlist",
        "sources": f"watchlist: {len(boards) - len(failed)} companies (Greenhouse/Lever/Ashby)",
        "geo": "Europe / remote EMEA", "as_of": date.today().isoformat(),
        "note": "\n".join(sorted(hits)) + (f"\n\nno response: {', '.join(failed)}" if failed else "")})
    return {"ok": True, "added": month, "counts": counts, "failed": failed}


# ---------- Indeed Hiring Lab: history of IT postings in Europe (backdrop for the watchlist) ----------
#
# The watchlist is a snapshot with no past. Hiring Lab publishes a daily index of
# Indeed posting volume per sector and country (Feb 2020 = 100), since 2020: the only
# free, real history of posting counts. It covers whole sectors, not specific roles;
# only GB, DE and FR publish per-sector CSVs in Europe. Collected like Trends: full
# months, the whole series rewritten each run (Hiring Lab revises past data).
HIRINGLAB_COUNTRIES = ["GB", "DE", "FR"]
_HIRINGLAB_URL = "https://raw.githubusercontent.com/hiring-lab/job_postings_tracker/master/{c}/job_postings_by_sector_{c}.csv"
HIRINGLAB_KEY = "it_eu"
# "IT broad": the mean of Indeed's four IT sectors (Software Development + the rest of IT).
HIRINGLAB_BROAD_KEY = "it_broad"
HIRINGLAB_BROAD = ["Software Development", "Data & Analytics", "IT Systems & Solutions",
                   "IT Infrastructure, Operations & Support"]


def hiringlab_monthly(csv_text, months, sector="Software Development"):
    """Monthly mean of a sector's 'total postings' index from a Hiring Lab CSV."""
    import csv, io
    acc = {}
    for row in csv.DictReader(io.StringIO(csv_text)):
        m = row["date"][:7]
        if m in months and row["variable"] == "total postings" and row["display_name"] == sector:
            acc.setdefault(m, []).append(float(row["indeed_job_postings_index"]))
    return {m: round(sum(v) / len(v), 1) for m, v in acc.items()}


def collect_hiringlab(force=False, fetch=None):
    """'hiringlab' stream: mean of the HIRINGLAB_COUNTRIES indices per full month."""
    import urllib.request
    import engine_bridge as eb
    import planner
    months = _full_months_since(HISTORY_START)
    # Straight from the table: list_barometer() filters hiringlab out of points, so old
    # rows would never be deleted and every run would duplicate the months.
    old_ids = {}
    for r in eb._rows("select id, month from market_barometer where stream='hiringlab'"):
        old_ids.setdefault(r["month"], []).append(r["id"])
    if not force and all(m in old_ids for m in months):
        return {"ok": True, "added": [], "up_to_date": _last_full_month()}
    if fetch is None:
        def fetch(c):
            req = urllib.request.Request(_HIRINGLAB_URL.format(c=c), headers={"User-Agent": "kist-barometer"})
            return urllib.request.urlopen(req, timeout=60).read().decode("utf-8")
    per_country = {}  # country -> sector -> {month: index}
    for c in HIRINGLAB_COUNTRIES:
        try:
            text = fetch(c)
            per_country[c] = {sec: hiringlab_monthly(text, set(months), sec) for sec in HIRINGLAB_BROAD}
        except Exception as e:
            return {"ok": False, "error": f"{c}: {str(e)[:120]}"}

    def avg(month, sectors):
        # mean of sectors within a country, then mean of countries (each weighs the same);
        # a country lacking a sector (FR has no "Data & Analytics") averages the ones it has
        per_c = []
        for c in HIRINGLAB_COUNTRIES:
            v = [per_country[c][sec][month] for sec in sectors if month in per_country[c][sec]]
            if v:
                per_c.append(sum(v) / len(v))
        return round(sum(per_c) / len(per_c), 1) if per_c else None

    added = []
    for month in months:
        sd, broad = avg(month, HIRINGLAB_BROAD[:1]), avg(month, HIRINGLAB_BROAD)
        if sd is None:
            continue
        for bid in old_ids.get(month, []):
            planner.delete_barometer_point(bid)
        counts = {HIRINGLAB_KEY: sd}
        if broad is not None:
            counts[HIRINGLAB_BROAD_KEY] = broad
        planner.add_barometer_point({
            "month": month, "counts": counts, "stream": "hiringlab",
            "sources": f"Indeed Hiring Lab: Software Development and IT broad ({len(HIRINGLAB_BROAD)} sectors), mean {'/'.join(HIRINGLAB_COUNTRIES)} (Feb 2020 = 100)",
            "geo": f"Europe ({', '.join(HIRINGLAB_COUNTRIES)})", "as_of": date.today().isoformat()})
        if month not in old_ids:
            added.append(month)
    done = _last_full_month() in (set(old_ids) | set(added))
    return {"ok": done, "added": added} if done else {"ok": False, "added": added, "error": f"missing {_last_full_month()}"}
