"""planner_debts — Kredyty: amortyzacja, meta, tempo spłaty, projekcja zmiennej stopy, nadpłaty.

Wydzielone z planner.py 2026-09-05 (kod 1:1; odwołania do innych modułów przez `P`).
"""
import uuid
from datetime import date, datetime

import engine_bridge as eb
from planner_proxy import P

# ---------- debts ----------

def _amortize(balance, annual_rate_pct, payment):
    """Months to payoff + total interest at fixed payment. None if payment
    doesn't cover interest."""
    r = (annual_rate_pct or 0) / 100 / 12
    if balance <= 0:
        return {"months": 0, "total_interest": 0}
    if payment <= balance * r:
        return {"months": None, "total_interest": None}
    months, interest, b = 0, 0.0, balance
    while b > 0 and months < 1200:
        i = b * r
        interest += i
        b -= (payment - i)
        months += 1
    return {"months": months, "total_interest": round(interest, 2)}


def _month_key(d=None):
    return (d or date.today()).strftime("%Y-%m")


def _debt_last_entry(debt_id):
    rows = eb._rows(
        "select month, balance from debt_values where debt_id = ? "
        "order by month desc, rowid desc limit 1", (debt_id,))
    return rows[0] if rows else None


def _post_month(debt, month, note="auto"):
    """Apply one scheduled payment: split into interest + principal.
    Prefers the bank's actual split (debt_meta) over the nominal-rate model."""
    balance = debt["balance"]
    if debt.get("interest_month_actual") and debt.get("principal_month_actual"):
        interest = debt["interest_month_actual"]
        principal = round(min(balance, debt["principal_month_actual"]), 2)
        note += " (wg banku)"
    else:
        r = (debt["interest_rate"] or 0) / 100 / 12
        interest = round(balance * r, 2)
        principal = round(min(balance, (debt["minimum_payment"] or 0) - interest), 2)
    if principal < 0:
        principal = 0  # payment below interest: balance would grow; keep flat, flag via note
        note += " (rata < odsetki!)"
    new_balance = round(balance - principal, 2)
    eb._exec(
        "insert into debt_values (id, debt_id, month, balance, principal_paid, "
        "interest_paid, note, created_at) values (?,?,?,?,?,?,?,?)",
        (str(uuid.uuid4()), debt["id"], month, new_balance, principal, interest,
         note, P._now()))
    eb._exec("update debts set balance = ?, updated_at = ? where id = ?",
             (new_balance, P._now(), debt["id"]))
    debt["balance"] = new_balance


def _auto_roll(debt):
    """Post scheduled rata for every month elapsed since last entry."""
    last = _debt_last_entry(debt["id"])
    if not last:
        return
    cur = _month_key()
    y, m = int(last["month"][:4]), int(last["month"][5:7])
    while True:
        m += 1
        if m > 12:
            y, m = y + 1, 1
        month = f"{y:04d}-{m:02d}"
        if month > cur or debt["balance"] <= 0:
            break
        _post_month(debt, month)


DEBT_META_FIELDS = ("months_left", "extra_monthly", "insurance_repayment",
                    "insurance_property", "interest_month_actual",
                    "principal_month_actual", "fixed_until", "margin_after_fixed")


def _save_debt_meta(debt_id, data):
    if not any(k in data for k in DEBT_META_FIELDS):
        return
    rows = eb._rows("select * from debt_meta where debt_id = ?", (debt_id,))
    cur = rows[0] if rows else {k: None for k in DEBT_META_FIELDS}
    vals = [data.get(k, cur.get(k)) for k in DEBT_META_FIELDS]
    cols = ", ".join(DEBT_META_FIELDS)
    sets = ", ".join(f"{c}=excluded.{c}" for c in DEBT_META_FIELDS)
    eb._exec(
        f"insert into debt_meta (debt_id, {cols}) "
        f"values (?{',?' * len(DEBT_META_FIELDS)}) "
        f"on conflict(debt_id) do update set {sets}",
        (debt_id, *vals))


def _debt_pace(d, history):
    """Am I overpaying — and how fast. Model = the clean schedule from the
    first known balance (minimum payment, interest per rate); actual = the
    recorded history (auto rows + bank corrections + overpayments). A positive
    difference means you are AHEAD of schedule."""
    if not history:
        return {"insufficient": True, "points": []}
    by_month = {}
    for h in history:
        by_month[h["month"]] = h["balance"]  # last entry of a month wins
    months = sorted(by_month)
    r = (d.get("effective_rate") or d.get("interest_rate") or 0) / 100 / 12
    rata = d.get("minimum_payment") or 0
    model_b = by_month[months[0]]
    points = [{"month": months[0], "actual": by_month[months[0]],
               "model": round(model_b, 2)}]
    y, m = int(months[0][:4]), int(months[0][5:7])
    last = months[-1]
    while f"{y:04d}-{m:02d}" < last:
        m += 1
        if m > 12:
            y, m = y + 1, 1
        mk = f"{y:04d}-{m:02d}"
        model_b = max(0.0, model_b + model_b * r - rata)
        if mk in by_month:
            points.append({"month": mk, "actual": by_month[mk],
                           "model": round(model_b, 2)})
    if len(points) < 2:
        return {"insufficient": True, "points": points}
    ahead = round(points[-1]["model"] - points[-1]["actual"], 2)
    span = max(1, P._months_between(points[0]["month"] + "-01",
                                  points[-1]["month"] + "-01"))
    pace = round(ahead / span, 2)
    saved = None
    if rata > 0:
        a = _amortize(points[-1]["actual"], d.get("effective_rate") or 0, rata)
        b = _amortize(points[-1]["model"], d.get("effective_rate") or 0, rata)
        if a["months"] is not None and b["months"] is not None:
            saved = b["months"] - a["months"]
    return {"insufficient": False, "points": points, "ahead_pln": ahead,
            "pace_monthly": pace, "months_saved": saved,
            "n_months": span + 1}


def list_debts():
    debts = eb._rows("select * from debts order by balance desc")
    for d in debts:
        meta = eb._rows("select * from debt_meta where debt_id = ?", (d["id"],))
        for k in DEBT_META_FIELDS:
            d[k] = meta[0][k] if meta else None
        _auto_roll(d)
        r = (d["interest_rate"] or 0) / 100 / 12
        d["interest_month"] = d["interest_month_actual"] or round(d["balance"] * r, 2)
        d["principal_month"] = d["principal_month_actual"] or round(
            max(0, (d["minimum_payment"] or 0) - d["interest_month"]), 2)
        # effective rate: bank's actual interest beats the nominal rate
        if d["interest_month_actual"] and d["balance"] > 0:
            d["effective_rate"] = round(d["interest_month_actual"] * 12 / d["balance"] * 100, 4)
        else:
            d["effective_rate"] = d["interest_rate"]
        d["schedule"] = _amortize(d["balance"], d["effective_rate"], d["minimum_payment"] or 0)
        d["monthly_cost_total"] = round(
            (d["minimum_payment"] or 0) + (d["extra_monthly"] or 0)
            + (d["insurance_repayment"] or 0) + (d["insurance_property"] or 0), 2)
        d["variable_projection"] = _variable_projection(d)
        hist = eb._rows(
            "select month, balance, note from debt_values where debt_id = ? "
            "order by month, created_at", (d["id"],))
        d["pace"] = _debt_pace(d, hist)
        d["history"] = eb._rows(
            "select month, balance, principal_paid, interest_paid, note, created_at "
            "from debt_values where debt_id = ? order by month, created_at", (d["id"],))
        for h in d["history"]:
            n = (h.get("note") or "").lower()
            h["kind"] = ("start" if "initial" in n or "opening" in n else
                         "overpayment" if "overpay" in n else
                         "correction" if "correction" in n or "bank" in n else "installment")
    total = sum(d["balance"] for d in debts)
    return {"debts": debts, "total": total,
            "monthly_cost_total": round(sum(d["monthly_cost_total"] for d in debts), 2)}


def _market_rates():
    import json as _json
    raw = P.get_setting("market_rates")
    try:
        return _json.loads(raw) if raw else {}
    except ValueError:
        return {}


def _annuity(balance, annual_pct, months):
    r = annual_pct / 100 / 12
    if months <= 0 or balance <= 0:
        return 0
    if r == 0:
        return balance / months
    return balance * r / (1 - (1 + r) ** -months)


def _variable_projection(d):
    """After the fixed-rate period: WIBOR (current & forecast) + margin."""
    rates = _market_rates()
    if not d.get("fixed_until") or not rates.get("wibor3m"):
        return None
    margin = d.get("margin_after_fixed") or rates.get("typical_margin", 2.0)
    months_left = d.get("months_left") or (d["schedule"]["months"] or 0)
    # principal at the switch date: roll forward with actual principal pace
    from datetime import date as _date
    today = _date.today()
    try:
        fy, fm = int(d["fixed_until"][:4]), int(d["fixed_until"][5:7])
        months_to_switch = max(0, (fy - today.year) * 12 + fm - today.month)
    except (ValueError, IndexError):
        return None
    principal_m = d.get("principal_month") or 0
    bal_at_switch = max(0, d["balance"] - principal_m * months_to_switch)
    rem = max(1, months_left - months_to_switch)
    out = {"fixed_until": d["fixed_until"], "margin": margin,
           "balance_at_switch": round(bal_at_switch, 2), "rates_asof": rates.get("asof")}
    for key, wib in (("now", rates["wibor3m"]),
                     ("forecast", rates.get("wibor_forecast"))):
        if wib is None:
            continue
        rate = wib + margin
        rata = _annuity(bal_at_switch, rate, rem)
        out[key] = {"wibor": wib, "rate": round(rate, 2),
                    "rata": round(rata, 2),
                    "delta_vs_now": round(rata - (d["minimum_payment"] or 0), 2)}
    return out


def add_debt(data):
    debt_id = str(uuid.uuid4())
    eb._exec(
        "insert into debts (id, name, balance, interest_rate, minimum_payment, "
        "type, currency, updated_at) values (?,?,?,?,?,?,?,?)",
        (debt_id, data["name"], float(data["balance"]),
         float(data.get("interest_rate", 0)), float(data.get("minimum_payment", 0)),
         data.get("type", "mortgage"), data.get("currency", "PLN"), P._now()))
    # baseline entry for current month, so auto-roll starts next month
    eb._exec(
        "insert into debt_values (id, debt_id, month, balance, note, created_at) "
        "values (?,?,?,?,?,?)",
        (str(uuid.uuid4()), debt_id, _month_key(), float(data["balance"]),
         "initial balance", P._now()))
    _save_debt_meta(debt_id, data)
    P._audit("debt", debt_id, "add", data)
    return debt_id


def update_debt(debt_id, data):
    cols, params = [], []
    for k in ("name", "balance", "interest_rate", "minimum_payment", "type"):
        if k in data:
            cols.append(k); params.append(data[k])
    if cols:
        cols.append("updated_at"); params.append(P._now())
        params.append(debt_id)
        eb._exec(eb.update_sql("debts", cols), tuple(params))
    _save_debt_meta(debt_id, data)
    P._audit("debt", debt_id, "update", data)
    if "balance" in data:  # manual correction becomes a history point
        eb._exec(
            "insert into debt_values (id, debt_id, month, balance, note, created_at) "
            "values (?,?,?,?,?,?)",
            (str(uuid.uuid4()), debt_id, _month_key(), float(data["balance"]),
             "manual correction", P._now()))


def overpay_debt(debt_id, data):
    """One-off overpayment: 100% goes to principal."""
    debts = eb._rows("select * from debts where id = ?", (debt_id,))
    if not debts:
        return
    d = debts[0]
    amount = min(float(data["amount"]), d["balance"])
    new_balance = round(d["balance"] - amount, 2)
    eb._exec(
        "insert into debt_values (id, debt_id, month, balance, principal_paid, "
        "note, created_at) values (?,?,?,?,?,?,?)",
        (str(uuid.uuid4()), debt_id, _month_key(), new_balance, amount,
         "overpayment", P._now()))
    eb._exec("update debts set balance = ?, updated_at = ? where id = ?",
             (new_balance, P._now(), debt_id))
    P._audit("debt", debt_id, "overpay", {"amount": amount, "new_balance": new_balance})


def delete_debt(debt_id):
    P._audit("debt", debt_id, "delete")
    eb._exec("delete from debt_meta where debt_id = ?", (debt_id,))
    eb._exec("delete from debt_values where debt_id = ?", (debt_id,))
    eb._exec("delete from debts where id = ?", (debt_id,))
