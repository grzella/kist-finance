"""Thin adapters over finance-assistant engines -> JSON-safe dicts.

All heavy lifting stays in the skill's scripts; this module only shapes
payloads for the API. Import AFTER config.setup() so FINANCE_PROJECT_DIR
is resolved before finance_storage computes the data dir.
"""
import re
from datetime import date

import db  # local self-contained SQLite layer


def _rows(query, params=()):
    with db.get_conn() as conn:
        cur = conn.execute(query, params)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


def _exec(query, params=()):
    with db.get_conn() as conn:
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
    # app.py fills the money totals from wealth items; only the legacy transactions
    # breakdown (the category chart's fallback) still comes from here
    month = date.today().strftime("%Y-%m")
    by_category = _rows(
        "select category, sum(abs(amount)) total from transactions "
        "where type='expense' and date like ? group by category "
        "order by total desc limit 8", (month + "%",))
    return {"month": month, "expenses_by_category": by_category}


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
