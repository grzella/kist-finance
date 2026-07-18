"""Strategic planner: wealth entries, goals with projections, job offers.

App-owned tables (created here, prefixed to avoid clashing with the
finance-assistant skill's schema): wealth_items, wealth_values,
goal_meta, job_offers, app_settings. Goals reuse the skill's `goals` table.
"""
import uuid
from datetime import date, datetime

import engine_bridge as eb

OWNERS = ("ja", "żona", "wspólne")
WEALTH_KINDS = ("investment", "cushion", "savings", "income")


def _now():
    return datetime.now().isoformat(timespec="seconds")


def ensure_tables():
    eb._exec("""create table if not exists wealth_items (
        id text primary key, name text not null, kind text not null,
        owner text default 'wspólne', currency text default 'PLN',
        notes text default '', archived integer default 0,
        created_at text not null)""")
    eb._exec("""create table if not exists wealth_values (
        id text primary key, item_id text not null, date text not null,
        value real not null, created_at text not null)""")
    eb._exec("""create table if not exists goal_meta (
        goal_id text primary key, monthly_contribution real)""")
    eb._exec("""create table if not exists job_offers (
        id text primary key, company text not null, role text default '',
        recruiter text default '', total_monthly real not null,
        base_monthly real, bonus_pct real, work_model text default '',
        status text default 'nowa', received_at text, notes text default '',
        created_at text not null)""")
    eb._exec("""create table if not exists app_settings (
        key text primary key, value text)""")
    eb._exec("""create table if not exists app_audit (
        id text primary key, ts text not null, entity text not null,
        entity_id text default '', action text not null, payload text)""")
    eb._exec("""create table if not exists debt_meta (
        debt_id text primary key, months_left integer,
        extra_monthly real default 0, insurance_repayment real default 0,
        insurance_property real default 0)""")
    for col in ("interest_month_actual", "principal_month_actual",
                "margin_after_fixed"):
        try:
            eb._exec("alter table debt_meta add column " + eb._ident(col) + " real")
        except Exception:
            pass  # column exists
    try:
        eb._exec("alter table job_offers add column tier integer")
    except Exception:
        pass  # column exists
    try:
        eb._exec("alter table wealth_items add column linked_debt_id text")
    except Exception:
        pass  # column exists
    try:
        eb._exec("alter table debt_meta add column fixed_until text")
    except Exception:
        pass  # column exists
    eb._exec("""create table if not exists debt_values (
        id text primary key, debt_id text not null, month text not null,
        balance real not null, principal_paid real default 0,
        interest_paid real default 0, note text default '',
        created_at text not null)""")
    eb._exec("""create table if not exists rsu_predictions (
        id text primary key, made_on text not null, ticker text not null,
        price_now real not null, horizon_days integer not null,
        target_date text not null, p10 real, p50 real, p90 real,
        scored integer default 0, actual real, in_band integer,
        dir_correct integer, abs_err_pct real)""")
    eb._exec("""create table if not exists reminders (
        id text primary key, title text not null, due_date text,
        note text default '', done integer default 0, created_at text not null)""")
    eb._exec("""create table if not exists market_barometer (
        id text primary key, month text not null, em_openings integer,
        head_openings integer, region text default 'Europa (remote)',
        note text default '', created_at text not null)""")
    eb._exec("""create table if not exists fire_snapshots (
        month text primary key, liquid real not null, net_worth real,
        created_at text not null)""")


def _audit(entity, entity_id, action, payload=None):
    import json as _json
    eb._exec(
        "insert into app_audit (id, ts, entity, entity_id, action, payload) "
        "values (?,?,?,?,?,?)",
        (str(uuid.uuid4()), _now(), entity, entity_id or "", action,
         _json.dumps(payload or {}, ensure_ascii=False, default=str)))


def audit_log(entity=None, limit=500):
    q = "select ts, entity, entity_id, action, payload from app_audit"
    params = []
    if entity:
        q += " where entity = ?"; params.append(entity)
    q += " order by ts desc limit ?"; params.append(limit)
    return eb._rows(q, tuple(params))


def get_setting(key, default=None):
    rows = eb._rows("select value from app_settings where key = ?", (key,))
    return rows[0]["value"] if rows else default


def set_settings(data):
    for k, v in data.items():
        eb._exec("insert into app_settings (key, value) values (?,?) "
                 "on conflict(key) do update set value=excluded.value", (k, str(v)))
    _audit("settings", None, "update", data)
    return settings()


def settings():
    return {
        "current_total_monthly": _num(get_setting("current_total_monthly")),
        "monthly_savings": _num(get_setting("monthly_savings")),
    }


def _num(v):
    try:
        return float(v) if v is not None else None
    except ValueError:
        return None


# ---------- module registry + first-run app config ----------
# The app is modular: core is always on; optional modules map to frontend
# views (nav tabs). The first-run wizard writes app_config; the frontend
# hides nav/routes for disabled modules.

MODULES = [
    {"id": "debts",    "label": "Loans & mortgage",  "icon": "🏠",
     "desc": "Track loans with principal/interest split and overpayment scenarios.",
     "views": ["debts"], "default": True},
    {"id": "taxes",    "label": "Taxes",             "icon": "🏛️",
     "desc": "Consolidated tax sources and a payment calendar.",
     "views": ["taxes"], "default": True},
    {"id": "markets",  "label": "Markets & FX",      "icon": "📈",
     "desc": "Watchlist, price analytics and a currency signal engine (needs Supabase for live data).",
     "views": ["market", "currency"], "default": True},
    {"id": "rsu",      "label": "Equity / RSU",      "icon": "💎",
     "desc": "Vesting schedule, Monte-Carlo projection, sell-vs-hold guidance. Skip if you get no stock comp.",
     "views": ["rsu"], "default": False},
    {"id": "business", "label": "Side business",     "icon": "🚁",
     "desc": "Revenue/costs of a side business or self-employment.",
     "views": ["firma"], "default": False},
    {"id": "career",   "label": "Career tracker",    "icon": "💼",
     "desc": "Inbound job offers, market barometer, commit-activity tracker.",
     "views": ["offers", "career", "commits"], "default": False},
    {"id": "property", "label": "Property analysis", "icon": "🏡",
     "desc": "Deep-dive analysis for a property-purchase goal (location, financing, rental math).",
     "views": ["property"], "default": False},
]

CORE_VIEWS = ["dashboard", "cashflow", "recs", "wealth", "allocation", "goals",
              "forecasts", "control", "reminders", "data", "wizard"]


def get_app_config():
    import json as _json
    raw = get_setting("app_config")
    try:
        cfg = _json.loads(raw) if raw else {}
    except ValueError:
        cfg = {}
    mods = cfg.get("modules") or {m["id"]: m["default"] for m in MODULES}
    enabled_views = list(CORE_VIEWS)
    for m in MODULES:
        if mods.get(m["id"], m["default"]):
            enabled_views += m["views"]
    return {
        "wizard_completed": bool(cfg.get("wizard_completed")),
        "modules": mods,
        "registry": MODULES,
        "enabled_views": enabled_views,
    }


def save_app_config(data):
    import json as _json
    cur = get_app_config()
    mods = {m["id"]: bool((data.get("modules") or {}).get(m["id"], cur["modules"].get(m["id"], m["default"])))
            for m in MODULES}
    cfg = {"wizard_completed": bool(data.get("wizard_completed", cur["wizard_completed"])),
           "modules": mods}
    set_settings({"app_config": _json.dumps(cfg)})
    return get_app_config()


# ---------- wealth ----------

def wealth_summary():
    items = eb._rows(
        "select * from wealth_items where archived = 0 order by kind, name")
    debts = eb._rows("select id, name, balance from debts")
    debt_by_id = {d["id"]: d for d in debts}
    for it in items:
        vals = eb._rows(
            "select date, value from wealth_values where item_id = ? "
            "order by date desc, created_at desc, rowid desc limit 1", (it["id"],))
        it["latest_value"] = vals[0]["value"] if vals else None
        it["latest_date"] = vals[0]["date"] if vals else None
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
        "select substr(v.date,1,7) month, v.item_id, v.value, v.date "
        "from wealth_values v join wealth_items i on i.id = v.item_id "
        "where i.archived = 0 order by v.date, v.rowid")
    monthly = {}
    latest_in_month = {}
    for row in history:
        key = (row["month"], row["item_id"])
        latest_in_month[key] = row["value"]
    for (month, _item), value in latest_in_month.items():
        monthly.setdefault(month, 0)
        monthly[month] += value
    trend = [{"month": m, "total": round(t, 2)} for m, t in sorted(monthly.items())]
    debt_total = eb._rows("select coalesce(sum(balance),0) s from debts")[0]["s"]
    return {
        "items": items,
        "debts": debts,
        "totals": by_kind,
        "total": sum(v for v in by_kind.values()),
        "debt_total": debt_total,
        "trend": trend,
    }


def add_wealth_item(data):
    assert data.get("kind") in WEALTH_KINDS, "invalid kind"
    item_id = str(uuid.uuid4())
    eb._exec(
        "insert into wealth_items (id, name, kind, owner, currency, notes, "
        "linked_debt_id, created_at) values (?,?,?,?,?,?,?,?)",
        (item_id, data["name"], data["kind"], data.get("owner", "wspólne"),
         data.get("currency", "PLN"), data.get("notes", ""),
         data.get("linked_debt_id"), _now()))
    _audit("wealth_item", item_id, "add", data)
    if data.get("value") is not None:
        add_wealth_value(item_id, {"value": data["value"]})
    return item_id


def update_wealth_item(item_id, data):
    cols, params = [], []
    for k in ("name", "kind", "owner", "currency", "notes", "archived",
              "linked_debt_id"):
        if k in data:
            cols.append(k); params.append(data[k])
    if cols:
        params.append(item_id)
        eb._exec(eb.update_sql("wealth_items", cols), tuple(params))
        _audit("wealth_item", item_id, "update", data)


def delete_wealth_item(item_id):
    _audit("wealth_item", item_id, "delete")
    eb._exec("delete from wealth_values where item_id = ?", (item_id,))
    eb._exec("delete from wealth_items where id = ?", (item_id,))


def add_wealth_value(item_id, data):
    eb._exec(
        "insert into wealth_values (id, item_id, date, value, created_at) "
        "values (?,?,?,?,?)",
        (str(uuid.uuid4()), item_id,
         data.get("date") or date.today().isoformat(),
         float(data["value"]), _now()))
    _audit("wealth_value", item_id, "add", data)


def wealth_item_history(item_id):
    return eb._rows(
        "select date, value from wealth_values where item_id = ? order by date",
        (item_id,))


# ---------- goals ----------

def list_goals():
    goals = eb._rows("select * from goals order by created_at")
    cfg = settings()
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
    # ETA jako ZAKRES, nie jedna data (pojedyncza data ukrywa niepewność tempa)
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
         data.get("currency", "PLN"), "active", _now(), _now()))
    if data.get("monthly_contribution") is not None:
        eb._exec("insert into goal_meta (goal_id, monthly_contribution) values (?,?)",
                 (goal_id, float(data["monthly_contribution"])))
    _audit("goal", goal_id, "add", data)
    return goal_id


def update_goal(goal_id, data):
    cols, params = [], []
    for k in ("name", "target_amount", "current_amount", "target_date", "currency", "status"):
        if k in data:
            cols.append(k); params.append(data[k])
    if cols:
        cols.append("updated_at"); params.append(_now())
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
    _audit("goal", goal_id, "update", data)


def delete_goal(goal_id):
    _audit("goal", goal_id, "delete")
    eb._exec("delete from goal_meta where goal_id = ?", (goal_id,))
    eb._exec("delete from goals where id = ?", (goal_id,))


# ---------- job offers ----------

def _current_total_monthly():
    """Auto: obecny total mies. = base/12 + (bonus + RSU)/12. Dynamiczne (RSU śledzi kurs spółki)."""
    base = (_num(get_setting("tax_salary_gross_annual")) or 120000) / 12.0
    extras = _annual_extras().get("monthly_equivalent", 0) or 0
    return round(base + extras)


def list_offers():
    offers = eb._rows("select * from job_offers order by received_at desc, created_at desc")
    cfg = settings()
    goals = list_goals()
    current = _current_total_monthly()
    cfg["current_total_monthly"] = current
    savings = cfg.get("monthly_savings")
    for o in offers:
        o["delta_monthly"] = (o["total_monthly"] - current) if current else None
        o["goal_impact"] = []
        if current and savings and savings > 0:
            for g in goals:
                if g["status"] != "active":
                    continue
                remaining = (g["target_amount"] or 0) - (g["current_amount"] or 0)
                if remaining <= 0:
                    continue
                base_pace = g["monthly_contribution"] or savings
                base_months = remaining / base_pace
                # assumption: comp delta flows fully into savings for this goal
                new_pace = base_pace + (o["total_monthly"] - current)
                new_months = remaining / new_pace if new_pace > 0 else None
                o["goal_impact"].append({
                    "goal": g["name"],
                    "base_months": round(base_months, 1),
                    "new_months": round(new_months, 1) if new_months else None,
                    "months_saved": round(base_months - new_months, 1) if new_months else None,
                })
    return {"offers": offers, "settings": cfg, "stats": _offers_stats(offers, current)}


def _offers_stats(offers, current):
    """Market-signal stats for inbound offers (all unsolicited)."""
    if not offers:
        return None
    # timespan in months from earliest received_at to today
    dates = sorted(o["received_at"] for o in offers if o.get("received_at"))
    span_months = 1.0
    if dates:
        try:
            y0, m0 = int(dates[0][:4]), int(dates[0][5:7])
            today = date.today()
            span_months = max(1.0, (today.year - y0) * 12 + (today.month - m0) + 1)
        except (ValueError, IndexError):
            pass
    tier1 = [o for o in offers if o.get("tier") == 1]
    quantified = [o for o in offers if o.get("total_monthly")]
    vals = sorted(o["total_monthly"] for o in quantified)
    median = None
    if vals:
        n = len(vals)
        median = vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2
    ge = [o for o in quantified if current and o["total_monthly"] >= current]
    return {
        "total": len(offers),
        "span_months": round(span_months, 1),
        "tier1_count": len(tier1),
        "tier1_per_month": round(len(tier1) / span_months, 2),
        "per_month": round(len(offers) / span_months, 2),
        "quantified_count": len(quantified),
        "median_comp": round(median, 0) if median is not None else None,
        "range_low": vals[0] if vals else None,
        "range_high": vals[-1] if vals else None,
        "ge_current_count": len(ge),
        "ge_current_pct": round(100 * len(ge) / len(quantified)) if quantified else None,
        "current": current,
    }


def add_offer(data):
    offer_id = str(uuid.uuid4())
    eb._exec(
        "insert into job_offers (id, company, role, recruiter, total_monthly, "
        "base_monthly, bonus_pct, work_model, status, received_at, notes, tier, created_at) "
        "values (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (offer_id, data["company"], data.get("role", ""), data.get("recruiter", ""),
         float(data["total_monthly"]),
         _num(data.get("base_monthly")), _num(data.get("bonus_pct")),
         data.get("work_model", ""), data.get("status", "nowa"),
         data.get("received_at") or date.today().isoformat(),
         data.get("notes", ""),
         int(data["tier"]) if data.get("tier") not in (None, "") else None, _now()))
    _audit("offer", offer_id, "add", data)
    return offer_id


def update_offer(offer_id, data):
    cols, params = [], []
    for k in ("company", "role", "recruiter", "total_monthly", "base_monthly",
              "bonus_pct", "work_model", "status", "received_at", "notes", "tier"):
        if k in data:
            cols.append(k); params.append(data[k])
    if cols:
        params.append(offer_id)
        eb._exec(eb.update_sql("job_offers", cols), tuple(params))
        _audit("offer", offer_id, "update", data)


def delete_offer(offer_id):
    _audit("offer", offer_id, "delete")
    eb._exec("delete from job_offers where id = ?", (offer_id,))


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
         note, _now()))
    eb._exec("update debts set balance = ?, updated_at = ? where id = ?",
             (new_balance, _now(), debt["id"]))
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
        d["history"] = eb._rows(
            "select month, balance, principal_paid, interest_paid, note "
            "from debt_values where debt_id = ? order by month", (d["id"],))
    total = sum(d["balance"] for d in debts)
    return {"debts": debts, "total": total,
            "monthly_cost_total": round(sum(d["monthly_cost_total"] for d in debts), 2)}


def _market_rates():
    import json as _json
    raw = get_setting("market_rates")
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
           "balance_at_switch": round(bal_at_switch, 2)}
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
         data.get("type", "mortgage"), data.get("currency", "PLN"), _now()))
    # baseline entry for current month, so auto-roll starts next month
    eb._exec(
        "insert into debt_values (id, debt_id, month, balance, note, created_at) "
        "values (?,?,?,?,?,?)",
        (str(uuid.uuid4()), debt_id, _month_key(), float(data["balance"]),
         "stan początkowy", _now()))
    _save_debt_meta(debt_id, data)
    _audit("debt", debt_id, "add", data)
    return debt_id


def update_debt(debt_id, data):
    cols, params = [], []
    for k in ("name", "balance", "interest_rate", "minimum_payment", "type"):
        if k in data:
            cols.append(k); params.append(data[k])
    if cols:
        cols.append("updated_at"); params.append(_now())
        params.append(debt_id)
        eb._exec(eb.update_sql("debts", cols), tuple(params))
    _save_debt_meta(debt_id, data)
    _audit("debt", debt_id, "update", data)
    if "balance" in data:  # manual correction becomes a history point
        eb._exec(
            "insert into debt_values (id, debt_id, month, balance, note, created_at) "
            "values (?,?,?,?,?,?)",
            (str(uuid.uuid4()), debt_id, _month_key(), float(data["balance"]),
             "korekta ręczna", _now()))


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
         "nadpłata", _now()))
    eb._exec("update debts set balance = ?, updated_at = ? where id = ?",
             (new_balance, _now(), debt_id))
    _audit("debt", debt_id, "overpay", {"amount": amount, "new_balance": new_balance})


def delete_debt(debt_id):
    _audit("debt", debt_id, "delete")
    eb._exec("delete from debt_meta where debt_id = ?", (debt_id,))
    eb._exec("delete from debt_values where debt_id = ?", (debt_id,))
    eb._exec("delete from debts where id = ?", (debt_id,))


# ---------- recommendation engine ----------
# Rule-based, encodes frameworks from the installed wealth-management skills:
# emergency-fund (3-6x essential costs), debt-management (avalanche +
# opportunity cost vs expected market return), diversification (concentration
# limits), tax-efficiency (tax-advantaged wrappers first), savings-goals.

EXPECTED_MARKET_RETURN = 6.5  # % nominal, conservative after-cost assumption


def _zl(v):
    return f"{v:,.0f}".replace(",", " ") + " zł"


def recommendation():
    w = wealth_summary()
    d = list_debts()
    cfg = settings()
    goals = [g for g in list_goals() if g["status"] == "active"]

    t = w["totals"]
    # The cushion definition: cash (kind=cushion) + brokerage + pension — all
    # quickly liquidable. Kaucja najemców (zobowiązanie) is excluded by kind.
    liquid_extra = sum(i["latest_value"] or 0 for i in w["items"]
                       if i["name"].startswith("brokerage") or i["name"] == "pension")
    cushion = t.get("cushion", 0) + liquid_extra
    assets = w["total"] - t.get("income", 0)  # income kind is a monthly figure, not an asset
    real_estate = sum(i["latest_value"] or 0 for i in w["items"]
                      if i["kind"] == "investment" and "ieszkanie" in i["name"])
    monthly_debt_cost = d["monthly_cost_total"]
    month = date.today().strftime("%Y-%m")
    expenses = eb._rows(
        "select coalesce(sum(abs(amount)),0) s from transactions "
        "where type='expense' and date like ?", (month + "%",))[0]["s"]
    # fixed_costs setting (essential_mine) beats the transaction-derived guess
    import json as _json
    fc_raw = get_setting("fixed_costs")
    essential_monthly = max(monthly_debt_cost + expenses, monthly_debt_cost)
    if fc_raw:
        try:
            essential_monthly = _json.loads(fc_raw).get("essential_mine") or essential_monthly
        except ValueError:
            pass

    recs = []

    # 0. user-chosen strategy overrides generic debt heuristics
    strategy = get_setting("debt_strategy")
    if strategy:
        recs.append({"area": "strategia (Twoja decyzja)", "priority": 0,
                     "text": strategy})

    # 1. emergency fund
    target = essential_monthly * 6
    if essential_monthly > 0 and cushion < target:
        gap = target - cushion
        recs.append({
            "area": "poduszka", "priority": 1,
            "text": (f"Zbuduj poduszkę bezpieczeństwa: masz {_zl(cushion)} "
                     f"(gotówka + brokerage + PPK), "
                     f"cel to ~{_zl(target)} (6 mies. kosztów stałych ~{_zl(essential_monthly)}/mies.); "
                     f"brakuje {_zl(gap)} — to priorytet przed nadpłatami i inwestycjami.")})

    # 2. debt avalanche vs investing
    for debt in sorted(d["debts"], key=lambda x: -(x["effective_rate"] or 0)):
        rate = debt["effective_rate"] or 0
        if debt["balance"] <= 0:
            continue
        if rate > EXPECTED_MARKET_RETURN:
            recs.append({
                "area": "długi", "priority": 6 if strategy else 2,
                "text": (f"Nadpłacaj {debt['name']}: efektywne {rate:.2f}% przewyższa "
                         f"oczekiwany zwrot z rynku (~{EXPECTED_MARKET_RETURN}%) — nadpłata to "
                         f"gwarantowany, nieopodatkowany zwrot {rate:.1f}%. "
                         f"Odsetki do końca przy obecnej racie: {_zl(debt['schedule']['total_interest'] or 0)}.")})
        else:
            recs.append({
                "area": "długi", "priority": 4,
                "text": (f"{debt['name']} ({rate:.2f}% efektywnie) nie nadpłacaj agresywnie — "
                         f"tani dług; kapitał lepiej pracuje gdzie indziej.")})
        break  # avalanche: only the top-rate debt gets the action

    # 2b. refinancing: fixed rate far above current market
    rates = _market_rates()
    if rates.get("wibor3m"):
        for debt in d["debts"]:
            margin = debt.get("margin_after_fixed") or rates.get("typical_margin", 2.0)
            market_rate = rates["wibor3m"] + margin
            gap = (debt["effective_rate"] or 0) - market_rate
            if gap > 1.0 and debt["balance"] > 100000:
                yearly = debt["balance"] * gap / 100
                extra = ""
                if debt.get("fixed_until"):
                    extra = (f" Stała stopa kończy się {debt['fixed_until']} — rata "
                             f"spadnie wtedy sama, ale do tego czasu nadpłacasz rynek o "
                             f"~{_zl(yearly)}/rok. Sprawdź: aneks/negocjacja marży w swoim "
                             f"banku albo refinansowanie (uwaga na rekompensatę za "
                             f"wcześniejszą spłatę przy stałej stopie).")
                recs.append({
                    "area": "refinansowanie", "priority": 2,
                    "text": (f"{debt['name']}: płacisz {debt['effective_rate']:.2f}% przy "
                             f"rynku ~{market_rate:.2f}% (WIBOR {rates['wibor3m']}% + marża "
                             f"{margin}%) — luka {gap:.1f} p.p. ≈ {_zl(yearly)}/rok "
                             f"nadpłacanych odsetek.{extra}")})
                recs.append({
                    "area": "negocjacje z bankiem", "priority": 2,
                    "text": (f"Playbook na {debt['name']}: (1) złóż wnioski o refinansowanie "
                             f"w 2–3 bankach (darmowe, ~tydzień) — realna oferta bije blef; "
                             f"(2) w swoim banku poproś o zaświadczenie o saldzie i historii "
                             f"kredytu 'do refinansowania' — ten wniosek trafia do systemu "
                             f"jako sygnał odejścia i często sam uruchamia dział utrzymania "
                             f"klienta; (3) zadzwoń/napisz do banku: 'mam ofertę X%, "
                             f"rozważam przeniesienie — co możecie zaproponować?'; "
                             f"(4) licz się z kontrofertą aneksu w 2–4 tyg.; jeśli brak — "
                             f"refinansuj naprawdę, po sprawdzeniu rekompensaty za "
                             f"wcześniejszą spłatę w umowie (stała stopa!).")})

    # 3. concentration / diversification
    if assets > 0 and real_estate / assets > 0.7:
        pct = real_estate / assets * 100
        recs.append({
            "area": "dywersyfikacja", "priority": 3,
            "text": (f"Nieruchomości to {pct:.0f}% majątku — wysoka koncentracja w jednej "
                     f"klasie aktywów i jednym kraju. Nowe oszczędności kieruj do płynnych "
                     f"instrumentów: najpierw limity tax-advantaged accounts (korzyść podatkowa od ręki), "
                     f"potem szeroki ETF.")})

    # 4. goals
    if not goals:
        recs.append({
            "area": "cele", "priority": 5,
            "text": "Nie masz aktywnego celu — dodaj go w zakładce Cele (np. mieszkanie "
                    "we Włoszech), a oferty pracy i tempo oszczędzania zaczną się do niego liczyć."})
    if cfg.get("monthly_savings") in (None, 0):
        recs.append({
            "area": "cele", "priority": 5,
            "text": "Ustaw realne miesięczne tempo oszczędzania w zakładce Cele — bez tego "
                    "projekcje celów i porównania ofert pracy nie działają."})

    recs.sort(key=lambda r: r["priority"])
    return {
        "headline": recs[0]["text"] if recs else "Dane wyglądają zdrowo — brak pilnych działań.",
        "items": recs,
        "facts": {
            "cushion": cushion, "cushion_target": target,
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
    import json as _json
    raw = get_setting("xtb_portfolio")
    if not raw:
        return None
    try:
        pf = _json.loads(raw)
    except ValueError:
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
            where = " i ".join(h["container"] for h in hits)
            recs.append({
                "area": "duplikaty", "priority": 1,
                "text": (f"{name} masz w {where} jednocześnie (łącznie {_zl(v)}) — "
                         f"to ten sam instrument w dwóch miejscach: podwójne opłaty za "
                         f"nakładkę bez żadnej dywersyfikacji. Skonsoliduj do jednego worka.")})

    # 2. theme concentration
    by_theme = {}
    for p in pos:
        by_theme[p["theme"]] = by_theme.get(p["theme"], 0) + p["value"]
    for theme, v in sorted(by_theme.items(), key=lambda kv: -kv[1]):
        share = v / total * 100
        if share > THEME_CAP:
            recs.append({
                "area": "koncentracja", "priority": 2,
                "text": (f"Motyw '{theme}' to {share:.0f}% portfela brokerage ({_zl(v)}) — "
                         f"NASDAQ 100, MSCI IT, Semiconductor, Nvidia, Alphabet i Amazon "
                         f"to w dużej mierze te same spółki kupione kilka razy. Realna "
                         f"dywersyfikacja jest dużo mniejsza, niż sugeruje liczba pozycji.")})
            break

    # 3. single-stock cap
    for p in pos:
        if p["container"] == "Akcje" and p["theme"] != "world":
            share = p["value"] / total * 100
            if share > SINGLE_POSITION_CAP:
                recs.append({
                    "area": "pojedyncze spółki", "priority": 3,
                    "text": (f"{p['name']} = {share:.0f}% portfela brokerage — powyżej "
                             f"rozsądnego limitu {SINGLE_POSITION_CAP:.0f}% na pojedynczą "
                             f"spółkę. Rozważ przycięcie przy okazji rebalansu "
                             f"(pamiętaj o 19% Belki od zysku).")})

    # 4. contribution steering: broad-world sleeve underweight
    world = by_theme.get("world", 0)
    world_share = world / total * 100
    if world_share < 20:
        recs.append({
            "area": "wpłaty", "priority": 4,
            "text": (f"Szeroki rynek to tylko {world_share:.0f}% portfela. Plan naprawy "
                     f"(bez podatku): zamroź wpłaty do Planów 1 i 2 (nie sprzedawaj — "
                     f"przenoszenie = Belka), załóż Plan 3 z VWCE (Vanguard FTSE "
                     f"All-World, 100%) i kieruj tam całe 2 000 zł/mies. Za rok world "
                     f"~25%, za dwa ~40%, tech spada z {by_theme.get('tech', 0) / total * 100:.0f}% "
                     f"do ~50%. Pełna instrukcja w backlogu (zakładka Rekomendacje).")})

    recs.sort(key=lambda r: r["priority"])
    return {
        "headline": recs[0]["text"] if recs else "Portfel brokerage wygląda zdrowo.",
        "items": recs,
        "facts": {
            "total": round(total, 2),
            "themes": {k: round(v / total * 100, 1) for k, v in by_theme.items()},
            "duplicates": [n for n, h in by_name.items() if len(h) > 1],
        },
    }


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
        if saved >= target:
            return {"months": m, "payoff_month": payoff_month,
                    "interest_paid_on_target_debt": round(interest_paid, 2)}
    return {"months": None, "payoff_month": payoff_month,
            "interest_paid_on_target_debt": round(interest_paid, 2)}


def _annual_extras():
    """Bonus + RSU vests: real disposable cash on top of monthly savings."""
    extras = {"bonus_net": _num(get_setting("annual_bonus_net")) or 0,
              "rsu_annual": 0}
    try:
        import market
        r = market.get_rsu()
        if r.get("shares_next_vest") and r.get("last_close") and r.get("usdpln"):
            n_vests = len(r.get("vest_months") or [2, 5, 8, 11])
            extras["rsu_annual"] = round(
                r["shares_next_vest"] * r["last_close"] * r["usdpln"] * n_vests, 0)
    except Exception:
        pass
    pct = _num(get_setting("extras_to_goal_pct"))
    extras["pct_to_goal"] = pct if pct is not None else 100
    extras["monthly_equivalent"] = round(
        (extras["bonus_net"] + extras["rsu_annual"]) / 12 * extras["pct_to_goal"] / 100, 2)
    return extras


def goal_scenarios():
    goals = [g for g in list_goals() if g["status"] == "active"]
    if not goals:
        return None
    goal = sorted(goals, key=lambda g: g["created_at"])[0]  # primary = oldest active
    target = (goal["target_amount"] or 0) - (goal["current_amount"] or 0)
    cfg = settings()
    base_savings = goal["monthly_contribution"] or cfg.get("monthly_savings") or 0
    extras = _annual_extras()
    savings = base_savings + extras["monthly_equivalent"]
    if target <= 0 or savings <= 0:
        return None
    d = list_debts()["debts"]
    scenarios = [{"key": "baseline", "label": "Bez nadpłat — wszystko na cel",
                  **_simulate_path(target, savings, d)}]
    for debt in d:
        base_interest = debt["schedule"]["total_interest"]
        sim = _simulate_path(target, savings, d, overpay_debt_id=debt["id"])
        saved_interest = (round(base_interest - sim["interest_paid_on_target_debt"], 2)
                         if base_interest is not None else None)
        scenarios.append({
            "key": debt["id"], "label": f"Najpierw nadpłać: {debt['name']}",
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
    _audit("snapshot", None, "add", {"net_worth": net})


# ---------- firma (działalności business ledger) ----------

BIZ_KINDS = ("koszt", "przychód")
BIZ_CATEGORIES = ("sprzęt", "marketing", "software", "ubezpieczenie",
                  "uprawnienia", "dojazd", "księgowość", "inne",
                  "usługa", "content", "licencje")


def ensure_biz_table():
    eb._exec("""create table if not exists biz_entries (
        id text primary key, date text not null, kind text not null,
        category text default 'inne', amount real not null,
        description text default '', created_at text not null)""")


def biz_summary():
    ensure_biz_table()
    rows = eb._rows("select * from biz_entries order by date desc, rowid desc")
    monthly = {}
    for r in rows:
        m = r["date"][:7]
        monthly.setdefault(m, {"month": m, "koszty": 0, "przychody": 0,
                               "marketing": 0})
        if r["kind"] == "koszt":
            monthly[m]["koszty"] += r["amount"]
            if r["category"] == "marketing":
                monthly[m]["marketing"] += r["amount"]
        else:
            monthly[m]["przychody"] += r["amount"]
    months = sorted(monthly.values(), key=lambda x: x["month"])
    cum = 0
    for m in months:
        m["wynik"] = round(m["przychody"] - m["koszty"], 2)
        cum += m["wynik"]
        m["narastajaco"] = round(cum, 2)
        m["roas"] = round(m["przychody"] / m["marketing"], 2) if m["marketing"] else None
        for k in ("koszty", "przychody", "marketing"):
            m[k] = round(m[k], 2)
    total_cost = sum(m["koszty"] for m in months)
    total_rev = sum(m["przychody"] for m in months)
    cur = date.today().strftime("%Y-%m")
    return {
        "entries": rows[:200],
        "months": months,
        "current": monthly.get(cur, {"koszty": 0, "przychody": 0, "wynik": 0}),
        "total_cost": round(total_cost, 2),
        "total_revenue": round(total_rev, 2),
        "total_result": round(total_rev - total_cost, 2),
        "categories": BIZ_CATEGORIES,
    }


def add_biz_entry(data):
    ensure_biz_table()
    assert data.get("kind") in BIZ_KINDS, "invalid kind"
    entry_id = str(uuid.uuid4())
    eb._exec(
        "insert into biz_entries (id, date, kind, category, amount, description, created_at) "
        "values (?,?,?,?,?,?,?)",
        (entry_id, data.get("date") or date.today().isoformat(), data["kind"],
         data.get("category", "inne"), float(data["amount"]),
         data.get("description", ""), _now()))
    _audit("biz", entry_id, "add", data)
    return entry_id


def delete_biz_entry(entry_id):
    _audit("biz", entry_id, "delete")
    eb._exec("delete from biz_entries where id = ?", (entry_id,))


# ---------- action plan (rekomendacje -> backlog -> efekty) ----------

ACTION_STATUSES = ("backlog", "w trakcie", "zrobione", "odrzucone")


def ensure_actions_table():
    eb._exec("""create table if not exists actions (
        id text primary key, title text not null, area text default '',
        detail text default '', status text default 'backlog',
        expected_impact text default '', actual_impact_pln real,
        actual_note text default '', created_at text not null,
        done_at text)""")


def list_actions():
    ensure_actions_table()
    rows = eb._rows("select * from actions order by "
                    "case status when 'w trakcie' then 0 when 'backlog' then 1 "
                    "when 'zrobione' then 2 else 3 end, created_at")
    done = [r for r in rows if r["status"] == "zrobione"]
    return {
        "actions": rows,
        "done_count": len(done),
        "total_actual_impact": round(sum(r["actual_impact_pln"] or 0 for r in done), 2),
    }


def add_action(data):
    ensure_actions_table()
    action_id = str(uuid.uuid4())
    eb._exec(
        "insert into actions (id, title, area, detail, status, expected_impact, created_at) "
        "values (?,?,?,?,?,?,?)",
        (action_id, data["title"], data.get("area", ""), data.get("detail", ""),
         data.get("status", "backlog"), data.get("expected_impact", ""), _now()))
    _audit("action", action_id, "add", {"title": data["title"]})
    return action_id


def update_action(action_id, data):
    cols, params = [], []
    for k in ("title", "area", "detail", "status", "expected_impact",
              "actual_impact_pln", "actual_note"):
        if k in data:
            cols.append(k); params.append(data[k])
    if data.get("status") == "zrobione":
        cols.append("done_at"); params.append(_now())
    if cols:
        params.append(action_id)
        eb._exec(eb.update_sql("actions", cols), tuple(params))
        _audit("action", action_id, "update", data)


def delete_action(action_id):
    _audit("action", action_id, "delete")
    eb._exec("delete from actions where id = ?", (action_id,))


# ---------- firma: performance marketing (Supabase — marketing agents) ----------

def _parse_pyjson(raw):
    """analysis_reports store python-dict strings; try json then literal_eval."""
    import json as _json
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return _json.loads(raw)
    except (ValueError, TypeError):
        pass
    try:
        import ast
        return ast.literal_eval(raw)
    except (ValueError, SyntaxError, TypeError):
        return None


def firma_marketing():
    """Weekly ads intelligence from the marketing agents (ads-collector/-analyst)."""
    import market
    try:
        reports = market._supabase_get(
            "analysis_reports?select=week_start,week_end,total_spend,report_json,"
            "recommendations,created_at&order=week_start.desc&limit=8")
        insights = market._supabase_get(
            "insights?select=category,platform,insight,confidence,is_active"
            "&is_active=eq.true&order=confidence.desc&limit=6")
        hypotheses = market._supabase_get(
            "hypotheses?select=title,predicted_outcome,success_metric,target_value,status"
            "&status=eq.active&limit=5")
        spend_rows = market._supabase_get(
            "ad_snapshots?select=date,spend,clicks,impressions&order=date.desc&limit=60")
    except Exception as e:
        return {"error": f"offline / brak połączenia z Supabase: {e}"}

    weeks = []
    for r in reports:
        rj = _parse_pyjson(r.get("report_json")) or {}
        rec = _parse_pyjson(r.get("recommendations")) or {}
        meta_rec = rec.get("meta") if isinstance(rec, dict) else None
        weeks.append({
            "week": f'{r["week_start"]} – {r["week_end"]}',
            "spend_eur": r.get("total_spend"),
            "summary": rj.get("summary"),
            "recommendation": (meta_rec or {}).get("reason") if isinstance(meta_rec, dict) else None,
        })
    total_spend = sum(float(r.get("total_spend") or 0) for r in reports)
    last30_spend = sum(float(s["spend"] or 0) for s in spend_rows)
    last30_clicks = sum(int(s["clicks"] or 0) for s in spend_rows)
    return {
        "weeks": weeks,
        "insights": insights,
        "hypotheses": hypotheses,
        "total_spend_eur": round(total_spend, 2),
        "recent_spend_eur": round(last30_spend, 2),
        "recent_clicks": last30_clicks,
    }


# ---------- cash-flow / liquidity timeline ----------

CF_DEFAULTS = {  # generyczne wartości startowe — realne trzymane w bazie (gitignored)
    "cf_monthly_surplus": 5000,    # nadwyżka bazowa/mies.
    "cf_safety_buffer": 30000,     # bufor bezpieczeństwa (dół salda płynnego)
    "cf_liquid_start": 0,          # startowe środki płynne
    "cf_bonus_month": 9,           # miesiąc bonusu
    "cf_sweep_target": "loan",     # dokąd trafia nadwyżka: loan | property | none
}


def cashflow(months=15):
    """Forward liquidity: base surplus + lumpy vests/bonus, sweeping excess
    above the safety buffer into primary-debt overpay until paid, then accumulating."""
    import market as _mkt
    from datetime import date

    def _cf(key):
        v = _num(get_setting(key))
        return v if v is not None else CF_DEFAULTS[key]

    surplus = _cf("cf_monthly_surplus")
    buffer = _cf("cf_safety_buffer")
    liquid = _cf("cf_liquid_start")
    bonus_month = int(_cf("cf_bonus_month"))
    bonus = _num(get_setting("annual_bonus_net")) or 20000

    debts = list_debts()["debts"]
    loan = next((d for d in debts if "loan" in d["name"].lower()
                 ), None)
    loan_bal = loan["balance"] if loan else 0
    loan_principal = (loan.get("principal_month") if loan else 0) or 0
    loan_freed = loan.get("monthly_cost_total", 0) if loan else 0

    rsu = {}
    try:
        rsu = _mkt.get_rsu()
    except Exception:
        pass
    vest_pln = rsu.get("next_vest_value_pln") or 0
    vest_months = set(rsu.get("vest_months") or [2, 5, 8, 11])
    shares_next = rsu.get("shares_next_vest") or 0

    today = date.today()
    y, m = today.year, today.month
    rows = []
    loan_paid_month = None
    base_surplus = surplus
    for i in range(months):
        mm = ((m - 1 + i) % 12) + 1
        yy = y + (m - 1 + i) // 12
        label = f"{yy:04d}-{mm:02d}"
        inflow = base_surplus
        parts = [f"nadwyżka {_zl(base_surplus)}"]
        if mm in vest_months and vest_pln:
            inflow += vest_pln
            parts.append(f"vest {shares_next} akcji {_zl(vest_pln)}")
        if mm == bonus_month and bonus:
            inflow += bonus
            parts.append(f"bonus {_zl(bonus)}")
        liquid += inflow
        # sweep excess above buffer into the debt until paid
        overpay = 0
        if loan_bal > 0:
            overpay = max(0, min(liquid - buffer, loan_bal))
            liquid -= overpay
            loan_bal = max(0, loan_bal - loan_principal - overpay)
            if loan_bal <= 0 and loan_paid_month is None:
                loan_paid_month = label
                base_surplus = surplus + loan_freed  # freed rata boosts surplus
        rows.append({
            "month": label,
            "inflow": round(inflow, 0),
            "inflow_parts": " · ".join(parts),
            "overpay_loan": round(overpay, 0),
            "liquid": round(liquid, 0),
            "loan_balance": round(loan_bal, 0),
            "below_buffer": liquid < buffer - 1,
            "is_vest": mm in vest_months and bool(vest_pln),
            "is_bonus": mm == bonus_month and bool(bonus),
        })
    return {
        "rows": rows,
        "buffer": buffer,
        "loan_start": loan["balance"] if loan else 0,
        "loan_paid_month": loan_paid_month,
        "loan_freed_monthly": loan_freed,
        "assumptions": {
            "cf_monthly_surplus": surplus,
            "cf_safety_buffer": buffer,
            "cf_liquid_start": _cf("cf_liquid_start"),
            "annual_bonus_net": bonus,
            "vest_value_pln": vest_pln,
            "vest_months": sorted(vest_months),
        },
    }


# ---------- taxes ----------

TAX_DEFAULTS = {  # generyczne wartości startowe — realne trzymane w bazie (gitignored)
    "tax_rental_monthly": 2000,
    "tax_rental_rate": 8.5,
    "tax_zus_monthly": 431.54,   # oficjalny mały ZUS (kwota publiczna)
    "tax_salary_gross_annual": 150000,
}


def tax_summary():
    from datetime import date
    def _t(k):
        v = _num(get_setting(k))
        return v if v is not None else TAX_DEFAULTS[k]
    rental_m = _t("tax_rental_monthly"); rate = _t("tax_rental_rate")
    zus = _t("tax_zus_monthly"); salary = _t("tax_salary_gross_annual")
    try:
        biz = biz_summary(); fpv_result = biz.get("total_result", 0)
    except Exception:
        fpv_result = 0
    fpv_profit = max(0, fpv_result)
    rental_annual = rental_m * 12
    rental_tax = round(rental_annual * rate / 100, 0)
    zus_annual = round(zus * 12, 0)
    fpv_pit = round(fpv_profit * 0.12, 0)

    items = [
        {"source": "Najem (ryczałt)", "rate": f"{rate}%",
         "base": rental_annual, "tax": rental_tax, "cadence": "miesięcznie do 20.",
         "managed": "Ty", "note": "ryczałt od przychodu — bez odliczeń"},
        {"source": "działalności — ZUS/zdrowotna", "rate": "—", "base": None, "tax": zus_annual,
         "cadence": "miesięcznie do 20.", "managed": "Ty (JDG)",
         "note": "Masz UoP ≥ min. krajowa → zbieg tytułów: JDG zwykle ZWOLNIONA ze społecznego ZUS, płacisz tylko zdrowotną. To NIE jest preferencja czasowa dopóki trwa etat (potwierdź u księgowego, co pokrywa 431,54)"},
        {"source": "działalności — PIT od zysku", "rate": "12–32% / 19%", "base": fpv_profit,
         "tax": fpv_pit, "cadence": "zaliczka mies./kwart.", "managed": "Ty (JDG)",
         "note": "obecnie strata → 0; strata rozlicza przyszłe zyski"},
        {"source": "RSU / Belka", "rate": "19%", "base": 0, "tax": 0,
         "cadence": "przy sprzedaży", "managed": "auto",
         "note": "≈0 przy sprzedaży od razu po veście (zysk po veście minimalny)"},
        {"source": "Pensja — PIT", "rate": "do 32%", "base": salary, "tax": None,
         "cadence": "potrąca pracodawca", "managed": "pracodawca",
         "note": "informacyjnie — nie zarządzasz sam (PIT-11)"},
    ]
    self_managed = rental_tax + zus_annual + fpv_pit

    today = date.today()
    def nth(month_offset, day):
        m = today.month + month_offset; y = today.year
        while m > 12: m -= 12; y += 1
        return f"{y:04d}-{m:02d}-{day:02d}"
    calendar = [
        {"date": nth(0 if today.day < 20 else 1, 20), "what": "Ryczałt najem + ZUS działalności",
         "amount": round(rental_tax / 12 + zus, 0)},
        {"date": f"{today.year + (1 if today.month > 4 else 0):04d}-04-30",
         "what": "Roczne: PIT-28 (najem) + PIT-36L/JDG", "amount": None},
    ]
    optimizations = [
        "RSU: sprzedawaj od razu po veście — Belka liczy się tylko od zysku po dacie vestu (≈0). Trzymanie = ryzyko + brak korzyści podatkowej.",
        "Cash vs equity: cash to PIT do 32%, sprzedane akcje to Belka 19% — ~13 pp różnicy. Wybieraj świadomie (cash podnosi zdolność kredytową).",
        "Najem: ryczałt 8,5% jest zwykle korzystny przy niskich kosztach; gdyby doszły duże remonty/odsetki, przelicz skalę.",
        "JDG: strata z lat startowych obniża przyszły PIT, gdy firma wyjdzie na plus — warto ją „zachować\" w rozliczeniu.",
        "ZUS przy zbiegu tytułów: jeśli masz etat (UoP) ≥ min. krajowa, z JDG płacisz zwykle TYLKO składkę zdrowotną — społeczny ZUS jest zwolniony. Uwaga: po utracie etatu społeczny ZUS z JDG się włącza (a okno preferencyjne może już minąć).",
    ]
    return {"items": items, "self_managed_annual": round(self_managed, 0),
            "calendar": calendar, "optimizations": optimizations,
            "assumptions": {"tax_rental_monthly": rental_m, "tax_rental_rate": rate,
                            "tax_zus_monthly": zus}}


# ---------- asset allocation ----------

ALLOC_TARGETS = {  # docelowe % netto (edytowalne)
    "nieruchomosci": 55, "etf": 22, "team": 4,
    "gotowka": 8, "emerytalne": 5, "auto": 6,
}
ALLOC_LABELS = {
    "nieruchomosci": "🏠 Nieruchomości (equity)", "etf": "🌍 Akcje/ETF (brokerage)",
    "team": "💎 Akcje RSU", "gotowka": "💵 Gotówka", "emerytalne": "🏦 Emerytalne (pension accounts)",
    "auto": "🚗 Auto (konsumpcyjne)",
}


def _alloc_class(name):
    n = name.lower()
    if "mieszkan" in n or "dom" in n or "nieruchom" in n:
        return "nieruchomosci"
    if "xtb" in n or "etf" in n:
        return "etf"
    if "rsu" in n or "team" in n:
        return "team"
    if "ikze" in n or "ike" in n or "ppk" in n or "emerytal" in n:
        return "emerytalne"
    if "gotówk" in n or "gotowk" in n or "cash" in n or "konto" in n:
        return "gotowka"
    if "kia" in n or " ev" in n or "auto" in n or "samoch" in n:
        return "auto"
    return None


def allocation():
    w = wealth_summary()
    classes = {k: 0.0 for k in ALLOC_TARGETS}
    for it in w.get("items", []):
        if it.get("kind") in ("income",):
            continue
        cls = _alloc_class(it.get("name", ""))
        if not cls:
            continue
        # use equity for debt-linked (real estate), else latest value
        val = it.get("equity") if it.get("equity") is not None else (it.get("latest_value") or 0)
        classes[cls] += val or 0
    total = sum(classes.values()) or 1
    rows = []
    for k in ALLOC_TARGETS:
        pct = round(100 * classes[k] / total, 1)
        target = ALLOC_TARGETS[k]
        drift = round(pct - target, 1)
        rows.append({
            "key": k, "label": ALLOC_LABELS[k], "value": round(classes[k], 0),
            "pct": pct, "target": target, "drift": drift,
            "flag": "za dużo" if drift > 8 else ("dokładaj" if drift < -8 else "ok"),
        })
    rows.sort(key=lambda r: -r["value"])
    hints = []
    re_row = next(r for r in rows if r["key"] == "nieruchomosci")
    if re_row["pct"] > 65:
        hints.append(f"Nieruchomości {re_row['pct']}% majątku — silna koncentracja. Nadwyżki po spłacie kredytu kieruj w płynne aktywa (VWCE), nie w kolejny beton.")
    etf_row = next(r for r in rows if r["key"] == "etf")
    if etf_row["pct"] < 15:
        hints.append(f"Akcje/ETF tylko {etf_row['pct']}% — to główny kierunek dokładania (Plan Core VWCE) do dywersyfikacji z nieruchomości i pracodawcy.")
    team_row = next(r for r in rows if r["key"] == "team")
    if team_row["pct"] > 4:
        hints.append(f"Akcje RSU {team_row['pct']}% — plus przyszłe vesty. Sprzedawaj przy veście, nie kumuluj (ryzyko: pensja+bonus+akcje w jednej firmie).")
    return {"rows": rows, "total": round(total, 0), "hints": hints}


# ---------- reminders ----------

def _auto_reminders():
    """Derive upcoming events from live data (not stored)."""
    from datetime import date
    import market as _mkt
    today = date.today()
    out = []

    def days_to(ds):
        try:
            y, m, d = map(int, ds.split("-"))
            return (date(y, m, d) - today).days
        except Exception:
            return None

    # next vest + bonus
    try:
        rsu = _mkt.get_rsu()
        vm = sorted(rsu.get("vest_months") or [2, 5, 8, 11])
        nvm = next((x for x in vm if x > today.month), None)
        vy = today.year if nvm else today.year + 1
        nvm = nvm or vm[0]
        vdate = f"{vy:04d}-{nvm:02d}-15"
        val = rsu.get("next_vest_value_pln")
        out.append({"title": f"Vest RSU ({rsu.get('shares_next_vest')} akcji"
                    + (f", ≈{_zl(val)}" if val else "") + ") — sprzedaj → nadpłata kredytu",
                    "due_date": vdate, "auto": True, "kind": "RSU"})
    except Exception:
        pass
    # bonus (configured month)
    by = today.year if today.month <= 9 else today.year + 1
    out.append({"title": "Bonus roczny (configured amountto) — nadpłata kredytu",
                "due_date": f"{by:04d}-09-30", "auto": True, "kind": "Dochód"})
    # kredyt hipoteczny fixed-rate end → aneks
    try:
        for d in list_debts()["debts"]:
            fu = d.get("fixed_until")
            if fu and days_to(fu) is not None:
                out.append({"title": f"{d['name']}: koniec stałej stopy — czas na aneks/refinansowanie",
                            "due_date": fu, "auto": True, "kind": "Kredyt"})
    except Exception:
        pass
    # RSU stock near/above target
    try:
        _tk = (_mkt.get_rsu() or {}).get("ticker") or "AAPL"
        an = _mkt.analytics(_tk)
        tgt = an.get("analyst_target"); last = an.get("last_close")
        if tgt and last and last >= tgt * 0.95:
            out.append({"title": f"{_tk} ${last} blisko/ponad target ${tgt} — rozważ sprzedaż posiadanych",
                        "due_date": today.isoformat(), "auto": True, "kind": "Rynek"})
    except Exception:
        pass
    # weekly (Claude): security scan + README
    from datetime import timedelta as _td
    nextweek = (today + _td(days=7 - today.weekday() if today.weekday() < 7 else 7)).isoformat()
    out.append({"title": "🔒 Claude: security scan repo (sekrety, wrażliwe pliki)",
                "due_date": nextweek, "auto": True, "kind": "Security"})
    out.append({"title": "📝 Claude: przegląd i aktualizacja README ",
                "due_date": nextweek, "auto": True, "kind": "Docs"})
    # next month's 1st, reused for monthly tasks
    by, bm = (today.year, today.month + 1) if today.month < 12 else (today.year + 1, 1)
    # monthly market barometer update (Claude task)
    out.append({"title": "📈 Claude: zaktualizuj barometr rynku (oferty EM/Head, Europa remote)",
                "due_date": f"{by:04d}-{bm:02d}-05", "auto": True, "kind": "Barometr"})
    # monthly market brief refresh (Claude task) — zakładka Rynek
    out.append({"title": "🧭 Claude: odśwież brief rynkowy (ruchy, kontekst makro, rekomendacje per pozycja)",
                "due_date": f"{by:04d}-{bm:02d}-05", "auto": True, "kind": "Rynek"})
    # monthly data backup
    out.append({"title": "💾 Backup danych — uruchom apps/budget/backup.sh (baza szyfrowana → Google Drive)",
                "due_date": f"{by:04d}-{bm:02d}-01", "auto": True, "kind": "Backup"})
    # quarterly review
    q_month = ((today.month - 1) // 3 + 1) * 3 + 1
    qy = today.year + (1 if q_month > 12 else 0)
    q_month = q_month if q_month <= 12 else q_month - 12
    out.append({"title": "Przegląd kwartalny portfela (alokacja, koncentracja, rebalancing)",
                "due_date": f"{qy:04d}-{q_month:02d}-01", "auto": True, "kind": "Przegląd"})

    for r in out:
        r["days"] = days_to(r["due_date"])
    return out


def list_reminders():
    manual = eb._rows("select * from reminders where done=0 order by "
                      "coalesce(due_date,'9999') asc, created_at asc")
    from datetime import date
    today = date.today()
    for r in manual:
        r["auto"] = False
        try:
            y, m, d = map(int, (r["due_date"] or "9999-12-31").split("-"))
            r["days"] = (date(y, m, d) - today).days
        except Exception:
            r["days"] = None
    combined = _auto_reminders() + manual
    combined.sort(key=lambda r: (r.get("days") if r.get("days") is not None else 99999))
    return {"reminders": combined,
            "done_count": (eb._rows("select count(*) c from reminders where done=1") or [{"c": 0}])[0]["c"]}


def add_reminder(data):
    rid = str(uuid.uuid4())
    eb._exec("insert into reminders (id, title, due_date, note, created_at) values (?,?,?,?,?)",
             (rid, data["title"], data.get("due_date"), data.get("note", ""), _now()))
    _audit("reminder", rid, "add", data)
    return rid


def update_reminder(rid, data):
    if "done" in data:
        eb._exec("update reminders set done=? where id=?", (1 if data["done"] else 0, rid))
    _audit("reminder", rid, "update", data)


def delete_reminder(rid):
    _audit("reminder", rid, "delete")
    eb._exec("delete from reminders where id=?", (rid,))


# ---------- market barometer (demand for tracked roles) ----------

def list_barometer():
    rows = eb._rows("select * from market_barometer order by month asc")
    # korelacja z inbound: ile ofert dostał w danym miesiącu
    offers = eb._rows("select received_at from job_offers")
    inbound = {}
    for o in offers:
        m = (o.get("received_at") or "")[:7]
        if m:
            inbound[m] = inbound.get(m, 0) + 1
    for r in rows:
        r["my_inbound"] = inbound.get(r["month"], 0)
    return {"points": rows}


def add_barometer_point(data):
    bid = str(uuid.uuid4())
    eb._exec(
        "insert into market_barometer (id, month, em_openings, head_openings, "
        "region, note, created_at) values (?,?,?,?,?,?,?)",
        (bid, data["month"], _num(data.get("em_openings")), _num(data.get("head_openings")),
         data.get("region", "Europa (remote)"), data.get("note", ""), _now()))
    _audit("barometer", bid, "add", data)
    return bid


def delete_barometer_point(bid):
    _audit("barometer", bid, "delete")
    eb._exec("delete from market_barometer where id=?", (bid,))


# ---------- control center / health ----------

def _days_since(dstr):
    from datetime import date
    try:
        parts = dstr[:10].split("-")
        d = date(int(parts[0]), int(parts[1]), int(parts[2]))
        return (date.today() - d).days
    except Exception:
        return None


def health():
    import os, subprocess
    from datetime import datetime
    from pathlib import Path
    import market as _mkt

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    repo = _mkt._finance_dir().parent
    tasks = []

    def task(name, freq, last, status, detail):
        tasks.append({"name": name, "freq": freq, "last": last,
                      "status": status, "detail": detail})

    # 1. kursy rynkowe (n8n → Supabase, dziennie 22:35)
    try:
        sync = _mkt.last_sync()
        _htk = (_mkt.get_rsu() or {}).get("ticker") or "AAPL"
        hist = _mkt.prices(_htk, days=5)
        lastd = hist[-1]["date"] if hist else None
        d = _days_since(lastd) if lastd else None
        st = "ok" if (d is not None and d <= 4) else "warn"
        task("Kursy rynkowe (akcje/FX)", "codziennie ~22:35",
             (sync or lastd or "—"), st,
             f"ostatnie notowanie {lastd} ({d} dni temu)" if lastd else "brak danych")
    except Exception as e:
        task("Kursy rynkowe (akcje/FX)", "codziennie ~22:35", "—", "error", str(e)[:80])

    # 2. śledzenie predykcji RSU (dziennie przy otwarciu RSU)
    try:
        r = eb._rows("select max(made_on) m, count(*) c from rsu_predictions")
        lastm = r[0]["m"] if r else None
        d = _days_since(lastm) if lastm else None
        st = "ok" if (d is not None and d <= 2) else ("warn" if lastm else "info")
        task("Śledzenie predykcji RSU", "codziennie", lastm or "—", st,
             f"{r[0]['c']} prognoz; ostatnia {d} dni temu" if lastm else "jeszcze brak")
    except Exception as e:
        task("Śledzenie predykcji RSU", "codziennie", "—", "error", str(e)[:80])

    # 2b. samouczący dziennik prognoz (pasma short-term, cała watchlista)
    try:
        ss = _mkt.forecast_selfscore()
        h21 = next((h for h in ss["horizons"] if h["days"] == 21), None)
        st = "ok" if (h21 and h21["coverage_pct"] and 70 <= h21["coverage_pct"] <= 92) else ("info" if ss["total_scored"] < 100 else "warn")
        task("Samouczenie prognoz (pasma)", "codziennie po syncu",
             f"{ss['total_scored']} rozliczonych", st,
             f"pokrycie 1M: {h21['coverage_pct']}% (cel ~80%)" if h21 else "dziennik się buduje")
    except Exception as e:
        task("Samouczenie prognoz (pasma)", "codziennie po syncu", "—", "warn", str(e)[:60])

    # 3. marketing (ads-analyst, tygodniowo pon ~07:00)
    try:
        rep = _mkt._supabase_get("analysis_reports?select=week_end&order=week_end.desc&limit=1")
        we = rep[0]["week_end"] if rep else None
        d = _days_since(we) if we else None
        st = "ok" if (d is not None and d <= 9) else ("warn" if we else "info")
        task("Marketing działalności (raporty ads)", "tygodniowo pon ~07:00", we or "—", st,
             f"ostatni raport tydzień do {we} ({d} dni temu)" if we else "brak/offline")
    except Exception as e:
        task("Marketing działalności (raporty ads)", "tygodniowo pon ~07:00", "—", "warn",
             "offline/brak Supabase")

    # 4. barometr rynku (Claude, miesięcznie)
    try:
        r = eb._rows("select max(month) m, count(*) c from market_barometer")
        lastm = (r[0]["m"] + "-15") if r and r[0]["m"] else None
        d = _days_since(lastm) if lastm else None
        st = "ok" if (d is not None and d <= 40) else ("warn" if lastm else "info")
        task("Barometr rynku (oferty EM/Head)", "miesięcznie (Claude)",
             (r[0]["m"] if r and r[0]["m"] else "—"), st,
             f"{r[0]['c']} punktów; ostatni {r[0]['m']}" if r and r[0]["m"] else "brak — do uzupełnienia")
    except Exception as e:
        task("Barometr rynku (oferty EM/Head)", "miesięcznie (Claude)", "—", "error", str(e)[:80])

    # 5. backup danych (miesięcznie)
    try:
        bdir = repo / "backups"
        enc = sorted(bdir.glob("finance-*.db.enc"), key=lambda p: p.stat().st_mtime) if bdir.exists() else []
        if enc:
            mt = datetime.fromtimestamp(enc[-1].stat().st_mtime)
            d = (datetime.now() - mt).days
            st = "ok" if d <= 35 else "warn"
            task("Backup danych (szyfrowany)", "miesięcznie", mt.strftime("%Y-%m-%d %H:%M"), st,
                 f"{len(enc)} kopii; ostatnia {d} dni temu")
        else:
            task("Backup danych (szyfrowany)", "miesięcznie", "—", "error", "brak kopii — uruchom backup.sh")
    except Exception as e:
        task("Backup danych (szyfrowany)", "miesięcznie", "—", "error", str(e)[:80])

    # 6. audyt danych wrażliwych w gicie
    try:
        out = subprocess.run(["git", "-C", str(repo), "ls-files"],
                             capture_output=True, text=True, timeout=10)
        tracked = out.stdout.splitlines()
        bad = [f for f in tracked if any(s in f.lower() for s in
               ("private/", ".finance/", "doc-raw/", "compensation", "finanse/", "psyche/", ".env"))
               and not f.endswith(".env.example")]
        if bad:
            task("Audyt: dane wrażliwe w gicie", "przy każdym pushu / miesięcznie",
                 now, "error", f"🚨 śledzone wrażliwe pliki: {', '.join(bad[:3])}")
        else:
            task("Audyt: dane wrażliwe w gicie", "przy każdym pushu / miesięcznie",
                 now, "ok", f"czysto — {len(tracked)} śledzonych plików, zero wrażliwych")
    except Exception as e:
        task("Audyt: dane wrażliwe w gicie", "przy każdym pushu", "—", "warn", "git niedostępny: " + str(e)[:60])

    # 7. baza danych — integralność
    try:
        chk = eb._rows("pragma integrity_check")
        okc = chk and (chk[0].get("integrity_check") == "ok" or list(chk[0].values())[0] == "ok")
        size = (repo / ".finance" / "finance.db").stat().st_size // 1024 if (repo / ".finance" / "finance.db").exists() else 0
        task("Baza danych (SQLite)", "ciągle", now, "ok" if okc else "error",
             f"integralność OK · {size} KB")
    except Exception as e:
        task("Baza danych (SQLite)", "ciągle", now, "warn", str(e)[:80])

    # 8. synchronizacja z GitHub
    try:
        gs = git_status(do_fetch=True)
        detail = gs["summary"]
        if gs.get("remote", "").startswith("http"):
            detail += f" · ostatni commit: {gs.get('last_commit_date', '')}"
        task("Synchronizacja z GitHub", "po zmianach kodu (Claude)",
             gs.get("last_commit_date") or "—", gs["status"], detail)
    except Exception as e:
        task("Synchronizacja z GitHub", "po zmianach kodu", "—", "warn", str(e)[:80])

    # 9b. security scan repo (co tydzień)
    try:
        sc = security_scan()
        task("Security scan repo (sekrety)", "co tydzień", now, sc["status"], sc["summary"])
    except Exception as e:
        task("Security scan repo (sekrety)", "co tydzień", "—", "warn", str(e)[:70])

    # 9. aktywność commitowa (cel: codziennie)
    try:
        ga = github_activity(days=30)
        if ga["today"] > 0:
            st = "ok"; detail = f"dziś {ga['today']} commitów · seria {ga['streak']} dni 🔥 (rekord {ga['best_streak']})"
        elif ga["streak"] > 0:
            st = "warn"; detail = f"dziś jeszcze 0 · seria {ga['streak']} dni — mały commit ją podtrzyma"
        else:
            st = "warn"; detail = f"dziś 0, seria przerwana · {ga['active_days']}/30 dni aktywnych ostatnio"
        task("Aktywność commitowa (GitHub)", "codziennie (cel)", now, st, detail)
    except Exception as e:
        task("Aktywność commitowa (GitHub)", "codziennie", "—", "warn", str(e)[:60])

    errors = sum(1 for t in tasks if t["status"] == "error")
    warns = sum(1 for t in tasks if t["status"] == "warn")
    return {"tasks": tasks, "checked_at": now,
            "summary": {"ok": sum(1 for t in tasks if t["status"] == "ok"),
                        "warn": warns, "error": errors, "total": len(tasks)}}


# ---------- inwentarz danych: co auto / claude / recznie ----------

def data_inventory():
    """Mapa wszystkich zrodel danych w aplikacji: tryb (auto/derived/claude/
    manual), zrodlo, czestotliwosc, ostatnia aktualizacja, liczba rekordow i
    szacowany reczny wysilek/mies. Cel: zminimalizowac reczne wprowadzanie."""
    from datetime import datetime
    import json as _json

    def one(q):
        try:
            r = eb._rows(q)
            return r[0] if r else {}
        except Exception:
            return {}

    def cnt_last(table, tcol=None):
        sel = "count(*) c" + (f", max({tcol}) m" if tcol else "")
        r = one(f"select {sel} from {table}")
        return r.get("c", 0), (r.get("m") if tcol else None)

    def setting_asof(key, field="as_of"):
        raw = get_setting(key)
        if not raw:
            return None, False
        try:
            return _json.loads(raw).get(field), True
        except Exception:
            return None, True

    acc_c, acc_last = cnt_last("accounts", "updated_at")
    wv_c, wv_last = cnt_last("wealth_values", "created_at")
    wi_c, _ = cnt_last("wealth_items")
    debt_c, debt_last = cnt_last("debts", "updated_at")
    dv_c, dv_last = cnt_last("debt_values", "created_at")
    goal_c, goal_last = cnt_last("goals", "updated_at")
    tx_c, tx_last = cnt_last("transactions", "created_at")
    off_c, off_last = cnt_last("job_offers", "created_at")
    biz_c, biz_last = cnt_last("biz_entries", "created_at")
    px_c, px_last = cnt_last("market_prices_cache", "date")
    bar_c, bar_last = cnt_last("market_barometer", "month")
    pred_c, pred_last = cnt_last("rsu_predictions", "made_on")
    snap_c, snap_last = cnt_last("snapshots", "date")
    fire_c, fire_last = cnt_last("fire_snapshots", "month")
    ins_c, _ = cnt_last("insurance_policies")
    brief_asof, brief_has = setting_asof("analysis_market_brief")
    vest_asof, vest_has = setting_asof("rsu_vest_analysis", "vest_month")
    prop_asof, prop_has = setting_asof("analysis_property_location")
    try:
        import market as _mkt
        sync = _mkt.last_sync()
    except Exception:
        sync = None

    def item(name, mode, source, freq, last, count=None, minutes=0, note="", suggest=""):
        return {"name": name, "mode": mode, "source": source, "freq": freq,
                "last": last or "\u2014", "count": count, "minutes": minutes,
                "note": note, "suggest": suggest}

    groups = [
        {"key": "auto", "title": "\U0001F7E2 W pelni automatyczne \u2014 zero pracy",
         "note": "Pobierane przez n8n/Supabase/gita albo liczone przez aplikacje. Nic nie wpisujesz.",
         "items": [
            item("Kursy akcji + FX", "auto", "n8n \u2192 Supabase \u2192 cache",
                 "codziennie", sync or px_last, px_c,
                 note=f"{px_c} notowan w cache; ostatnie {px_last}"),
            item("Raporty marketingu/ads", "auto", "n8n \u2192 Supabase (analysis_reports)",
                 "tygodniowo", None, note="czytane z Supabase; offline gdy brak polaczenia"),
            item("Aktywnosc commitow (GitHub)", "auto", "lokalne repo (git log)",
                 "na zadanie / dziennie", None, note="liczone z gita, nic nie wpisujesz"),
            item("Audyt danych wrazliwych", "auto", "git ls-files + skan sekretow",
                 "przy pushu / tygodniowo", None, note="pilnuje, ze .finance/.env nie trafia do gita"),
         ]},
        {"key": "derived", "title": "\U0001F535 Liczone z innych danych \u2014 zero pracy",
         "note": "Aplikacja wylicza je sama z tego, co juz masz. Tez nic nie wpisujesz.",
         "items": [
            item("Snapshot majatku (miesieczny)", "derived", "auto z pozycji majatku",
                 "1x/mies. (auto)", snap_last, snap_c, note="jeden punkt netto na miesiac do wykresu majatku"),
            item("Snapshot FIRE (plan vs realnie)", "derived", "auto z plynnosci",
                 "1x/mies. (auto)", fire_last, fire_c, note="karmi prognoze work-optional"),
            item("Przypomnienia automatyczne", "derived", "z danych (vesty, koniec stalej stopy...)",
                 "na biezaco", None, note="wyliczane z danych \u2014 nie trzymane recznie"),
            item("Sledzenie trafnosci predykcji", "derived", "auto przy otwarciu RSU",
                 "codziennie", pred_last, pred_c, note=f"{pred_c} prognoz do backtestu"),
            item("Saldo kredytu (model)", "derived", "rata \u2212 odsetki co miesiac",
                 "co miesiac (auto)", debt_last, debt_c,
                 note="saldo spada samo; korekta wg banku tylko okazjonalnie (nizej)"),
         ]},
        {"key": "claude", "title": "\U0001F7E3 Utrzymywane offline (Claude/notatki) \u2014 miesiecznie/na zadanie",
         "note": "Snapshoty researchu, autorowane poza runtime. Aplikacja tylko je czyta.",
         "items": [
            item("Brief rynkowy", "claude", "app_settings: analysis_market_brief",
                 "miesiecznie", brief_asof, note="ruchy + kontekst makro + rekomendacje per pozycja" if brief_has else "brak \u2014 do wygenerowania"),
            item("Barometr rynku pracy", "claude", "market_barometer",
                 "miesiecznie", bar_last, bar_c, note=f"{bar_c} punktow popytu na role"),
            item("Analiza vestu (RSU)", "claude", "app_settings: rsu_vest_analysis",
                 "co vest (~kwartalnie)", vest_asof, note="wyniki, guidance, targety" if vest_has else "brak"),
            item("Analiza celu (np. nieruchomosc)", "claude", "app_settings: analysis_property_location",
                 "na zadanie / rzadko", prop_asof, note="gleboka analiza" if prop_has else "brak"),
         ]},
        {"key": "manual_reg", "title": "\U0001F7E1 Recznie \u2014 regularnie (to chcemy zredukowac)",
         "note": "Jedyne, co realnie wpisujesz co miesiac. Cel: doprowadzic to do minimum.",
         "items": [
            item("Salda kont / gotowka", "manual", "Ty (zakladka Majatek)",
                 "miesiecznie", acc_last, acc_c, minutes=3,
                 note="najbardziej reczny punkt \u2014 banki nie maja otwartego API bez integracji",
                 suggest="n8n + GoCardless/Nordigen (darmowe PSD2 w UE) \u2192 dzienne saldo bez wpisywania"),
            item("Wartosc portfela (broker/ETF)", "manual", "Ty (setting portfela + pozycje majatku)",
                 "miesiecznie / przy transakcji", wv_last, wi_c, minutes=3,
                 note="dzis wpisujesz WARTOSC recznie",
                 suggest="trzymaj tylko LICZBE jednostek; wartosc policzy sie sama z kursow w cache \u2014 aktualizacja tylko przy zakupie"),
            item("Stan celow (odlozone)", "manual", "Ty (zakladka Cele)",
                 "miesiecznie", goal_last, goal_c, minutes=1,
                 note="ile uzbierane",
                 suggest="wyliczaj z plynnych aktywow (konta \u2212 bufor) zamiast wpisywac recznie"),
            item("Przychody/koszty dzialalnosci", "manual", "Ty (zakladka Firma)",
                 "miesiecznie", biz_last, biz_c, minutes=2,
                 note="wynik dzialalnosci",
                 suggest="jesli masz dane sprzedazy w Supabase \u2014 auto-zaciagaj przychod z pipeline'u"),
            item("Korekta salda kredytu wg banku", "manual", "Ty (zakladka Kredyty)",
                 "okazjonalnie (model liczy sam)", dv_last, dv_c, minutes=1,
                 note="tylko gdy chcesz zgrac co do grosza z wyciagiem",
                 suggest="import 1 liczby z wyciagu bankowego (PSD2) zamiast recznej korekty"),
         ]},
        {"key": "manual_rare", "title": "\u26AA Recznie \u2014 rzadko / zdarzeniowo (setup)",
         "note": "Wpisujesz raz albo tylko gdy cos sie realnie zmienia \u2014 nie obciaza miesiecznie.",
         "items": [
            item("Oferty pracy", "manual", "Ty (zakladka Oferty)",
                 "gdy przyjda (zdarzeniowo)", off_last, off_c, minutes=0,
                 note="nie cykliczne \u2014 dopisujesz, gdy rekruter napisze"),
            item("Koszty stale / plan budzetu", "manual", "setting: fixed_costs",
                 "rzadko (gdy sie zmienia)", None, minutes=0, note="raty, czynsz, subskrypcje \u2014 stabilne"),
            item("Dane podatkowe", "manual", "settings: tax_*",
                 "~rocznie", None, minutes=0, note="zmiana raz na jakis czas"),
            item("Konfiguracja RSU (ticker, vesty, akcje)", "manual", "market_meta / RSU",
                 "rzadko", None, minutes=0, note="aktualizacja przy grancie/vescie"),
            item("Watchlista + targety cenowe", "manual", "Ty (zakladka Rynek)",
                 "okazjonalnie", None, minutes=0, note="dodajesz ticker/target, gdy chcesz go sledzic"),
            item("Ubezpieczenia", "manual", "insurance_policies",
                 "rzadko", None, ins_c, minutes=0, note="polisy \u2014 zmiana przy odnowieniu"),
         ]},
    ]

    manual_reg = next(g for g in groups if g["key"] == "manual_reg")["items"]
    minutes = sum(i["minutes"] for g in groups for i in g["items"])
    counts = {g["key"]: len(g["items"]) for g in groups}

    roadmap = [
        {"title": "Portfel: trzymaj liczbe jednostek, nie wartosc",
         "impact": "wysoki", "effort": "niski",
         "saves": "~3 min/mies + zawsze aktualne",
         "how": "Masz juz kursy w cache. Zapisuj tylko ile masz jednostek; wartosc = jednostki x ostatni kurs. "
                "Wpis tylko przy zakupie, nie co miesiac."},
        {"title": "Stan celow liczony z plynnosci",
         "impact": "sredni", "effort": "niski",
         "saves": "~1 min/mies + spojnosc",
         "how": "Uzbierane wylicz z (konta plynne \u2212 bufor bezpieczenstwa) zamiast osobnego pola. "
                "Jedno zrodlo prawdy zamiast dwoch."},
        {"title": "Salda kont przez PSD2 (GoCardless/Nordigen)",
         "impact": "wysoki", "effort": "sredni",
         "saves": "~3 min/mies \u2014 likwiduje ostatni reczny punkt",
         "how": "Darmowe UE API bankowe (Open Banking). n8n raz dziennie pobiera saldo do Supabase, "
                "apka czyta jak kursy. Zostaje zero comiesiecznego wpisywania sald."},
        {"title": "Przychod dzialalnosci auto z pipeline'u",
         "impact": "sredni", "effort": "sredni",
         "saves": "~2 min/mies",
         "how": "Jesli dane sprzedazy sa w Supabase, auto-uzupelniaj przychod zamiast wpisywac wynik recznie."},
        {"title": "Alert przy nieswiezych danych \u2705 gotowe",
         "impact": "niski", "effort": "zrobione",
         "saves": "spokoj \u2014 lapiesz zerwany sync sam",
         "how": "Gotowy workflow n8n \u2192 Telegram w integrations/n8n/ (codzienny check swiezosci "
                "market_prices w Supabase, alert gdy > prog dni). Import do n8n wg README; rozszerzalny."},
    ]

    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "groups": groups,
        "roadmap": roadmap,
        "summary": {
            "auto": counts.get("auto", 0) + counts.get("derived", 0),
            "claude": counts.get("claude", 0),
            "manual_regular": len(manual_reg),
            "manual_rare": counts.get("manual_rare", 0),
            "manual_minutes": minutes,
            "manual_touchpoints": sum(1 for i in manual_reg if i["minutes"] > 0),
        },
    }


# ---------- git / GitHub sync status ----------

def git_status(do_fetch=True):
    import subprocess
    from pathlib import Path
    import market as _mkt
    repo = str(_mkt._finance_dir().parent)

    def g(args, timeout=10):
        try:
            r = subprocess.run(["git", "-C", repo] + args, capture_output=True,
                               text=True, timeout=timeout)
            return r.stdout.strip()
        except Exception:
            return ""

    out = {"repo": repo}
    out["branch"] = g(["rev-parse", "--abbrev-ref", "HEAD"]) or "?"
    out["remote"] = g(["remote", "get-url", "origin"]) or "brak remote"
    fetched = False
    if do_fetch and out["remote"] != "brak remote":
        try:
            import subprocess as _sp
            _sp.run(["git", "-C", repo, "fetch", "--quiet", "origin"],
                    capture_output=True, timeout=20)
            fetched = True
        except Exception:
            fetched = False
    out["fetched"] = fetched
    porcelain = g(["status", "--porcelain"])
    out["uncommitted"] = len([l for l in porcelain.splitlines() if l.strip()])
    ahead = g(["rev-list", "--count", "origin/main..HEAD"])
    behind = g(["rev-list", "--count", "HEAD..origin/main"])
    out["ahead"] = int(ahead) if ahead.isdigit() else 0
    out["behind"] = int(behind) if behind.isdigit() else 0
    out["last_commit"] = g(["log", "-1", "--format=%h %s"])
    out["last_commit_date"] = g(["log", "-1", "--format=%cd", "--date=format:%Y-%m-%d %H:%M"])
    out["total_commits"] = g(["rev-list", "--count", "HEAD"]) or "?"
    unpushed = g(["log", "origin/main..HEAD", "--format=%h %s"])
    out["unpushed_list"] = [l for l in unpushed.splitlines() if l.strip()][:15]
    uncommitted_files = [l[3:] for l in porcelain.splitlines() if l.strip()][:15]
    out["uncommitted_files"] = uncommitted_files
    out["synced"] = (out["uncommitted"] == 0 and out["ahead"] == 0 and out["behind"] == 0)
    if out["synced"]:
        out["status"] = "ok"; out["summary"] = "Zsynchronizowane z GitHub ✓"
    elif out["behind"] > 0:
        out["status"] = "warn"; out["summary"] = f"GitHub ma {out['behind']} commitów, których nie masz lokalnie"
    elif out["uncommitted"] or out["ahead"]:
        parts = []
        if out["uncommitted"]:
            parts.append(f"{out['uncommitted']} niezacommitowanych zmian")
        if out["ahead"]:
            parts.append(f"{out['ahead']} commitów przed GitHub")
        out["status"] = "warn"; out["summary"] = "Do wypchnięcia: " + ", ".join(parts)
    else:
        out["status"] = "ok"; out["summary"] = "Zsynchronizowane"
    return out


# ---------- FIRE / work-optional projection (zamiast Monte Carlo) ----------

def fire_projection():
    """Projekcja płynnego portfela do celu work-optional (3 mln), 3 scenariusze
    zwrotu + wersja realna (po inflacji). Czytelne linie zamiast histogramu MC."""
    from datetime import date
    goals = list_goals()
    g = next((x for x in goals if any(k in x["name"].lower()
             for k in ("work-optional", "płynn", "3 mln", "niezależ"))), None)
    start = (g and g.get("current_amount")) or 289000
    target = (g and g.get("target_amount")) or 1000000
    base_month = _num(get_setting("monthly_savings")) or 10000
    extras = _annual_extras().get("monthly_equivalent", 0) or 0
    contrib = base_month + extras
    # po spłacie kredytu uwolniona rata dorzuca do oszczędności (uproszczenie: +3200 od startu+~1 rok)
    freed = 0
    try:
        loan = next((d for d in list_debts()["debts"] if "loan" in d["name"].lower()
                     ), None)
        freed = loan.get("monthly_cost_total", 0) if loan else 0
    except Exception:
        freed = 0

    scenarios = {"ostrożny (4%)": 0.04, "bazowy (6,5%)": 0.065, "optymistyczny (9%)": 0.09}
    today = date.today()
    horizon = 15 * 12
    series = {k: [] for k in scenarios}
    labels = []
    crossover = {}

    def label_at(m):
        yy = today.year + (today.month - 1 + m) // 12
        mm = (today.month - 1 + m) % 12 + 1
        return f"{yy:04d}-{mm:02d}"

    for name, r in scenarios.items():
        bal = start
        rm = r / 12
        for m in range(horizon + 1):
            if m % 12 == 0:
                series[name].append(round(bal))
                if name == list(scenarios)[1]:
                    labels.append(label_at(m))
            if name not in crossover and bal >= target:
                crossover[name] = label_at(m)
            # uwolniona rata kredytu dorzuca po ~12 miesiącach
            add = contrib + (freed if m >= 12 else 0)
            bal = bal * (1 + rm) + add

    # kamienie milowe dla scenariusza bazowego
    base_r = 0.065 / 12
    milestones = {}
    bal = start
    for m in range(horizon + 1):
        for mk in (1000000, 660000, 1000000):
            if mk not in milestones and bal >= mk:
                milestones[mk] = label_at(m)
        bal = bal * (1 + base_r) + contrib + (freed if m >= 12 else 0)

    # wersja realna (po inflacji 3%): zwrot realny bazowy 3,5%
    real_r = 0.035 / 12
    bal = start
    real_cross = None
    for m in range(horizon + 1):
        if real_cross is None and bal >= target:
            real_cross = label_at(m)
        bal = bal * (1 + real_r) + contrib + (freed if m >= 12 else 0)

    # --- prognoza cel/Hiszpania (wkład 50%) ---
    ig = next((x for x in goals if any(k in x["name"].lower()
              for k in ("wło", "property", "garda", "hiszp", "andaluz"))), None)
    property_target = (ig and ig.get("target_amount")) or 200000
    property_start = (ig and ig.get("current_amount")) or 0
    delay = 5
    try:
        cf = cashflow()
        lp = cf.get("loan_paid_month")
        if lp:
            delay = max(0, (int(lp[:4]) - today.year) * 12 + (int(lp[5:7]) - today.month))
    except Exception:
        pass
    property_r = 0.04 / 12  # blisko celu → ostrożniej/płynniej
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
        tracking = {"status": "brak danych"}

    return {
        "start": round(start), "target": round(target),
        "monthly_contribution": round(contrib), "freed_after_loan": round(freed),
        "labels": labels, "series": series, "crossover": crossover,
        "milestones": {str(k): v for k, v in milestones.items()},
        "real_crossover": real_cross,
        "property": {"target": round(property_target), "start": round(property_start),
                  "crossover": property_cross, "series": property_series, "delay_months": delay,
                  "note": "Akumulacja wkładu startuje po spłacie kredytu (~" + (label_at(delay)) + "). Ostrożny zwrot 4% (środki blisko celu). UWAGA: te same nadwyżki co work-optional — kupno domu opóźnia dojście do 3 mln."},
        "tracking": tracking,
        "assumptions": {"base_return": "6,5% nominalnie", "inflation": "3%",
                        "contrib_note": f"{round(contrib)} zł/mies. (oszczędności {round(base_month)} + bonus/RSU {round(extras)}); po spłacie kredytu +{round(freed)}"},
    }


def _liquid_now():
    """Płynny portfel = ETF + akcje RSU + gotówka + emerytalne (bez nieruchomości)."""
    try:
        a = allocation()
        keys = {"etf", "team", "gotowka", "emerytalne"}
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
        nw = wealth_summary()["total"] - wealth_summary()["debt_total"]
    except Exception:
        pass
    eb._exec("insert into fire_snapshots (month, liquid, net_worth, created_at) values (?,?,?,?)",
             (month, liquid, nw, _now()))


def fire_tracking(contrib, freed, base_annual):
    """Porównuje realne miesięczne snapshoty z oczekiwanym tempem (plan)."""
    snaps = eb._rows("select month, liquid from fire_snapshots order by month asc")
    if len(snaps) < 2:
        return {"status": "zbieram dane", "snapshots": len(snaps),
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
    verdict = ("wyprzedzasz plan" if cum_delta > 5000 else
               "jesteś za planem" if cum_delta < -5000 else "zgodnie z planem")
    return {"status": "ok", "rows": rows[-6:], "cum_delta": round(cum_delta),
            "verdict": verdict, "months_tracked": len(snaps),
            "latest_liquid": round(snaps[-1]["liquid"])}


# ---------- GitHub / aktywność commitowa (skill: commitowanie) ----------

def github_activity(days=90):
    """Daily commit activity across local git repos. Configure which repos and
    author to count via settings `commit_repos` (comma-separated absolute paths)
    and `commit_author` (git --author filter; blank = all authors)."""
    import os
    import subprocess
    from datetime import date, timedelta
    from pathlib import Path
    home = Path.home()
    repos = set()
    configured = (get_setting("commit_repos") or os.environ.get("COMMIT_REPOS", "")).strip()
    if configured:
        for p in configured.split(","):
            if (Path(p.strip()) / ".git").exists():
                repos.add(p.strip())
    else:
        try:
            for d in home.iterdir():
                if (d / ".git").is_dir():
                    repos.add(str(d))
        except Exception:
            pass
    author = (get_setting("commit_author") or os.environ.get("COMMIT_AUTHOR", "")).strip()

    counts = {}
    for repo in repos:
        try:
            cmd = ["git", "-C", repo, "log", f"--since={days} days ago",
                   "--format=%cd", "--date=short"]
            if author:
                cmd.insert(4, f"--author={author}")
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=12).stdout
            for line in out.splitlines():
                dd = line.strip()
                if dd:
                    counts[dd] = counts.get(dd, 0) + 1
        except Exception:
            pass

    today = date.today()
    series = []
    for i in range(days - 1, -1, -1):
        dd = (today - timedelta(days=i)).isoformat()
        series.append({"date": dd, "count": counts.get(dd, 0)})
    total = sum(c["count"] for c in series)
    active_days = sum(1 for c in series if c["count"] > 0)
    # streak (kolejne dni do dziś z ≥1 commitem)
    streak = 0
    i = 0
    while counts.get((today - timedelta(days=i)).isoformat(), 0) > 0:
        streak += 1
        i += 1
    # najdłuższy streak w oknie
    best = cur = 0
    for c in series:
        if c["count"] > 0:
            cur += 1; best = max(best, cur)
        else:
            cur = 0
    week = sum(counts.get((today - timedelta(days=i)).isoformat(), 0) for i in range(7))
    return {
        "series": series, "days": days, "repos": len(repos),
        "today": counts.get(today.isoformat(), 0),
        "week": week, "total": total, "active_days": active_days,
        "streak": streak, "best_streak": best,
        "avg_per_active": round(total / active_days, 1) if active_days else 0,
        "active_pct": round(100 * active_days / days),
    }


# ---------- security scan (sekrety w repo) ----------

def security_scan():
    import subprocess, re
    from pathlib import Path
    from datetime import datetime
    import market as _mkt
    repo = str(_mkt._finance_dir().parent)
    findings = []

    def g(args, timeout=20):
        try:
            return subprocess.run(["git", "-C", repo] + args, capture_output=True, text=True, timeout=timeout)
        except Exception:
            return None

    ls = g(["ls-files"])
    tracked = ls.stdout.splitlines() if ls else []

    # 1. pliki-sekrety śledzone
    bad = [f for f in tracked if re.search(r"(^|/)\.env($|\.)(?!example)|\.pem$|\.key$|id_rsa|\.p12$|secret", f, re.I)]
    if bad:
        findings.append({"sev": "high", "what": "Śledzone pliki-sekrety", "detail": ", ".join(bad[:5])})

    # 2. wrażliwe ścieżki nie-ignorowane
    for p in ("private", ".finance", "doc-raw", "backups"):
        ci = g(["check-ignore", p + "/"])
        leaked = [f for f in tracked if f.startswith(p + "/")]
        if leaked:
            findings.append({"sev": "high", "what": f"Śledzone pliki w {p}/", "detail": ", ".join(leaked[:3])})

    # 3. leak-check: realne wartości z .env w śledzonych plikach
    env = Path(repo) / ".env"
    checked = 0
    if env.exists():
        for line in env.read_text().splitlines():
            line = line.strip()
            if "=" not in line or line.startswith("#"):
                continue
            k, _, v = line.partition("=")
            v = v.strip().strip('"').strip("'")
            if len(v) < 12:  # pomiń krótkie (PORT itd.)
                continue
            checked += 1
            r = g(["grep", "-F", v, "--", "."])
            if r and r.stdout.strip():
                findings.append({"sev": "critical", "what": f"WYCIEK wartości {k.strip()}", "detail": "wartość z .env znaleziona w śledzonym pliku!"})

    # 4. wzorce sekretów (poza base64/blogami). Literały rozbite, by skaner nie łapał sam siebie.
    pat = "|".join([
        "eyJ" + "hbGciOiJ",                       # JWT header
        r"https://[a-z0-9]{15,}\.supabase\.co",   # realny URL Supabase
        r"/webhook/[a-f0-9-]{36}",                # webhook n8n
        "sk" + r"-[A-Za-z0-9]{20,}",              # OpenAI-style
        "ghp" + r"_[A-Za-z0-9]{20,}",             # GitHub token
        "AKI" + r"A[0-9A-Z]{16}",                 # AWS
        "-----" + "BEGIN (RSA |OPENSSH |EC )?PRIVATE",
    ])
    r = g(["grep", "-nIE", pat,
           "--", ".", ":(exclude)posts/*", ":(exclude)*.html", ":(exclude)doc-raw/*"])
    if r and r.stdout.strip():
        for ln in r.stdout.strip().splitlines()[:5]:
            findings.append({"sev": "high", "what": "Wzorzec sekretu", "detail": ln[:100]})

    crit = sum(1 for f in findings if f["sev"] == "critical")
    high = sum(1 for f in findings if f["sev"] == "high")
    status = "error" if (crit or high) else "ok"
    return {"status": status, "findings": findings, "tracked_files": len(tracked),
            "secrets_checked": checked, "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "summary": ("🚨 " + str(crit + high) + " znalezisk — sprawdź!") if findings else f"Czysto — {len(tracked)} plików, {checked} wartości .env zweryfikowanych, zero wycieków"}
