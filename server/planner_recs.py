"""planner_recs — Recommendation engine with memory and outcomes, cushion, essential costs, brokerage portfolio.

Split out of planner.py on 2026-09-05 (code moved 1:1; other modules are reached through `P`).
"""

import engine_bridge as eb
from planner_proxy import P

# ---------- recommendation engine ----------
# Rule-based, encodes frameworks from the installed wealth-management skills:
# emergency-fund (3-6x essential costs), debt-management (avalanche +
# opportunity cost vs expected market return), diversification (concentration
# limits), tax-efficiency (tax-advantaged wrappers first), savings-goals.

EXPECTED_MARKET_RETURN = 6.5  # % nominal, conservative after-cost assumption
BROKERAGE_HAIRCUT = 0.8       # share of the ETF/stock portfolio counted toward the cushion (a crash = −20…−25%)


def _pct_setting(key, default):
    v = P._num(P.get_setting(key))
    return default if v is None else v


def capital_gains_tax_pct():
    return _pct_setting("capital_gains_tax_pct", 19.0)


def expected_return_after_tax():
    """Expected market return AFTER capital gains tax — the number a loan rate must beat
    (interest is not deductible, so 'overpayment = net return'). 6.5% × 0.81 ≈ 5.3%."""
    return round(EXPECTED_MARKET_RETURN * (1 - capital_gains_tax_pct() / 100), 2)


def essential_monthly():
    """ONE definition of essential monthly costs (fixed expenses marked essential → legacy
    fixed_costs blob → debt service alone). Returns (essential, debt_service)."""
    d = P.list_debts()
    monthly_debt = d.get("monthly_cost_total") or 0
    exp_essential = P.expense_summary().get("essential_mine")
    if exp_essential:
        return float(exp_essential), monthly_debt
    fc = P._num((P.get_json_setting("fixed_costs") or {}).get("essential_mine"))
    if fc:
        return fc, monthly_debt
    return float(monthly_debt), monthly_debt


def liquid_cushion(w=None):
    """Cushion = cash + 80% of the brokerage portfolio (ETF/stocks, not RSU). Retirement
    accounts are NOT counted — early withdrawal costs matching and tax; shown separately."""
    w = w or P.wealth_summary()
    cash = broker = retire = 0.0
    for it in w["items"]:
        v = it.get("latest_value") or 0
        if v <= 0 or it.get("kind") == "income":
            continue
        cls = P._alloc_class(it.get("name", ""))
        if it.get("kind") == "cushion" or cls == "cash":
            cash += v
        elif cls == "etf":
            broker += v
        elif cls == "retirement":
            retire += v
    # the tax reserve (capital-gains tax due) sits in cash but is a liability, not a cushion
    cash = max(0.0, cash - (w.get("tax_reserve") or 0))
    return {"cash": round(cash), "brokerage": round(broker), "brokerage_counted": round(broker * BROKERAGE_HAIRCUT),
            "retirement": round(retire), "total": round(cash + broker * BROKERAGE_HAIRCUT), "haircut": BROKERAGE_HAIRCUT}


def _rec_key(area, text):
    import hashlib
    return area + ":" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def _rec_memory(items):
    """Recommendation memory: first/last time each one appeared (key = area + text);
    disappearing = 'resolved'. Without memory every recommendation looked new every day.
    Each item also carries its `key` and a recorded `outcome`, if any."""
    _ensure_rec_log()
    now = P._now(); seen = set()
    for r in items:
        k = _rec_key(r["area"], r["text"]); seen.add(k)
        r["key"] = k
        row = eb._rows("select first_seen, resolved_at, outcome, outcome_note from rec_log where key=?", (k,))
        if row:
            eb._exec("update rec_log set last_seen=?, resolved_at=NULL where key=?", (now, k))
            r["since"] = row[0]["first_seen"][:10]
            r["outcome"] = row[0].get("outcome")
            r["outcome_note"] = row[0].get("outcome_note")
        else:
            eb._exec("insert into rec_log (key, area, text, first_seen, last_seen) values (?,?,?,?,?)",
                     (k, r["area"], r["text"], now, now))
            r["since"] = now[:10]
    for row in eb._rows("select key from rec_log where resolved_at is null"):
        if row["key"] not in seen:
            eb._exec("update rec_log set resolved_at=? where key=?", (now, row["key"]))
    hist = eb._rows("select key, area, text, first_seen, resolved_at, outcome, outcome_note from rec_log "
                    "where resolved_at is not null order by resolved_at desc limit 10")
    return [{"key": h["key"], "area": h["area"], "text": h["text"], "since": h["first_seen"][:10],
             "resolved": h["resolved_at"][:10], "outcome": h.get("outcome"), "outcome_note": h.get("outcome_note")}
            for h in hist]


REC_OUTCOMES = ("done", "rejected", "obsolete")


def _ensure_rec_log():
    eb._exec("""create table if not exists rec_log (
        key text primary key, area text, text text, first_seen text, last_seen text, resolved_at text)""")
    for col in ("outcome", "outcome_note", "outcome_at"):
        try:
            eb._exec("alter table rec_log add column " + eb._ident(col) + " text")
        except Exception:
            pass  # column already exists


def set_rec_outcome(key, outcome, note=""):
    """Record what happened to a recommendation (done / rejected / obsolete) — without it the
    rules engine only "learns" that something disappeared, not whether it was worth following."""
    _ensure_rec_log()
    if outcome not in REC_OUTCOMES and outcome not in ("", None):
        raise ValueError("outcome")
    if not eb._rows("select 1 from rec_log where key=?", (key,)):
        raise KeyError(key)
    eb._exec("update rec_log set outcome=?, outcome_note=?, outcome_at=? where key=?",
             (outcome or None, (note or "")[:300], P._now() if outcome else None, key))
    P._audit("rec_log", key, "outcome", {"outcome": outcome})
    return {"key": key, "outcome": outcome or None}


def rec_review():
    """Monthly review: how many recommendations appeared / resolved / with which outcome;
    the list of resolved ones WITHOUT a recorded outcome (that is what needs closing)."""
    _ensure_rec_log()
    rows = eb._rows("select key, area, text, first_seen, last_seen, resolved_at, outcome, outcome_note, outcome_at "
                    "from rec_log order by first_seen desc")
    months = {}
    for r in rows:
        m = (r["first_seen"] or "")[:7]
        mm = months.setdefault(m, {"month": m, "new": 0, "resolved": 0, "executed": 0, "rejected": 0,
                                   "stale": 0, "no_outcome": 0})
        mm["new"] += 1
        if r.get("resolved_at"):
            mm["resolved"] += 1
        oc = r.get("outcome")
        if oc == "done":
            mm["executed"] += 1
        elif oc == "rejected":
            mm["rejected"] += 1
        elif oc == "obsolete":
            mm["stale"] += 1
        elif r.get("resolved_at"):
            mm["no_outcome"] += 1
    pending = [{"key": r["key"], "area": r["area"], "text": r["text"], "since": r["first_seen"][:10],
                "resolved": r["resolved_at"][:10]}
               for r in rows if r.get("resolved_at") and not r.get("outcome")]
    total = len(rows)
    executed = sum(1 for r in rows if r.get("outcome") == "done")
    return {"months": sorted(months.values(), key=lambda x: x["month"], reverse=True)[:12],
            "pending": pending, "total": total, "executed": executed,
            "with_outcome": sum(1 for r in rows if r.get("outcome")),
            "execution_rate_pct": round(executed / total * 100) if total else None}


def _zl(v):
    cur = P.get_setting("base_currency") or "PLN"
    return f"{v:,.0f}".replace(",", " ") + " " + cur


def recommendation():
    w = P.wealth_summary()
    d = P.list_debts()
    cfg = P.settings()
    goals = [g for g in P.list_goals() if g["status"] == "active"]

    t = w["totals"]
    # Cushion definition: cash (kind=cushion) + brokerage + pension — all
    # quickly liquidable. A tenant deposit (a liability) is excluded by kind.
    lc = liquid_cushion(w)
    cushion = lc["total"]
    assets = w["total"] - t.get("income", 0)  # income kind is a monthly figure, not an asset
    real_estate = sum(i["latest_value"] or 0 for i in w["items"]
                      if i["kind"] == "investment" and "ieszkanie" in i["name"])
    monthly_debt_cost = d["monthly_cost_total"]
    essential_m, _ = essential_monthly()
    after_tax = expected_return_after_tax()

    recs = []

    # rebalancing per the 5/25 rule (threshold beats calendar — Vanguard/Bernstein)
    try:
        breaches = [r for r in P.allocation()["rows"] if r["flag"] != "ok" and r["value"] > 0]
        if breaches:
            lines = "\n".join(f"{b['label']}: {b['pct']}% vs target {b['target']}% "
                              f"({'+' if b['drift'] > 0 else ''}{b['drift']} pp)" for b in breaches[:3])
            recs.append({"area": "rebalancing (5/25)", "priority": 2,
                         "title": "Allocation outside the 5/25 band: steer new contributions to classes below target",
                         "text": (f"{lines}\nAdding to underweight classes triggers no tax, selling would. "
                                  "Targets are editable in the Allocation tab.")})
    except Exception:
        pass

    # 0. user-chosen strategy overrides generic debt heuristics
    strategy = P.get_setting("debt_strategy")
    if strategy:
        # the volatile part (loan events since the note) goes to the title, not the text: the text
        # is the rec_log key, so every installment changed the key and dropped the recorded outcome
        at = P.get_setting("debt_strategy_at")
        title = "Your debt strategy" + (f" (written {at[:10]})" if at else "")
        if at:
            ev = eb._rows("select count(*) n, coalesce(sum(principal_paid),0) p from debt_values where created_at > ?", (at,))[0]
            if ev["n"]:
                title += (f" ⚠️ loan events since: {ev['n']} (principal repaid {_zl(ev['p'])}), "
                          "check the numbers")
        recs.append({"area": "strategy (your decision)", "priority": 0, "title": title, "text": strategy})

    # 1. emergency fund
    target = essential_m * 6
    if essential_m > 0 and cushion < target:
        gap = target - cushion
        recs.append({
            "area": "emergency fund", "priority": 1,
            "title": f"Emergency cushion: {_zl(gap)} short of 6 months of essential costs",
            "text": (f"You have {_zl(cushion)}: cash {_zl(lc['cash'])} + {int(lc['haircut'] * 100)}% of the "
                     f"brokerage portfolio ({_zl(lc['brokerage_counted'])}).\n"
                     f"Target ~{_zl(target)}, i.e. 6 × ~{_zl(essential_m)}/mo.\n"
                     f"Retirement accounts ({_zl(lc['retirement'])}) are counted separately: early withdrawal costs.\n"
                     "The cushion comes before overpayments and investing.")})

    # 2. debt avalanche vs investing
    for debt in sorted(d["debts"], key=lambda x: -(x["effective_rate"] or 0)):
        rate = debt["effective_rate"] or 0
        if debt["balance"] <= 0:
            continue
        if rate > after_tax:
            recs.append({
                "area": "debts", "priority": 6 if strategy else 2,
                "title": f"Overpay {debt['name']}: {rate:.2f}% beats the market after tax (~{after_tax}%)",
                "text": (f"Market after tax: {EXPECTED_MARKET_RETURN}% × (1 − {capital_gains_tax_pct():g}%) ≈ {after_tax}%.\n"
                         f"An overpayment is a guaranteed, untaxed {rate:.1f}% return.\n"
                         f"Interest to maturity at the current installment: {_zl(debt['schedule']['total_interest'] or 0)}.")})
        else:
            recs.append({
                "area": "debts", "priority": 4,
                "title": f"{debt['name']}: do not overpay aggressively ({rate:.2f}% effective)",
                "text": (f"Cheap debt: the market after tax returns ~{after_tax}%, so the money works "
                         "comparably or better elsewhere.")})
        break  # avalanche: only the top-rate debt gets the action

    # 2b. refinancing: fixed rate far above current market
    rates = P._market_rates()
    if rates.get("wibor3m"):
        for debt in d["debts"]:
            margin = debt.get("margin_after_fixed") or rates.get("typical_margin", 2.0)
            market_rate = rates["wibor3m"] + margin
            gap = (debt["effective_rate"] or 0) - market_rate
            if gap > 1.0 and debt["balance"] > 100000:
                yearly = debt["balance"] * gap / 100
                extra = ""
                if debt.get("fixed_until"):
                    extra = (f"\nThe fixed rate ends {debt['fixed_until']} and the installment drops by itself then. Until "
                             "then check a margin renegotiation at your bank, or refinancing. "
                             "On a fixed rate read the contract first: early-repayment compensation.")
                recs.append({
                    "area": "refinancing", "priority": 2,
                    "title": f"{debt['name']}: ~{_zl(yearly)}/yr of interest above the market",
                    "text": (f"You pay {debt['effective_rate']:.2f}%, the market is ~{market_rate:.2f}% "
                             f"(WIBOR {rates['wibor3m']}% + margin {margin}%). Gap {gap:.1f} pp.{extra}")})
                recs.append({
                    "area": "bank negotiations", "priority": 2,
                    "title": f"Negotiate {debt['name']}: get an offer from another bank and show it to yours",
                    "text": ("1. File refinancing applications at 2–3 banks (free, about a week). "
                             "A real offer negotiates better than a bluff.\n"
                             "2. At your own bank request a balance-and-history certificate 'for refinancing'. "
                             "The bank reads it as a leaving signal and the retention team often calls by itself.\n"
                             "3. Write or call: 'I have an offer at X%, I am considering moving, what can you propose?'\n"
                             "4. A counter-offer from your bank usually comes within 2–4 weeks. If it does not, "
                             "refinance for real, but first check the early-repayment compensation in the "
                             "contract (fixed rate).")})

    # 3. concentration / diversification
    if assets > 0 and real_estate / assets > 0.7:
        pct = real_estate / assets * 100
        recs.append({
            "area": "diversification", "priority": 3,
            "title": f"Real estate is {pct:.0f}% of wealth: direct new savings into liquid instruments",
            "text": ("Almost all wealth sits in one asset class and one country.\n"
                     "Order: retirement-account limits first (instant tax benefit), then a broad ETF.")})

    # 4. goals
    if not goals:
        recs.append({
            "area": "goals", "priority": 5, "title": "Add an active goal",
            "text": "Goals tab (e.g. a home down payment). With a goal, job offers and the savings pace "
                    "start counting toward it."})
    if P.monthly_surplus() in (None, 0):
        recs.append({
            "area": "goals", "priority": 5, "title": "Set a monthly savings pace",
            "text": "In Goals or Cash-flow (base surplus). Without it goal projections and job-offer "
                    "comparisons do not work."})

    recs.sort(key=lambda r: r["priority"])
    history = _rec_memory(recs)
    return {
        "history": history,
        "headline": recs[0]["text"] if recs else "The data looks healthy — no urgent actions.",
        "items": recs,
        "facts": {
            "cushion": cushion, "cushion_parts": lc, "cushion_target": target,
            "after_tax_return_pct": after_tax,
            "monthly_debt_cost": monthly_debt_cost,
            "real_estate_share": round(real_estate / assets * 100, 1) if assets else None,
            "top_debt_rate": max((x["effective_rate"] or 0) for x in d["debts"]) if d["debts"] else None,
        },
    }


# ---------- brokerage portfolio recommendation ----------
# Rules from diversification / asset-allocation / rebalancing skills:
# duplicate-instrument detection, theme concentration, single-position caps,
# contribution steering toward the underweight broad-market sleeve.

SINGLE_POSITION_CAP = 10.0   # % of portfolio per single stock
THEME_CAP = 60.0             # % per theme before it's flagged


def xtb_recommendation():
    pf = P.get_json_setting("xtb_portfolio")
    if not pf:
        return None
    pos = pf.get("positions", [])
    total = sum(p["value"] for p in pos)
    if not pos or total <= 0:
        return None
    recs = []

    # 1. same instrument held in more than one container
    by_name = {}
    for p in pos:
        by_name.setdefault(p["name"], []).append(p)
    for name, hits in by_name.items():
        if len(hits) > 1:
            v = sum(h["value"] for h in hits)
            where = " and ".join(h["container"] for h in hits)
            recs.append({
                "area": "duplicates", "priority": 1,
                "text": (f"You hold {name} in {where} at the same time (total {_zl(v)}) — "
                         f"the same instrument in two places: double wrapper fees "
                         f"with zero diversification. Consolidate into one bucket.")})

    # 2. theme concentration
    by_theme = {}
    for p in pos:
        by_theme[p["theme"]] = by_theme.get(p["theme"], 0) + p["value"]
    for theme, v in sorted(by_theme.items(), key=lambda kv: -kv[1]):
        share = v / total * 100
        if share > THEME_CAP:
            recs.append({
                "area": "concentration", "priority": 2,
                "text": (f"The '{theme}' theme is {share:.0f}% of the brokerage portfolio ({_zl(v)}). "
                         f"Funds and stocks in one theme largely hold the same companies, so real "
                         f"diversification is much smaller than the number of positions suggests.")})
            break

    # 3. single-stock cap
    for p in pos:
        if p["container"] in ("Stocks", "Akcje") and p["theme"] != "world":  # "Akcje": older imports
            share = p["value"] / total * 100
            if share > SINGLE_POSITION_CAP:
                recs.append({
                    "area": "single stocks", "priority": 3,
                    "text": (f"{p['name']} = {share:.0f}% of the brokerage portfolio — above "
                             f"the reasonable {SINGLE_POSITION_CAP:.0f}% cap per single "
                             f"stock. Consider trimming at the next rebalance "
                             f"(mind the {capital_gains_tax_pct():g}% capital gains tax on the profit).")})

    # 4. contribution steering: broad-world sleeve underweight
    world = by_theme.get("world", 0)
    world_share = world / total * 100
    if world_share < 20:
        recs.append({
            "area": "contributions", "priority": 4,
            "text": (f"The broad market is only {world_share:.0f}% of the portfolio. To raise it "
                     f"without selling (a sale triggers capital gains tax), send new contributions "
                     f"to a broad world ETF until it reaches your target share.")})

    recs.sort(key=lambda r: r["priority"])
    return {
        "headline": recs[0]["text"] if recs else "The brokerage portfolio looks healthy.",
        "items": recs,
        "facts": {
            "total": round(total, 2),
            "themes": {k: round(v / total * 100, 1) for k, v in by_theme.items()},
            "duplicates": [n for n, h in by_name.items() if len(h) > 1],
        },
    }
