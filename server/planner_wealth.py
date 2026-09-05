"""planner_wealth — Wealth: items and values, live pricing, trend, monthly net-worth snapshot.

Split out of planner.py on 2026-09-05 (code moved 1:1; other modules are reached through `P`).
"""
import uuid
from datetime import date

import engine_bridge as eb
from planner_proxy import P

# ---------- wealth ----------

def wealth_summary():
    items = eb._rows(
        "select * from wealth_items where archived = 0 order by kind, name")
    debts = eb._rows("select id, name, balance from debts")
    debt_by_id = {d["id"]: d for d in debts}
    live_px = {}

    def _live_value(it):
        """Valuation from the cached quote: units × close × FX→base. For the RSU
        grant's ticker units=NULL takes shares_held from rsu.json — one source of
        truth for the share count, no monthly value retyping."""
        tk = (it.get("ticker") or "").upper()
        if not tk:
            return None
        try:
            import market as _mkt
            if tk not in live_px:
                px = _mkt.prices(tk, days=7)
                live_px[tk] = px[-1] if px else None
            row = live_px[tk]
            if not row:
                return None
            units = it.get("units")
            if units is None:
                import json as _json
                g = _json.loads(_mkt._rsu_path().read_text())
                if (g.get("ticker") or "").upper() != tk:
                    return None
                units = g.get("shares_held") or 0
            val = units * row["close"]
            if (row.get("currency") or "USD") == "USD":
                fx, _ = _mkt._usd_base_rate()
                val *= fx or 0
            return {"value": round(val, 2), "date": row["date"], "units": units}
        except Exception:
            return None

    for it in items:
        vals = eb._rows(
            "select date, value from wealth_values where item_id = ? "
            "order by date desc, created_at desc, rowid desc limit 1", (it["id"],))
        it["latest_value"] = vals[0]["value"] if vals else None
        it["latest_date"] = vals[0]["date"] if vals else None
        # USD items: values are STORED in USD and converted to PLN with the
        # cached rate for totals/allocation/trend (entry stays in dollars)
        if (it.get("currency") or "PLN") == "USD" and it["latest_value"] is not None:
            try:
                import market as _mkt
                fx, _ = _mkt._usd_base_rate()
                if fx:
                    it["value_ccy"] = it["latest_value"]
                    it["latest_value"] = round(it["latest_value"] * fx, 2)
                    it["fx_rate"] = round(fx, 4)
            except Exception:
                pass
        lv = _live_value(it)
        if lv:
            it["latest_value"] = lv["value"]
            it["latest_date"] = lv["date"]
            it["live"] = True
            it["live_units"] = lv["units"]
        linked = debt_by_id.get(it.get("linked_debt_id"))
        it["debt_name"] = linked["name"] if linked else None
        it["debt_balance"] = linked["balance"] if linked else None
        it["equity"] = round((it["latest_value"] or 0) - linked["balance"], 2) if linked else None
    by_kind = {}
    for it in items:
        by_kind.setdefault(it["kind"], 0)
        by_kind[it["kind"]] += it["latest_value"] or 0
    # trend: sum of latest values per month across items
    history = eb._rows(
        "select substr(v.date,1,7) month, v.item_id, v.value, v.date, i.currency "
        "from wealth_values v join wealth_items i on i.id = v.item_id "
        "where i.archived = 0 order by v.date, v.rowid")
    # CARRY-FORWARD: a monthly point = the sum of the LAST KNOWN value of every
    # item (not just entries made that month). With mixed strip cadences
    # (real estate quarterly, live items with no rows) per-month summing
    # collapsed the chart. Live items contribute their current valuation in
    # the current month.
    _fx = None

    def _to_base(v, ccy):
        nonlocal _fx
        if (ccy or "PLN") != "USD":
            return v
        if _fx is None:
            try:
                import market as _mkt
                _fx, _ = _mkt._usd_base_rate()
            except Exception:
                _fx = 0
        return v * _fx if _fx else v

    per_item = {}
    for row in history:
        per_item.setdefault(row["item_id"], []).append(
            (row["month"], _to_base(row["value"], row.get("currency"))))
    cur_month = date.today().strftime("%Y-%m")
    all_months = sorted({m for series in per_item.values() for m, _ in series}
                        | ({cur_month} if per_item else set()))
    live_by_id = {it["id"]: it["latest_value"] for it in items if it.get("live")}
    monthly = {}
    for m in all_months:
        total = 0.0
        for iid, series in per_item.items():
            if m == cur_month and iid in live_by_id:
                continue  # live wins over the carried-forward stored value
            past = [v for (mm, v) in series if mm <= m]
            if past:
                total += past[-1]
        if m == cur_month:
            total += sum(v for v in live_by_id.values() if v is not None)
        monthly[m] = total
    trend = [{"month": m, "total": round(t, 2)} for m, t in sorted(monthly.items())]
    loans_total = eb._rows("select coalesce(sum(balance),0) s from debts")[0]["s"]
    # capital gains reserve on this year's share sales: money on the account, but not yours
    reserve = 0.0
    reserve_note = None
    try:
        import market as _mkt
        tx = _mkt.rsu_tax_summary()
        if tx.get("tax_due_pln"):
            reserve = float(tx["tax_due_pln"])
            reserve_note = f"PIT-38 {tx['year']} ({tx['shares_sold']:.0f} szt., do {tx['deadline']})" if not True else f"capital gains tax {tx['year']} ({tx['shares_sold']:.0f} shares, due {tx['deadline']})"
    except Exception:
        pass
    return {
        "items": items,
        "debts": debts,
        "totals": by_kind,
        "total": sum(v for v in by_kind.values()),
        "loans_total": loans_total,
        "tax_reserve": round(reserve, 2),
        "tax_reserve_note": reserve_note,
        "debt_total": round(loans_total + reserve, 2),
        "trend": trend,
    }


def add_wealth_item(data):
    assert data.get("kind") in P.WEALTH_KINDS, "invalid kind"
    item_id = str(uuid.uuid4())
    eb._exec(
        "insert into wealth_items (id, name, kind, owner, currency, notes, "
        "linked_debt_id, created_at) values (?,?,?,?,?,?,?,?)",
        (item_id, data["name"], data["kind"], data.get("owner", "joint"),
         data.get("currency", "PLN"), data.get("notes", ""),
         data.get("linked_debt_id"), P._now()))
    P._audit("wealth_item", item_id, "add", data)
    if data.get("value") is not None:
        add_wealth_value(item_id, {"value": data["value"]})
    return item_id


def update_wealth_item(item_id, data):
    cols, params = [], []
    for k in ("name", "kind", "owner", "currency", "notes", "archived",
              "linked_debt_id", "ticker", "units"):
        if k in data:
            cols.append(k); params.append(data[k])
    if cols:
        params.append(item_id)
        eb._exec(eb.update_sql("wealth_items", cols), tuple(params))
        P._audit("wealth_item", item_id, "update", data)


def delete_wealth_item(item_id):
    P._audit("wealth_item", item_id, "delete")
    eb._exec("delete from wealth_values where item_id = ?", (item_id,))
    eb._exec("delete from wealth_items where id = ?", (item_id,))


def add_wealth_value(item_id, data):
    eb._exec(
        "insert into wealth_values (id, item_id, date, value, created_at) "
        "values (?,?,?,?,?)",
        (str(uuid.uuid4()), item_id,
         data.get("date") or date.today().isoformat(),
         float(data["value"]), P._now()))
    P._audit("wealth_value", item_id, "add", data)


# ---------- monthly net-worth snapshot ----------

def ensure_monthly_snapshot():
    """One net-worth snapshot per month (skill's `snapshots` table) so the
    dashboard time-series builds itself as the app is used."""
    import json as _json
    month = date.today().strftime("%Y-%m")
    existing = eb._rows(
        "select 1 from snapshots where type='net_worth' and date like ?",
        (month + "%",))
    if existing:
        return
    w = wealth_summary()
    assets = w["total"] - w["totals"].get("income", 0)
    net = round(assets - w["debt_total"], 2)
    eb._exec(
        "insert into snapshots (date, type, data) values (?,?,?)",
        (date.today().isoformat(), "net_worth",
         _json.dumps({"net_worth": net, "assets": round(assets, 2),
                      "debts": round(w["debt_total"], 2)})))
    P._audit("snapshot", None, "add", {"net_worth": net})
