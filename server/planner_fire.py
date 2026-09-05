"""planner_fire — FIRE / work-optional: projekcja, stożek, snapshoty i śledzenie postępu.

Wydzielone z planner.py 2026-09-05 (kod 1:1; odwołania do innych modułów przez `P`).
"""
from datetime import date, datetime

import engine_bridge as eb
from planner_proxy import P

# ---------- FIRE / work-optional projection (zamiast Monte Carlo) ----------

def fire_projection():
    """Liquid-portfolio projection toward the work-optional goal, 3 scenarios
    zwrotu + wersja realna (po inflacji). Czytelne linie zamiast histogramu MC."""
    from datetime import date
    goals = P.list_goals()
    g = next((x for x in goals if any(k in x["name"].lower()
             for k in ("work-optional", "liquid", "independent", "portfolio"))), None)
    start = (g and g.get("current_amount")) or 289000
    target = (g and g.get("target_amount")) or 1000000
    base_month = P.monthly_surplus() or 10000
    extras = P._annual_extras().get("monthly_equivalent", 0) or 0
    contrib = base_month + extras
    # after the loan is paid off, the freed installment adds to savings
    freed = 0
    try:
        loan = next((d for d in P.list_debts()["debts"] if any(k in d["name"].lower()
                     for k in ("mortgage", "loan", "home", "house"))), None)
        freed = loan.get("monthly_cost_total", 0) if loan else 0
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
    freed_from = 12
    try:
        lp = P.cashflow().get("target_paid_month")
        if lp:
            freed_from = max(0, (int(lp[:4]) - today.year) * 12 + (int(lp[5:7]) - today.month))
    except Exception:
        pass

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
    delay = 5
    try:
        cf = P.cashflow()
        lp = cf.get("loan_paid_month")
        if lp:
            delay = max(0, (int(lp[:4]) - today.year) * 12 + (int(lp[5:7]) - today.month))
    except Exception:
        pass
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

    # --- snapshot + tracking (plan vs realnie) ---
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
                  "note": "Down-payment accumulation starts after the loan is paid off (~" + (label_at(delay)) + "). Cautious 4% return (funds close to the goal). NOTE: the same surpluses as work-optional — buying the house delays reaching 3M."},
        "tracking": tracking,
        "assumptions": {"base_return": "6.5% nominal", "inflation": f"{infl * 100:g}% (target indexed)",
                        "income_growth": f"{growth * 100:g}%/yr (contributions grow with income)", "tax": f"{tax * 100:g}% on gains at withdrawal",
                        "contrib_note": f"{round(contrib)}/mo (savings {round(base_month)} + net bonus/RSU {round(extras)}); after the loan payoff (+{round(freed)}) from {label_at(freed_from)}"},
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
        nw = P.wealth_summary()["total"] - P.wealth_summary()["debt_total"]
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
