"""Market data: Supabase reader (public prices), local cache, watchlist,
analytics and RSU tracker. Personal data (amounts, targets, grant) stays local.
"""
import json
import math
import os
import random
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


def refresh_cache():
    """Pull all market_prices rows from Supabase into the local cache.
    Paginated — Supabase caps a single response at 1000 rows."""
    _ensure_cache()
    rows, offset = [], 0
    while True:
        batch = _supabase_get(
            "market_prices?select=ticker,date,close,currency&order=date.asc"
            f"&limit=1000&offset={offset}")
        rows.extend(batch)
        if len(batch) < 1000:
            break
        offset += 1000
    with db.get_conn() as conn:
        for r in rows:
            conn.execute(
                "insert or replace into market_prices_cache (ticker,date,close,currency) values (?,?,?,?)",
                (r["ticker"], r["date"], r["close"], r.get("currency", "USD")))
        conn.execute("insert or replace into market_meta (key,value) values ('last_sync',?)",
                     (datetime.now().isoformat(timespec="seconds"),))
        conn.commit()
    return {"rows": len(rows)}


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
    "grant_value_usd": 100000,     # generyczne — realne w rsu.json (gitignored)
    "pricing_window": "2026-08",       # average of this month's closes
    "grant_month": "2026-09",
    "vesting_years": 4,
    "vests_per_year": 4,
    "shares_held": 0,                  # shares already held (after vests)
    "shares_next_vest": 0,             # how many shares vest next
    "vest_months": [2, 5, 8, 11],      # Feb, May, Aug, Nov
    "target_bear": 75,                 # lower analyst target / 52w low
    "target_bull": 115,                # upper analyst target
    "analyst_target_mid": 145,         # consensus (median of targets)
    "mc_drift_annual": 0.08,           # dryf w symulacji Monte Carlo (roczny)
    "mc_sims": 1500,                   # number of MC paths
    "perf_equity_multiplier": 1.5,     # 150% akcji rocznie (Twoja ocena Exceeds/Greatly)
    "perf_base_raise_annual": 0.08,    # ~8% base raise per year
}


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
    return {
        **grant,
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
        **_rsu_holdings(grant, last, usdpln),
    }


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
    """Holdings, next-vest projection and price-scenario simulation."""
    from datetime import date as _date
    held = grant.get("shares_held") or 0
    nxt = grant.get("shares_next_vest") or 0
    months = sorted(grant.get("vest_months") or [2, 5, 8, 11])
    today = _date.today()
    next_vest = next((f"{today.year:04d}-{m:02d}" for m in months if m > today.month),
                     f"{today.year + 1:04d}-{months[0]:02d}")
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
        out["scenarios"] = [
            {"price": pr,
             "next_vest_pln": round(nxt * pr * usdpln, 0),
             "total_pln": round((held + nxt) * pr * usdpln, 0)}
            for pr in (70, 80, 90, 100, 110, 120)]
        # timeline: cumulative cash across the next 8 vest windows.
        # base = FLAT at today's price; bear/bull drift linearly to analyst
        # low/high targets (configurable in rsu.json)
        targets = {"bear": grant.get("target_bear") or 75,
                   "base": last,
                   "bull": grant.get("target_bull") or 115}
        horizon = 8
        vm = sorted(grant.get("vest_months") or [2, 5, 8, 11])
        y, m = today.year, today.month
        windows = []
        while len(windows) < horizon:
            nxt_m = next((x for x in vm if x > m), None)
            if nxt_m is None:
                y, m = y + 1, 0
                nxt_m = vm[0] if False else next(x for x in vm if x > 0)
            m = nxt_m
            windows.append(f"{y:04d}-{m:02d}")
        proj = []
        for k, month in enumerate(windows, start=1):
            shares_cum = held + nxt * k
            row = {"month": month, "shares": shares_cum}
            for kind, tgt in targets.items():
                price = last + (tgt - last) * k / horizon
                row[kind] = round(shares_cum * price * usdpln, 0)
                row[kind + "_price"] = round(price, 1)
            proj.append(row)
        out["projection"] = proj
    return out


def update_rsu(data):
    p = _rsu_path()
    grant = dict(_RSU_DEFAULT)
    if p.exists():
        grant.update(json.loads(p.read_text()))
    for k in _RSU_DEFAULT:
        if k in data:
            grant[k] = data[k]
    p.write_text(json.dumps(grant, indent=2))
    return get_rsu()


# ---------- prediction accuracy: backtest + live tracking ----------

_Z = {0.10: -1.2816, 0.50: 0.0, 0.90: 1.2816}  # normal quantiles


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
            vol = _vol_upto(closes[i - 120:i + 1])
            p10 = _lognormal_price(s0, mu, vol, H, 0.10)
            p50 = _lognormal_price(s0, mu, vol, H, 0.50)
            p90 = _lognormal_price(s0, mu, vol, H, 0.90)
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
    out["assumed_drift_pct"] = round(mu * 100, 1)
    out["realized_drift_pct"] = realized
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
            conn.execute(
                "insert into rsu_predictions (id, made_on, ticker, price_now, "
                "horizon_days, target_date, p10, p50, p90) values (?,?,?,?,?,?,?,?,?)",
                (f"{today}-{H}", today, grant["ticker"], s0, H, td,
                 round(_lognormal_price(s0, mu, vol, H, 0.10), 2),
                 round(_lognormal_price(s0, mu, vol, H, 0.50), 2),
                 round(_lognormal_price(s0, mu, vol, H, 0.90), 2)))
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
    nxt = grant.get("shares_next_vest") or 0
    vm = sorted(grant.get("vest_months") or [2, 5, 8, 11])
    today = date.today()

    # build next 8 vest windows with month index for horizon (in trading days)
    windows, y, m = [], today.year, today.month
    while len(windows) < 8:
        nm = next((x for x in vm if x > m), None)
        if nm is None:
            y += 1
            nm = vm[0]
        m = nm
        months_ahead = (y - today.year) * 12 + (m - today.month)
        windows.append({"month": f"{y:04d}-{m:02d}", "months_ahead": max(1, months_ahead)})

    # Monte Carlo GBM on price
    drift = float(grant.get("mc_drift_annual", 0.08))
    sims = int(grant.get("mc_sims", 1500))
    dt = 1.0 / 252.0
    max_days = windows[-1]["months_ahead"] * 21
    sample_idx = [w["months_ahead"] * 21 - 1 for w in windows]
    rng = random.Random(20260717)  # fixed seed → stable across reloads
    # collect simulated prices at each sample point
    price_samples = [[] for _ in windows]
    for _ in range(sims):
        s = last
        step = 0
        want = 0
        for d in range(max_days):
            z = rng.gauss(0, 1)
            s *= math.exp((drift - 0.5 * vol * vol) * dt + vol * math.sqrt(dt) * z)
            if want < len(sample_idx) and d == sample_idx[want]:
                price_samples[want].append(s)
                want += 1
        # ensure trailing windows captured if rounding short
        while want < len(sample_idx):
            price_samples[want].append(s)
            want += 1

    # performance-scaled share accumulation: existing refresh grants deliver
    # `nxt`/quarter; each new annual grant (~grant_month) adds shares scaled by
    # perf multiplier. Approximate uplift: +perf% to per-quarter after 1 year.
    perf = float(grant.get("perf_equity_multiplier", 1.5))
    proj = []
    for k, w in enumerate(windows, start=1):
        # base shares: cumulative quarterly vests at flat count
        shares_base = held + nxt * k
        # perf shares: quarters beyond ~4 (1yr) step up by perf multiplier
        extra_q = max(0, k - 4)
        shares_perf = held + nxt * min(k, 4) + nxt * perf * extra_q
        ps = sorted(price_samples[k - 1])
        row = {
            "month": w["month"],
            "months_ahead": w["months_ahead"],
            "shares_base": shares_base,
            "shares_perf": round(shares_perf),
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
        for tag, tprice in (("bear", grant.get("target_bear", 75)),
                            ("mid", grant.get("analyst_target_mid", 145)),
                            ("bull", grant.get("target_bull", 115))):
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
        "sims": sims,
        "prob_above_current_1y_pct": prob_above_current,
        "analyst": {"bear": grant.get("target_bear"), "mid": grant.get("analyst_target_mid"),
                    "bull": grant.get("target_bull")},
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


def forecast_residuals(ticker):
    """Normalized errors of settled forecasts per horizon (for calibration)."""
    rows = _ft_rows("select horizon_days, resid_z from forecast_track "
                    "where ticker=? and resid_z is not null "
                    "order by made_on desc limit 400", (ticker,))
    out = {}
    for r in rows:
        out.setdefault(r["horizon_days"], []).append(r["resid_z"])
    return out


def record_and_score_forecasts():
    """Daily self-learning cycle: (1) settle matured forecasts against real
    prices, (2) store today's bands for the whole watchlist.
    Called on data refresh and from health()."""
    import forecast_models as fm
    _ensure_cache()
    tickers = [t["ticker"] for t in get_watchlist()]
    scored = recorded = 0
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
        bands = fm.short_term_bands_calibrated(closes, forecast_residuals(tk))
        if not bands:
            continue
        sig_d = bands["ewma_vol_daily_pct"] / 100.0
        for h in bands["horizons"]:
            with db.get_conn() as conn:
                conn.execute("insert or ignore into forecast_track "
                             "(made_on, ticker, horizon_days, base_close, sigma_daily, p10, p50, p90) "
                             "values (?,?,?,?,?,?,?,?)",
                             (today, tk, h["days"], bands["last_close"], sig_d,
                              h["p10"], h["p50"], h["p90"]))
                conn.commit()
            recorded += 1
    return {"scored": scored, "recorded": recorded, "tickers": len(tickers)}


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
    out = fm.short_term_bands_calibrated(closes, forecast_residuals(ticker))
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



def fetch_yahoo_history(ticker, range_="1y"):
    """Keyless Yahoo history for ANY ticker (public data) → market_prices_cache,
    so charts/indicators have depth even for symbols the nightly sync doesn't
    cover (e.g. the risk-radar commodities/FX). Returns the number of rows stored."""
    import json as _json
    import urllib.parse
    import urllib.request
    url = ("https://query1.finance.yahoo.com/v8/finance/chart/"
           + urllib.parse.quote(ticker) + f"?range={range_}&interval=1d")
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
