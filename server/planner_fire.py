"""planner_fire — FIRE / work-optional: projection, cone, snapshots and progress tracking.

Split out of planner.py on 2026-09-05 (code moved 1:1; other modules are reached through `P`).
"""
from datetime import date, datetime

import engine_bridge as eb
from planner_proxy import P

# ---------- FIRE / work-optional projection (zamiast Monte Carlo) ----------

def fire_projection():
    """Liquid-portfolio projection toward the work-optional goal: 3 return scenarios
    plus a real (inflation-adjusted) version. Readable lines instead of a Monte-Carlo histogram."""
    from datetime import date
    goals = P.list_goals()
    g = next((x for x in goals if any(k in x["name"].lower()
             for k in ("work-optional", "liquid", "independent", "portfolio"))), None)
    start = (g and g.get("current_amount")) or 289000
    target = (g and g.get("target_amount")) or 1000000
    base_month = P.monthly_surplus() or 10000
    extras = P._annual_extras().get("monthly_equivalent", 0) or 0
    contrib = base_month + extras
    # The freed installment adds to savings only while the loan is still running.
    # Once it is paid off its monthly cost is 0 and the freed money already sits in
    # the baseline surplus, so adding it here again would count it twice.
    freed = 0
    loan_open = False
    try:
        loan = next((d for d in P.list_debts()["debts"] if any(k in d["name"].lower()
                     for k in ("mortgage", "loan", "home", "house"))), None)
        freed = loan.get("monthly_cost_total", 0) if loan else 0
        loan_open = bool(loan and (loan.get("balance") or 0) > 0)
    except Exception:
        freed = 0

    scenarios = {"cautious (4%)": 0.04, "base (6.5%)": 0.065, "optimistic (9%)": 0.09}
    today = date.today()
    horizon = 15 * 12
    series = {k: [] for k in scenarios}
    labels = []
    crossover = {}
    # inflation indexes the TARGET (cost of living), contributions grow with income; gains taxed at withdrawal
    infl = P._pct_setting("inflation_pct", 3.0) / 100
    # contribution growth: default = inflation (3%); a base raise applies to salary, not to the whole
    # surplus (which contains vests and cash-vest); override with income_growth_pct
    growth = P._pct_setting("income_growth_pct", 3.0) / 100
    tax = P.capital_gains_tax_pct() / 100
    # month the loan installment is freed: from Cash-flow (the actual payoff month), not "in a year"
    freed_from = 12 if loan_open else 0
    lp = None
    try:
        lp = P.cashflow().get("target_paid_month")
    except Exception:
        pass
    if lp:
        freed_from = max(0, (int(lp[:4]) - today.year) * 12 + (int(lp[5:7]) - today.month))

    def label_at(m):
        yy = today.year + (today.month - 1 + m) // 12
        mm = (today.month - 1 + m) % 12 + 1
        return f"{yy:04d}-{mm:02d}"

    def contrib_at(m):
        return contrib * ((1 + growth) ** (m / 12.0)) + (freed if m >= freed_from else 0)

    def target_at(m):
        return target * ((1 + infl) ** (m / 12.0))

    series_net = []
    for name, r in scenarios.items():
        bal = start
        contributed = start
        rm = r / 12
        for m in range(horizon + 1):
            if m % 12 == 0:
                series[name].append(round(bal))
                if name == list(scenarios)[1]:
                    labels.append(label_at(m))
                    series_net.append(round(contributed + max(0.0, bal - contributed) * (1 - tax)))
            if name not in crossover and bal >= target_at(m):
                crossover[name] = label_at(m)
            add = contrib_at(m)
            bal = bal * (1 + rm) + add
            contributed += add

    # milestones for the base scenario (nominal)
    base_r = 0.065 / 12
    milestones = {}
    bal = start
    for m in range(horizon + 1):
        for mk in (round(target / 3), round(target * 2 / 3), target):  # thirds of the goal
            if mk not in milestones and bal >= mk:
                milestones[mk] = label_at(m)
        bal = bal * (1 + base_r) + contrib_at(m)

    # real version: real return = base − inflation, target not indexed
    real_r = (0.065 - infl) / 12
    bal = start
    real_cross = None
    for m in range(horizon + 1):
        if real_cross is None and bal >= target:
            real_cross = label_at(m)
        bal = bal * (1 + real_r) + contrib_at(m)
    # after tax: when the portfolio AFTER capital gains tax crosses the indexed target
    net_cross = None
    bal = start; contributed = start
    for m in range(horizon + 1):
        if net_cross is None and (contributed + max(0.0, bal - contributed) * (1 - tax)) >= target_at(m):
            net_cross = label_at(m)
        add = contrib_at(m); bal = bal * (1 + base_r) + add; contributed += add

    # cone from a block bootstrap of the benchmark's real monthly returns (e.g. a world ETF)
    cone = None
    try:
        import market as _mkt, forecast_models as _fm
        bench = P.get_setting("fire_benchmark_ticker") or "IWDA.AS"
        hist = _mkt.prices(bench, days=4000)
        by_m = {}
        for r in hist:
            by_m[r["date"][:7]] = r["close"]
        months_sorted = sorted(by_m)
        mrets = [by_m[b] / by_m[a] - 1 for a, b in zip(months_sorted, months_sorted[1:]) if by_m[a]]
        if len(mrets) >= 48:
            cone = {"benchmark": bench, "months_of_data": len(mrets), "points": {}}
            for yrs in (5, 10, 15):
                bb = _fm.block_bootstrap_annual(mrets, yrs, sims=600, block=24)
                if bb:
                    total_contrib = sum(contrib_at(m) for m in range(yrs * 12))
                    cone["points"][yrs] = {q: round(start * bb[q] + total_contrib * (bb[q] ** 0.5)) for q in ("p10", "p50", "p90")}
        else:
            cone = {"benchmark": bench, "months_of_data": len(mrets), "points": {}, "note": "too little history (48 months needed)"}
    except Exception as e:
        cone = {"error": str(e)[:80]}

    # --- property-goal projection (50% down payment) ---
    ig = next((x for x in goals if any(k in x["name"].lower()
              for k in ("propert", "house", "home", "apartment", "flat", "down payment", "mortgage"))), None)
    property_target = (ig and ig.get("target_amount")) or 200000
    property_start = (ig and ig.get("current_amount")) or 0
    # Loan already paid off: accumulation starts now. While it runs: from the payoff month.
    delay = freed_from if lp else (5 if loan_open else 0)
    property_r = 0.04 / 12  # close to the goal → more cautious/liquid
    property_contrib = contrib + freed
    bal = property_start
    property_series = []
    property_cross = None
    for m in range(horizon + 1):
        if m % 12 == 0:
            property_series.append(round(bal))
        if property_cross is None and bal >= property_target and m >= delay:
            property_cross = label_at(m)
        bal = bal * (1 + property_r) + (property_contrib if m >= delay else 0)

    # --- snapshot + tracking (plan vs actual) ---
    try:
        record_fire_snapshot(start)
    except Exception:
        pass
    tracking = {}
    try:
        tracking = fire_tracking(contrib, freed, 0.065)
    except Exception:
        tracking = {"status": "no data"}

    return {
        "start": round(start), "target": round(target),
        "monthly_contribution": round(contrib), "freed_after_loan": round(freed),
        "labels": labels, "series": series, "crossover": crossover,
        "milestones": {str(k): v for k, v in milestones.items()},
        "real_crossover": real_cross,
        "net_crossover": net_cross,
        "series_net": series_net,
        "cone": cone,
        "inflation_pct": round(infl * 100, 2), "income_growth_pct": round(growth * 100, 2), "tax_pct": round(tax * 100, 1),
        "freed_from_month": label_at(freed_from),
        "property": {"target": round(property_target), "start": round(property_start),
                  "crossover": property_cross, "series": property_series, "delay_months": delay,
                  "note": (("Down-payment accumulation starts after the loan is paid off (~" + label_at(delay) + "). ")
                           if loan_open else
                           "The loan is paid off, so down-payment accumulation is already running. ")
                          + "Cautious 4% return (funds close to the goal). NOTE: the same surpluses as work-optional — buying the house delays reaching "
                          + P._zl(target) + "."},
        "tracking": tracking,
        "assumptions": {"base_return": "6.5% nominal", "inflation": f"{infl * 100:g}% (target indexed)",
                        "income_growth": f"{growth * 100:g}%/yr (contributions grow with income)", "tax": f"{tax * 100:g}% on gains at withdrawal",
                        "contrib_note": (f"{round(contrib)}/mo (savings {round(base_month)} + net bonus/RSU {round(extras)})"
                                         + (f"; after the loan payoff (+{round(freed)}) from {label_at(freed_from)}"
                                            if loan_open and freed else
                                            "; the freed loan installment is already included in savings"))},
    }


def _liquid_now():
    """Liquid portfolio = ETF + RSU shares + cash + pension (excluding real estate)."""
    try:
        a = P.allocation()
        keys = {"etf", "rsu", "cash", "retirement"}
        return round(sum(r["value"] for r in a["rows"] if r["key"] in keys), 0)
    except Exception:
        return None


def record_fire_snapshot(fallback_liquid=None):
    from datetime import date
    month = date.today().strftime("%Y-%m")
    exists = eb._rows("select 1 from fire_snapshots where month=?", (month,))
    if exists:
        return
    liquid = _liquid_now()
    if liquid is None:
        liquid = fallback_liquid or 0
    nw = None
    try:
        w = P.wealth_summary()
        nw = w["total"] - w["debt_total"]
    except Exception:
        pass
    eb._exec("insert into fire_snapshots (month, liquid, net_worth, created_at) values (?,?,?,?)",
             (month, liquid, nw, P._now()))


def fire_tracking(contrib, freed, base_annual):
    """Compares real monthly snapshots with the expected pace (plan)."""
    snaps = eb._rows("select month, liquid from fire_snapshots order by month asc")
    if len(snaps) < 2:
        return {"status": "collecting data", "snapshots": len(snaps),
                "first": snaps[0]["month"] if snaps else None}
    base_r = base_annual / 12
    rows = []
    cum_delta = 0.0
    for i in range(1, len(snaps)):
        prev, cur = snaps[i - 1], snaps[i]
        actual_growth = cur["liquid"] - prev["liquid"]
        expected_growth = prev["liquid"] * base_r + contrib + freed
        delta = actual_growth - expected_growth
        cum_delta += delta
        rows.append({"month": cur["month"], "actual": round(cur["liquid"]),
                     "actual_growth": round(actual_growth),
                     "expected_growth": round(expected_growth), "delta": round(delta)})
    last = rows[-1]
    verdict = ("ahead of plan" if cum_delta > 5000 else
               "behind plan" if cum_delta < -5000 else "on plan")
    return {"status": "ok", "rows": rows[-6:], "cum_delta": round(cum_delta),
            "verdict": verdict, "months_tracked": len(snaps),
            "latest_liquid": round(snaps[-1]["liquid"])}


# ---------- investment policy: a model portfolio for new money ----------

# weights for money AFTER the cushion, the tax reserve and tax-advantaged account limits (no short-term goal);
# sector satellites are kept small: pay and equity from one employer are already one big sector bet
INVEST_MODEL = {"core": 70, "bonds": 15, "themes": 0, "satellite": 10, "sandbox": 5}
INVEST_BUCKETS = {
    "core": {"label": "🌍 Core: whole world", "instrument": "global all-world equity ETF", "ret": 6.5},
    "bonds": {"label": "🛡️ Ballast: bonds", "instrument": "inflation-linked government bonds", "ret": 4.5},
    "themes": {"label": "🧭 Themes", "instrument": "per the themes table below", "ret": 6.5},
    "satellite": {"label": "🚀 Satellites: sectors", "instrument": "sector ETFs (e.g. tech, semiconductors)", "ret": 6.5},
    "sandbox": {"label": "🧪 Sandbox: own picks", "instrument": "individual stocks", "ret": 6.5},
}


def _invest_bucket(name, theme_keys=()):
    n = name.lower()
    if any(k in n for k in theme_keys):
        return "themes"
    if any(k in n for k in ("world", "core", "global", "vwce")):
        return "core"
    if any(k in n for k in ("bond", "treasur", "gilt")):
        return "bonds"
    if any(k in n for k in ("nasdaq", "semicond", "sector", "s&p")):
        return "satellite"
    return "sandbox"


def invest_plan(today=None):
    """Model portfolio for new money vs the brokerage positions in Wealth, a buy list for the next
    vest (top up what is below weight, never sell) and a 5/10/15-year projection when the whole
    surplus is invested."""
    weights = dict(INVEST_MODEL)
    for k, v in (P.get_json_setting("invest_model") or {}).items():
        if k in weights and P._num(v) is not None:
            weights[k] = float(v)
    wsum = sum(weights.values()) or 1

    # themes plan (setting invest_themes): amount per quarter per theme; tickers of the "themes"
    # rows recognise Wealth positions, prices come from the market cache
    themes = P.get_json_setting("invest_themes") or {}
    theme_keys = tuple(i["ticker"].split(".")[0].lower() for r in themes.get("rows") or []
                       if r.get("bucket") == "themes" for i in r.get("items") or [] if i.get("ticker"))
    try:
        import market as _mkt
        for r in themes.get("rows") or []:
            for i in r.get("items") or []:
                h = _mkt.prices(i["ticker"], days=400) if i.get("ticker") else []
                if h:
                    i["last"] = round(h[-1]["close"], 2)
                    i["ccy"] = h[-1].get("currency")
                    i["chg_1y_pct"] = round(100 * (h[-1]["close"] / h[0]["close"] - 1), 1) if len(h) >= 200 and h[0]["close"] else None
    except Exception:
        pass

    cur = {k: 0.0 for k in weights}
    for it in P.wealth_summary().get("items", []):
        if it.get("group") != "invest" or P._alloc_class(it.get("name", "")) == "rsu":
            continue
        cur[_invest_bucket(it.get("name", ""), theme_keys)] += it.get("latest_value") or 0
    total = sum(cur.values())

    deploy, deploy_month, surplus_until = 0.0, None, 0.0
    try:
        for r in P.cashflow(months=6, today=today)["rows"]:
            deploy += r["inflow"]
            if r["is_vest"]:
                deploy_month = r["month"]
                break
            surplus_until += r["inflow"]
    except Exception:
        pass

    rows, buy_raw = [], {}
    for k, w in weights.items():
        if not w and not cur[k]:
            continue
        tgt = w / wsum
        pct = 100 * cur[k] / total if total else 0
        drift = pct - 100 * tgt
        buy_raw[k] = max(0.0, (total + deploy) * tgt - cur[k])
        rows.append({"key": k, **INVEST_BUCKETS[k], "target": round(100 * tgt, 1), "value": round(cur[k]),
                     "pct": round(pct, 1), "drift": round(drift, 1),
                     # 5/25 as in Allocation: ±5 pp or 25% of the weight
                     "flag": ("overweight" if drift > 0 else "top up") if (abs(drift) >= 5 or abs(drift) >= 25 * tgt) else "ok"})
    scale = deploy / sum(buy_raw.values()) if sum(buy_raw.values()) else 0
    for r in rows:
        r["buy"] = round(buy_raw[r["key"]] * scale)

    blended = sum(INVEST_BUCKETS[k]["ret"] * w for k, w in weights.items()) / wsum
    contrib = (P.monthly_surplus() or 0) + (P._annual_extras().get("monthly_equivalent") or 0)
    proj = []
    for yrs in (5, 10, 15):
        row = {"years": yrs, "contributed": round(total + contrib * 12 * yrs)}
        for name, r in (("cautious", 4.0), ("base", blended), ("optimistic", 9.0)):
            bal, rm = total, r / 100 / 12
            for _ in range(yrs * 12):
                bal = bal * (1 + rm) + contrib
            row[name] = round(bal)
        proj.append(row)
    return {"rows": rows, "total": round(total), "deploy": round(deploy), "deploy_month": deploy_month,
            "surplus_until_vest": round(surplus_until), "contrib_monthly": round(contrib),
            "blended_return_pct": round(blended, 1), "projection": proj, "themes": themes}
