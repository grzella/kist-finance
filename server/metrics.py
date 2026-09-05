"""Metrics layer (2026-09-05): wealth points (weekly, not once a month), personal-finance
ratios as a MONTHLY SERIES with traffic lights vs targets, and a net-worth trajectory as
a 24-month cone with scenarios (bonus, employer stock, USD, inflation).

Why a separate module: `planner.py` computes everything ad hoc (cushion, essential share)
but never stores history — after a quarter you could not tell whether the savings rate was
rising or falling. The trajectory had 3 points (monthly snapshot), so every "trend analysis"
was an extrapolation from a single quarter.
"""
import json
import random
from datetime import date, datetime

import engine_bridge as eb
import planner


def _now():
    return datetime.now().isoformat(timespec="seconds")


def ensure_tables():
    eb._exec("""create table if not exists wealth_points (
        date text primary key, net_worth real, assets real, debt real, liquid real,
        invested real, retirement real, cash real, rsu real, real_estate real,
        created_at text not null)""")
    eb._exec("""create table if not exists metrics_monthly (
        month text primary key, data text not null, created_at text not null)""")


def _alloc_values():
    try:
        a = planner.allocation()
        return {r["key"]: float(r["value"] or 0) for r in a["rows"]}, a
    except Exception:
        return {}, None


# ---------------------------------------------------------------- wealth points

def record_point(today=None):
    """One point per day (insert or replace) — the scheduler calls it weekly; a manual
    "recompute derived" overwrites today's point."""
    ensure_tables()
    today = today or date.today()
    w = planner.wealth_summary()
    vals, _ = _alloc_values()
    assets = float(w.get("total") or 0) - float((w.get("totals") or {}).get("income", 0) or 0)
    debt = float(w.get("debt_total") or 0)
    row = {"date": today.isoformat(), "net_worth": round(assets - debt, 2),
           "assets": round(assets, 2), "debt": round(debt, 2),
           "cash": round(vals.get("cash", 0)), "rsu": round(vals.get("rsu", 0)),
           "retirement": round(vals.get("retirement", 0)),
           "real_estate": round(vals.get("real_estate", 0)),
           "invested": round(vals.get("etf", 0) + vals.get("rsu", 0) + vals.get("retirement", 0))}
    row["liquid"] = round(row["cash"] + row["invested"])
    eb._exec("insert or replace into wealth_points (date, net_worth, assets, debt, liquid, "
             "invested, retirement, cash, rsu, real_estate, created_at) values (?,?,?,?,?,?,?,?,?,?,?)",
             (row["date"], row["net_worth"], row["assets"], row["debt"], row["liquid"],
              row["invested"], row["retirement"], row["cash"], row["rsu"], row["real_estate"], _now()))
    return row


def points(limit=160):
    ensure_tables()
    rows = eb._rows("select * from wealth_points order by date desc limit ?", (limit,))
    rows.reverse()
    # merge older monthly snapshots (net worth) so the chart does not start today
    try:
        have = {r["date"][:7] for r in rows}
        for s in eb._rows("select date, data from snapshots where type='net_worth' order by date"):
            if s["date"][:7] in have:
                continue
            d = json.loads(s["data"] or "{}")
            if d.get("net_worth") is not None:
                rows.append({"date": s["date"], "net_worth": d["net_worth"], "assets": d.get("assets"),
                             "debt": d.get("debts"), "liquid": None, "invested": None,
                             "legacy": True})
        rows.sort(key=lambda r: r["date"])
    except Exception:
        pass
    return rows


# ---------------------------------------------------------------- ratios

# key, label, unit, direction (high = more is better, low = less is better, info),
# green threshold, amber threshold, definition
TARGETS = [
    ("savings_rate_pct", "Savings rate", "%", "high", 30, 15,
     "base surplus / (surplus + fixed expenses + debt service)"),
    ("essential_share_pct", "Essential share of expenses", "%", "low", 60, 75,
     "expenses flagged essential / all fixed expenses"),
    ("cushion_months", "Cushion", "mo", "high", 6, 3,
     "cash + 80% of brokerage / (essential costs + loan payments)"),
    ("dti_pct", "Debt service / income", "%", "low", 30, 40,
     "loan payments and insurance / estimated net income (surplus + expenses + payments)"),
    ("liquid_to_debt_pct", "Liquid assets / debt", "%", "high", 50, 25,
     "cash + ETF + employer stock + retirement / loan balances incl. tax reserve"),
    ("invest_share_pct", "Investment share", "%", "high", 25, 15,
     "ETF + employer stock + retirement / wealth (real estate net of loans)"),
    ("rsu_share_pct", "Employer concentration", "%", "low", 4, 10,
     "employer stock / wealth — salary, bonus and shares in one company"),
    ("real_estate_share_pct", "Real estate in wealth", "%", "low", 65, 75,
     "home equity / wealth"),
    ("fx_share_pct", "FX exposure (USD)", "%", "low", 30, 45,
     "USD positions (cash, employer stock) / wealth"),
    ("debt_cost_pct", "Effective cost of debt", "%", "low", None, None,
     "balance-weighted average; green when below the expected after-tax return"),
    ("nw_growth_mom_pct", "Net worth m/m", "%", "info", None, None,
     "latest point vs the previous month"),
]


def _light(value, good, green, amber):
    if value is None or good == "info" or green is None:
        return "grey"
    if good == "high":
        return "green" if value >= green else "amber" if value >= amber else "red"
    return "green" if value <= green else "amber" if value <= amber else "red"


def compute():
    """Current ratios from live data (nothing stored)."""
    w = planner.wealth_summary()
    vals, alloc = _alloc_values()
    try:
        exp = planner.expense_summary()
    except Exception:
        exp = {}
    try:
        d = planner.list_debts()
    except Exception:
        d = {"debts": [], "total": 0}
    lc = planner.liquid_cushion(w)
    essential, debt_service = planner.essential_monthly()
    surplus = float(planner.monthly_surplus() or 0)
    total_exp = float(exp.get("total_mine") or 0)
    net_income = surplus + total_exp + float(debt_service or 0)
    assets = float(w.get("total") or 0) - float((w.get("totals") or {}).get("income", 0) or 0)
    base = float(alloc["total"]) if alloc and alloc.get("total") else assets
    invest = vals.get("etf", 0) + vals.get("rsu", 0) + vals.get("retirement", 0)
    liquid = vals.get("cash", 0) + invest
    debt_total = float(w.get("debt_total") or 0)
    fx = 0.0
    for it in w.get("items", []):
        if it.get("kind") == "income":
            continue
        v = float(it.get("latest_value") or 0)
        if (it.get("currency") or "PLN") == "USD" or planner._alloc_class(it.get("name", "")) == "rsu":
            fx += v
    debts = d.get("debts") or []
    bal = sum(float(x.get("balance") or 0) for x in debts)
    debt_cost = (sum(float(x.get("balance") or 0) * float(x.get("effective_rate") or 0) for x in debts) / bal) if bal else None
    after_tax = planner.expected_return_after_tax()
    growth = None
    try:
        pts = [p for p in points() if p.get("net_worth") is not None]
        if len(pts) >= 2:
            last = pts[-1]
            prev = next((p for p in reversed(pts[:-1]) if p["date"][:7] < last["date"][:7]), None)
            if prev and prev["net_worth"]:
                growth = (last["net_worth"] / prev["net_worth"] - 1) * 100
    except Exception:
        pass
    raw = {
        "savings_rate_pct": (surplus / net_income * 100) if net_income > 0 else None,
        "essential_share_pct": (float(essential) / total_exp * 100) if total_exp > 0 and essential else None,
        "cushion_months": (lc["total"] / (float(essential) + float(debt_service or 0))) if (essential or debt_service) else None,
        "dti_pct": (float(debt_service or 0) / net_income * 100) if net_income > 0 else None,
        "liquid_to_debt_pct": (liquid / debt_total * 100) if debt_total > 0 else None,
        "invest_share_pct": (invest / base * 100) if base > 0 else None,
        "rsu_share_pct": (vals.get("rsu", 0) / base * 100) if base > 0 else None,
        "real_estate_share_pct": (vals.get("real_estate", 0) / base * 100) if base > 0 else None,
        "fx_share_pct": (fx / base * 100) if base > 0 else None,
        "debt_cost_pct": debt_cost,
        "nw_growth_mom_pct": growth,
    }
    items = []
    for key, label, unit, good, green, amber, note in TARGETS:
        v = raw.get(key)
        v = round(v, 1) if v is not None else None
        if key == "debt_cost_pct":
            g, a = after_tax, after_tax + 2
            light = "grey" if v is None else "green" if v < g else "amber" if v < a else "red"
            target = f"< {after_tax:.1f}% (expected after-tax return)"
        elif good == "info":
            light = "grey" if v is None else "green" if v >= 0 else "amber"
            target = "—"
        else:
            light = _light(v, good, green, amber)
            target = (f"≥ {green}" if good == "high" else f"≤ {green}") + (" " + unit if unit != "%" else "%")
        items.append({"key": key, "label": label, "value": v, "unit": unit, "light": light,
                      "target": target, "note": note})
    return {"as_of": date.today().isoformat(), "items": items,
            "facts": {"net_income_est": round(net_income), "surplus": round(surplus),
                      "expenses": round(total_exp), "debt_service": round(float(debt_service or 0)),
                      "liquid": round(liquid), "invested": round(invest), "debt_total": round(debt_total),
                      "after_tax_return_pct": after_tax}}


def record_month(today=None):
    """Upsert this month's ratios (idempotent: the latest recompute wins)."""
    ensure_tables()
    today = today or date.today()
    cur = compute()
    data = {it["key"]: it["value"] for it in cur["items"]}
    data["_facts"] = cur["facts"]
    eb._exec("insert or replace into metrics_monthly (month, data, created_at) values (?,?,?)",
             (today.strftime("%Y-%m"), json.dumps(data), _now()))
    return data


def history(limit=36):
    ensure_tables()
    rows = eb._rows("select month, data from metrics_monthly order by month desc limit ?", (limit,))
    out = []
    for r in reversed(rows):
        try:
            d = json.loads(r["data"] or "{}")
        except ValueError:
            d = {}
        d.pop("_facts", None)
        out.append({"month": r["month"], **d})
    return out


def summary():
    return {"current": compute(), "history": history(), "points": points(),
            "targets": [{"key": k, "label": l, "unit": u, "good": g} for k, l, u, g, _, _, _ in TARGETS]}


# ---------------------------------------------------------------- trajectory

def _benchmark_monthly_returns():
    """Monthly benchmark returns (as in the FIRE cone) — DEMEANED; drift is added explicitly."""
    try:
        import market as _mkt
        bench = planner.get_setting("fire_benchmark_ticker") or "IWDA.AS"
        hist = _mkt.prices(bench, days=4000)
        by_m = {}
        for r in hist:
            by_m[r["date"][:7]] = r["close"]
        ms = sorted(by_m)
        rets = [by_m[b] / by_m[a] - 1 for a, b in zip(ms, ms[1:]) if by_m[a]]
        if len(rets) < 48:
            return bench, []
        mu = sum(rets) / len(rets)
        return bench, [r - mu for r in rets]
    except Exception:
        return None, []


def _simulate(start_other, start_inv, months, flow, bonus, bonus_at, drift_m, rets, sims, seed):
    rng = random.Random(seed)
    block = 6
    per_month = [[] for _ in range(months)]
    for _ in range(sims):
        inv, other = start_inv, start_other
        m = 0
        while m < months:
            if rets:
                s0 = rng.randrange(0, max(1, len(rets) - block))
                chunk = rets[s0:s0 + block]
            else:
                chunk = [rng.gauss(0, 0.045) for _ in range(block)]
            for r in chunk:
                inv *= (1 + drift_m + r)
                other += flow + (bonus if (m % 12) == bonus_at else 0)
                per_month[m].append(inv + other)
                m += 1
                if m >= months:
                    break
    out = {"p10": [], "p50": [], "p90": []}
    for vals in per_month:
        vals.sort()
        n = len(vals)
        out["p10"].append(round(vals[int(0.10 * (n - 1))]))
        out["p50"].append(round(vals[int(0.50 * (n - 1))]))
        out["p90"].append(round(vals[int(0.90 * (n - 1))]))
    return out


def trajectory(months=24, bonus=True, team_shock_pct=0.0, usd_shock_pct=0.0, real=False,
               sims=300, today=None):
    """Net-worth cone: the invested part grows with drift + block bootstrap of the benchmark's
    monthly returns; the rest (cash, home equity) accrues the surplus and net vest cash; the
    bonus lands in its month. Employer-stock / USD shocks are one-off at t0 (we know we cannot
    predict their direction — we show how much they matter)."""
    today = today or date.today()
    months = max(6, min(int(months or 24), 60))
    w = planner.wealth_summary()
    vals, alloc = _alloc_values()
    assets = float(w.get("total") or 0) - float((w.get("totals") or {}).get("income", 0) or 0)
    net0 = assets - float(w.get("debt_total") or 0)
    invested = vals.get("etf", 0) + vals.get("rsu", 0) + vals.get("retirement", 0)
    rsu_val = vals.get("rsu", 0)
    fx_val = 0.0
    for it in w.get("items", []):
        if it.get("kind") != "income" and (it.get("currency") or "PLN") == "USD":
            fx_val += float(it.get("latest_value") or 0)
    shock = rsu_val * team_shock_pct / 100.0 + fx_val * usd_shock_pct / 100.0
    inv0 = max(0.0, invested + rsu_val * team_shock_pct / 100.0)
    other0 = net0 + shock - inv0
    surplus = float(planner.monthly_surplus() or 0)
    extras = planner._annual_extras(today=today)
    flow = surplus + (float(extras.get("rsu_annual") or 0) + float(extras.get("cash_vest_annual_net") or 0)) / 12.0
    bonus_net = float(extras.get("bonus_net") or 0) if bonus else 0.0
    try:
        bonus_month = int(planner._num(planner.get_setting("cf_bonus_month")) or planner.CF_DEFAULTS.get("cf_bonus_month", 9))
    except Exception:
        bonus_month = 9
    bonus_at = (bonus_month - today.month - 1) % 12   # month index (0..11) from today when the bonus lands
    drift_m = float(planner.EXPECTED_MARKET_RETURN) / 100.0 / 12.0
    bench, rets = _benchmark_monthly_returns()
    sim = _simulate(other0, inv0, months, flow, bonus_net, bonus_at, drift_m, rets, sims, seed=20260905)
    labels = []
    y, m = today.year, today.month
    for i in range(1, months + 1):
        mm = (m - 1 + i) % 12 + 1
        yy = y + (m - 1 + i) // 12
        labels.append(f"{yy:04d}-{mm:02d}")
    infl = planner._pct_setting("inflation_pct", 3.0) / 100.0
    if real and infl:
        for q in ("p10", "p50", "p90"):
            sim[q] = [round(v / ((1 + infl / 12) ** (i + 1))) for i, v in enumerate(sim[q])]
    out = {"labels": labels, **sim, "start": round(net0), "months": months,
           "assumptions": {"surplus": round(surplus), "flow_monthly": round(flow),
                           "bonus_net": round(bonus_net), "bonus_month": bonus_month,
                           "invested": round(inv0), "rsu": round(rsu_val), "fx_usd": round(fx_val),
                           "drift_annual_pct": planner.EXPECTED_MARKET_RETURN,
                           "benchmark": bench, "months_of_data": len(rets),
                           "method": "block bootstrap (6 mo) of demeaned returns" if rets
                                     else "gaussian fallback (σ 4.5%/mo)",
                           "real": bool(real), "inflation_pct": round(infl * 100, 1)},
           "variants": []}
    base_end = sim["p50"][-1]
    variants = [("base", "base", 0.0, bonus_net), ("no_bonus", "no bonus", 0.0, 0.0),
                ("team_down", "employer stock −30%", -0.30 * rsu_val, bonus_net),
                ("team_up", "employer stock +30%", 0.30 * rsu_val, bonus_net),
                ("usd_down", "USD −10%", -0.10 * fx_val, bonus_net),
                ("all_bad", "no bonus + stock −30% + USD −10%", -0.30 * rsu_val - 0.10 * fx_val, 0.0)]
    for key, label, delta0, b in variants:
        end = base_end + delta0 * ((1 + drift_m) ** months if delta0 < 0 else 1) + (b - bonus_net) * max(1, months // 12)
        out["variants"].append({"key": key, "label": label, "p50_end": round(end),
                                "delta_vs_base": round(end - base_end)})
    try:  # the engine's `scenarios` table stops being dead: the last run is stored
        eb._exec("insert or replace into scenarios (slug, name, type, inputs, result, profile_snapshot, saved_at) "
                 "values (?,?,?,?,?,?,?)",
                 ("trajectory-%dm" % months, "Net-worth trajectory", "trajectory",
                  json.dumps({"months": months, "bonus": bonus, "team_shock_pct": team_shock_pct,
                              "usd_shock_pct": usd_shock_pct, "real": real}),
                  json.dumps({"start": out["start"], "p10_end": sim["p10"][-1], "p50_end": base_end,
                              "p90_end": sim["p90"][-1]}),
                  json.dumps(out["assumptions"]), _now()))
    except Exception:
        pass
    return out
