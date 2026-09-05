"""planner_business — Firma: księga przychodów/kosztów, plan działań, marketing (Supabase).

Wydzielone z planner.py 2026-09-05 (kod 1:1; odwołania do innych modułów przez `P`).
"""
import uuid
from datetime import date

import engine_bridge as eb
from planner_proxy import P

# ---------- side business (revenue/cost ledger) ----------

BIZ_KINDS = ("cost", "revenue")
BIZ_CATEGORIES = ("equipment", "marketing", "software", "insurance",
                  "certifications", "travel", "accounting", "other",
                  "service", "content", "licenses")


def ensure_biz_table():
    eb._exec("""create table if not exists biz_entries (
        id text primary key, date text not null, kind text not null,
        category text default 'other', amount real not null,
        description text default '', created_at text not null)""")


def biz_summary():
    ensure_biz_table()
    rows = eb._rows("select * from biz_entries order by date desc, rowid desc")
    monthly = {}
    for r in rows:
        m = r["date"][:7]
        monthly.setdefault(m, {"month": m, "costs": 0, "revenue": 0,
                               "marketing": 0})
        if r["kind"] == "cost":
            monthly[m]["costs"] += r["amount"]
            if r["category"] == "marketing":
                monthly[m]["marketing"] += r["amount"]
        else:
            monthly[m]["revenue"] += r["amount"]
    months = sorted(monthly.values(), key=lambda x: x["month"])
    cum = 0
    for m in months:
        m["result"] = round(m["revenue"] - m["costs"], 2)
        cum += m["result"]
        m["cumulative"] = round(cum, 2)
        m["roas"] = round(m["revenue"] / m["marketing"], 2) if m["marketing"] else None
        for k in ("costs", "revenue", "marketing"):
            m[k] = round(m[k], 2)
    total_cost = sum(m["costs"] for m in months)
    total_rev = sum(m["revenue"] for m in months)
    cur = date.today().strftime("%Y-%m")
    return {
        "entries": rows[:200],
        "months": months,
        "current": monthly.get(cur, {"costs": 0, "revenue": 0, "result": 0}),
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
         data.get("category", "other"), float(data["amount"]),
         data.get("description", ""), P._now()))
    P._audit("biz", entry_id, "add", data)
    return entry_id


def delete_biz_entry(entry_id):
    P._audit("biz", entry_id, "delete")
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
         data.get("status", "backlog"), data.get("expected_impact", ""), P._now()))
    P._audit("action", action_id, "add", {"title": data["title"]})
    return action_id


def update_action(action_id, data):
    cols, params = [], []
    for k in ("title", "area", "detail", "status", "expected_impact",
              "actual_impact_pln", "actual_note"):
        if k in data:
            cols.append(k); params.append(data[k])
    if data.get("status") == "zrobione":
        cols.append("done_at"); params.append(P._now())
    if cols:
        params.append(action_id)
        eb._exec(eb.update_sql("actions", cols), tuple(params))
        P._audit("action", action_id, "update", data)


def delete_action(action_id):
    P._audit("action", action_id, "delete")
    eb._exec("delete from actions where id = ?", (action_id,))


# ---------- business: performance marketing (Supabase — marketing agents) ----------

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


def business_marketing():
    """Weekly ads intelligence from the marketing agents (ads-collector/-analyst)."""
    import market
    try:
        reports = market._supabase_get(
            "analysis_reports?select=week_start,week_end,total_spend,report_json,"
            "recommendations,created_at&order=week_start.desc&limit=8", service=True)
        insights = market._supabase_get(
            "insights?select=category,platform,insight,confidence,is_active"
            "&is_active=eq.true&order=confidence.desc&limit=6", service=True)
        hypotheses = market._supabase_get(
            "hypotheses?select=title,predicted_outcome,success_metric,target_value,status"
            "&status=eq.active&limit=5", service=True)
        spend_rows = market._supabase_get(
            "ad_snapshots?select=date,spend,clicks,impressions&order=date.desc&limit=60", service=True)
    except Exception as e:
        return {"error": f"offline / no connection to Supabase: {e}"}

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
