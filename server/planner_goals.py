"""planner_goals — Goals: projection, ETA, extra inflows (bonus/vests), goal-path scenarios.

Split out of planner.py on 2026-09-05 (code moved 1:1; other modules are reached through `P`).
"""
import uuid
from datetime import date, datetime

import engine_bridge as eb
from planner_proxy import P

# ---------- goals ----------

def list_goals():
    goals = eb._rows("select * from goals order by created_at")
    cfg = P.settings()
    for g in goals:
        meta = eb._rows("select monthly_contribution from goal_meta where goal_id = ?",
                        (g["id"],))
        g["monthly_contribution"] = meta[0]["monthly_contribution"] if meta else None
        g["projection"] = _project(g, cfg)
    return goals


def _project(goal, cfg):
    remaining = (goal["target_amount"] or 0) - (goal["current_amount"] or 0)
    pace = goal.get("monthly_contribution")
    if not pace:
        base = cfg.get("monthly_savings") or 0
        try:
            base += _annual_extras()["monthly_equivalent"]
        except Exception:
            pass
        pace = base or None
    if remaining <= 0:
        return {"months": 0, "eta": date.today().isoformat(), "pace": pace}
    if not pace or pace <= 0:
        return {"months": None, "eta": None, "pace": pace}
    months = remaining / pace
    y, m = date.today().year, date.today().month + int(months + 0.999)
    y += (m - 1) // 12
    m = (m - 1) % 12 + 1
    # ETA as a RANGE, not a single date (a single date hides the pace uncertainty)
    import forecast_models as _fm
    band = _fm.goal_eta_band(remaining, pace)
    return {"months": round(months, 1), "eta": f"{y:04d}-{m:02d}", "pace": pace,
            "eta_band": band}


def add_goal(data):
    goal_id = str(uuid.uuid4())
    eb._exec(
        "insert into goals (id, name, target_amount, current_amount, target_date, "
        "currency, status, created_at, updated_at) values (?,?,?,?,?,?,?,?,?)",
        (goal_id, data["name"], float(data["target_amount"]),
         float(data.get("current_amount", 0)), data.get("target_date"),
         data.get("currency", "PLN"), "active", P._now(), P._now()))
    if data.get("monthly_contribution") is not None:
        eb._exec("insert into goal_meta (goal_id, monthly_contribution) values (?,?)",
                 (goal_id, float(data["monthly_contribution"])))
    P._audit("goal", goal_id, "add", data)
    return goal_id


def update_goal(goal_id, data):
    cols, params = [], []
    for k in ("name", "target_amount", "current_amount", "target_date", "currency", "status"):
        if k in data:
            cols.append(k); params.append(data[k])
    if cols:
        cols.append("updated_at"); params.append(P._now())
        params.append(goal_id)
        eb._exec(eb.update_sql("goals", cols), tuple(params))
    if "monthly_contribution" in data:
        mc = data["monthly_contribution"]
        if mc is None or mc == "":
            eb._exec("delete from goal_meta where goal_id = ?", (goal_id,))
        else:
            eb._exec("insert into goal_meta (goal_id, monthly_contribution) values (?,?) "
                     "on conflict(goal_id) do update set monthly_contribution=excluded.monthly_contribution",
                     (goal_id, float(mc)))
    P._audit("goal", goal_id, "update", data)


def delete_goal(goal_id):
    P._audit("goal", goal_id, "delete")
    eb._exec("delete from goal_meta where goal_id = ?", (goal_id,))
    eb._exec("delete from goals where id = ?", (goal_id,))


# ---------- goal path scenarios ----------

def _simulate_path(target, monthly_savings, debts, overpay_debt_id=None,
                   horizon_months=600):
    """Month-by-month: optionally throw all savings at one debt first
    (its freed monthly cost then boosts savings), accumulate toward target.
    Returns months to goal, payoff month, and total interest paid on the
    overpaid debt (for comparison against its natural schedule)."""
    state = {d["id"]: {"balance": d["balance"],
                       "r": (d["effective_rate"] or 0) / 100 / 12,
                       "payment": d["minimum_payment"] or 0,
                       "freed": d["monthly_cost_total"]}
             for d in debts}
    saved, interest_paid, payoff_month = 0.0, 0.0, None
    infl = P._pct_setting("inflation_pct", 3.0) / 100
    for m in range(1, horizon_months + 1):
        contrib = monthly_savings
        for did, st in state.items():
            if st["balance"] <= 0:
                contrib += st["freed"]  # paid-off debt frees its monthly cost
                continue
            i = st["balance"] * st["r"]
            pay = st["payment"]
            if did == overpay_debt_id:
                pay += monthly_savings
                contrib -= monthly_savings  # savings redirected to debt
            principal = min(st["balance"], pay - i)
            if did == overpay_debt_id:
                interest_paid += i
            st["balance"] -= principal
            if st["balance"] <= 0.01:
                st["balance"] = 0
                if did == overpay_debt_id and payoff_month is None:
                    payoff_month = m
        saved += max(0, contrib)
        if saved >= target * ((1 + infl) ** (m / 12.0)):  # the target grows with inflation (house prices too)
            return {"months": m, "payoff_month": payoff_month,
                    "interest_paid_on_target_debt": round(interest_paid, 2)}
    return {"months": None, "payoff_month": payoff_month,
            "interest_paid_on_target_debt": round(interest_paid, 2)}


def _annual_extras(today=None):
    """Bonus + RSU vests + cash-vest: real NET cash on top of the monthly surplus.
    Shares: the next 12 months from the grant schedule × price × (1 − tax at sale);
    cash-vest: × the payslip net factor. Previously gross and without cash-vest — the pace to
    the goal was overstated by ~19% on shares and ignored the cash part."""
    extras = {"bonus_net": P._num(P.get_setting("annual_bonus_net")) or 0,
              "rsu_annual": 0, "rsu_annual_gross": 0, "cash_vest_annual_net": 0,
              "rsu_shares_12m": 0, "net_factor": None}
    try:
        import market
        r = market.get_rsu()
        sched = r.get("vest_schedule") or []
        last, fx = r.get("last_close"), r.get("usdpln")
        if sched and last and fx:
            from datetime import date as _d
            today = today or _d.today()
            horizon = {f"{today.year + (today.month - 1 + i) // 12:04d}-{(today.month - 1 + i) % 12 + 1:02d}" for i in range(12)}
            nxt12 = [m for m in sched if m["month"] in horizon]
            shares = sum(m["shares"] for m in nxt12)
            cash_usd = sum(m.get("cash_usd", 0) for m in nxt12)
            nf = r.get("net_factor") or 0.81
            cf = r.get("cash_vest_net_factor") or 0.55
            extras["rsu_shares_12m"] = round(shares, 1)
            extras["rsu_annual_gross"] = round(shares * last * fx, 0)
            extras["rsu_annual"] = round(shares * last * fx * nf, 0)
            extras["cash_vest_annual_net"] = round(cash_usd * fx * cf, 0)
            extras["net_factor"] = nf
    except Exception:
        pass
    pct = P._num(P.get_setting("extras_to_goal_pct"))
    extras["pct_to_goal"] = pct if pct is not None else 100
    extras["monthly_equivalent"] = round(
        (extras["bonus_net"] + extras["rsu_annual"] + extras["cash_vest_annual_net"]) / 12
        * extras["pct_to_goal"] / 100, 2)
    return extras


def goal_scenarios():
    goals = [g for g in list_goals() if g["status"] == "active"]
    if not goals:
        return None
    goal = sorted(goals, key=lambda g: g["created_at"])[0]  # primary = oldest active
    target = (goal["target_amount"] or 0) - (goal["current_amount"] or 0)
    cfg = P.settings()
    base_savings = goal["monthly_contribution"] or cfg.get("monthly_savings") or 0
    extras = _annual_extras()
    savings = base_savings + extras["monthly_equivalent"]
    if target <= 0 or savings <= 0:
        return None
    d = P.list_debts()["debts"]
    scenarios = [{"key": "baseline", "label": "No overpayments — everything toward the goal",
                  **_simulate_path(target, savings, d)}]
    for debt in d:
        base_interest = debt["schedule"]["total_interest"]
        sim = _simulate_path(target, savings, d, overpay_debt_id=debt["id"])
        saved_interest = (round(base_interest - sim["interest_paid_on_target_debt"], 2)
                         if base_interest is not None else None)
        scenarios.append({
            "key": debt["id"], "label": f"Overpay first: {debt['name']}",
            **sim, "interest_saved": saved_interest})
    for sc in scenarios:
        if sc["months"]:
            y, m = date.today().year, date.today().month + sc["months"]
            y += (m - 1) // 12; m = (m - 1) % 12 + 1
            sc["eta"] = f"{y:04d}-{m:02d}"
            sc["years"] = round(sc["months"] / 12, 1)
    return {"goal": goal["name"], "target_remaining": target,
            "monthly_savings": savings, "base_savings": base_savings,
            "extras": extras, "scenarios": scenarios}
