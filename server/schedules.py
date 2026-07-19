"""User-configurable schedules for the app's recurring tasks.

The app is a local web server with no daemon, so 'app'-kind tasks run on the
next app open **after** their scheduled moment (checked from /api/health via
run_due()): each task remembers the last period it ran in (day / ISO week /
month) and fires once per period, at or after the chosen day+hour.

Kinds:
  app      — executed by this module (backup snapshot, wealth snapshot,
             forecast self-learning cycle, RAG reindex).
  external — shown read-only (e.g. an n8n cloud workflow); edit at the source.

Config lives in app_settings: `schedules` = {task_id: {freq, day, hour}} and
`sched_last.<id>` = period key of the last run.
"""
import json
from datetime import datetime

import planner


def _run_backup():
    import data_backup
    if not planner.get_setting("backup_auto"):
        return False  # master switch in Control Center is off
    return data_backup.create_backup().get("ok", False)


def _run_wealth_snapshot():
    planner.ensure_monthly_snapshot()
    return True


def _run_forecast_cycle():
    import market
    market.record_and_score_forecasts()
    return True


def _run_rag_reindex():
    import rag
    return rag.reindex() >= 0


def _run_risk_radar():
    import risk_radar
    return risk_radar.snapshot()


# id → definition. freq: daily|weekly|monthly. day: 0-6 Mon-Sun (weekly) or
# 1-28 (monthly). hour: 0-23 local.
REGISTRY = [
    {"id": "backup_snapshot", "label": "Database backup (encrypted snapshot)",
     "kind": "app", "runner": _run_backup,
     "note": "runs only when a backup folder is set in Control Center",
     "default": {"freq": "daily", "day": 0, "hour": 10}},
    {"id": "wealth_snapshot", "label": "Wealth snapshot (net-worth history point)",
     "kind": "app", "runner": _run_wealth_snapshot,
     "note": "one point per month feeds the wealth chart",
     "default": {"freq": "monthly", "day": 1, "hour": 9}},
    {"id": "forecast_cycle", "label": "Forecast self-learning cycle",
     "kind": "app", "runner": _run_forecast_cycle,
     "note": "settles matured forecasts and records today's bands",
     "default": {"freq": "daily", "day": 0, "hour": 8}},
    {"id": "risk_radar", "label": "Risk radar (daily reading)",
     "kind": "app", "runner": _run_risk_radar,
     "note": "VIX+gold+oil+USD → composite with a local-AI one-liner",
     "default": {"freq": "daily", "day": 0, "hour": 9}},
    {"id": "rag_reindex", "label": "AI memory refresh (RAG reindex)",
     "kind": "app", "runner": _run_rag_reindex,
     "note": "keeps AI answers grounded in your latest data",
     "default": {"freq": "weekly", "day": 0, "hour": 7}},
]

EXTERNAL = [
    {"id": "n8n_market_sync", "label": "Market quotes sync (n8n → Supabase)",
     "kind": "external", "freq_text": "daily 23:15",
     "note": "edit in your n8n workflow — the app only reads the results"},
]


def _cfgs():
    try:
        return json.loads(planner.get_setting("schedules") or "{}")
    except Exception:
        return {}


def get_schedules():
    cfgs = _cfgs()
    out = []
    for t in REGISTRY:
        cfg = {**t["default"], **cfgs.get(t["id"], {})}
        out.append({"id": t["id"], "label": t["label"], "kind": t["kind"],
                    "note": t["note"], **cfg,
                    "last_run": planner.get_setting(f"sched_last.{t['id']}") or None})
    return {"tasks": out, "external": EXTERNAL}


def set_schedule(task_id, data):
    if not any(t["id"] == task_id for t in REGISTRY):
        return {"ok": False, "error": "unknown task"}
    freq = data.get("freq")
    if freq not in ("daily", "weekly", "monthly"):
        return {"ok": False, "error": "freq must be daily|weekly|monthly"}
    day = int(data.get("day", 0))
    hour = int(data.get("hour", 9))
    if not (0 <= hour <= 23):
        return {"ok": False, "error": "hour out of range"}
    if freq == "weekly" and not (0 <= day <= 6):
        return {"ok": False, "error": "weekday must be 0-6"}
    if freq == "monthly" and not (1 <= day <= 28):
        return {"ok": False, "error": "day of month must be 1-28"}
    cfgs = _cfgs()
    cfgs[task_id] = {"freq": freq, "day": day, "hour": hour}
    planner.set_settings({"schedules": json.dumps(cfgs)})
    return {"ok": True, **cfgs[task_id]}


def _period_key(cfg, now):
    if cfg["freq"] == "daily":
        return now.strftime("%Y-%m-%d")
    if cfg["freq"] == "weekly":
        return now.strftime("%G-W%V")
    return now.strftime("%Y-%m")


def _is_due(cfg, last_period, now):
    """Due = we're at/past the scheduled moment of the current period and the
    task hasn't run in this period yet."""
    if _period_key(cfg, now) == last_period:
        return False
    if cfg["freq"] == "daily":
        return now.hour >= cfg["hour"]
    if cfg["freq"] == "weekly":
        wd = now.weekday()
        return wd > cfg["day"] or (wd == cfg["day"] and now.hour >= cfg["hour"])
    d = now.day
    return d > cfg["day"] or (d == cfg["day"] and now.hour >= cfg["hour"])


def run_due(now=None):
    """Run every due 'app' task once. Called from /api/health (best-effort)."""
    now = now or datetime.now()
    cfgs = _cfgs()
    ran = []
    for t in REGISTRY:
        cfg = {**t["default"], **cfgs.get(t["id"], {})}
        key = f"sched_last.{t['id']}"
        if not _is_due(cfg, planner.get_setting(key), now):
            continue
        try:
            ok = t["runner"]()
        except Exception:
            ok = False
        if ok:
            planner.set_settings({key: _period_key(cfg, now)})
            ran.append(t["id"])
    return ran
