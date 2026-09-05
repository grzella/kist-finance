"""planner_core — Core: app tables, settings, audit log, shared helpers (_num, _now, _zl).

Split out of planner.py on 2026-09-05 (code moved 1:1; other modules are reached through `P`).
"""
import uuid
from datetime import date, datetime

import engine_bridge as eb

OWNERS = ("me", "partner", "joint")
WEALTH_KINDS = ("investment", "cushion", "savings", "income")


def _now():
    return datetime.now().isoformat(timespec="seconds")


def ensure_tables():
    eb._exec("""create table if not exists wealth_items (
        id text primary key, name text not null, kind text not null,
        owner text default 'joint', currency text default 'PLN',
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
        status text default 'new', received_at text, notes text default '',
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
    # quote-based valuation: ticker (+ optional units; units NULL with a ticker
    # matching the RSU grant = share count flows from rsu.json shares_held)
    for col, typ in (("ticker", "text"), ("units", "real")):
        try:
            eb._exec("alter table wealth_items add column " + eb._ident(col) + " " + typ)
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
    # generalized barometer: per-role counts (JSON), explicit methodology, stream
    # (trends = search-interest demand proxy / openings = real posting counts)
    for col, ddl in (("counts", "text"), ("sources", "text"), ("geo", "text"),
                     ("as_of", "text"), ("stream", "text default 'trends'")):
        try:
            eb._exec(f"alter table market_barometer add column {col} {ddl}")
        except Exception:
            pass  # column already exists
    eb._exec("""create table if not exists fire_snapshots (
        month text primary key, liquid real not null, net_worth real,
        created_at text not null)""")
    # fixed expenses: item + amount PER MONTH (mirrors wealth_items/values) —
    # an item you don't touch this month simply carries its last value forward
    # (see expense_summary), so there's no monthly copy-paste of the whole list
    # and no separately-kept totals to keep in sync by hand
    eb._exec("""create table if not exists expense_items (
        id text primary key, name text not null, category text default '',
        payer text default 'me', essential integer default 1,
        currency text default 'USD', archived integer default 0,
        entity text default 'personal', invoice integer default 0,
        billing text default 'monthly',
        created_at text not null)""")
    try:  # databases created before the billing cadence existed
        eb._exec("alter table expense_items add column billing text default 'monthly'")
    except Exception:
        pass
    eb._exec("""create table if not exists expense_values (
        id text primary key, item_id text not null, month text not null,
        amount real not null, created_at text not null)""")
    eb._exec("create unique index if not exists ux_expense_values_item_month "
             "on expense_values(item_id, month)")


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
    data = dict(data)
    # mirror: one savings pace under two historical keys
    if "monthly_savings" in data and "cf_monthly_surplus" not in data:
        data["cf_monthly_surplus"] = data["monthly_savings"]
    elif "cf_monthly_surplus" in data and "monthly_savings" not in data:
        data["monthly_savings"] = data["cf_monthly_surplus"]
    # debt-strategy timestamp — the recommendation shows how much changed since it was written
    if "debt_strategy" in data and "debt_strategy_at" not in data:
        data["debt_strategy_at"] = _now()
    for k, v in data.items():
        eb._exec("insert into app_settings (key, value) values (?,?) "
                 "on conflict(key) do update set value=excluded.value", (k, str(v)))
    _audit("settings", None, "update", data)
    return settings()


# Keys that the generic PUT /api/settings endpoint must NOT be allowed to write:
# each has its own dedicated endpoint or is internal state. Blocking them here
# stops "mass assignment" — e.g. pointing the commit tracker at an arbitrary path
# (git-log info disclosure) or flipping the AI to cloud mode — via the one open
# key/value writer. Internal callers use set_settings() directly and are unaffected.
_PROTECTED_SETTINGS = {
    "commit_repos", "commit_author",      # → git log on arbitrary local paths
    "backup_dir", "backup_auto",          # → filesystem/backup (has /api/backup/config)
    "app_config",                         # → modules/wizard (has /api/app-config)
    "ai_mode",                            # → local vs cloud (has /api/llm/config)
    "rag_dirty", "gh_activity_cache", "last_security_review",  # internal state
}


def set_settings_public(data):
    """set_settings for the browser-facing PUT /api/settings endpoint: silently
    drops protected keys so a same-origin/CSRF write can't set security-sensitive
    settings through the generic writer. Returns the rejected keys for visibility."""
    rejected = [k for k in data if k in _PROTECTED_SETTINGS]
    allowed = {k: v for k, v in data.items() if k not in _PROTECTED_SETTINGS}
    if allowed:
        set_settings(allowed)
    if rejected:
        _audit("settings", None, "reject", {"blocked": rejected})
    return {**settings(), "rejected": rejected}


def monthly_surplus():
    """ONE savings pace for Goals, Offers, FIRE and Cash-flow: cf_monthly_surplus
    (fallback: the legacy monthly_savings). Two keys were two sources of truth for the same
    number — from now on set_settings mirrors one into the other."""
    v = _num(get_setting("cf_monthly_surplus"))
    if v is None:
        v = _num(get_setting("monthly_savings"))
    return v


def settings():
    return {
        "current_total_monthly": _num(get_setting("current_total_monthly")),
        "monthly_savings": monthly_surplus(),
        "cf_monthly_surplus": monthly_surplus(),
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
     "views": ["business"], "default": False},
    {"id": "career",   "label": "Career tracker",    "icon": "💼",
     "desc": "Inbound job offers, market barometer, commit-activity tracker.",
     "views": ["offers", "career", "commits"], "default": False},
    {"id": "property", "label": "Property analysis", "icon": "🏡",
     "desc": "Deep-dive analysis for a property-purchase goal (location, financing, rental math).",
     "views": ["property"], "default": False},
]

CORE_VIEWS = ["dashboard", "cashflow", "recs", "wealth", "expenses", "allocation", "goals",
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
        "currency": get_setting("base_currency") or "PLN",
        "registry": MODULES,
        "enabled_views": enabled_views,
    }


def save_app_config(data):
    import json as _json
    cur = get_app_config()
    raw = data.get("modules") or {}
    if isinstance(raw, list):
        # tolerate a plain list of enabled module ids (natural API-consumer shape)
        raw = {m["id"]: (m["id"] in raw) for m in MODULES}
    mods = {m["id"]: bool(raw.get(m["id"], cur["modules"].get(m["id"], m["default"])))
            for m in MODULES}
    cfg = {"wizard_completed": bool(data.get("wizard_completed", cur["wizard_completed"])),
           "modules": mods}
    if data.get("base_currency") in ("PLN", "EUR", "USD", "GBP", "CHF"):
        set_settings({"base_currency": data["base_currency"]})
    set_settings({"app_config": _json.dumps(cfg)})
    return get_app_config()


# ---------- data freshness (monthly update rhythm) ----------

def _months_between(a, b):
    """Whole calendar months between ISO dates (a <= b)."""
    return (int(b[:4]) - int(a[:4])) * 12 + (int(b[5:7]) - int(a[5:7]))
