"""Thin adapters over finance-assistant engines -> JSON-safe dicts.

All heavy lifting stays in the skill's scripts; this module only shapes
payloads for the API. Import AFTER config.setup() so FINANCE_PROJECT_DIR
is resolved before finance_storage computes the data dir.
"""
import re
import uuid
from datetime import date, datetime, timedelta

import db  # local self-contained SQLite layer


def _rows(query, params=()):
    with db.get_conn() as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        cur = conn.execute(query, params)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


def _exec(query, params=()):
    with db.get_conn() as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        cur = conn.execute(query, params)
        conn.commit()
        return cur.lastrowid


# ---------- safe SQL building with column names ----------
# Values always go through parameters (?, tuple). Table/column names cannot be
# parametrised, so we validate them to a bare identifier — this blocks injection
# even if a column name ever comes from untrusted input in the future.
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _ident(name):
    if not _IDENT_RE.match(name or ""):
        raise ValueError("unsafe SQL identifier: %r" % (name,))
    return name


def update_sql(table, columns, where="id"):
    """Build a parametrised UPDATE for the given columns (identifiers validated).
    Returns the SQL string; bind values yourself in column order + the where value.
    The string is built OUTSIDE the execute() call on purpose."""
    sets = ", ".join(_ident(c) + " = ?" for c in columns)
    return "update " + _ident(table) + " set " + sets + " where " + _ident(where) + " = ?"


# ---------- dashboard ----------

def dashboard_summary():
    month = date.today().strftime("%Y-%m")
    income = _rows(
        "select coalesce(sum(amount),0) s from transactions "
        "where type='income' and date like ?", (month + "%",))[0]["s"]
    expenses = _rows(
        "select coalesce(sum(abs(amount)),0) s from transactions "
        "where type='expense' and date like ?", (month + "%",))[0]["s"]
    accounts = _rows("select name, type, balance, currency from accounts")
    total_balance = sum(a["balance"] or 0 for a in accounts)
    holdings = _rows("select coalesce(sum(current_price*quantity),0) s from holdings")[0]["s"]
    debts = _rows("select coalesce(sum(balance),0) s from debts")[0]["s"]
    by_category = _rows(
        "select category, sum(abs(amount)) total from transactions "
        "where type='expense' and date like ? group by category "
        "order by total desc limit 8", (month + "%",))
    return {
        "month": month,
        "income": income,
        "expenses": expenses,
        "savings_rate": round((income - expenses) / income * 100, 1) if income else None,
        "accounts": accounts,
        "cash_total": total_balance,
        "investments_total": holdings,
        "debt_total": debts,
        "net_worth": total_balance + holdings - debts,
        "expenses_by_category": by_category,
    }


def net_worth_history():
    snaps = _rows(
        "select date, data from snapshots where type='net_worth' order by date")
    import json
    out = []
    for s in snaps:
        try:
            d = json.loads(s["data"])
            out.append({"date": s["date"], "net_worth": d.get("net_worth") or d.get("total")})
        except Exception:
            continue
    return out


def spending_trends(months=6):
    out = []
    today = date.today().replace(day=1)
    for i in range(months - 1, -1, -1):
        y, m = today.year, today.month - i
        while m <= 0:
            y, m = y - 1, m + 12
        key = f"{y:04d}-{m:02d}"
        row = _rows(
            "select coalesce(sum(abs(amount)),0) e from transactions "
            "where type='expense' and date like ?", (key + "%",))[0]
        inc = _rows(
            "select coalesce(sum(amount),0) i from transactions "
            "where type='income' and date like ?", (key + "%",))[0]
        out.append({"month": key, "expenses": row["e"], "income": inc["i"]})
    return out


# ---------- transactions ----------

TX_TYPES = ("income", "expense", "transfer", "investment", "debt_payment")


def list_transactions(month=None, category=None, limit=200):
    q = "select id, account_id, date, amount, type, currency, category, description, payee from transactions"
    conds, params = [], []
    if month:
        conds.append("date like ?"); params.append(month + "%")
    if category:
        conds.append("category = ?"); params.append(category)
    if conds:
        q += " where " + " and ".join(conds)
    q += " order by date desc, id desc limit ?"
    params.append(limit)
    return _rows(q, tuple(params))


def _default_account_id():
    rows = _rows("select id from accounts order by id limit 1")
    if rows:
        return rows[0]["id"]
    acc_id = str(uuid.uuid4())
    _exec(
        "insert into accounts (id, name, type, balance, currency, institution, updated_at) "
        "values (?,?,?,?,?,?,?)",
        (acc_id, "Main", "checking", 0, "PLN", "",
         datetime.now().isoformat(timespec="seconds")))
    return acc_id


def add_transaction(data):
    assert data.get("type") in TX_TYPES, "invalid type"
    if not data.get("account_id"):
        data["account_id"] = _default_account_id()
    tx_id = str(uuid.uuid4())
    _exec(
        "insert into transactions (id, account_id, date, amount, type, currency, category, description, payee, source, created_at) "
        "values (?,?,?,?,?,?,?,?,?,?,?)",
        (tx_id, data.get("account_id"), data["date"], float(data["amount"]), data["type"],
         data.get("currency", "PLN"), data.get("category", "other"),
         data.get("description", ""), data.get("payee", ""), "budget-app",
         datetime.now().isoformat(timespec="seconds")))
    return tx_id


def update_transaction(tx_id, data):
    cols, params = [], []
    for k in ("date", "amount", "type", "currency", "category", "description", "payee"):
        if k in data:
            cols.append(k)
            params.append(data[k])
    if not cols:
        return
    params.append(tx_id)
    _exec(update_sql("transactions", cols), tuple(params))


def delete_transaction(tx_id):
    _exec("delete from transactions where id = ?", (tx_id,))


def categories():
    rows = _rows("select distinct category from transactions where category is not null order by category")
    return [r["category"] for r in rows]


def budget_vs_actual(month=None):
    month = month or date.today().strftime("%Y-%m")
    budgets = _rows(
        "select category, limit_amount from budget_categories where month = ?", (month,))
    actuals = {r["category"]: r["t"] for r in _rows(
        "select category, sum(abs(amount)) t from transactions "
        "where type='expense' and date like ? group by category", (month + "%",))}
    seen = set()
    out = []
    for b in budgets:
        seen.add(b["category"])
        out.append({"category": b["category"], "limit": b["limit_amount"],
                    "actual": actuals.get(b["category"], 0)})
    for cat, actual in actuals.items():
        if cat not in seen:
            out.append({"category": cat, "limit": None, "actual": actual})
    return {"month": month, "rows": sorted(out, key=lambda r: -(r["actual"] or 0))}
