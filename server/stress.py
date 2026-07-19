"""Stress test — a deterministic "financial fire drill" (no AI, no simulation).

Three what-if scenarios computed straight from the user's data, each answered
in one plain sentence (the pattern advisors use: "in a 25% stock decline my
portfolio falls X, my cash covers Y months"). Plus a Guyton-Klinger-style
dynamic withdrawal policy for the work-optional phase: an initial rate with
±20% guardrails and a ±10% spending adjustment when a guardrail is crossed —
a policy that reacts to markets instead of a single fixed date.
"""
import planner


def _liquid_and_equity():
    w = planner.wealth_summary()
    liquid = equity = 0.0
    for it in w.get("items", []):
        kind = it.get("kind")
        val = it.get("latest_value") or 0
        if kind in ("cushion", "savings"):
            liquid += val
        if kind == "investment" and it.get("equity") is None:
            # unlinked investments (brokerage/ETF/stock); real estate carries
            # a linked loan and an equity figure, and doesn't crash like equities
            equity += val
    return liquid, equity, w


def _essential_monthly():
    import json as _json
    d = planner.list_debts()
    monthly_debt = d.get("monthly_cost_total") or 0
    fc_raw = planner.get_setting("fixed_costs")
    if fc_raw:
        try:
            fc = _json.loads(fc_raw).get("essential_mine")
            if fc:
                return float(fc), monthly_debt
        except ValueError:
            pass
    return monthly_debt, monthly_debt


def run():
    zl = planner._zl
    liquid, equity, w = _liquid_and_equity()
    essential, monthly_debt = _essential_monthly()
    d = planner.list_debts()
    total = w.get("total") or 0

    scenarios = []

    # 1. equity crash −25%
    loss = round(equity * 0.25)
    pct_of_wealth = round(100 * loss / total, 1) if total else 0
    scenarios.append({
        "icon": "📉", "title": "Stocks fall 25%",
        "impact": f"−{zl(loss)}",
        "detail": (f"Your equity-like holdings ({zl(equity)}) would lose {zl(loss)} "
                   f"— {pct_of_wealth}% of net wealth. Nothing to do if the horizon "
                   "is long; the plan should survive this on paper, which is the point of checking now.")
        if equity else "No equity-like holdings found — this scenario doesn't touch you."})

    # 2. rates +2pp on all debt
    extra_m = round(sum((db.get("balance") or 0) for db in d.get("debts", [])) * 0.02 / 12)
    scenarios.append({
        "icon": "📈", "title": "Interest rates +2pp",
        "impact": f"+{zl(extra_m)}/mo" if extra_m else "—",
        "detail": (f"Interest on your debt would cost about {zl(extra_m)} more per month "
                   f"({zl(extra_m * 12)}/yr). Check which loans have a fixed-rate period as the buffer.")
        if extra_m else "No debt — rate shocks don't reach you."})

    # 3. income stops
    runway = round(liquid / essential, 1) if essential else None
    scenarios.append({
        "icon": "🪫", "title": "Income stops",
        "impact": f"{runway} months" if runway is not None else "—",
        "detail": (f"Liquid assets ({zl(liquid)}) cover about {runway} months of essential "
                   f"costs ({zl(essential)}/mo incl. debt payments {zl(monthly_debt)}). "
                   + ("Solid — 6+ months is the usual bar." if (runway or 0) >= 6
                      else "Below the usual 6-month bar — see the emergency-fund recommendation."))
        if essential else "Set your fixed costs (Cash-flow tab) to compute the runway."})

    return {"scenarios": scenarios, "policy": withdrawal_policy(liquid, equity, essential)}


def withdrawal_policy(liquid=None, equity=None, essential=None):
    """Guyton-Klinger guardrails, applied to the work-optional portfolio:
    start at wd_initial_pct (default 5.0% — G-K's dynamic start beats a fixed
    4% because the rules below adjust spending), guardrails at ±20% of that
    rate, crossing one adjusts spending by 10%. No cuts in the last 15 years
    of a plan (classic G-K provision — noted, not modeled)."""
    if liquid is None:
        liquid, equity, _ = _liquid_and_equity()
        essential, _md = _essential_monthly()
    zl = planner._zl
    portfolio = (liquid or 0) + (equity or 0)
    init = planner._num(planner.get_setting("wd_initial_pct")) or 5.0
    spend_y = (essential or 0) * 12
    out = {"initial_pct": init, "upper_pct": round(init * 1.2, 2),
           "lower_pct": round(init * 0.8, 2), "portfolio": round(portfolio),
           "annual_spend": round(spend_y)}
    if not portfolio or not spend_y:
        out["verdict"] = "Add wealth items and fixed costs to compute the policy."
        return out
    cur = round(100 * spend_y / portfolio, 2)
    out["current_pct"] = cur
    need = round(spend_y / (init / 100))
    out["portfolio_needed"] = need
    if cur > out["upper_pct"]:
        out["verdict"] = (f"If you stopped working today you'd withdraw {cur}%/yr — above the "
                          f"{out['upper_pct']}% guardrail. G-K rule: cut spending 10% (or keep working; "
                          f"the portfolio for a calm {init}% start is {zl(need)}).")
    elif cur < out["lower_pct"]:
        out["verdict"] = (f"Withdrawals today would be only {cur}%/yr — below the {out['lower_pct']}% "
                          f"guardrail. G-K rule: you could spend ~10% more; you're past the work-optional bar.")
    else:
        out["verdict"] = (f"Today's implied withdrawal rate is {cur}%/yr — inside the "
                          f"{out['lower_pct']}–{out['upper_pct']}% guardrails around the {init}% start. "
                          f"Work-optional is a policy, not a date: crossing a guardrail adjusts spending ±10%.")
    return out
