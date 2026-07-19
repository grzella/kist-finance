#!/usr/bin/env python3
"""Build the static, clickable GitHub Pages demo.

Seeds a THROWAWAY database with the fake "Alex Demo" persona (a mid-level
software developer, everything in USD), enriches it so every module has a
coherent story — net worth growing for 30 months, the mortgage falling in
step, a career analysis, a market barometer, fake performance-marketing
reports, an advanced RSU deep-dive — snapshots every GET endpoint to a JSON
file, and assembles `dist/`: the real frontend plus those snapshots. api.js
serves GETs from the baked files when window.KIST_STATIC_DEMO is set, and
writes become a friendly toast.

The only real data: public market quotes (Yahoo, keyless) and the maintainer's
public GitHub activity (both visible to anyone anyway). Yahoo/GitHub calls are
best-effort — offline the demo simply has thinner charts.

Usage:  python3 demo/build_demo.py [--out dist]
"""
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else ROOT / "dist")
RNG = random.Random(42)  # deterministic fake history
TODAY = date.today()

# --- throwaway data dir, seeded with the sample persona ---
data_dir = Path(tempfile.mkdtemp(prefix="kist-demo-"))
os.environ["FINANCE_PROJECT_DIR"] = str(data_dir)
subprocess.run([sys.executable, str(ROOT / "seed.py")], check=True,
               env={**os.environ}, cwd=ROOT)

sys.path.insert(0, str(ROOT / "server"))
import config  # noqa: E402
config.setup()
import engine_bridge as eb  # noqa: E402
import planner  # noqa: E402
import market  # noqa: E402

# watchlist + risk-radar components + FX pairs the currency view needs
TICKERS = ["AAPL", "MSFT", "VWCE.DE", "EURPLN=X", "USDPLN=X", "EURUSD=X",
           "^VIX", "GC=F", "CL=F"]


def best_effort(label, fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except Exception as e:
        print(f"  (skipped {label}: {str(e)[:80]})")
        return None


def month_iso(months_ago):
    y, m = TODAY.year, TODAY.month - months_ago
    while m <= 0:
        y, m = y - 1, m + 12
    return f"{y:04d}-{m:02d}"


# ================= enrich: a coherent 30-month story, all in USD ==============
print("Enriching demo data…")
planner.save_app_config({"wizard_completed": True, "base_currency": "USD",
                         "modules": {"debts": True, "taxes": True, "markets": True,
                                     "rsu": True, "business": True, "career": True,
                                     "property": True}})

for t in TICKERS:
    best_effort(f"yahoo {t}", market.fetch_yahoo_history, t, "2y")
try:
    import risk_radar
    best_effort("risk radar", risk_radar.backfill, 32)
except Exception:
    pass
best_effort("forecast journal", market.backfill_forecasts, 10)

# --- net worth: 30 months of growth (~388k → today's ~545k) ---
nw = 388_000.0
for back in range(30, 0, -1):
    nw += RNG.uniform(3_000, 7_500)          # savings + market drift
    if back in (24, 14):                      # two believable dips
        nw -= RNG.uniform(6_000, 11_000)
    eb._exec("insert into snapshots (date, type, data) values (?,?,?)",
             (month_iso(back) + "-01", "net_worth",
              json.dumps({"net_worth": round(nw, 2)})))

# --- mortgage history: 14 months, balance falling in step with the story ---
debt = eb._rows("select id, balance from debts")[0]
bal = 348_500.0
for back in range(14, 0, -1):
    principal = RNG.uniform(1_850, 2_150)
    bal -= principal
    eb._exec("insert into debt_values (id, debt_id, month, balance, principal_paid, "
             "interest_paid, note, created_at) values (?,?,?,?,?,?,?,?)",
             (f"demo-debt-{back}", debt["id"], month_iso(back), round(bal, 2),
              round(principal, 2), round(bal * 0.065 / 12, 2), "",
              datetime.now().isoformat()))
eb._exec("update debts set balance = ? where id = ?", (round(bal, 2), debt["id"]))

# --- per-item wealth history so item charts have depth too ---
growth = {"ETF portfolio (broker)": (52_000, 85_000),
          "Company shares (RSU)": (28_000, 60_000),
          "Pension account": (34_000, 45_000),
          "Apartment — Sample City": (585_000, 620_000)}
for it in eb._rows("select id, name from wealth_items"):
    if it["name"] not in growth:
        continue
    lo, hi = growth[it["name"]]
    for back in range(24, 0, -1):
        frac = (24 - back) / 24
        v = lo + (hi - lo) * frac + RNG.uniform(-1500, 1500)
        eb._exec("insert into wealth_values (id, item_id, date, value, created_at) "
                 "values (?,?,?,?,?)",
                 (f"demo-{it['id']}-{back}", it["id"], month_iso(back) + "-01",
                  round(v, 2), datetime.now().isoformat()))

# --- career: PM persona — Senior PM offers, PM barometer, principal/HoP analysis ---
eb._exec("delete from job_offers")  # replace the seed's EM offers
planner.add_offer({"company": "Acme Corp", "role": "Senior Product Manager",
                   "total_monthly": 15500, "work_model": "hybrid", "status": "new",
                   "received_at": month_iso(2) + "-10",
                   "notes": "Sample offer — demo data.", "tier": 2})
planner.add_offer({"company": "Globex", "role": "Senior Product Manager (Platform)",
                   "total_monthly": 17800, "work_model": "remote", "status": "interviewing",
                   "received_at": month_iso(1) + "-18",
                   "notes": "Sample offer — demo data.", "tier": 1})

planner.set_settings({"career_role_a": "Senior PM",
                      "career_role_b": "Head of Product"})
for back in range(8, 0, -1):
    best_effort("barometer", planner.add_barometer_point, {
        "month": month_iso(back),
        "em_openings": 40 + (8 - back) * 3 + RNG.randint(-4, 4),
        "head_openings": 11 + (8 - back) + RNG.randint(-2, 2),
        "region": "US/EU (remote)",
        "note": "sample data" if back == 8 else ""})

planner.set_settings({"analysis_career": json.dumps({
    "headline": "Senior PM with shipped outcomes — the fork ahead is Principal (IC craft "
                "at scale) vs Head of Product (org leverage); both pay, they compound "
                "differently.",
    "as_of": TODAY.isoformat(), "target_role": "Principal PM / Head of Product (2–3 yrs)",
    "comp_levels": [
        {"role": "Product Manager", "comp": "$125–155k", "you": False},
        {"role": "Senior PM", "comp": "$155–190k", "you": True},
        {"role": "Principal PM", "comp": "$190–235k", "you": False},
        {"role": "Head of Product", "comp": "$230–300k", "you": False}],
    "money_paths": [
        {"tag": "A", "title": "Principal track where you are", "verdict": "solid",
         "text": "Own the hardest product area end-to-end, write the strategy memos "
                 "leadership forwards; principal within ~2 years at +20–25% comp, "
                 "no management overhead."},
        {"tag": "B", "title": "Head of Product at a scale-up", "verdict": "highest EV",
         "text": "Series B–D companies pay a premium for a senior PM who has shipped "
                 "0→1 and run discovery; expect +35–50% plus meaningful equity — and "
                 "a genuinely different job (hiring, roadmap politics, board decks)."},
        {"tag": "C", "title": "Fractional / advisory", "verdict": "later",
         "text": "Fractional CPO rates are strong ($150–250/h) but the pipeline needs "
                 "a reputation that principal or HoP scope builds first."}],
    "head_of_eng": "Head of Product is a real option within 2–3 years — but only if "
                   "you enjoy hiring, stakeholder management and being measured on the "
                   "team's outcomes. If the craft is what you love, Principal pays "
                   "nearly as well without the meetings tax. Decide by trying: lead a "
                   "PM hire and a quarter of roadmap before you commit.",
    "ai_impact": [
        "Spec-writing, ticket grooming and basic analytics are commoditizing — the "
        "junior-PM tasks of 2020.",
        "PMs who prototype with AI tools compress discovery from weeks to days; make "
        "that visible.",
        "Judgment, narrative, and stakeholder trust stay human longest — that's the "
        "principal/HoP moat."],
    "skills": [
        {"skill": "Product strategy & narrative", "why": "The principal gate — memos that change the roadmap, not just describe it."},
        {"skill": "AI-assisted discovery", "why": "Prototype-first PMs ship evidence, not opinions — becoming the baseline."},
        {"skill": "Org leadership", "why": "Hiring and developing PMs — the Head-of-Product gate; testable before you commit."}],
    "skills_note": "Sample analysis written for the demo persona — in the real app "
                   "you author this yourself or with any AI assistant.",
    "roadmap": [
        {"period": "0–6 mo", "title": "Own the hardest product area",
         "text": "Take the messy, cross-team problem; write the strategy memo that frames it."},
        {"period": "6–18 mo", "title": "Test both forks",
         "text": "Lead one PM hire and a quarter of roadmap (HoP test) while shipping a principal-level bet."},
        {"period": "18–36 mo", "title": "Commit and cash in",
         "text": "Promo to Principal, or jump to Head of Product at a scale-up — whichever fork felt like energy, not drain."}],
    "philosophies": {
        "max": {"title": "Max earnings", "text":
                "Optimize comp aggressively: jump every 2–3 years, interview yearly "
                "to stay calibrated, chase the biggest scope you can hold."},
        "coast": {"title": "Coast & compound", "text":
                  "Stay where the work is sane, automate savings, let the portfolio "
                  "do the second job. Less money, more life."},
        "note": "Sample framing — the app doesn't pick for you; it shows what each "
                "path does to the numbers in Forecasts."},
    "next_steps": [
        "Write one strategy memo this quarter that proposes killing something.",
        "Volunteer to run the next PM hiring loop — cheapest Head-of-Product test.",
        "Update the market barometer monthly — trend beats snapshot.",
        "Re-run this analysis after the next comp review."],
    "sources": []})})

# --- side business: a few months of drone-services revenue/costs ---
for back, entries in {
    3: [("revenue", "service", 3800, "Aerial photo shoot — sample entry"),
        ("cost", "equipment", -950, "Spare propellers & batteries — sample entry")],
    2: [("revenue", "service", 4200, "Roof inspection flight — sample entry"),
        ("cost", "marketing", -180, "Meta ads — sample entry"),
        ("cost", "software", -49, "Editing suite subscription — sample entry")],
    1: [("revenue", "service", 3600, "Construction-site progress video — sample entry"),
        ("revenue", "content", 450, "Stock-footage royalties — sample entry"),
        ("cost", "marketing", -175, "Meta ads — sample entry")],
}.items():
    for kind, cat, amount, desc in entries:
        best_effort("biz entry", planner.add_biz_entry, {
            "date": month_iso(back) + "-14", "kind": kind, "category": cat,
            "amount": amount, "description": desc})

# --- brokerage portfolio for the XTB-style rule engine (duplicates + tech concentration) ---
planner.set_settings({"xtb_portfolio": json.dumps({"positions": [
    {"name": "NASDAQ 100 ETF", "container": "Plan 1", "value": 20000, "theme": "tech"},
    {"name": "NASDAQ 100 ETF", "container": "Plan 2", "value": 10000, "theme": "tech"},
    {"name": "MSCI World IT ETF", "container": "Plan 1", "value": 16000, "theme": "tech"},
    {"name": "Semiconductors ETF", "container": "Plan 2", "value": 10000, "theme": "tech"},
    {"name": "VWCE All-World ETF", "container": "Plan 2", "value": 20000, "theme": "world"},
    {"name": "S&P 500 ETF", "container": "Plan 1", "value": 9000, "theme": "us"}]})})

# --- open-source contribution research (generic sample) ---
planner.set_settings({"analysis_contributions": json.dumps({
    "goal": "Become a visible contributor to one well-known open-source project "
            "in the tools you already use every day.",
    "method": "Sample research: pick projects you actually run, sort by contributor "
              "activity and good-first-issue availability, start with docs/tests.",
    "repos": [
        {"name": "ggml-org/llama.cpp", "url": "https://github.com/ggml-org/llama.cpp",
         "activity": "very active", "lang": "C++", "difficulty": "hard",
         "why": "You run it locally (this app's AI) — start with docs or build fixes."},
        {"name": "simonw/llm", "url": "https://github.com/simonw/llm",
         "activity": "very active", "lang": "Python", "difficulty": "easy",
         "why": "Plugin ecosystem designed for outside contributors — ship a plugin."},
        {"name": "chartjs/Chart.js", "url": "https://github.com/chartjs/Chart.js",
         "activity": "active", "lang": "JavaScript", "difficulty": "medium",
         "why": "This app's chart library — reproducible bug reports are welcomed."}],
    "badges": [
        {"name": "Pull Shark", "how": "Two merged PRs anywhere", "status": "easy"},
        {"name": "Public Sponsor", "how": "Sponsor a maintainer you rely on ($1/mo counts)", "status": "instant"},
        {"name": "Starstruck", "how": "Publish a useful tool that earns 16+ stars", "status": "long game"}],
    "playbook": [
        "Pick the project you use most — familiarity beats prestige for a first PR.",
        "Start with a docs fix or a failing-test repro; maintainers merge those fast.",
        "Answer two Discussions questions — visibility compounds.",
        "Then take one good-first-issue and see it through review."]})})

# --- fake performance-marketing intelligence (business module) ---
MARKETING = {
    "weeks": [
        {"week": "2026-07-06 – 2026-07-12", "spend_eur": 184.5,
         "summary": "CTR up 14% after the new creative set; CPC steady at €0.42.",
         "recommendation": "Shift 20% of budget to the lookalike audience — it converts 1.8× better."},
        {"week": "2026-06-29 – 2026-07-05", "spend_eur": 176.2,
         "summary": "Weekend impressions dipped (holiday); conversions held.",
         "recommendation": "Keep budgets flat; revisit after the seasonal dip."},
        {"week": "2026-06-22 – 2026-06-28", "spend_eur": 190.0,
         "summary": "New landing page cut bounce rate from 61% to 48%.",
         "recommendation": "Roll the winning variant to all ad sets."}],
    "insights": [
        {"category": "audience", "platform": "meta", "confidence": 0.86, "is_active": True,
         "insight": "Lookalike 1% of past customers outperforms interest targeting 1.8× on ROAS."},
        {"category": "creative", "platform": "meta", "confidence": 0.74, "is_active": True,
         "insight": "Short vertical video beats static images on CPM-adjusted conversions."},
        {"category": "timing", "platform": "meta", "confidence": 0.61, "is_active": True,
         "insight": "Tue–Thu mornings deliver the cheapest qualified clicks."}],
    "hypotheses": [
        {"title": "UGC-style creative lowers CPA", "predicted_outcome": "CPA −20%",
         "success_metric": "CPA", "target_value": "≤ €9.50", "status": "active"},
        {"title": "Broad targeting + strong creative beats narrow interests",
         "predicted_outcome": "ROAS +15%", "success_metric": "ROAS",
         "target_value": "≥ 3.2", "status": "active"}],
    "total_spend_eur": 1420.7, "recent_spend_eur": 550.7, "recent_clicks": 1311,
}

# --- RSU sized for the mid-dev story (seed's grant would dwarf the salary) ---
best_effort("rsu resize", market.update_rsu,
            {"ticker": "AAPL", "grant_value_usd": 60000,
             "shares_held": 120, "shares_next_vest": 30})

# --- an "advanced" RSU vest deep-dive (sample research snapshot) ---
last_aapl = (market.prices("AAPL", days=5) or [{}])[-1].get("close", 230)
planner.set_settings({"rsu_vest_analysis": json.dumps({
    "vest_month": "August 2026", "as_of": TODAY.isoformat(),
    "price": round(float(last_aapl), 2),
    "headline": "Hold through the vest, then sell 60% within the trading window — "
                "concentration risk outweighs the upside of waiting.",
    "sections": [
        {"title": "Concentration math",
         "text": "Post-vest, employer stock would be ~11% of net worth and ~24% of the "
                 "liquid portfolio — above the 10% single-name ceiling this plan uses. "
                 "Selling 60% at vest brings it back inside the band; taxes are neutral "
                 "since the vest itself is the taxable event."},
        {"title": "What the market is pricing",
         "text": "Options imply ~29% annualized volatility into the next earnings print; "
                 "the 1-month band from this app's own forecast model is wide but "
                 "symmetric — no directional edge, so risk management decides, not timing."},
        {"title": "Scenario table",
         "text": "Bull (+15%): extra ~$3.4k on the held tranche. Bear (−15%): −$3.4k plus "
                 "the correlated hit to salary security. The asymmetry of holding "
                 "concentrated employer stock is behavioral, not financial."},
        {"title": "Execution",
         "text": "Sell in two tranches inside the window (day 1 and day 10) to average "
                 "out the post-vest dip pattern; route proceeds to the ETF auto-invest "
                 "the same week so the cash doesn't linger."}],
    "sources": []})})

# --- market brief (handcrafted — no LLM in the build) ---
brief = {
    "headline": "Markets are drifting sideways while rate-cut expectations firm up; "
                "nothing in this demo portfolio needs action this week.",
    "as_of": TODAY.isoformat(), "generated_by": "demo snapshot",
    "regime": "Calm — carry on with the plan",
    "highlights": [
        {"icon": "📈", "title": "Equities steady", "text": "Broad indices near highs on soft-landing hopes."},
        {"icon": "💱", "title": "FX quiet", "text": "EUR/USD range-bound; no conversion signal."},
        {"icon": "🏦", "title": "Rates drifting down", "text": "Markets price gradual cuts into year-end."},
        {"icon": "🛢️", "title": "Oil calm", "text": "Supply steady; inflation pass-through muted."}],
    "geopolitics": [
        {"title": "Why this matters for a long-term plan",
         "text": "Sample context written for the demo: headlines move daily prices, "
                 "but the plan only reacts when thresholds are crossed."}],
    "positions": [
        {"ticker": "VWCE.DE", "stance": "hold", "text": "Core holding — keep the monthly auto-invest."},
        {"ticker": "AAPL", "stance": "hold", "text": "RSU exposure already large; don't add."},
        {"ticker": "EURUSD=X", "stance": "hold", "text": "No signal — wait for the engine's threshold."}],
    "method_note": "Demo brief — in the real app this is generated daily by YOUR local "
                   "model from cached quotes, schema-locked so it always renders.",
}
planner.set_settings({"analysis_market_brief_daily": json.dumps(brief),
                      "analysis_market_brief": json.dumps({**brief,
                          "as_of": (TODAY - timedelta(days=5)).isoformat(),
                          "headline": "Weekly view: same picture — stay the course. "
                                      "(Demo copy of the weekly brief.)"})})


# --- public GitHub activity of the maintainer (public data; synthetic fallback) ---
def github_activity_snapshot(days=90):
    counts, prs, issues, reviews = {}, 0, 0, 0
    try:
        for page in (1, 2, 3):
            req = urllib.request.Request(
                f"https://api.github.com/users/grzella/events/public?per_page=100&page={page}",
                headers={"User-Agent": "kist-demo-build"})
            with urllib.request.urlopen(req, timeout=10) as r:
                events = json.loads(r.read())
            if not events:
                break
            for ev in events:
                d = ev["created_at"][:10]
                if ev["type"] == "PushEvent":
                    counts[d] = counts.get(d, 0) + len(ev["payload"].get("commits") or [1])
                elif ev["type"] == "PullRequestEvent":
                    prs += 1
                elif ev["type"] == "IssuesEvent":
                    issues += 1
                elif ev["type"] == "PullRequestReviewEvent":
                    reviews += 1
        connected = bool(counts)
    except Exception as e:
        print(f"  (github events fallback: {str(e)[:60]})")
        connected = False
    if not connected:  # deterministic synthetic pattern
        for back in range(days):
            d = (TODAY - timedelta(days=back)).isoformat()
            counts[d] = max(0, RNG.randint(-2, 6))
        prs, issues, reviews = 4, 2, 3
    series = [{"date": (TODAY - timedelta(days=back)).isoformat(),
               "count": counts.get((TODAY - timedelta(days=back)).isoformat(), 0)}
              for back in range(days - 1, -1, -1)]
    active = [s for s in series if s["count"] > 0]
    streak = best = 0
    for s in series:
        streak = streak + 1 if s["count"] > 0 else 0
        best = max(best, streak)
    total = sum(s["count"] for s in series)
    return {"configured": True, "repos": 1, "days": days, "today": series[-1]["count"],
            "week": sum(s["count"] for s in series[-7:]),
            "streak": streak, "best_streak": best,
            "active_days": len(active),
            "active_pct": round(100 * len(active) / days),
            "total": total,
            "avg_per_active": round(total / max(1, len(active)), 1),
            "series": series,
            "github": {"connected": connected, "login": "grzella",
                       "prs": prs, "issues": issues, "reviews": reviews}}


# ================= snapshot every GET endpoint ================================
import app as kist_app  # noqa: E402

client = kist_app.app.test_client()


def fname(path_q):
    return re.sub(r"[^A-Za-z0-9._-]", "_", path_q.lstrip("/")) + ".json"


snap_dir = OUT / "demo-data"
if OUT.exists():
    shutil.rmtree(OUT)
snap_dir.mkdir(parents=True)

paths = sorted(str(r) for r in kist_app.app.url_map.iter_rules()
               if "GET" in r.methods and not r.arguments and str(r).startswith("/api"))
for t in TICKERS:
    paths += [f"/api/market/prices/{t}?days=100000",
              f"/api/market/analytics/{t}",
              f"/api/forecast/bands/{t}"]
# parametrized rules the crawl above can't enumerate
paths += ["/api/analysis/career", "/api/analysis/contributions", "/api/analysis/property"]

ok = fail = 0
for p in paths:
    try:
        r = client.get(p)
        if r.status_code == 200 and r.is_json:
            (snap_dir / fname(p)).write_text(json.dumps(r.get_json(), ensure_ascii=False))
            ok += 1
        else:
            fail += 1
            print(f"  skip {p} ({r.status_code})")
    except Exception as e:
        fail += 1
        print(f"  skip {p} ({str(e)[:60]})")
print(f"Snapshots: {ok} saved, {fail} skipped")

# post-crawl patches: endpoints that need Supabase / gh CLI in a real install
(snap_dir / fname("/api/business/marketing")).write_text(json.dumps(MARKETING))
(snap_dir / fname("/api/github-activity")).write_text(
    json.dumps(github_activity_snapshot()))


# --- compute-only POSTs the Forecasts view fires (overpayment simulations):
# bake their responses under a path+body key that api.js reconstructs ---
def js_num(v):
    """Mirror JSON.stringify: integral floats print as ints (3500.0 → 3500)."""
    return int(v) if isinstance(v, float) and v.is_integer() else v


def post_snapshot(path, body):
    key = "post_" + path + "__" + json.dumps(body, separators=(",", ":"))
    r = client.post(path, json=body)
    if r.status_code == 200 and r.is_json:
        (snap_dir / (re.sub(r"[^A-Za-z0-9._-]", "_", key.lstrip("/")) + ".json")
         ).write_text(json.dumps(r.get_json(), ensure_ascii=False))
    else:
        print(f"  skip POST {path} ({r.status_code})")


def snap(n):
    return json.loads((snap_dir / fname(n)).read_text())


loan = next((d for d in snap("/api/debts")["debts"] if d["balance"] > 0), None)
if loan:
    bonus = js_num(float(snap("/api/settings").get("annual_bonus_net") or 20000))
    vest = js_num(float(snap("/api/rsu").get("next_vest_value_pln") or 0))
    for amount in {bonus, vest, js_num(bonus + vest)}:
        if amount < loan["balance"]:  # JS skips only amounts covering the whole balance
            post_snapshot("/api/forecast/mortgage", {
                "balance": js_num(loan["balance"]),
                "monthly_payment": js_num(loan["minimum_payment"]),
                "months_left": js_num(loan.get("months_left") or loan["schedule"]["months"]),
                "overpayment": amount})

# ================= assemble dist ==============================================
for d in ("css", "js", "vendor"):
    shutil.copytree(ROOT / "static" / d, OUT / d)
html = (ROOT / "static" / "index.html").read_text()
html = html.replace('"/static/', '"')
html = html.replace("<script", '<script>window.KIST_STATIC_DEMO=1</script>\n  <script', 1)
html = html.replace("<body>", """<body>
<div style="background:#ffd166;color:#1c1e26;text-align:center;padding:6px 12px;
  font-weight:600;font-size:.9em">🟡 Demo mode — sample data (fake persona
  “Alex Demo”), read-only. Nothing here is real or financial advice.</div>""", 1)
(OUT / "index.html").write_text(html)
(OUT / ".nojekyll").write_text("")

print(f"✅ Demo built → {OUT}")
