"""🌍 Risk Radar — a measurable, honest alternative to meme "pizza indexes".

Instead of scraping meme indicators, the radar reads the fear proxies the market
ALREADY prices: VIX (equity fear), gold (flight to safety),
oil (geopolitical/supply shock), USD via EURUSD (global risk-off).
Thresholds are EXPLICIT and explainable (no black boxes) — the radar predicts
nothing; it contextualizes: "how nervous is the world today". The daily reading
stores a history, so over time it shows whether it ever led anything.

Data: the price cache fed by the nightly sync (n8n → Supabase → market_prices_cache).
A ticker missing from the watchlist = a "no data" component (said plainly).
"""
import json
from datetime import date

import engine_bridge as eb

# (ticker, label, 0-2 scoring fn, threshold description)
# Classic market thresholds — see the card. 0=calm, 1=elevated, 2=hot.


def _score_vix(level, chg):
    s = 0 if level < 18 else (1 if level <= 25 else 2)
    if chg is not None and chg > 10:
        s = min(2, s + 1)
    return s


def _score_gold(level, chg):
    if chg is None:
        return 0
    return 2 if chg > 2.5 else (1 if chg > 1.0 else 0)


def _score_oil(level, chg):
    if chg is None:
        return 0
    a = abs(chg)
    return 2 if a > 6 else (1 if a > 3 else 0)


def _score_usd(level, chg):
    # EURUSD component: falling EURUSD = stronger USD = risk-off
    if chg is None:
        return 0
    return 2 if chg < -1.2 else (1 if chg < -0.5 else 0)


COMPONENTS = [
    {"ticker": "^VIX", "label": "VIX (US equity fear)", "score": _score_vix,
     "unit": "pts", "what": "S&P 500 volatility index — expected annualized volatility in %; historically 12–20 normal, 30+ panic",
     "rule": "level <18 calm · 18–25 elevated · >25 hot; a +10%/d jump bumps it"},
    {"ticker": "GC=F", "label": "Gold (flight to safety)", "score": _score_gold,
     "unit": "USD/oz", "what": "gold price per ounce in dollars (futures)",
     "rule": "daily change >+1% elevated · >+2.5% hot"},
    {"ticker": "CL=F", "label": "WTI oil (geopolitical shock)", "score": _score_oil,
     "unit": "USD/bbl", "what": "WTI barrel price in dollars (futures)",
     "rule": "|daily change| >3% elevated · >6% hot"},
    {"ticker": "EURUSD=X", "label": "USD (global risk-off)", "score": _score_usd,
     "unit": "", "what": "euro priced in dollars — a drop = a strengthening dollar (flight to USD)",
     "rule": "EURUSD −0.5%/d elevated · −1.2%/d hot (a drop = strong USD)"},
]

STATES = [(0, 1, "🟢 calm"), (2, 3, "🟡 elevated"), (4, 99, "🔴 hot")]


def ensure_tables():
    eb._exec("""create table if not exists risk_radar_history (
        date text primary key, score integer not null, state text,
        details text, comment text)""")


def _last_two_closes(ticker):
    rows = eb._rows(
        "select date, close from market_prices_cache where ticker=? "
        "order by date desc limit 2", (ticker,))
    if not rows:
        return None, None, None
    level = rows[0]["close"]
    chg = None
    if len(rows) == 2 and rows[1]["close"]:
        chg = round((level - rows[1]["close"]) / rows[1]["close"] * 100, 2)
    return level, chg, rows[0]["date"]


def compute():
    """Current radar reading from the price cache (no write)."""
    parts, total, missing = [], 0, []
    for c in COMPONENTS:
        level, chg, asof = _last_two_closes(c["ticker"])
        if level is None:
            missing.append(c["ticker"])
            parts.append({"ticker": c["ticker"], "label": c["label"], "rule": c["rule"],
                          "unit": c.get("unit", ""), "what": c.get("what", ""),
                          "level": None, "chg_1d": None, "score": None, "asof": None})
            continue
        s = c["score"](level, chg)
        total += s
        parts.append({"ticker": c["ticker"], "label": c["label"], "rule": c["rule"],
                      "unit": c.get("unit", ""), "what": c.get("what", ""),
                      "level": round(level, 2), "chg_1d": chg, "score": s, "asof": asof})
    state = next(lbl for lo, hi, lbl in STATES if lo <= total <= hi)
    return {"score": total, "max_score": 2 * len(COMPONENTS), "state": state,
            "components": parts, "missing": missing,
            "note": ("tickers missing from the watchlist: " + ", ".join(missing)
                     + " — add them and the nightly sync starts fetching") if missing else ""}


def _ai_one_liner(reading):
    """A one-liner from the LOCAL model (private, fast).
    No model = no comment — the radar works without AI."""
    try:
        import llm_local
        parts = "; ".join(f"{p['label']}: {p['level']} ({p['chg_1d']}%/d, score {p['score']})"
                          for p in reading["components"] if p["level"] is not None)
        return llm_local.chat(
            f"Market risk radar: {reading['state']}, {reading['score']}/{reading['max_score']}. "
            f"Components: {parts}. At most 2 complete sentences (finish the thought!): what this reading means for a calm "
            f"long-term investor.", max_tokens=220)
    except Exception:
        return None


def _finish_sentence(text):
    """Trim to the last complete sentence — better shorter than cut mid-word."""
    if not text:
        return text
    t = text.strip()
    if t[-1] in ".!?":
        return t
    cut = max(t.rfind("."), t.rfind("!"), t.rfind("?"))
    return t[: cut + 1] if cut > 20 else t


def snapshot():
    """Daily reading: compute, comment (local AI, best-effort), store.
    Returns True when stored (idempotent per day) — the schedule runner."""
    ensure_tables()
    reading = compute()
    if reading["missing"] and len(reading["missing"]) == len(COMPONENTS):
        return False  # zero data — don't store empty readings
    today = date.today().isoformat()
    if eb._rows("select 1 from risk_radar_history where date=?", (today,)):
        return True
    comment = _finish_sentence(_ai_one_liner(reading))
    eb._exec("insert into risk_radar_history (date, score, state, details, comment) "
             "values (?,?,?,?,?)",
             (today, reading["score"], reading["state"],
              json.dumps(reading["components"], ensure_ascii=False), comment))
    _alert_if_hot(reading, comment)
    return True


def _alert_if_hot(reading, comment=None):
    """When the composite goes hot (🔴), ping Telegram — a sign to LOOK, not an
    order to act. Needs TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID in .env; without
    them this is a silent no-op. Fires at most once per day (with the snapshot).
    A standalone n8n alternative lives in integrations/n8n/ (works with the app off)."""
    import os
    import urllib.parse
    import urllib.request
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat or "🔴" not in (reading.get("state") or ""):
        return False
    hot = ", ".join(f"{p['label']}: {p['level']} ({p['chg_1d']:+}%/d)"
                    for p in reading["components"]
                    if p.get("score") == 2 and p.get("level") is not None)
    text = (f"🔴 Risk radar: {reading['score']}/{reading['max_score']} — markets are hot. "
            f"Drivers: {hot or 'see the app'}. "
            + (comment + " " if comment else "")
            + "Worth a look — this is a signal to investigate, not to act.")
    try:
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=urllib.parse.urlencode({"chat_id": chat, "text": text}).encode())
        with urllib.request.urlopen(req, timeout=10):
            pass
        return True
    except Exception:
        return False




def fetch_missing(reading=None):
    """Fetch missing components right away (Yahoo). Returns the fetched list."""
    import market
    reading = reading or compute()
    got = []
    for t in reading["missing"]:
        if market.fetch_yahoo_history(t, "5d"):
            got.append(t)
    return got




def backfill(days=32):
    """Backfill the history: fetch ~45 days of quotes (Yahoo) and compute the
    composite for each day. No AI comments (those are for live readings only).
    Idempotent — existing dates stay."""
    import market
    ensure_tables()
    for c in COMPONENTS:
        market.fetch_yahoo_history(c["ticker"], "3mo")  # Yahoo takes fixed ranges only; 3mo covers days + 14
    series = {}
    for c in COMPONENTS:
        rows = eb._rows("select date, close from market_prices_cache where ticker=? "
                        "order by date", (c["ticker"],))
        series[c["ticker"]] = [(r["date"], r["close"]) for r in rows]
    # shared dates (days with readings for at least 2 components)
    from datetime import date as _d, timedelta
    added = 0
    for back in range(days, 0, -1):
        day = (_d.today() - timedelta(days=back)).isoformat()
        if eb._rows("select 1 from risk_radar_history where date=?", (day,)):
            continue
        total, seen = 0, 0
        for c in COMPONENTS:
            pts = [p for p in series[c["ticker"]] if p[0] <= day]
            if len(pts) < 2:
                continue
            level, prev = pts[-1][1], pts[-2][1]
            if pts[-1][0] != day:
                continue  # no quote that day (weekend/holiday)
            chg = round((level - prev) / prev * 100, 2) if prev else None
            total += c["score"](level, chg)
            seen += 1
        if seen >= 2:
            state = next(lbl for lo, hi, lbl in STATES if lo <= total <= hi)
            eb._exec("insert into risk_radar_history (date, score, state, details, comment) "
                     "values (?,?,?,?,?)", (day, total, state, None, None))
            added += 1
    return added


def full():
    """Reading + history; on gaps it tries a one-shot Yahoo fetch."""
    ensure_tables()
    reading = compute()
    if reading["missing"] and fetch_missing(reading):
        reading = compute()
    hist = eb._rows("select date, score, state, comment from risk_radar_history "
                    "order by date desc limit 90")
    if len(hist) < 5:  # first run: backfill a month of history
        backfill()
        hist = eb._rows("select date, score, state, comment from risk_radar_history "
                        "order by date desc limit 90")
    return {**reading, "history": list(reversed(hist))}
