"""Growth as an engineering leader (2026-09-05): evidence log, the week in four numbers and
the state of a 90-day plan.

Career had analyses and market data but no MEASUREMENT: nowhere to write "what I did, with
which number, with which proof". This module is that place — it feeds performance reviews,
scope conversations and any "AI operating model" page you build for your org.
"""
import json
import uuid
from datetime import date, datetime

import engine_bridge as eb
import planner

KINDS = ("impact", "visibility", "scope", "feedback", "learning")
WEEK_FIELDS = ("energy", "deep_hours", "one_on_ones", "decisions")


def _now():
    return datetime.now().isoformat(timespec="seconds")


def ensure_tables():
    eb._exec("""create table if not exists em_log (
        id text primary key, date text not null, kind text not null, text text not null,
        metric text default '', value real, link text default '', created_at text not null)""")
    eb._exec("""create table if not exists em_week (
        week text primary key, energy real, deep_hours real, one_on_ones real, decisions real,
        note text default '', created_at text not null)""")


def week_key(d=None):
    d = d or date.today()
    y, w, _ = d.isocalendar()
    return f"{y:04d}-W{w:02d}"


# ---------------------------------------------------------------- evidence log

def list_log(limit=200):
    ensure_tables()
    return eb._rows("select * from em_log order by date desc, created_at desc limit ?", (limit,))


def add_log(data):
    ensure_tables()
    kind = (data.get("kind") or "impact").strip()
    if kind not in KINDS:
        raise ValueError("kind")
    text = (data.get("text") or "").strip()
    if not text:
        raise ValueError("text")
    value = planner._num(data.get("value"))
    row = (uuid.uuid4().hex, (data.get("date") or date.today().isoformat())[:10], kind, text[:600],
           (data.get("metric") or "").strip()[:80], value, (data.get("link") or "").strip()[:300], _now())
    eb._exec("insert into em_log (id, date, kind, text, metric, value, link, created_at) values (?,?,?,?,?,?,?,?)", row)
    planner._audit("em_log", row[0], "add", {"kind": kind})
    return {"id": row[0]}


def delete_log(eid):
    ensure_tables()
    eb._exec("delete from em_log where id=?", (eid,))
    planner._audit("em_log", eid, "delete")


# ---------------------------------------------------------------- the week in 4 numbers

def get_weeks(n=12):
    ensure_tables()
    rows = eb._rows("select * from em_week order by week desc limit ?", (n,))
    rows.reverse()
    return rows


def put_week(data):
    ensure_tables()
    wk = (data.get("week") or week_key()).strip()[:8]
    vals = {}
    for f in WEEK_FIELDS:
        v = planner._num(data.get(f))
        vals[f] = None if v is None else max(0.0, float(v))
    if vals["energy"] is not None:
        vals["energy"] = min(5.0, vals["energy"])
    eb._exec("insert or replace into em_week (week, energy, deep_hours, one_on_ones, decisions, note, created_at) "
             "values (?,?,?,?,?,?,?)",
             (wk, vals["energy"], vals["deep_hours"], vals["one_on_ones"], vals["decisions"],
              (data.get("note") or "").strip()[:300], _now()))
    return {"week": wk, **vals}


# ---------------------------------------------------------------- 90-day plan (state)

def plan_state():
    try:
        return json.loads(planner.get_setting("plan90_state") or "{}")
    except ValueError:
        return {}


def set_plan_state(idx, status, note=""):
    st = plan_state()
    key = str(int(idx))
    if status not in ("todo", "doing", "done"):
        raise ValueError("status")
    st[key] = {"status": status, "note": (note or "")[:200], "at": date.today().isoformat()}
    planner.set_settings({"plan90_state": json.dumps(st)})
    return st


# ---------------------------------------------------------------- summary

def summary():
    log = list_log(80)
    counts = {k: 0 for k in KINDS}
    for r in log:
        counts[r["kind"]] = counts.get(r["kind"], 0) + 1
    weeks = get_weeks(12)
    return {"log": log, "counts": counts, "weeks": weeks, "this_week": week_key(),
            "kinds": list(KINDS), "plan": plan_state()}
