"""planner_expenses — Fixed expenses: per-month items (carry-forward), currencies, cost hints.

Split out of planner.py on 2026-09-05 (code moved 1:1; other modules are reached through `P`).
"""
import uuid
from datetime import date

import engine_bridge as eb
from planner_proxy import P

# ---------- fixed expenses ----------

def add_expense_item(data):
    item_id = str(uuid.uuid4())
    eb._exec(
        "insert into expense_items (id, name, category, payer, essential, "
        "currency, entity, invoice, billing, created_at) values (?,?,?,?,?,?,?,?,?,?)",
        (item_id, data["name"], data.get("category", ""),
         data.get("payer", "me"), 1 if data.get("essential", True) else 0,
         data.get("currency", "USD"), data.get("entity", "personal"),
         1 if data.get("invoice") else 0,
         "yearly" if data.get("billing") == "yearly" else "monthly", P._now()))
    P._audit("expense_item", item_id, "add", data)
    if data.get("amount") is not None:
        set_expense_value(item_id, data.get("month") or date.today().strftime("%Y-%m"),
                          data["amount"])
    return item_id


def update_expense_item(item_id, data):
    cols, params = [], []
    for k in ("name", "category", "payer", "essential", "currency", "archived", "entity",
              "invoice", "billing"):
        if k in data:
            v = data[k]
            if k in ("essential", "archived", "invoice"):
                v = 1 if v else 0
            if k == "billing":
                v = "yearly" if v == "yearly" else "monthly"
            cols.append(k); params.append(v)
    if cols:
        params.append(item_id)
        eb._exec(eb.update_sql("expense_items", cols), tuple(params))
        P._audit("expense_item", item_id, "update", data)


def delete_expense_item(item_id):
    P._audit("expense_item", item_id, "delete")
    eb._exec("delete from expense_values where item_id = ?", (item_id,))
    eb._exec("delete from expense_items where id = ?", (item_id,))


def set_expense_value(item_id, month, amount):
    """Amount for this item in a given month (YYYY-MM). Setting it again for
    the same month overwrites — it never multiplies rows."""
    eb._exec(
        "insert into expense_values (id, item_id, month, amount, created_at) "
        "values (?,?,?,?,?) on conflict(item_id, month) do update set amount=excluded.amount",
        (str(uuid.uuid4()), item_id, month, float(amount), P._now()))
    P._audit("expense_value", item_id, "set", {"month": month, "amount": amount})


def expense_item_history(item_id):
    return eb._rows(
        "select month, amount from expense_values where item_id = ? order by month",
        (item_id,))


_SUB_CATEGORY_LABELS = {
    "subscription-work": "Subscriptions: work",
    "subscription-entertainment": "Subscriptions: entertainment",
    "subscription-health": "Subscriptions: health / sport",
    "subscription-other": "Subscriptions: other",
}


def expense_summary():
    """Items + latest known amount per item (carry-forward — an item with no
    entry this month simply 'carries' its last known value, so you never
    retype the whole list) + total/essential trend over time."""
    items = eb._rows(
        "select * from expense_items where archived = 0 order by category, name")
    cur_month = date.today().strftime("%Y-%m")
    fx_cache = {}

    def _fx(ccy):
        """Item currency → base rate (1.0 for the base). Amounts are STORED in the item's currency
        and converted on every read — a PLN amount typed 'at the day's rate' lies six months later."""
        ccy = (ccy or "PLN").upper()
        if ccy not in fx_cache:
            try:
                import market as _mkt
                fx_cache[ccy] = _mkt.fx_to_base(ccy)
            except Exception:
                fx_cache[ccy] = None
        return fx_cache[ccy]

    for it in items:
        vals = eb._rows(
            "select month, amount from expense_values where item_id = ? "
            "order by month desc limit 1", (it["id"],))
        raw = vals[0]["amount"] if vals else None
        rate = _fx(it.get("currency"))
        base_ccy = "PLN"
        it["latest_amount_ccy"] = raw
        it["fx_rate"] = rate
        it["fx_missing"] = bool(raw is not None and rate is None)
        it["latest_amount"] = (round(raw * rate, 2) if (raw is not None and rate) else raw)
        it["latest_month"] = vals[0]["month"] if vals else None
        it["current_month_set"] = bool(vals and vals[0]["month"] == cur_month)

    history = eb._rows(
        "select v.month, v.item_id, v.amount, i.essential, i.payer, i.currency "
        "from expense_values v join expense_items i on i.id = v.item_id "
        "where i.archived = 0 order by v.month")
    per_item = {}
    for row in history:
        rate = _fx(row.get("currency")) or 1.0
        per_item.setdefault(row["item_id"], []).append(
            (row["month"], row["amount"] * rate, row["essential"], row["payer"]))
    all_months = sorted({m for series in per_item.values() for m, *_ in series}
                        | ({cur_month} if per_item else set()))
    trend = []
    for m in all_months:
        total = essential_total = 0.0
        for series in per_item.values():
            past = [r for r in series if r[0] <= m]
            if not past:
                continue
            _, amount, essential, payer = past[-1]
            if payer != "me":
                continue
            total += amount
            if essential:
                essential_total += amount
        trend.append({"month": m, "total": round(total, 2),
                      "essential": round(essential_total, 2)})
    latest = trend[-1] if trend else {"total": 0, "essential": 0}
    by_category = {}
    for it in items:
        if it.get("latest_amount") and it.get("payer") == "me":
            cat = it.get("category") or ""
            if cat in _SUB_CATEGORY_LABELS:
                label = _SUB_CATEGORY_LABELS[cat]
            elif it.get("entity") and it["entity"] != "personal":
                label = it["entity"].capitalize()
            else:
                label = "Personal (other)"
            by_category[label] = by_category.get(label, 0) + it["latest_amount"]
    invoiceable = round(sum(it["latest_amount"] or 0 for it in items if it.get("invoice")), 2)
    return {
        "items": items,
        "total_mine": latest["total"],
        "essential_mine": latest["essential"],
        "invoiceable_total": invoiceable,
        "trend": trend,
        "by_category": sorted(
            ({"category": k, "total": round(v, 2)} for k, v in by_category.items()),
            key=lambda x: -x["total"]),
        "current_month": cur_month,
        "optimizations": _expense_optimizations(items, cur_month),
    }


def _expense_optimizations(items, cur_month):
    """Cost-optimization hints — cheap heuristics recomputed every time the
    tab loads. Honest framing: these read your own data; they don't scan the
    market for live deals (that would fit a scheduled/background job)."""
    tips = []
    active = [i for i in items if i.get("latest_amount")]

    def _months_ago(m):
        try:
            y1, mo1 = map(int, cur_month.split("-"))
            y2, mo2 = map(int, (m or cur_month).split("-"))
            return (y1 - y2) * 12 + (mo1 - mo2)
        except Exception:
            return 0
    stale = [i for i in active if _months_ago(i.get("latest_month")) >= 3]
    if stale:
        tips.append({"kind": "stale", "severity": "info",
                     "text": f"{len(stale)} item(s) not updated in 3+ months — "
                             f"double-check current prices/deals: "
                             + ", ".join(i["name"] for i in stale[:5])})

    ent = [i for i in active if i.get("category") == "subscription-entertainment"]
    if len(ent) >= 3:
        s = round(sum(i["latest_amount"] for i in ent), 2)
        tips.append({"kind": "entertainment", "severity": "warn",
                     "text": f"{len(ent)} entertainment subscriptions = {s}/mo "
                             f"({round(s*12)}/yr). You rarely watch all of them at once — "
                             "consider rotating (keep 1–2 active, cycle the rest seasonally)."})

    # annual billing where monthly (usually 15–20% cheaper). Source of truth is the
    # `billing` field (toggle in the table), not a guess from the item name.
    monthly_subs = [i for i in active if (i.get("category") or "").startswith("subscription-")
                    and (i.get("billing") or "monthly") != "yearly"]
    if monthly_subs:
        s = round(sum(i["latest_amount"] for i in monthly_subs), 2)
        save_lo, save_hi = round(s * 12 * 0.15), round(s * 12 * 0.20)
        tips.append({"kind": "annual", "severity": "info" if len(monthly_subs) < 4 else "warn",
                     "text": f"{len(monthly_subs)} subscription(s) bill monthly ({s}/mo): "
                             + ", ".join(i["name"] for i in monthly_subs[:6])
                             + (", …" if len(monthly_subs) > 6 else "")
                             + f". An annual plan is often 15–20% cheaper — roughly "
                             f"{save_lo}–{save_hi}/yr. Check at the next renewal and flip "
                             "the item to \"yearly\" in the table."})

    inv = [i for i in active if i.get("invoice")]
    if inv:
        s = round(sum(i["latest_amount"] for i in inv), 2)
        tips.append({"kind": "invoice", "severity": "info",
                     "text": f"{len(inv)} item(s) tagged as invoiced = {s}/mo in "
                             "deductible/business costs — keep the actual invoices matched "
                             "to these amounts."})
    return tips


def wealth_item_history(item_id):
    return eb._rows(
        "select date, value from wealth_values where item_id = ? order by date",
        (item_id,))
