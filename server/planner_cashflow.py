"""planner_cashflow — Płynność: oś czasu cash-flow netto, podsumowanie podatków.

Wydzielone z planner.py 2026-09-05 (kod 1:1; odwołania do innych modułów przez `P`).
"""
from datetime import date, datetime
from planner_proxy import P

# ---------- cash-flow / liquidity timeline ----------

CF_DEFAULTS = {  # generic starting values — real ones live in the DB (git-ignored)
    "cf_monthly_surplus": 5000,    # base surplus per month
    "cf_safety_buffer": 30000,     # safety buffer (floor of the liquid balance)
    "cf_liquid_start": 0,          # starting liquid funds
    "cf_bonus_month": 9,           # bonus month
    "cf_sweep_target": "debt",  # where surplus is swept: loan name/fragment, 'debt' (highest rate) or 'none'
    "capital_gains_tax_pct": 19,   # capital gains tax on share sales
    "cash_vest_net_factor": 0.55,  # share of the cash-vest left net on the payslip     # where surplus goes: loan | property | none
}


def _cash_liquid_now():
    """Cash from wealth (class 'cash' + kind 'cushion'), in the base currency."""
    try:
        w = P.wealth_summary()
        return round(sum((it.get("latest_value") or 0) for it in w["items"]
                         if (it.get("latest_value") or 0) > 0
                         and (it.get("kind") == "cushion" or P._alloc_class(it.get("name", "")) == "cash")), 0)
    except Exception:
        return None


def cashflow(months=15, today=None):
    """Forward liquidity, NET: base surplus + vests from the grant SCHEDULE (× 1 − tax)
    + net cash-vest + bonus; the tax reserve on shares is set aside separately (not liquidity).
    Surplus above the buffer is swept into the loan named by cf_sweep_target — after payoff
    (or with no target) it simply accumulates."""
    import market as _mkt
    from datetime import date

    def _cf(key):
        v = P._num(P.get_setting(key))
        return v if v is not None else CF_DEFAULTS[key]

    surplus = P.monthly_surplus() if P.monthly_surplus() is not None else CF_DEFAULTS["cf_monthly_surplus"]
    buffer = _cf("cf_safety_buffer")
    manual_start = P._num(P.get_setting("cf_liquid_start"))
    auto_start = _cash_liquid_now()
    if manual_start is not None and manual_start > 0:
        liquid, liquid_source = manual_start, "manual"
    else:
        liquid, liquid_source = (auto_start if auto_start is not None else CF_DEFAULTS["cf_liquid_start"]), "wealth"
    bonus_month = int(_cf("cf_bonus_month"))
    bonus = P._num(P.get_setting("annual_bonus_net")) or 0
    sweep_cfg = (P.get_setting("cf_sweep_target") or CF_DEFAULTS["cf_sweep_target"] or "none").strip().lower()

    debts = P.list_debts()["debts"]
    target = None
    if sweep_cfg not in ("none", "", "goal"):
        key = sweep_cfg.split(":", 1)[1] if sweep_cfg.startswith("debt:") else sweep_cfg
        cands = [d for d in debts if d["balance"] > 0 and (key in d["name"].lower()
                 or (key == "loan" and any(k in d["name"].lower() for k in ("mortgage", "loan", "home", "house"))))]
        if not cands and key in ("debt", "top"):
            cands = [d for d in debts if d["balance"] > 0]
        target = sorted(cands, key=lambda d: -(d.get("effective_rate") or 0))[0] if cands else None
    sweep_mode = "debt" if target else "accumulate"
    loan_bal = target["balance"] if target else 0
    loan_principal = (target.get("principal_month") if target else 0) or 0
    loan_freed = target.get("monthly_cost_total", 0) if target else 0

    rsu = {}
    try:
        rsu = _mkt.get_rsu()
    except Exception:
        pass
    sched = {m["month"]: m for m in (rsu.get("vest_schedule") or [])}
    last, fx = rsu.get("last_close") or 0, rsu.get("usdpln") or 0
    nf = rsu.get("net_factor") or 0.81
    cf_net = rsu.get("cash_vest_net_factor") or 0.55
    tax_pct = rsu.get("tax_pct") or 19.0
    vest_months = set(rsu.get("vest_months") or [2, 5, 8, 11])

    today = today or date.today()
    y, m = today.year, today.month
    rows = []
    loan_paid_month = None
    base_surplus = surplus
    reserve = 0.0
    for i in range(months):
        mm = ((m - 1 + i) % 12) + 1
        yy = y + (m - 1 + i) // 12
        label = f"{yy:04d}-{mm:02d}"
        inflow = base_surplus
        parts = [f"surplus {P._zl(base_surplus)}"]
        vest_row = sched.get(label)
        vest_gross = vest_net = cash_net = 0.0
        if vest_row and last and fx:
            vest_gross = vest_row["shares"] * last * fx
            vest_net = vest_gross * nf
            cash_net = (vest_row.get("cash_usd") or 0) * fx * cf_net
            if vest_net:
                inflow += vest_net
                parts.append(f"vest {vest_row['shares']:.0f} shares {P._zl(vest_net)} netto")
            if cash_net:
                inflow += cash_net
                parts.append(f"cash-vest {P._zl(cash_net)} netto")
            reserve += vest_gross * tax_pct / 100
        if mm == bonus_month and bonus:
            inflow += bonus
            parts.append(f"bonus {P._zl(bonus)}")
        liquid += inflow
        overpay = 0
        if loan_bal > 0:
            overpay = max(0, min(liquid - buffer, loan_bal))
            liquid -= overpay
            loan_bal = max(0, loan_bal - loan_principal - overpay)
            if loan_bal <= 0 and loan_paid_month is None:
                loan_paid_month = label
                base_surplus = surplus + loan_freed
        rows.append({
            "month": label,
            "inflow": round(inflow, 0),
            "inflow_parts": " · ".join(parts),
            "vest_net": round(vest_net, 0), "cash_vest_net": round(cash_net, 0),
            "overpay_loan": round(overpay, 0), "overpay": round(overpay, 0),
            "liquid": round(liquid, 0),
            "tax_reserve": round(reserve, 0),
            "loan_balance": round(loan_bal, 0), "target_balance": round(loan_bal, 0),
            "below_buffer": liquid < buffer - 1,
            "is_vest": bool(vest_row) and vest_net > 0,
            "is_bonus": mm == bonus_month and bool(bonus),
        })
    return {
        "rows": rows,
        "buffer": buffer,
        "sweep_mode": sweep_mode,
        "sweep_target_name": target["name"] if target else None,
        "sweep_setting": sweep_cfg,
        "loan_start": target["balance"] if target else 0,
        "loan_paid_month": loan_paid_month,
        "loan_freed_monthly": loan_freed,
        "target_start": target["balance"] if target else 0,
        "target_paid_month": loan_paid_month,
        "target_freed_monthly": loan_freed,
        "liquid_start": round(liquid if not rows else (rows[0]["liquid"] - rows[0]["inflow"] + rows[0]["overpay"]), 0),
        "liquid_start_source": liquid_source,
        "liquid_start_auto": auto_start,
        "tax_reserve_total": round(reserve, 0),
        "assumptions": {
            "cf_monthly_surplus": surplus,
            "cf_safety_buffer": buffer,
            "cf_liquid_start": manual_start,
            "annual_bonus_net": bonus,
            "net_factor": nf, "cash_vest_net_factor": cf_net, "tax_pct": tax_pct,
            "vest_value_pln": rsu.get("next_vest_value_net_pln"),
            "vest_months": sorted(vest_months),
            "cf_sweep_target": sweep_cfg,
        },
    }


# ---------- taxes ----------

TAX_DEFAULTS = {  # generic starting values — real ones live in the DB (git-ignored)
    "tax_rental_monthly": 2000,
    "tax_rental_rate": 8.5,
    "tax_zus_monthly": 431.54,   # official reduced social-security amount (public figure)
    "tax_salary_gross_annual": 150000,
}


def tax_summary():
    from datetime import date
    def _t(k):
        v = P._num(P.get_setting(k))
        return v if v is not None else TAX_DEFAULTS[k]
    rental_m = _t("tax_rental_monthly"); rate = _t("tax_rental_rate")
    zus = _t("tax_zus_monthly"); salary = _t("tax_salary_gross_annual")
    try:
        biz = P.biz_summary(); biz_result = biz.get("total_result", 0)
    except Exception:
        biz_result = 0
    biz_profit = max(0, biz_result)
    rental_annual = rental_m * 12
    rental_tax = round(rental_annual * rate / 100, 0)
    zus_annual = round(zus * 12, 0)
    biz_rate = (P._num(P.get_setting("tax_biz_rate_pct")) or 12) / 100
    biz_pit = round(biz_profit * biz_rate, 0)
    try:
        import market as _mkt
        rsu_tax = _mkt.rsu_tax_summary()
    except Exception:
        rsu_tax = {"year": date.today().year, "tax_pct": 19, "gross_pln": 0, "tax_due_pln": 0,
                   "shares_sold": 0, "deadline": f"{date.today().year + 1}-04-30", "sales_count": 0}

    items = [
        {"source": "Rental (lump-sum)", "rate": f"{rate}%",
         "base": rental_annual, "tax": rental_tax, "cadence": "monthly by the 20th",
         "managed": "you", "note": "lump-sum tax on revenue — no deductions"},
        {"source": "business — social security/health", "rate": "—", "base": None, "tax": zus_annual,
         "cadence": "monthly by the 20th", "managed": "you (sole prop.)",
         "note": "With an employment contract ≥ minimum wage → overlapping titles: the sole proprietorship is usually EXEMPT from social contributions, you pay only the health premium. This is NOT a time-limited preference while the job lasts (confirm with your accountant what the 431.54 covers)"},
        {"source": "business — income tax on profit", "rate": "12–32% / 19%", "base": biz_profit,
         "tax": biz_pit, "cadence": "monthly/quarterly advance", "managed": "you (sole prop.)",
         "note": "currently a loss → 0; the loss offsets future profits"},
        {"source": f"RSU — capital gains tax on {rsu_tax['year']} sales", "rate": f"{rsu_tax['tax_pct']:g}%",
         "base": rsu_tax["gross_pln"], "tax": rsu_tax["tax_due_pln"],
         "cadence": f"by {rsu_tax['deadline']}", "managed": "you",
         "note": (f"{rsu_tax['shares_sold']:.0f} shares sold in {rsu_tax['year']} — tax on the FULL sale amount "
                  "(incentive plan: cost basis ≈ 0), not on the gain after vest. Reserve deducted from net worth."
                  if rsu_tax["sales_count"] else "no sales this year — log sales in the RSU tab and the tax computes itself")},
        {"source": "Salary — income tax", "rate": "up to 32%", "base": salary, "tax": None,
         "cadence": "withheld by the employer", "managed": "employer",
         "note": "for reference — you do not manage it yourself (PIT-11)"},
    ]
    self_managed = rental_tax + zus_annual + biz_pit + (rsu_tax["tax_due_pln"] or 0)

    today = date.today()
    def nth(month_offset, day):
        m = today.month + month_offset; y = today.year
        while m > 12: m -= 12; y += 1
        return f"{y:04d}-{m:02d}-{day:02d}"
    calendar = [
        {"date": nth(0 if today.day < 20 else 1, 20), "what": "Rental lump-sum tax + business social security",
         "amount": round(rental_tax / 12 + zus, 0)},
        {"date": f"{today.year + (1 if today.month > 4 else 0):04d}-04-30",
         "what": "Annual: PIT-28 (rental) + PIT-36L/sole prop.", "amount": None},
    ]
    if rsu_tax["tax_due_pln"]:
        calendar.append({"date": rsu_tax["deadline"], "what": f"Capital gains tax on {rsu_tax['year']} RSU sales (reserve)",
                         "amount": rsu_tax["tax_due_pln"]})
    optimizations = [
        "RSU: sell at vest — the tax (capital gains on the full sale amount under an incentive plan) is the same today and in a year, while holding adds single-stock risk; move the tax reserve to a separate account right away (due 30 April next year).",
        "Cash vs equity: cash is income tax up to 32%, sold shares are 19% capital gains — a ~13 pp difference. Choose consciously (cash raises borrowing capacity).",
        "Rental: the 8.5% lump sum is usually favorable at low costs; if big renovations/interest come in, recompute the progressive scale.",
        "Sole proprietorship: the start-up years' loss lowers future income tax once the business turns a profit — worth 'keeping' it in the filing.",
        "Social security with overlapping titles: with an employment contract ≥ minimum wage, the sole proprietorship usually pays ONLY the health premium — social contributions are exempt. Note: after losing the job, social contributions kick in (and the preferential window may have passed).",
    ]
    return {"items": items, "self_managed_annual": round(self_managed, 0),
            "calendar": calendar, "optimizations": optimizations,
            "assumptions": {"tax_rental_monthly": rental_m, "tax_rental_rate": rate,
                        "tax_biz_rate_pct": (P._num(P.get_setting("tax_biz_rate_pct")) or 12),
                            "tax_zus_monthly": zus}}
