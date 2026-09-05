"""Market data: Supabase reader (public prices), local cache, watchlist,
analytics and RSU tracker. Personal data (amounts, targets, grant) stays local.
"""
import json
import math
import os
import random
import re
import urllib.request
import urllib.parse
from datetime import date, datetime
from pathlib import Path
from statistics import mean, pstdev

import db  # skill module (sys.path set by engine_bridge import in app.py)
from config import setup

_CFG = None


def cfg():
    global _CFG
    if _CFG is None:
        _CFG = {
            "url": os.environ.get("SUPABASE_URL", "").rstrip("/"),
            "key": os.environ.get("SUPABASE_ANON_KEY", ""),
            # service_role key (server-side only, .env, gitignored) for reads of tables
            # that RLS denies to the public anon key — see _supabase_get(service=True)
            "service_key": os.environ.get("SUPABASE_SERVICE_KEY", ""),
        }
    return _CFG


def _finance_dir():
    return Path(os.environ["FINANCE_PROJECT_DIR"]) / ".finance"


# ---------- local cache (works offline) ----------

def _ensure_cache():
    with db.get_conn() as conn:
        conn.execute("""create table if not exists market_prices_cache (
            ticker text not null, date text not null, close real not null,
            currency text default 'USD', primary key (ticker, date))""")
        conn.execute("""create table if not exists market_meta (
            key text primary key, value text)""")
        conn.execute("""create table if not exists forecast_track (
            id integer primary key autoincrement,
            made_on text not null, ticker text not null, horizon_days integer not null,
            base_close real, sigma_daily real, p10 real, p50 real, p90 real,
            realized_close real, realized_on text, inside integer, resid_z real,
            unique (made_on, ticker, horizon_days))""")
        try:
            conn.execute("alter table forecast_track add column calibrated integer default 0")
        except Exception:
            pass  # column already exists
        conn.commit()


def _supabase_get(path_and_query, service=False):
    c = cfg()
    # service=True reads with the service_role key so RLS can deny the public anon key
    # any access to sensitive tables (ads analytics). Falls back to anon if no service
    # key is configured, so dev/CI without it keeps working.
    key = (c.get("service_key") or c["key"]) if service else c["key"]
    if not c["url"] or not key:
        raise RuntimeError("SUPABASE_URL / SUPABASE_ANON_KEY not configured (.env)")
    req = urllib.request.Request(
        f"{c['url']}/rest/v1/{path_and_query}",
        headers={"apikey": key, "Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())


def _supabase_send(method, path, payload=None):
    c = cfg()
    req = urllib.request.Request(
        f"{c['url']}/rest/v1/{path}", method=method,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"apikey": c["key"], "Authorization": f"Bearer {c['key']}",
                 "Content-Type": "application/json", "Prefer": "return=minimal"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.status


def _cache_max_date():
    _ensure_cache()
    with db.get_conn() as conn:
        r = conn.execute("select max(date) from market_prices_cache").fetchone()
    return r[0] if r and r[0] else None


def _stale_days(max_date=None):
    """How many business days behind today the data is (0 = fresh)."""
    from datetime import date as _date, datetime as _dt, timedelta
    md = max_date or _cache_max_date()
    if not md:
        return 999
    d = _dt.strptime(md, "%Y-%m-%d").date()
    today, n, cur = _date.today(), 0, _date.today()
    while cur > d:                        # count weekdays only (Mon–Fri)
        if cur.weekday() < 5:
            n += 1
        cur -= timedelta(days=1)
    return n


def _topup_from_yahoo(max_tickers=60):
    """SELF-HEALING: pull the last days from Yahoo (keyless) for EVERY ticker already
    in the cache — so charts/radar stay fresh EVEN IF the upstream collector is down.
    Best-effort: a failure for one ticker does not break the rest."""
    _ensure_cache()
    with db.get_conn() as conn:
        tickers = [r[0] for r in conn.execute(
            "select distinct ticker from market_prices_cache order by ticker limit ?",
            (max_tickers,)).fetchall()]
    filled = 0
    for t in tickers:
        try:
            if fetch_yahoo_history(t, "1mo"):
                filled += 1
        except Exception:
            continue
    return filled


def refresh_cache():
    """Refresh the local cache: (1) Supabase (historical depth from the collector),
    (2) SELF-HEAL from Yahoo for recent days — so data is fresh regardless of whether
    the upstream collector is running. Also returns a freshness signal (stale_days)."""
    _ensure_cache()
    supa_rows, supa_ok = [], True
    try:                                              # Supabase best-effort — a failure must not block Yahoo
        offset = 0
        while True:
            batch = _supabase_get(
                "market_prices?select=ticker,date,close,currency&order=date.asc"
                f"&limit=1000&offset={offset}")
            supa_rows.extend(batch)
            if len(batch) < 1000:
                break
            offset += 1000
    except Exception:
        supa_ok = False
    with db.get_conn() as conn:
        for r in supa_rows:
            conn.execute(
                "insert or replace into market_prices_cache (ticker,date,close,currency) values (?,?,?,?)",
                (r["ticker"], r["date"], r["close"], r.get("currency", "USD")))
        conn.commit()
    # self-heal: fresh quotes straight from Yahoo (independent of the collector)
    filled = _topup_from_yahoo()
    with db.get_conn() as conn:
        conn.execute("insert or replace into market_meta (key,value) values ('last_sync',?)",
                     (datetime.now().isoformat(timespec="seconds"),))
        conn.commit()
    md = _cache_max_date()
    return {"rows": len(supa_rows), "supabase_ok": supa_ok, "yahoo_topup": filled,
            "data_through": md, "stale_days": _stale_days(md)}


def auto_sync():
    """Refresh local cache from Supabase if not synced today (cheap, ~40 rows).
    Silent on failure — offline mode keeps yesterday's cache."""
    ls = last_sync()
    from datetime import date as _date
    if ls and ls[:10] == _date.today().isoformat():
        return
    try:
        refresh_cache()
    except Exception:
        pass


def last_sync():
    _ensure_cache()
    with db.get_conn() as conn:
        cur = conn.execute("select value from market_meta where key='last_sync'")
        row = cur.fetchone()
        return row[0] if row else None


def prices(ticker, days=365):
    _ensure_cache()
    with db.get_conn() as conn:
        cur = conn.execute(
            "select date, close, currency from market_prices_cache "
            "where ticker=? order by date desc limit ?", (ticker.upper(), days))
        rows = [{"date": d, "close": c, "currency": cur_} for d, c, cur_ in cur.fetchall()]
    return list(reversed(rows))


# ---------- watchlist (tickers in Supabase; notes/targets local) ----------

def get_watchlist():
    try:
        remote = _supabase_get("market_watchlist?select=ticker,added_at,notes&order=ticker")
    except Exception:
        # offline: derive from cache
        _ensure_cache()
        with db.get_conn() as conn:
            cur = conn.execute("select distinct ticker from market_prices_cache order by ticker")
            remote = [{"ticker": r[0], "added_at": None, "notes": None} for r in cur.fetchall()]
    return remote


def add_ticker(ticker, notes=""):
    try:
        _supabase_send("POST", "market_watchlist", {"ticker": ticker.upper(), "notes": notes})
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": "The watchlist needs Supabase (keys in .env) — "
                                      "see README › Connecting your own services. " + str(e)[:60]}


def remove_ticker(ticker):
    try:
        return _remove_ticker_inner(ticker)
    except Exception as e:
        return {"ok": False, "error": str(e)[:80]}


def _remove_ticker_inner(ticker):
    _supabase_send("DELETE", f"market_watchlist?ticker=eq.{urllib.parse.quote(ticker.upper())}")
    return {"ok": True}


# ---------- local analyst targets ----------

def _targets_path():
    return _finance_dir() / "market_targets.json"


def get_targets():
    p = _targets_path()
    return json.loads(p.read_text()) if p.exists() else {}


def set_target(ticker, target):
    t = get_targets()
    t[ticker.upper()] = float(target)
    _targets_path().write_text(json.dumps(t, indent=2))
    return t


# ---------- analytics ----------

def _sma(closes, n):
    return round(mean(closes[-n:]), 2) if len(closes) >= n else None


def _rsi(closes, n=14):
    """Wilder's RSI over the last n changes. 0-100: >70 overbought, <30 oversold,
    ~50 neutral. Needs n+1 closes; None otherwise. Momentum, works on short history."""
    if len(closes) < n + 1:
        return None
    gains = losses = 0.0
    for i in range(-n, 0):
        d = closes[i] - closes[i - 1]
        gains += max(d, 0.0)
        losses += max(-d, 0.0)
    if losses == 0:
        return 100.0
    rs = (gains / n) / (losses / n)
    return round(100 - 100 / (1 + rs), 1)


def _bollinger(closes, n=20, k=2.0):
    """Bollinger Bands: SMA(n) +/- k*stddev(n). Returns (lower, mid, upper) or
    None. Price near the upper band = stretched up; near lower = stretched down;
    band width = volatility. Needs n closes."""
    if len(closes) < n:
        return None
    from statistics import pstdev
    window = closes[-n:]
    mid = mean(window)
    sd = pstdev(window)
    return round(mid - k * sd, 2), round(mid, 2), round(mid + k * sd, 2)


def analytics(ticker):
    hist = prices(ticker, days=400)
    if not hist:
        return {"ticker": ticker.upper(), "error": "no data — run refresh"}
    closes = [r["close"] for r in hist]
    last = closes[-1]
    hi_52w = max(closes[-252:]) if closes else None
    lo_52w = min(closes[-252:]) if closes else None
    target = get_targets().get(ticker.upper())
    def delta(n):
        return round((last / closes[-n - 1] - 1) * 100, 2) if len(closes) > n else None
    return {
        "ticker": ticker.upper(),
        "last_close": round(last, 2),
        "last_date": hist[-1]["date"],
        "currency": hist[-1]["currency"],
        "change_1d_pct": delta(1),
        "change_30d_pct": delta(21),
        "sma20": _sma(closes, 20), "sma50": _sma(closes, 50), "sma200": _sma(closes, 200),
        "rsi14": _rsi(closes, 14),
        "bollinger": (lambda b: {"lower": b[0], "mid": b[1], "upper": b[2]} if b else None)(_bollinger(closes)),
        "points": len(closes), "first_date": hist[0]["date"],
        "high_52w": round(hi_52w, 2), "low_52w": round(lo_52w, 2),
        "drawdown_from_high_pct": round((last / hi_52w - 1) * 100, 2) if hi_52w else None,
        "analyst_target": target,
        "target_upside_pct": round((target / last - 1) * 100, 2) if target else None,
    }


# ---------- RSU tracker ----------

def _rsu_path():
    return _finance_dir() / "rsu.json"

_RSU_DEFAULT = {
    "ticker": "AAPL",
    "grant_value_usd": 100000,     # placeholder — real values live in rsu.json (gitignored)
    "pricing_window": "2026-08",       # average of this month's closes
    "grant_month": "2026-09",
    "vesting_years": 4,
    "vests_per_year": 4,
    "shares_held": 0,                  # shares already held (after vests)
    "shares_next_vest": 0,             # how many shares vest next (broker's number; wins over the model)
    # optional in rsu.json: "legacy_shares_per_vest" (older grants still vesting),
    # "extra_grants": [{"label", "value_usd", "pricing_window", "vesting_years", "note"}],
    # "new_grants_vesting": true once the new grants start vesting (model replaces shares_next_vest)
    "vest_months": [2, 5, 8, 11],      # Feb, May, Aug, Nov
    "target_bear": None,               # lower analyst target; None -> 0.65x spot
    "target_bull": None,               # upper analyst target; None -> 1.30x spot
    "analyst_target_mid": None,        # consensus; None -> current price (no view)
    "mc_drift_annual": 0.08,           # annual drift for the Monte Carlo simulation
    "mc_sims": 1500,                   # number of MC paths
    "perf_equity_multiplier": 1.5,     # yearly refresh-grant uplift at a strong company performance rating
    "perf_base_raise_annual": 0.08,    # ~8% base raise per year
}


def _months_iter(start_ym, count, vest_months):
    """Successive vesting months from start_ym (inclusive), count of them.""" if not True else """Successive vesting months from start_ym (inclusive), count of them."""
    y, m = int(start_ym[:4]), int(start_ym[5:7])
    out = []
    while len(out) < count:
        if m in vest_months:
            out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out


def _next_vest_month(today, vest_months):
    y, m = today.year, today.month
    nm = next((x for x in vest_months if x > m), None)
    if nm is None:
        return f"{y + 1:04d}-{vest_months[0]:02d}"
    return f"{y:04d}-{nm:02d}"


def _grant_shares(value_usd, window_ym, hist):
    """Shares from a grant: value / pricing-window average (or the last close when the window
    has not started yet). Returns (shares, price, source)."""
    last = hist[-1]["close"] if hist else None
    win = [r for r in hist if r["date"].startswith(window_ym or "")]
    avg = round(mean([r["close"] for r in win]), 2) if win else None
    px = avg or last
    if not px or not value_usd:
        return None, px, None
    return int(value_usd / px), px, ("pricing window" if avg else "last close (window not started yet)")


def vest_schedule(grant, hist, months=48, today=None):
    """Vest schedule: how many shares and how much cash-vest land in EVERY future vesting
    month — from the list of grants, not one flat number. Legacy grants EXPIRE
    (legacy_until), new ones START (first_vest), each runs vesting_years × vests_per_year
    tranches. One source for: the RSU view, Cash-flow, Goals, FIRE and Monte Carlo."""
    from datetime import date as _date
    vm = sorted(grant.get("vest_months") or [2, 5, 8, 11])
    vpy = int(grant.get("vests_per_year") or len(vm))
    today = today or grant.get("_today") or _date.today()
    start = _next_vest_month(today, vm)
    horizon = _months_iter(start, max(1, months // 12 * vpy), vm)
    rows = {m: {"month": m, "shares": 0.0, "cash_usd": 0.0, "parts": {}} for m in horizon}
    sources = []

    def add(label, first_vest, n_vests, per_vest, cash_per_vest=0.0):
        months_active = _months_iter(first_vest, n_vests, vm) if first_vest else []
        sources.append({"label": label, "first_vest": months_active[0] if months_active else None,
                         "last_vest": months_active[-1] if months_active else None,
                         "per_vest": round(per_vest, 1), "n_vests": n_vests,
                         "cash_per_vest_usd": cash_per_vest})
        for mth in months_active:
            if mth in rows:
                rows[mth]["shares"] += per_vest
                rows[mth]["cash_usd"] += cash_per_vest
                rows[mth]["parts"][label] = round(per_vest, 1)

    # 1) legacy grants: a flat tranche until legacy_until (missing = open-ended, flagged)
    legacy = float(grant.get("legacy_shares_per_vest") or 0)
    legacy_until = grant.get("legacy_until")
    legacy_open = bool(legacy) and not legacy_until
    if legacy:
        if legacy_until:
            n = sum(1 for m in horizon if m <= legacy_until)
            add("legacy grants", start, n, legacy)
        else:
            add("legacy grants", start, len(horizon), legacy)

    # 2) main (yearly) grant: value / pricing window, first_vest, n_vests tranches
    n_main = int(grant.get("vesting_years") or 4) * vpy
    main_first = grant.get("first_vest") or start
    main_shares, main_px, main_src = _grant_shares(grant.get("grant_value_usd"), grant.get("pricing_window"), hist)
    main_per = (main_shares / n_main) if main_shares else 0.0
    cash_q = float(grant.get("cash_vest_usd_per_quarter") or 0)
    if main_per or cash_q:
        add(f"grant {grant.get('grant_month') or '?'}", main_first, n_main, main_per, cash_q)

    # 3) extra grants (own window, own start)
    extras = []
    for g in grant.get("extra_grants") or []:
        g_sh, g_px, g_src = _grant_shares(g.get("value_usd"), g.get("pricing_window"), hist)
        g_n = int(g.get("vesting_years") or grant.get("vesting_years") or 4) * vpy
        per = (g_sh / g_n) if g_sh else 0.0
        add(g.get("label") or "extra", g.get("first_vest") or main_first, g_n, per)
        extras.append({**g, "priced_at": g_px, "shares_total": g_sh, "shares_per_vest": round(per, 1) if per else None,
                       "n_vests": g_n, "priced_from": g_src,
                       "window_days_counted": len([r for r in hist if r["date"].startswith(g.get("pricing_window") or "")])})

    out = []
    for m in horizon:
        r = rows[m]
        out.append({"month": m, "shares": round(r["shares"], 1), "cash_usd": round(r["cash_usd"], 2), "parts": r["parts"]})
    # broker override: the rsu.json number wins for the NEXT vest until the new grants start vesting
    fixed = grant.get("shares_next_vest") or 0
    if out and fixed and not grant.get("new_grants_vesting"):
        out[0]["shares"] = float(fixed)
        out[0]["parts"] = {"broker": float(fixed)}
    return {"months": out, "sources": sources, "legacy_open_ended": legacy_open,
            "main": {"shares_total": main_shares, "per_vest": round(main_per, 1), "priced_at": main_px,
                     "priced_from": main_src, "first_vest": main_first, "n_vests": n_main},
            "extras": extras}


def _net_factors():
    """Net factors: shares 1−19% (capital gains tax at sale), cash-vest ~55% (income tax + contributions
    on the payslip). Settings: capital_gains_tax_pct (default 19), cash_vest_net_factor (default 0.55)."""
    try:
        from planner import get_setting, _num
        tax = _num(get_setting("capital_gains_tax_pct"))
        cash = _num(get_setting("cash_vest_net_factor"))
    except Exception:
        tax, cash = None, None
    tax = 19.0 if tax is None else tax
    cash = 0.55 if cash is None else cash
    return {"tax_pct": tax, "shares": round(1 - tax / 100, 4), "cash": cash}


def _rsu_vest_stream(grant, hist):
    """Backward compatibility: (extras_computed, extras_per_vest, shares in the NEXT vest)
    — now from the grant schedule (vest_schedule), not a flat sum."""
    sch = vest_schedule(grant, hist)
    nxt = sch["months"][0] if sch["months"] else None
    extras_sh = sum((e.get("shares_per_vest") or 0) for e in sch["extras"])
    return sch["extras"], extras_sh, (nxt["shares"] if nxt else 0.0)


def _shares_per_vest(grant, hist, month=None):
    """Shares landing in a given vest month (default: the next one) — from the schedule.
    `shares_next_vest` from rsu.json (the broker's number) wins for the next vest until
    `new_grants_vesting` is set."""
    sch = vest_schedule(grant, hist)
    if not sch["months"]:
        return int(grant.get("shares_next_vest") or 0)
    if month:
        row = next((r for r in sch["months"] if r["month"] == month), None)
        return int(round(row["shares"])) if row else 0
    return int(round(sch["months"][0]["shares"]))


def get_rsu():
    p = _rsu_path()
    grant = dict(_RSU_DEFAULT)
    if p.exists():
        grant.update(json.loads(p.read_text()))
    auto_sync()
    hist = prices(grant["ticker"], days=400)
    window = [r for r in hist if r["date"].startswith(grant["pricing_window"])]
    avg = round(mean([r["close"] for r in window]), 2) if window else None
    last = hist[-1]["close"] if hist else None
    shares = int(grant["grant_value_usd"] / avg) if avg else None
    est_shares = int(grant["grant_value_usd"] / last) if (not avg and last) else None
    usdpln, usdpln_date = _usd_base_rate()
    last_close_date = hist[-1]["date"] if hist else None
    n_vests = grant["vesting_years"] * grant["vests_per_year"]
    eff_shares = shares or est_shares

    sch = vest_schedule(grant, hist)
    nf = _net_factors()
    nxt = sch["months"][0] if sch["months"] else {"shares": 0.0, "cash_usd": 0.0, "month": None}
    total_per_vest = nxt["shares"]
    old_per_vest = grant.get("legacy_shares_per_vest") or 0
    fx = (usdpln or 0)
    return {
        **grant,
        "extra_grants_computed": sch["extras"],
        "legacy_shares_per_vest": old_per_vest,
        "legacy_until": grant.get("legacy_until"),
        "legacy_open_ended": sch["legacy_open_ended"],
        "vest_schedule": sch["months"][:12],
        "vest_sources": sch["sources"],
        "total_shares_per_vest": round(total_per_vest, 1),
        "total_vest_value_pln": (round(total_per_vest * last * fx, 0) if (last and fx) else None),
        "net_factor": nf["shares"], "tax_pct": nf["tax_pct"], "cash_vest_net_factor": nf["cash"],
        "next_vest_value_net_pln": (round(total_per_vest * last * fx * nf["shares"], 0) if (last and fx) else None),
        "next_cash_vest_usd": nxt["cash_usd"],
        "next_cash_vest_net_pln": (round(nxt["cash_usd"] * fx * nf["cash"], 0) if fx else None),
        "window_days_counted": len(window),
        "window_running_average": avg,
        "last_close": round(last, 2) if last is not None else None,
        "projected_shares": shares,
        "estimate_from_last_close": est_shares,
        "shares_per_vest": round(eff_shares / n_vests, 1) if eff_shares else None,
        "vest_value_usd": round(eff_shares / n_vests * last, 0) if (eff_shares and last) else None,
        "vest_value_pln": round(eff_shares / n_vests * last * usdpln, 0) if (eff_shares and last and usdpln) else None,
        "usdpln": usdpln,
        "last_close_date": last_close_date,
        "usdpln_date": usdpln_date,
        "cache_synced": last_sync(),
        "n_vests": n_vests,
        "sales": rsu_sales(),
        "tax": rsu_tax_summary(),
        **_rsu_holdings({**grant, "_schedule": sch["months"], "_shares_next_vest": int(round(total_per_vest))},
                        last, usdpln),
    }


def fx_to_base(ccy, days=10):
    """Currency → app base currency: 1.0 for the base, USD via _usd_base_rate, others via the
    '<CCY><BASE>=X' pair from the cache (e.g. EURPLN=X). None when no rate (the UI shows it)."""
    from planner import get_setting
    base = (get_setting("base_currency") or "PLN").upper()
    ccy = (ccy or base).upper()
    if ccy == base:
        return 1.0
    if ccy == "USD":
        fx, _ = _usd_base_rate(days)
        return fx
    hist = prices(f"{ccy}{base}=X", days=days)
    return hist[-1]["close"] if hist else None


def refresh_market_rates():
    """Monthly rate refresh (PLN base only): NBP reference rate from the official XML + WIBOR 3M
    from stooq. Writes `market_rates` (asof, nbp_ref, wibor3m; wibor_forecast and typical_margin
    are kept). Returns a dict with 'ok' like every scheduled runner. Other base currencies: skip."""
    import json as _json
    import re as _re
    import urllib.request
    from planner import get_setting, set_settings
    base = (get_setting("base_currency") or "PLN").upper()
    if base != "PLN":
        return {"ok": True, "skipped": f"base {base} — NBP/WIBOR do not apply"}
    try:
        cur = _json.loads(get_setting("market_rates") or "{}")
    except ValueError:
        cur = {}
    out = dict(cur)
    errors = []
    try:
        req = urllib.request.Request("https://static.nbp.pl/dane/stopy/stopy_procentowe.xml",
                                     headers={"User-Agent": "Mozilla/5.0"})
        xml = urllib.request.urlopen(req, timeout=10).read().decode("utf-8", "replace")
        m = _re.search(r'id="ref"[^>]*oprocentowanie="([\d,\.]+)"', xml)
        if m:
            out["nbp_ref"] = float(m.group(1).replace(",", "."))
        else:
            errors.append("NBP: no ref entry in XML")
    except Exception as e:
        errors.append(f"NBP: {str(e)[:60]}")
    try:
        req = urllib.request.Request("https://stooq.pl/q/l/?s=plopln3m&f=sd2t2ohlcv&h&e=csv",
                                     headers={"User-Agent": "Mozilla/5.0"})
        csv = urllib.request.urlopen(req, timeout=10).read().decode("utf-8", "replace").splitlines()
        if len(csv) >= 2:
            cols = csv[1].split(",")
            close = float(cols[6]) if len(cols) > 6 and cols[6] not in ("", "N/D") else None
            if close:
                out["wibor3m"] = round(close, 2)
            else:
                errors.append("stooq: no PLOPLN3M close")
    except Exception as e:
        errors.append(f"stooq: {str(e)[:60]}")
    nbp_ok = any(e.startswith("NBP") for e in errors) is False and "nbp_ref" in out
    wibor_ok = not any(e.startswith("stooq") for e in errors) and "wibor3m" in out
    if nbp_ok:
        # WIBOR 3M has no free API: estimate = reference rate + typical ~0.15 pp spread
        # (a manual `wibor3m` stays; the estimate is stored separately)
        out["wibor3m_est"] = round(out["nbp_ref"] + 0.15, 2)
        if not wibor_ok and not out.get("wibor3m"):
            out["wibor3m"] = out["wibor3m_est"]
            out["wibor3m_source"] = "estimate: NBP ref + 0.15"
        elif wibor_ok:
            out["wibor3m_source"] = "stooq"
    if nbp_ok or wibor_ok:
        out["asof"] = date.today().isoformat()
        out.setdefault("typical_margin", 2.0)
        set_settings({"market_rates": _json.dumps(out)})
    # success = NBP rate refreshed (WIBOR optional: no public API)
    ok = nbp_ok
    res = {"ok": ok, "rates": out}
    if errors:
        res["warning" if ok else "error"] = "; ".join(errors)
    return res




def _usd_base_rate(days=10):
    """FX rate that converts USD amounts into the app's base currency.
    Base USD → 1.0 (no conversion); otherwise the USD<base>=X pair from the
    price cache (e.g. USDPLN=X). Returns (rate, rate_date) — (None, None)
    when the pair has no data yet."""
    from planner import get_setting
    base = (get_setting("base_currency") or "PLN").upper()
    if base == "USD":
        return 1.0, None
    hist = prices(f"USD{base}=X", days=days)
    if hist:
        return hist[-1]["close"], hist[-1]["date"]
    return None, None


def _rsu_holdings(grant, last, usdpln):
    """Holdings, next-vest projection and price-scenario simulation — windows and share counts
    from the grant schedule (`_schedule`), not a flat `nxt × k`."""
    from datetime import date as _date
    held = grant.get("shares_held") or 0
    sched = grant.get("_schedule") or []
    nxt = grant.get("_shares_next_vest", grant.get("shares_next_vest") or 0)
    months = sorted(grant.get("vest_months") or [2, 5, 8, 11])
    today = _date.today()
    next_vest = sched[0]["month"] if sched else _next_vest_month(today, months)
    out = {
        "shares_held": held,
        "shares_next_vest": nxt,
        "next_vest_month": next_vest,
        "shares_after_vest": held + nxt,
    }
    if last and usdpln:
        out["held_value_usd"] = round(held * last, 0)
        out["held_value_pln"] = round(held * last * usdpln, 0)
        out["next_vest_value_pln"] = round(nxt * last * usdpln, 0)
        out["after_vest_value_pln"] = round((held + nxt) * last * usdpln, 0)
        ladder = sorted({max(5.0, round(last * mult / 5) * 5)
                         for mult in (0.5, 0.7, 0.85, 1.0, 1.15, 1.35)})
        out["scenarios"] = [
            {"price": pr,
             "next_vest_pln": round(nxt * pr * usdpln, 0),
             "total_pln": round((held + nxt) * pr * usdpln, 0)}
            for pr in ladder]
        targets = {"bear": grant.get("target_bear") or round(last * 0.65 / 5) * 5,
                   "base": last,
                   "bull": grant.get("target_bull") or round(last * 1.30 / 5) * 5}
        horizon = 8
        windows = [r["month"] for r in sched[:horizon]]
        if len(windows) < horizon:  # no schedule → calendar windows
            windows = _months_iter(_next_vest_month(today, months), horizon, months)
        by_month = {r["month"]: r["shares"] for r in sched}
        proj = []
        shares_cum = held
        for k, month in enumerate(windows, start=1):
            shares_cum += by_month.get(month, nxt)
            row = {"month": month, "shares": round(shares_cum)}
            for kind, tgt in targets.items():
                price = last + (tgt - last) * k / horizon
                row[kind] = round(shares_cum * price * usdpln, 0)
                row[kind + "_price"] = round(price, 1)
            proj.append(row)
        out["projection"] = proj
    return out


def _log_rsu_shares(shares):
    # state log: the user reports HOW MANY shares they hold each month; the
    # app infers vest inflows vs sales from the delta and the vest calendar
    _ensure_cache()
    with db.get_conn() as conn:
        conn.execute("""create table if not exists rsu_shares_log (
            month text primary key, shares real not null, created_at text)""")
        conn.execute("insert or replace into rsu_shares_log (month, shares, created_at) "
                     "values (?,?,?)", (date.today().isoformat()[:7], shares,
                                        datetime.now().isoformat(timespec="seconds")))
        conn.commit()


def rsu_shares_history(grant=None):
    if grant is None:
        p = _rsu_path()
        grant = dict(_RSU_DEFAULT)
        if p.exists():
            grant.update(json.loads(p.read_text()))
    _ensure_cache()
    with db.get_conn() as conn:
        try:
            rows = [dict(r) for r in conn.execute(
                "select month, shares from rsu_shares_log order by month")]
        except Exception:
            rows = []
    vm = set(grant.get("vest_months") or [2, 5, 8, 11])
    hist = prices(grant["ticker"], days=400)
    sch = {r["month"]: r["shares"] for r in vest_schedule(grant, hist)["months"]}
    nxt_default = _shares_per_vest(grant, hist)
    out = []
    prev = None
    for r in rows:
        entry = {"month": r["month"], "shares": r["shares"]}
        if prev is not None:
            delta = r["shares"] - prev
            vest_in = (sch.get(r["month"], nxt_default) if int(r["month"][5:7]) in vm else 0)
            entry["delta"] = round(delta, 0)
            entry["vest_in"] = round(vest_in, 0)
            entry["sold_est"] = round(max(0, prev + vest_in - r["shares"]), 0)
        prev = r["shares"]
        out.append(entry)
    return out


_RSU_EXTRA_KEYS = ("legacy_shares_per_vest", "legacy_until", "extra_grants", "new_grants_vesting",
                   "equity_cash_split_pct", "cash_vest_usd_per_quarter", "first_vest")


def update_rsu(data):
    p = _rsu_path()
    grant = dict(_RSU_DEFAULT)
    if p.exists():
        grant.update(json.loads(p.read_text()))
    for k in list(_RSU_DEFAULT) + list(_RSU_EXTRA_KEYS):
        if k in data:
            grant[k] = data[k]
    p.write_text(json.dumps(grant, indent=2, ensure_ascii=False))
    if "shares_held" in data:
        try:
            _log_rsu_shares(float(data["shares_held"]))
        except Exception:
            pass
    try:  # derived values (wealth snapshot, FIRE, tracker) recompute after an RSU change
        import planner as _pl
        _pl.refresh_derived()
    except Exception:
        pass
    return get_rsu()


# ---------- RSU sales + tax (capital gains) ----------

def _ensure_sales_table(conn):
    conn.execute("""create table if not exists rsu_sales (
        id text primary key, date text not null, shares real not null, price_usd real not null,
        usdpln real not null, gross_pln real not null, note text default '', created_at text)""")


def rsu_sales(year=None):
    _ensure_cache()
    with db.get_conn() as conn:
        _ensure_sales_table(conn)
        q = "select * from rsu_sales" + (" where date like ?" if year else "") + " order by date desc"
        rows = [dict(r) for r in conn.execute(q, ((f"{year}%",) if year else ()))]
    return rows


def log_rsu_sale(data):
    """Log a sale: date, shares, USD price (+ optional USD→base rate; default from the cache).
    Reduces shares_held in rsu.json and logs the month's holdings."""
    import uuid as _uuid
    from datetime import datetime as _dt
    shares = float(data["shares"]); price = float(data["price_usd"])
    fx = data.get("usdpln")
    if not fx:
        fx, _ = _usd_base_rate()
    fx = float(fx or 1.0)
    gross = round(shares * price * fx, 2)
    sid = str(_uuid.uuid4())
    _ensure_cache()
    with db.get_conn() as conn:
        _ensure_sales_table(conn)
        conn.execute("insert into rsu_sales (id, date, shares, price_usd, usdpln, gross_pln, note, created_at) "
                     "values (?,?,?,?,?,?,?,?)",
                     (sid, data.get("date") or date.today().isoformat(), shares, price, fx, gross,
                      data.get("note") or "", _dt.now().isoformat(timespec="seconds")))
        conn.commit()
    if data.get("adjust_holdings", True):
        p = _rsu_path()
        grant = dict(_RSU_DEFAULT)
        if p.exists():
            grant.update(json.loads(p.read_text()))
        held = max(0.0, float(grant.get("shares_held") or 0) - shares)
        update_rsu({"shares_held": int(round(held))})
    return {"id": sid, "gross_pln": gross, "usdpln": fx}


def delete_rsu_sale(sid):
    _ensure_cache()
    with db.get_conn() as conn:
        _ensure_sales_table(conn)
        conn.execute("delete from rsu_sales where id=?", (sid,))
        conn.commit()


def rsu_tax_summary(year=None):
    """Tax on the year's share sales: 19% of the FULL sale amount (incentive plan — cost basis ≈ 0),
    due by 30 April next year. The reserve is a liability in net worth."""
    year = year or date.today().year
    nf = _net_factors()
    rows = rsu_sales(year)
    gross = round(sum(r["gross_pln"] for r in rows), 2)
    shares = round(sum(r["shares"] for r in rows), 1)
    tax = round(gross * nf["tax_pct"] / 100, 0)
    return {"year": year, "shares_sold": shares, "gross_pln": gross, "tax_pct": nf["tax_pct"],
            "tax_due_pln": tax, "deadline": f"{year + 1}-04-30", "sales_count": len(rows)}


# ---------- prediction accuracy: backtest + live tracking ----------

_Z = {0.10: -1.2816, 0.50: 0.0, 0.90: 1.2816}  # normal quantiles


def _bootstrap_price_paths(closes, max_days, sims, sample_idx, drift_annual=0.0, seed=20260717, block=20):
    """Price paths from a BLOCK BOOTSTRAP of real daily returns (blocks of ~20 sessions keep
    volatility clustering and fat tails that GBM cannot see). Returns are DEMEANED (drift 0 —
    a single stock's direction is unpredictable, Meese-Rogoff); `drift_annual` only applies
    after one year, as a long-run assumption. Returns a list per sample point in sample_idx
    with the prices from all simulations."""
    rets = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes)) if closes[i - 1] > 0]
    if len(rets) < 60:
        return None
    mu = sum(rets) / len(rets)
    rets = [r - mu for r in rets]
    rng = random.Random(seed)
    n = len(rets)
    out = [[] for _ in sample_idx]
    want_idx = sorted(range(len(sample_idx)), key=lambda i: sample_idx[i])
    for _ in range(sims):
        s0 = closes[-1]
        logp = math.log(s0)
        d = 0
        w = 0
        while d < max_days and w < len(want_idx):
            start = rng.randrange(0, max(1, n - block))
            for r in rets[start:start + block]:
                logp += r
                if d >= 252:
                    logp += drift_annual / 252.0
                if w < len(want_idx) and d == sample_idx[want_idx[w]]:
                    out[want_idx[w]].append(math.exp(logp))
                    w += 1
                d += 1
                if d >= max_days:
                    break
        while w < len(want_idx):  # close out on rounding
            out[want_idx[w]].append(math.exp(logp))
            w += 1
    return out


def _bootstrap_quantiles(closes, days, sims=400, seed=20260717, drift_annual=0.0):
    """p10/p50/p90 price after `days` sessions from the bootstrap; None when history is too short."""
    paths = _bootstrap_price_paths(closes, days, sims, [days - 1], drift_annual, seed)
    if not paths:
        return None
    ps = sorted(paths[0])
    return {0.10: _percentile(ps, 0.10), 0.50: _percentile(ps, 0.50), 0.90: _percentile(ps, 0.90)}




def _lognormal_price(s0, mu, vol, days, q):
    """Analytic GBM percentile price (no simulation needed)."""
    t = days / 252.0
    return s0 * math.exp((mu - 0.5 * vol * vol) * t + vol * math.sqrt(t) * _Z[q])


def _vol_upto(closes):
    v, _ = _annualized_vol(closes)
    return v or 0.45


def rsu_backtest(grant, horizons=(21, 63)):
    """Walk-forward backtest on cached history — how well the model's bands
    would have held. No lookahead: vol at each start uses only prior closes."""
    hist = prices(grant["ticker"], days=400)
    closes = [r["close"] for r in hist]
    n = len(closes)
    if n < 160:
        return {"status": "not enough history for a backtest"}
    mu = float(grant.get("mc_drift_annual", 0.08))
    out = {}
    for H in horizons:
        rows = []
        # start points every 5 sessions, need 120 trailing + H forward
        for i in range(120, n - H, 5):
            s0 = closes[i]
            q = _bootstrap_quantiles(closes[max(0, i - 260):i + 1], H, sims=300, seed=i)
            if q is None:
                vol = _vol_upto(closes[i - 120:i + 1])
                q = {0.10: _lognormal_price(s0, mu, vol, H, 0.10), 0.50: _lognormal_price(s0, mu, vol, H, 0.50),
                     0.90: _lognormal_price(s0, mu, vol, H, 0.90)}
            p10, p50, p90 = q[0.10], q[0.50], q[0.90]
            actual = closes[i + H]
            rows.append({
                "in_band": p10 <= actual <= p90,
                "dir_correct": (actual >= s0) == (p50 >= s0),
                "abs_err_pct": abs(actual - p50) / actual * 100,
            })
        if not rows:
            continue
        cov = 100 * sum(r["in_band"] for r in rows) / len(rows)
        dirp = 100 * sum(r["dir_correct"] for r in rows) / len(rows)
        errs = sorted(r["abs_err_pct"] for r in rows)
        med_err = errs[len(errs) // 2]
        out[f"h{H}"] = {
            "horizon_days": H,
            "n": len(rows),
            "band_coverage_pct": round(cov),
            "directional_pct": round(dirp),
            "median_abs_err_pct": round(med_err, 1),
        }
    # realized vs assumed drift over full sample
    realized = None
    if n > 1:
        yrs = n / 252.0
        realized = round((math.log(closes[-1] / closes[0]) / yrs) * 100, 1)
    out["assumed_drift_pct"] = 0.0  # demeaned bootstrap: drift 0 for horizons < 1 year
    out["realized_drift_pct"] = realized
    out["method"] = "block bootstrap of real returns (drift 0, 20-session blocks)"
    out["source"] = f"{hist[0]['date']} → {hist[-1]['date']}"
    return out


def _record_forward_snapshot(grant, closes_hist):
    """Once/day: store live predictions (5/21/63 sessions) for later scoring."""
    import db as _db
    from planner import _now
    today = date.today().isoformat()
    with _db.get_conn() as conn:
        exists = conn.execute(
            "select 1 from rsu_predictions where made_on=? limit 1", (today,)).fetchone()
        if exists:
            return
        closes = [r["close"] for r in closes_hist]
        s0 = closes[-1]
        vol = _vol_upto(closes)
        mu = float(grant.get("mc_drift_annual", 0.08))
        dates = [r["date"] for r in closes_hist]
        for H in (5, 21, 63):
            # approximate calendar target date
            import datetime as _dt
            td = (_dt.date.fromisoformat(today) + _dt.timedelta(days=round(H * 1.4))).isoformat()
            q = _bootstrap_quantiles(closes, H, sims=400) or {
                0.10: _lognormal_price(s0, mu, vol, H, 0.10), 0.50: _lognormal_price(s0, mu, vol, H, 0.50),
                0.90: _lognormal_price(s0, mu, vol, H, 0.90)}
            conn.execute(
                "insert into rsu_predictions (id, made_on, ticker, price_now, "
                "horizon_days, target_date, p10, p50, p90) values (?,?,?,?,?,?,?,?,?)",
                (f"{today}-{H}", today, grant["ticker"], s0, H, td,
                 round(q[0.10], 2), round(q[0.50], 2), round(q[0.90], 2)))
        conn.commit()


def _score_forward(closes_hist):
    """Score matured predictions against actual cached prices."""
    import db as _db
    today = date.today().isoformat()
    by_date = {r["date"]: r["close"] for r in closes_hist}
    all_dates = sorted(by_date)
    with _db.get_conn() as conn:
        rows = conn.execute(
            "select id, price_now, p10, p50, p90, target_date from rsu_predictions "
            "where scored=0 and target_date<=?", (today,)).fetchall()
        for pid, s0, p10, p50, p90, tdate in rows:
            # nearest available close on/after target_date
            actual = by_date.get(tdate)
            if actual is None:
                later = [d for d in all_dates if d >= tdate]
                if not later:
                    continue
                actual = by_date[later[0]]
            conn.execute(
                "update rsu_predictions set scored=1, actual=?, in_band=?, "
                "dir_correct=?, abs_err_pct=? where id=?",
                (actual, int(p10 <= actual <= p90),
                 int((actual >= s0) == (p50 >= s0)),
                 round(abs(actual - p50) / actual * 100, 2), pid))
        conn.commit()


def _live_track_record():
    import db as _db
    with _db.get_conn() as conn:
        scored = conn.execute(
            "select in_band, dir_correct, abs_err_pct from rsu_predictions "
            "where scored=1").fetchall()
        first = conn.execute(
            "select min(made_on), count(*) from rsu_predictions").fetchone()
    if not scored:
        return {"status": "zbieram dane", "tracked_since": first[0] if first else None,
                "predictions_made": first[1] if first else 0, "scored": 0}
    n = len(scored)
    cov = round(100 * sum(r[0] for r in scored) / n)
    dirp = round(100 * sum(r[1] for r in scored) / n)
    errs = sorted(r[2] for r in scored)
    return {
        "scored": n, "band_coverage_pct": cov, "directional_pct": dirp,
        "directional_note": "direction on a random walk is a coin flip — we grade the bands, not the direction",
        "median_abs_err_pct": round(errs[len(errs) // 2], 1),
        "tracked_since": first[0], "predictions_made": first[1],
    }


def rsu_accuracy(grant=None):
    if grant is None:
        p = _rsu_path()
        grant = dict(_RSU_DEFAULT)
        if p.exists():
            grant.update(json.loads(p.read_text()))
    hist = prices(grant["ticker"], days=400)
    if not hist:
        return {"error": "brak danych"}
    try:
        _record_forward_snapshot(grant, hist)
        _score_forward(hist)
    except Exception:
        pass  # tracking is best-effort
    return {"backtest": rsu_backtest(grant), "live": _live_track_record()}


# ---------- advanced RSU: Monte Carlo + comp trajectory ----------

def _annualized_vol(closes):
    """Annualized volatility from daily log returns."""
    rets = [math.log(closes[i] / closes[i - 1])
            for i in range(1, len(closes)) if closes[i - 1] > 0]
    if len(rets) < 20:
        return None, None
    daily = pstdev(rets)
    return round(daily * math.sqrt(252), 4), round(mean(rets) * 252, 4)


def _percentile(sorted_vals, q):
    if not sorted_vals:
        return None
    idx = q * (len(sorted_vals) - 1)
    lo = int(math.floor(idx))
    hi = int(math.ceil(idx))
    if lo == hi:
        return sorted_vals[lo]
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (idx - lo)


def rsu_advanced():
    """Probabilistic RSU trajectory: Monte Carlo price paths on real
    volatility + analyst anchors + performance-scaled grant accumulation."""
    p = _rsu_path()
    grant = dict(_RSU_DEFAULT)
    if p.exists():
        grant.update(json.loads(p.read_text()))
    ticker = grant["ticker"]
    hist = prices(ticker, days=400)
    if not hist:
        return {"error": "no RSU price data — refresh the market cache"}
    closes = [r["close"] for r in hist]
    last = closes[-1]
    usdpln, _ = _usd_base_rate()
    usdpln = usdpln or 1.0

    vol, hist_drift = _annualized_vol(closes)
    vol = vol or 0.45
    hi_52w = max(closes[-252:])
    lo_52w = min(closes[-252:])
    sma50 = _sma(closes, 50)
    sma200 = _sma(closes, 200)

    held = grant.get("shares_held") or 0
    nxt = _shares_per_vest(grant, hist)
    vm = sorted(grant.get("vest_months") or [2, 5, 8, 11])
    today = date.today()

    # next 8 vest windows FROM THE GRANT SCHEDULE (legacy grants expire, new ones start)
    sch = vest_schedule(grant, hist)["months"]
    windows = []
    for r in sch[:8]:
        y, m = int(r["month"][:4]), int(r["month"][5:7])
        months_ahead = (y - today.year) * 12 + (m - today.month)
        windows.append({"month": r["month"], "months_ahead": max(1, months_ahead), "shares_in": r["shares"]})
    while len(windows) < 8:  # no schedule → calendar + flat nxt
        y, m = (today.year, today.month) if not windows else (int(windows[-1]["month"][:4]), int(windows[-1]["month"][5:7]))
        nm = next((x for x in vm if x > m), None)
        if nm is None:
            y += 1
            nm = vm[0]
        m = nm
        months_ahead = (y - today.year) * 12 + (m - today.month)
        windows.append({"month": f"{y:04d}-{m:02d}", "months_ahead": max(1, months_ahead), "shares_in": nxt})

    # Monte Carlo GBM on price
    drift = float(grant.get("mc_drift_annual", 0.08))
    sims = int(grant.get("mc_sims", 1500))
    dt = 1.0 / 252.0
    max_days = windows[-1]["months_ahead"] * 21
    sample_idx = [w["months_ahead"] * 21 - 1 for w in windows]
    # block bootstrap of real returns (drift 0 up to a year, then mc_drift_annual) — the same
    # method as the backtest and the forecast journal; GBM with a fixed 8% drift covered 53–68%
    price_samples = _bootstrap_price_paths(closes, max_days, sims, sample_idx, drift_annual=drift)
    method = "block bootstrap of real returns"
    if price_samples is None:  # too little history → GBM as before
        method = "GBM (short history)"
        rng = random.Random(20260717)
        price_samples = [[] for _ in windows]
        for _ in range(sims):
            s = last
            want = 0
            for d in range(max_days):
                z = rng.gauss(0, 1)
                s *= math.exp((drift - 0.5 * vol * vol) * dt + vol * math.sqrt(dt) * z)
                if want < len(sample_idx) and d == sample_idx[want]:
                    price_samples[want].append(s)
                    want += 1
            while want < len(sample_idx):
                price_samples[want].append(s)
                want += 1

    # performance-scaled share accumulation: existing refresh grants deliver
    # `nxt`/quarter; each new annual grant (~grant_month) adds shares scaled by
    # perf multiplier. Approximate uplift: +perf% to per-quarter after 1 year.
    perf = float(grant.get("perf_equity_multiplier", 1.5))
    # hypothetical FUTURE yearly grants (not in rsu.json yet): every year in grant_month a new grant
    # worth grant_value_usd × perf at today's price, vesting in 16 tranches from the first vest after
    # the award — that is "perf", not a ×k multiplier
    gm = int((grant.get("grant_month") or f"{today.year}-09")[5:7])
    n_v = int(grant.get("vesting_years") or 4) * int(grant.get("vests_per_year") or 4)
    future_per_vest = ((float(grant.get("grant_value_usd") or 0) * perf / last) / n_v) if last else 0
    future_starts = []
    for yr in range(today.year + 1, today.year + 6):
        fv = _months_iter(f"{yr:04d}-{gm:02d}", 1, vm)[0]
        future_starts.append(fv)
    proj = []
    shares_base = held
    shares_perf = held
    for k, w in enumerate(windows, start=1):
        shares_base += w["shares_in"]
        extra = sum(future_per_vest for fs in future_starts if fs <= w["month"])
        shares_perf = shares_base + extra
        ps = sorted(price_samples[k - 1])
        row = {
            "month": w["month"],
            "months_ahead": w["months_ahead"],
            "shares_base": round(shares_base),
            "shares_perf": round(shares_perf),
            "shares_in": round(w["shares_in"], 1),
            "p10_price": round(_percentile(ps, 0.10), 1),
            "p50_price": round(_percentile(ps, 0.50), 1),
            "p90_price": round(_percentile(ps, 0.90), 1),
        }
        for tag, q in (("p10", 0.10), ("p25", 0.25), ("p50", 0.50),
                       ("p75", 0.75), ("p90", 0.90)):
            price = _percentile(ps, q)
            row[tag] = round(shares_base * price * usdpln, 0)
            row[tag + "_perf"] = round(shares_perf * price * usdpln, 0)
        # analyst anchors (discrete fundamental view, not vol-driven)
        for tag, tprice in (("bear", grant.get("target_bear") or round(last * 0.65 / 5) * 5),
                            ("mid", grant.get("analyst_target_mid") or last),
                            ("bull", grant.get("target_bull") or round(last * 1.30 / 5) * 5)):
            # linear drift from today to target over 12 months, capped at window
            frac = min(1.0, w["months_ahead"] / 12.0)
            aprice = last + (tprice - last) * frac
            row[tag + "_analyst"] = round(shares_base * aprice * usdpln, 0)
        proj.append(row)

    prob_above_current = None
    # P(price at 1yr window >= today) as a simple confidence read
    one_yr = next((i for i, w in enumerate(windows) if w["months_ahead"] >= 12), None)
    if one_yr is not None:
        ups = sum(1 for pr in price_samples[one_yr] if pr >= last)
        prob_above_current = round(100 * ups / len(price_samples[one_yr]))

    accuracy = rsu_accuracy(grant)

    return {
        "ticker": ticker,
        "last_close": round(last, 2),
        "last_date": hist[-1]["date"],
        "usdpln": usdpln,
        "accuracy": accuracy,
        "vol_annual_pct": round(vol * 100, 1),
        "hist_drift_annual_pct": round(hist_drift * 100, 1) if hist_drift else None,
        "high_52w": round(hi_52w, 2),
        "low_52w": round(lo_52w, 2),
        "pos_in_52w_pct": round(100 * (last - lo_52w) / (hi_52w - lo_52w)) if hi_52w > lo_52w else None,
        "sma50": sma50,
        "sma200": sma200,
        "trend": ("above SMA50 and SMA200" if (sma50 and sma200 and last > sma50 > sma200)
                  else "below SMA50" if (sma50 and last < sma50) else "mixed"),
        "drift_annual_pct": round(drift * 100, 1),
        "method": method,
        "tax_pct": _net_factors()["tax_pct"],
        "sims": sims,
        "prob_above_current_1y_pct": prob_above_current,
        "analyst": {"bear": grant.get("target_bear") or round(last * 0.65 / 5) * 5,
                    "mid": grant.get("analyst_target_mid") or last,
                    "bull": grant.get("target_bull") or round(last * 1.30 / 5) * 5},
        "perf_equity_multiplier": perf,
        "perf_base_raise_annual": grant.get("perf_base_raise_annual"),
        "shares_held": held,
        "shares_next_vest": nxt,
        "projection": proj,
    }


# ---------- deep FX analysis (trend + momentum + backtest) ----------

_FX_PAIRS = [
    {"pair": "USDPLN=X", "title": "USD/PLN", "conv": "USD → PLN (vest → overpayment/spending)",
     "favorable": "high", "why_fav": "you are selling USD, so the higher the better"},
    {"pair": "EURUSD=X", "title": "EUR/USD", "conv": "USD → EUR (vest → house down payment)",
     "favorable": "low", "why_fav": "you are buying EUR with USD, so the lower EUR/USD the more EUR"},
    {"pair": "EURPLN=X", "title": "EUR/PLN", "conv": "PLN → EUR (house down payment from zloty)",
     "favorable": "low", "why_fav": "you are buying EUR with PLN, so the lower the better"},
]


def _fx_one(cfg):
    hist = prices(cfg["pair"], days=400)
    if len(hist) < 60:
        return {"pair": cfg["pair"], "title": cfg["title"], "error": "not enough data — this pair needs daily quotes in your local cache; connect a sync (README \u203a Connecting your own services) or wait for the nightly one"}
    closes = [r["close"] for r in hist]
    last = closes[-1]
    fav_high = cfg["favorable"] == "high"
    hi = max(closes[-252:]); lo = min(closes[-252:])
    pos = round(100 * (last - lo) / (hi - lo)) if hi > lo else 50
    sma20, sma50, sma200 = _sma(closes, 20), _sma(closes, 50), _sma(closes, 200)
    mom30 = round((last / closes[-22] - 1) * 100, 2) if len(closes) > 22 else 0
    mom90 = round((last / closes[-64] - 1) * 100, 2) if len(closes) > 64 else 0
    dist50 = round((last / sma50 - 1) * 100, 2) if sma50 else 0
    # trend
    if sma50 and sma200:
        if last > sma50 > sma200:
            trend = "up"
        elif last < sma50 < sma200:
            trend = "down"
        else:
            trend = "sideways/mixed"
    else:
        trend = "?"
    # „favorable position": jak blisko korzystnego skraju (0-100, 100 = idealny moment poziomowo)
    fav_pos = pos if fav_high else (100 - pos)
    # does trend/momentum push FURTHER the favorable way (i.e. worth waiting)?
    # for fav_high: favorable=higher; if momentum positive and trend up -> may rise -> wait
    pushing_further = ((mom30 > 0.5 and trend == "up") if fav_high
                       else (mom30 < -0.5 and trend == "down"))
    # overshoot vs SMA50 (mean-reversion): favorable extreme + deviation = now
    overshoot = (dist50 > 1.5) if fav_high else (dist50 < -1.5)

    reasons = []
    score = 0
    if fav_pos >= 70:
        score += 2; reasons.append(f"Favorable level: {fav_pos}/100 in the 52-week range (price {'high' if fav_high else 'low'}).")
    elif fav_pos <= 35:
        score -= 2; reasons.append(f"UNfavorable level: {fav_pos}/100 — price on the wrong side of the range.")
    else:
        reasons.append(f"Neutral level: {fav_pos}/100 in the 52-week range.")
    if pushing_further:
        score -= 1
        reasons.append(f"⚠️ Trend {trend} + 30d momentum {mom30:+}% is pushing the rate FURTHER in your favor — it may get even better; risk of selling at a false top. Consider splitting the tranche.")
    else:
        reasons.append(f"Trend {trend}, momentum 30d {mom30:+}% / 90d {mom90:+}% — no strong further move, the level is more reliable.")
    if overshoot:
        score += 1
        reasons.append(f"Deviation {dist50:+}% from SMA50 — the rate is stretched, favors a reversal (mean-reversion) = act now.")

    if score >= 3:
        verdict = "Good moment — act (consider the full amount)"; vcls = "pos"
    elif score >= 1:
        verdict = "Moderately favorable — consider part of the tranche now"; vcls = ""
    elif score <= -2:
        verdict = "Unfavorable — wait"; vcls = "neg"
    else:
        verdict = "Neutral — no rush / split it"; vcls = "muted"

    bt = _fx_backtest(closes, fav_high)
    return {
        "pair": cfg["pair"], "title": cfg["title"], "conv": cfg["conv"], "why_fav": cfg["why_fav"],
        "last": round(last, 4), "pos": pos, "fav_pos": fav_pos, "trend": trend,
        "mom30": mom30, "mom90": mom90, "dist50": dist50,
        "sma50": sma50, "sma200": sma200, "hi_52w": round(hi, 4), "lo_52w": round(lo, 4),
        "verdict": verdict, "vcls": vcls, "reasons": reasons, "backtest": bt,
    }


def _fx_backtest(closes, fav_high, horizon=21):
    """Did the 'favorable level' signal actually catch good moments?
    Measures: after a signal, how the rate moved over ~a month (in your favor = bad,
    you could have waited; against you = good, you caught the extreme)."""
    n = len(closes)
    win = 120  # shorter window (FX data ~1 year) — more testable points
    hits = 0; total = 0; fwd_sum = 0.0
    for i in range(win, n - horizon):
        window = closes[i - win:i + 1]
        hi = max(window); lo = min(window)
        if hi <= lo:
            continue
        p = 100 * (closes[i] - lo) / (hi - lo)
        favp = p if fav_high else (100 - p)
        if favp >= 70:  # 'favorable level' signal
            total += 1
            fwd = (closes[i + horizon] / closes[i] - 1) * 100
            # 'in your favor' further = fwd>0 when fav_high (rate kept rising -> could have waited)
            moved_further = fwd > 0 if fav_high else fwd < 0
            if not moved_further:
                hits += 1  # rate pulled back = good, you caught a good moment
            fwd_sum += (fwd if fav_high else -fwd)
    if total < 5:
        return {"status": "not enough signals in history", "n": total}
    return {"status": "ok", "n": total,
            "hit_rate": round(100 * hits / total),
            "avg_fwd_move": round(fwd_sum / total, 2)}


def fx_analysis():
    return {"pairs": [_fx_one(c) for c in _FX_PAIRS]}


# ---------- self-learning forecast journal (conformal) ----------

def _ft_rows(q, params=()):
    with db.get_conn() as conn:
        cur = conn.execute(q, params)
        cols = [c[0] for c in cur.description] if cur.description else []
        return [dict(zip(cols, r)) for r in cur.fetchall()]


def forecast_residuals(ticker, window=120):
    """Normalized errors of settled forecasts per horizon (for calibration) — a ROLLING
    WINDOW of the last `window` settlements PER HORIZON (before: 400 rows in total, so the
    63-day horizon got leftovers and an old regime weighed as much as the current one)."""
    rows = _ft_rows("select horizon_days, resid_z from forecast_track "
                    "where ticker=? and resid_z is not null "
                    "order by made_on desc limit 1200", (ticker,))
    out = {}
    for r in rows:
        lst = out.setdefault(r["horizon_days"], [])
        if len(lst) < window:
            lst.append(r["resid_z"])
    return out


def vol_regime():
    """Sigma multiplier from the latest VIX close in the cache (risk radar):
    <20 → 1.0; 20–30 → 1.15; >30 → 1.3. Simple, explicit, testable — instead of a GARCH."""
    vix = None
    try:
        px = prices("^VIX", days=7)
        vix = px[-1]["close"] if px else None
    except Exception:
        vix = None
    if vix is None:
        return {"factor": 1.0, "vix": None, "label": "no VIX (1.00)"}
    f = 1.0 if vix < 20 else 1.15 if vix < 30 else 1.3
    return {"factor": f, "vix": round(vix, 1), "label": f"VIX {vix:.0f} → ×{f:.2f}"}


def record_and_score_forecasts():
    """Daily self-learning cycle: (1) settle matured forecasts against real
    prices, (2) store today's bands for the whole watchlist.
    Called on data refresh and from health()."""
    import forecast_models as fm
    _ensure_cache()
    tickers = [t["ticker"] for t in get_watchlist()]
    scored = recorded = 0
    reg = vol_regime()["factor"]
    for tk in tickers:
        hist = prices(tk, days=600)
        if len(hist) < 60:
            continue
        closes = [h["close"] for h in hist]
        dates = [h["date"] for h in hist]
        idx = {d: i for i, d in enumerate(dates)}
        # 1) settle matured
        for row in _ft_rows("select * from forecast_track where ticker=? "
                            "and realized_close is null", (tk,)):
            i0 = idx.get(row["made_on"])
            if i0 is None or i0 + row["horizon_days"] >= len(closes):
                continue
            i1 = i0 + row["horizon_days"]
            real = closes[i1]
            base, sig = row["base_close"], row["sigma_daily"]
            if not base or not sig:
                continue
            move = math.log(real / base)
            s_n = sig * math.sqrt(row["horizon_days"])
            with db.get_conn() as conn:
                conn.execute("update forecast_track set realized_close=?, realized_on=?, "
                             "inside=?, resid_z=? where id=?",
                             (real, dates[i1],
                              1 if row["p10"] <= real <= row["p90"] else 0,
                              round(move / s_n, 4) if s_n else None, row["id"]))
                conn.commit()
            scored += 1
        # 2) store today's bands (calibrated with own errors when available)
        today = dates[-1]
        bands = fm.short_term_bands_calibrated(closes, forecast_residuals(tk), vol_regime=reg)
        if not bands:
            continue
        sig_d = bands["ewma_vol_daily_pct"] / 100.0
        for h in bands["horizons"]:
            with db.get_conn() as conn:
                conn.execute("insert or ignore into forecast_track "
                             "(made_on, ticker, horizon_days, base_close, sigma_daily, p10, p50, p90, calibrated) "
                             "values (?,?,?,?,?,?,?,?,?)",
                             (today, tk, h["days"], bands["last_close"], sig_d,
                              h["p10"], h["p50"], h["p90"], 1 if h.get("calibrated") else 0))
                conn.commit()
            recorded += 1
    return {"scored": scored, "recorded": recorded, "tickers": len(tickers), "vol_regime": reg}


def forecast_calibration():
    """Calibration per ticker × horizon: coverage, miss direction, Winkler, share of
    self-calibrated forecasts. Answers "which ticker and which horizon is off, and are
    the bands too narrow or too wide" instead of one global coverage number."""
    import forecast_models as fm
    rows = _ft_rows("select ticker, horizon_days, p10, p90, base_close, realized_close, "
                    "coalesce(calibrated,0) calibrated, made_on from forecast_track "
                    "where realized_close is not null order by ticker, horizon_days, made_on")
    groups = {}
    for r in rows:
        groups.setdefault((r["ticker"], r["horizon_days"]), []).append(r)
    by_ticker = []
    for (tk, h), rs in sorted(groups.items()):
        sc = fm.interval_scores(rs)
        if not sc:
            continue
        cal = [r for r in rs if r["calibrated"]]
        sc_cal = fm.interval_scores(cal) if len(cal) >= 10 else None
        by_ticker.append({"ticker": tk, "horizon_days": h, **sc,
                          "calibrated_n": len(cal),
                          "calibrated_coverage_pct": sc_cal["coverage_pct"] if sc_cal else None,
                          "first": rs[0]["made_on"], "last": rs[-1]["made_on"]})
    by_h = {}
    for r in rows:
        by_h.setdefault(r["horizon_days"], []).append(r)
    by_horizon = []
    for h, rs in sorted(by_h.items()):
        sc = fm.interval_scores(rs)
        if sc:
            by_horizon.append({"horizon_days": h, **sc})
    return {"by_ticker": by_ticker, "by_horizon": by_horizon, "regime": vol_regime(),
            "target_pct": 80, "total_scored": len(rows)}


def forecast_selfscore():
    """Own accuracy: band coverage per horizon (target ~80%) + count."""
    rows = _ft_rows("select horizon_days h, count(*) n, sum(inside) k "
                    "from forecast_track where inside is not null group by horizon_days")
    out = {"horizons": [], "total_scored": 0}
    for r in rows:
        cov = round(r["k"] / r["n"] * 100, 1) if r["n"] else None
        out["horizons"].append({"days": r["h"], "scored": r["n"], "coverage_pct": cov,
                                "target_pct": 80,
                                "verdict": "ok" if cov and 70 <= cov <= 92 else "calibrating"})
        out["total_scored"] += r["n"]
    pend = _ft_rows("select count(*) c from forecast_track where inside is null")
    out["pending"] = pend[0]["c"] if pend else 0
    return out


def ticker_bands(ticker):
    """Short-term bands for a ticker, self-calibrated when we have enough settlements."""
    import forecast_models as fm
    hist = prices(ticker, days=600)
    closes = [h["close"] for h in hist]
    if len(closes) < 60:
        return {"error": "not enough history"}
    reg = vol_regime()
    out = fm.short_term_bands_calibrated(closes, forecast_residuals(ticker), vol_regime=reg["factor"])
    out["regime"] = reg
    out["coverage"] = fm.short_term_coverage_backtest(closes, 21)
    return out


def backfill_forecasts(step=5):
    """Jednorazowe zasilenie dziennika: prognozy walk-forward wstecz po historii
    (only data available on that day), settled immediately. This lets the
    conformal calibration start with real material instead of waiting a quarter."""
    import forecast_models as fm
    _ensure_cache()
    added = 0
    for t in get_watchlist():
        tk = t["ticker"]
        hist = prices(tk, days=600)
        closes = [h["close"] for h in hist]
        dates = [h["date"] for h in hist]
        if len(closes) < 140:
            continue
        for i in range(100, len(closes) - 5, step):
            window = closes[:i + 1]
            bands = fm.short_term_bands(window)
            if not bands:
                continue
            sig_d = bands["ewma_vol_daily_pct"] / 100.0
            for h in bands["horizons"]:
                if i + h["days"] >= len(closes):
                    continue
                with db.get_conn() as conn:
                    cur = conn.execute(
                        "insert or ignore into forecast_track "
                        "(made_on, ticker, horizon_days, base_close, sigma_daily, p10, p50, p90) "
                        "values (?,?,?,?,?,?,?,?)",
                        (dates[i], tk, h["days"], window[-1], sig_d,
                         h["p10"], h["p50"], h["p90"]))
                    conn.commit()
                    added += cur.rowcount
    score = record_and_score_forecasts()
    return {"backfilled": added, **score}


# ---------- market brief: daily/weekly, generated by the LOCAL model ----------

BRIEF_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["headline", "highlights", "positions"],
    "properties": {
        "headline": {"type": "string"},
        "highlights": {"type": "array", "maxItems": 4, "items": {
            "type": "object", "additionalProperties": False,
            "required": ["icon", "title", "text"],
            "properties": {"icon": {"type": "string"}, "title": {"type": "string"},
                           "text": {"type": "string"}}}},
        "positions": {"type": "array", "maxItems": 8, "items": {
            "type": "object", "additionalProperties": False,
            "required": ["ticker", "stance", "text"],
            "properties": {"ticker": {"type": "string"},
                           "stance": {"type": "string"},
                           "text": {"type": "string"}}}},
    },
}

BRIEF_KEYS = {"daily": "analysis_market_brief_daily", "weekly": "analysis_market_brief"}


def _brief_facts(days):
    """Plain-text facts from the local cache: per-ticker move over the window
    plus the risk-radar state — everything the model needs, nothing it must invent."""
    lines = []
    for t in get_watchlist():
        tk = t["ticker"] if isinstance(t, dict) else t
        try:
            px = prices(tk, days=days + 5)
            if len(px) < 2:
                continue
            last, first = px[-1]["close"], px[max(0, len(px) - 1 - days)]["close"]
            chg = round(100 * (last - first) / first, 1) if first else 0
            lines.append(f"{tk}: close {round(last, 2)}, {chg:+}% over {days}d")
        except Exception:
            continue
    try:
        import risk_radar
        r = risk_radar.compute()
        lines.append(f"risk radar: {r['state']} ({r['score']}/{r['max_score']})")
    except Exception:
        pass
    return lines


def generate_brief(kind="daily"):
    """Ask the LOCAL model for a brief grounded in cached quotes (schema-locked
    JSON). Stored under the kind's settings key; offline AI → ok:False and the
    stored brief stays untouched."""
    import llm_local
    from planner import set_settings
    days = 1 if kind == "daily" else 7
    facts = _brief_facts(days)
    if not facts:
        return {"ok": False, "error": "no cached quotes — add tickers / connect a sync"}
    horizon = "the past trading day" if kind == "daily" else "the past week"
    prompt = ("Write a market brief covering " + horizon + " for a calm long-term investor, "
              "based ONLY on these facts (no invented numbers):\n" + "\n".join(facts) +
              "\nheadline: one sentence. highlights: up to 4 key moves/observations. "
              "positions: a stance (hold/add/trim/watch) per ticker with one-line rationale.")
    system = "You are a concise market analyst. No disclaimers."
    # engine per the Control AI mode: 'both' tries the cloud model first
    # (richer synthesis), local is the always-there fallback — same policy as
    # every other AI feature in the app
    from planner import get_setting
    data, by = None, None
    if (get_setting("ai_mode") or "local") == "both":
        try:
            import llm_cloud
            raw = llm_cloud.chat(prompt + "\nReturn ONLY valid JSON with keys: "
                                 "headline (str), highlights ([{icon,title,text}]), "
                                 "positions ([{ticker,stance,text}]). No prose.",
                                 system=system)
            if raw:
                cand = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
                if cand.get("headline"):
                    data, by = cand, llm_cloud.status().get("model", "Claude")
        except Exception:
            data = None
    if data is None:
        data = llm_local.chat_json(prompt, BRIEF_SCHEMA, system=system,
                                   max_tokens=900, think=True)
        by = llm_local.status().get("model", "local model")
    if not data:
        return {"ok": False, "error": "AI offline — start llama-server (Control → AI mode)"}
    data["as_of"] = datetime.now().strftime("%Y-%m-%d, %H:%M")
    # date of the actual data (last cached candle) — without it "as of" implies
    # the insights include today's session even when the collector hasn't run yet
    try:
        with db.get_conn() as _c:
            _row = _c.execute("select max(date) from market_prices_cache").fetchone()
        data["data_through"] = _row[0] if _row and _row[0] else ""
    except Exception:
        data["data_through"] = ""
    data["kind"] = kind
    data["generated_by"] = by
    set_settings({BRIEF_KEYS[kind]: json.dumps(data, ensure_ascii=False)})
    return {"ok": True, "brief": data}


def get_briefs():
    from planner import get_setting
    out = {}
    for kind, key in BRIEF_KEYS.items():
        try:
            out[kind] = json.loads(get_setting(key) or "null")
        except Exception:
            out[kind] = None
    return out



# Closed set of ranges accepted by the Yahoo chart API plus a narrow allow-list
# of ticker characters (letters/digits and `.-=^` from symbols like BTC-USD,
# ^GSPC, EURUSD=X, CL=F). Both inputs (`ticker` from the path, `range_` from the
# request body) are request-controlled — these two constants turn them into
# closed enumerations so they cannot inject a foreign host, path or extra query
# parameters into the outbound URL (SSRF / parameter smuggling).
_YF_RANGES = frozenset(
    {"1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "ytd", "max"})
_YF_TICKER_RE = re.compile(r"^[A-Za-z0-9.\-=^]{1,20}$")
_YF_CHART_BASE = "https://query1.finance.yahoo.com/v8/finance/chart/"


def _yf_chart_url(ticker, range_="1y"):
    """Build the keyless Yahoo chart URL with ENFORCED invariants: fixed
    scheme+host, ticker restricted to the character allow-list (no `/`, `@`,
    `:`, CR/LF → no host/path injection), range restricted to Yahoo's closed set
    (no query-param smuggling). A ticker outside the allow-list is rejected
    (ValueError); an unknown `range_` silently falls back to the safe default `1y`."""
    t = (ticker or "").strip().upper()
    if not _YF_TICKER_RE.match(t):
        raise ValueError("invalid ticker for Yahoo fetch: %r" % (ticker,))
    r = range_ if range_ in _YF_RANGES else "1y"
    return (_YF_CHART_BASE + urllib.parse.quote(t, safe="")
            + f"?range={r}&interval=1d")


def fetch_yahoo_history(ticker, range_="1y"):
    """Keyless Yahoo history for ANY ticker (public data) → market_prices_cache,
    so charts/indicators have depth even for symbols the nightly sync doesn't
    cover (e.g. the risk-radar commodities/FX). Returns the number of rows stored."""
    import json as _json
    import urllib.request
    try:
        url = _yf_chart_url(ticker, range_)
    except ValueError:
        return 0
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            data = _json.loads(r.read())["chart"]["result"][0]
        stamps = data.get("timestamp") or []
        quote = (data.get("indicators", {}).get("quote") or [{}])[0]
        closes = quote.get("close") or []
        currency = (data.get("meta") or {}).get("currency", "USD")
    except Exception:
        return 0
    from datetime import datetime, timezone
    n = 0
    _ensure_cache()
    with db.get_conn() as conn:
        for ts, close in zip(stamps, closes):
            if close is None:
                continue
            d = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
            conn.execute("insert or replace into market_prices_cache (ticker, date, close, currency) "
                         "values (?,?,?,?)", (ticker.upper(), d, float(close), currency))
            n += 1
    return n
