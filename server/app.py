"""Kist — local Flask app. Personal data never leaves this machine."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config

CFG = config.setup()  # must run before engine imports (FINANCE_PROJECT_DIR)

from flask import Flask, jsonify, request, send_from_directory  # noqa: E402

import db  # noqa: E402
import engine_bridge as eb  # noqa: E402
import market  # noqa: E402
import forecasts as fc  # noqa: E402
import planner  # noqa: E402

db.init_db()          # base tables (self-contained; replaces external skill)
planner.ensure_tables()

STATIC = Path(__file__).resolve().parent.parent / "static"
app = Flask(__name__, static_folder=str(STATIC), static_url_path="/static")


@app.get("/")
def index():
    return send_from_directory(str(STATIC), "index.html")


_RAG_SKIP = ("/api/llm", "/api/rag", "/api/security-review", "/api/health",
             "/api/schedules", "/api/backup", "/api/market/refresh")


@app.after_request
def _rag_dirty_hook(resp):
    # data changed → mark the AI memory stale; it reindexes itself before the
    # next answer (no more manual "Refresh memory" after adding data)
    try:
        if (request.method in ("POST", "PUT", "DELETE", "PATCH")
                and request.path.startswith("/api/")
                and not request.path.startswith(_RAG_SKIP)
                and resp.status_code < 400):
            planner.set_settings({"rag_dirty": "1"})
    except Exception:
        pass
    return resp


@app.after_request
def _no_cache(resp):
    # local single-user app in active development — always serve fresh JS/CSS/HTML
    p = request.path
    if p == "/" or p.endswith((".js", ".css", ".html")):
        resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
    # cheap hardening for every response: no framing (clickjacking), no MIME
    # sniffing, and don't leak the loopback URL as a referrer to any external link
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "no-referrer"
    # Content-Security-Policy: all scripts are external files under /static (no
    # inline <script>, no on* handlers), so 'self' is enough — this NEUTRALIZES
    # any injected <script>/onerror even if some field slipped through unescaped
    # (defense in depth for stored data, incl. market text synced from Supabase).
    # 'unsafe-inline' is scoped to styles only (the UI uses inline style="").
    resp.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; connect-src 'self'; object-src 'none'; "
        "base-uri 'none'; frame-ancestors 'none'")
    return resp


def _loopback_hosts():
    """Host/authority values that count as 'this machine'. The app only ever
    binds 127.0.0.1, so a request whose Host is anything else is either a
    DNS-rebinding attack or a misconfiguration."""
    port = str(CFG.get("port", ""))
    hosts = {"127.0.0.1", "localhost", "[::1]", "::1"}
    return hosts | {f"{h}:{port}" for h in hosts}


@app.before_request
def _guard_local_only():
    """No auth by design (localhost, single user) — so we defend the two ways a
    browser could reach this server on the user's behalf without their consent:

    1. DNS rebinding: the attacker's page resolves its own hostname to 127.0.0.1
       and talks to us — but the Host header is then the attacker's domain, not
       loopback. Reject any non-loopback Host.
    2. CSRF: a cross-site POST/PUT/DELETE carries an Origin (or Referer) that
       isn't ours. Reject state-changing API calls whose Origin isn't loopback.
       Same-origin fetches from our own page send Origin=http://127.0.0.1:PORT;
       trusted local tooling (curl, the test client) sends no Origin and passes.
    """
    allowed = _loopback_hosts()
    host = (request.host or "").lower()
    if host and host not in allowed:
        return jsonify({"error": "forbidden host — this app is loopback-only"}), 403
    if request.method in ("POST", "PUT", "DELETE", "PATCH") and request.path.startswith("/api/"):
        origin = request.headers.get("Origin") or request.headers.get("Referer") or ""
        if origin:
            from urllib.parse import urlparse
            netloc = urlparse(origin).netloc.lower()
            if netloc and netloc not in allowed:
                return jsonify({"error": "cross-origin request blocked"}), 403
    return None


# ---------- dashboard ----------

@app.get("/api/dashboard/summary")
def dashboard_summary():
    data = eb.dashboard_summary()
    # planned figures: income items from wealth + fixed costs from settings
    import json as _json
    w = planner.wealth_summary()
    # net worth from wealth items (source of truth), not the skill's empty
    # accounts/holdings tables
    t = w["totals"]
    assets = w["total"] - t.get("income", 0)
    data["cash_total"] = round(t.get("cushion", 0) + t.get("savings", 0), 2)
    data["investments_total"] = round(t.get("investment", 0), 2)
    data["debt_total"] = w["debt_total"]
    data["net_worth"] = round(assets - w["debt_total"], 2)
    data["planned_income"] = round(w["totals"].get("income", 0), 2)
    fc_raw = planner.get_setting("fixed_costs")
    if fc_raw:
        try:
            fc = _json.loads(fc_raw)
            data["planned_costs"] = fc.get("total_mine")
            data["planned_essential"] = fc.get("essential_mine")
        except ValueError:
            pass
    if data.get("planned_costs") and data["planned_income"]:
        data["planned_surplus"] = round(data["planned_income"] - data["planned_costs"], 2)
    if fc_raw:
        try:
            items = _json.loads(fc_raw).get("items", [])
            mine = sorted((i for i in items if i.get("payer") == "me"),
                          key=lambda i: -i["monthly"])
            top = mine[:8]
            rest = sum(i["monthly"] for i in mine[8:])
            data["planned_categories"] = (
                [{"category": i["name"], "total": i["monthly"]} for i in top]
                + ([{"category": "other", "total": round(rest, 2)}] if rest else []))
        except ValueError:
            pass
    planner.ensure_monthly_snapshot()
    return jsonify(data)


@app.get("/api/dashboard/net-worth-history")
def net_worth_history():
    return jsonify(eb.net_worth_history())


@app.get("/api/dashboard/spending-trends")
def spending_trends():
    months = int(request.args.get("months", 6))
    return jsonify(eb.spending_trends(months))


# ---------- transactions ----------

@app.get("/api/transactions")
def list_transactions():
    return jsonify(eb.list_transactions(
        month=request.args.get("month"),
        category=request.args.get("category")))


@app.post("/api/transactions")
def add_transaction():
    tx_id = eb.add_transaction(request.get_json(force=True))
    return jsonify({"id": tx_id}), 201


@app.put("/api/transactions/<tx_id>")
def update_transaction(tx_id):
    eb.update_transaction(tx_id, request.get_json(force=True))
    return jsonify({"ok": True})


@app.delete("/api/transactions/<tx_id>")
def delete_transaction(tx_id):
    eb.delete_transaction(tx_id)
    return jsonify({"ok": True})


@app.get("/api/categories")
def categories():
    return jsonify(eb.categories())


@app.get("/api/budget/vs-actual")
def budget_vs_actual():
    return jsonify(eb.budget_vs_actual(request.args.get("month")))


# ---------- market / watchlist ----------

@app.get("/api/watchlist")
def watchlist():
    return jsonify({"tickers": market.get_watchlist(), "last_sync": market.last_sync()})


@app.post("/api/watchlist/<ticker>")
def watchlist_add(ticker):
    return jsonify(market.add_ticker(ticker, request.args.get("notes", "")))


@app.delete("/api/watchlist/<ticker>")
def watchlist_remove(ticker):
    return jsonify(market.remove_ticker(ticker))


@app.get("/api/market/prices/<ticker>")
def market_prices(ticker):
    return jsonify(market.prices(ticker, int(request.args.get("days", 365))))


@app.post("/api/market/deepen/<ticker>")
def market_deepen(ticker):
    """Backfill a ticker's full history from Yahoo (keyless) so its chart and
    indicators have depth — for symbols the nightly sync doesn't cover."""
    rng = (request.get_json(silent=True) or {}).get("range", "1y")
    return jsonify({"stored": market.fetch_yahoo_history(ticker, rng)})


@app.get("/api/market/analytics/<ticker>")
def market_analytics(ticker):
    return jsonify(market.analytics(ticker))


@app.post("/api/market/refresh")
def market_refresh():
    out = market.refresh_cache()
    try:  # self-learning: after fresh data, score and record forecasts
        out["forecast_cycle"] = market.record_and_score_forecasts()
    except Exception as e:
        out["forecast_cycle"] = {"error": str(e)[:80]}
    return jsonify(out)


@app.get("/api/forecast/bands/<path:ticker>")
def forecast_bands(ticker):
    return jsonify(market.ticker_bands(ticker))


@app.get("/api/forecast/selfscore")
def forecast_selfscore():
    return jsonify(market.forecast_selfscore())


@app.post("/api/forecast/cycle")
def forecast_cycle():
    return jsonify(market.record_and_score_forecasts())


@app.get("/api/market/brief")
def market_brief_get():
    return jsonify(market.get_briefs())


@app.post("/api/market/brief/refresh")
def market_brief_refresh():
    """Regenerate a brief now (daily view's "fetch latest" button): pull fresh
    quotes first, then have the local model rewrite the brief from them."""
    kind = (request.get_json(force=True) or {}).get("kind", "daily")
    try:
        market.refresh_cache()
    except Exception:
        pass
    return jsonify(market.generate_brief(kind))


@app.get("/api/fx-analysis")
def fx_analysis():
    return jsonify(market.fx_analysis())


@app.get("/api/risk-radar")
def risk_radar_get():
    import risk_radar
    return jsonify(risk_radar.full())


@app.post("/api/risk-radar/snapshot")
def risk_radar_snap():
    import risk_radar
    return jsonify({"ok": risk_radar.snapshot()})


@app.put("/api/market/target/<ticker>")
def market_target(ticker):
    body = request.get_json(force=True)
    return jsonify(market.set_target(ticker, body["target"]))


# ---------- forecasts ----------





@app.post("/api/forecast/mortgage")
def forecast_mortgage():
    return jsonify(fc.mortgage_overpayment(request.get_json(force=True)))


# ---------- wealth ----------

@app.get("/api/wealth/summary")
def wealth_summary():
    return jsonify(planner.wealth_summary())


@app.post("/api/wealth/items")
def wealth_item_add():
    return jsonify({"id": planner.add_wealth_item(request.get_json(force=True))}), 201


@app.put("/api/wealth/items/<item_id>")
def wealth_item_update(item_id):
    planner.update_wealth_item(item_id, request.get_json(force=True))
    return jsonify({"ok": True})


@app.delete("/api/wealth/items/<item_id>")
def wealth_item_delete(item_id):
    planner.delete_wealth_item(item_id)
    return jsonify({"ok": True})


@app.post("/api/wealth/items/<item_id>/values")
def wealth_value_add(item_id):
    planner.add_wealth_value(item_id, request.get_json(force=True))
    return jsonify({"ok": True}), 201


@app.get("/api/wealth/items/<item_id>/history")
def wealth_history(item_id):
    return jsonify(planner.wealth_item_history(item_id))


# ---------- goals ----------

@app.get("/api/goals")
def goals_list():
    return jsonify(planner.list_goals())


@app.post("/api/goals")
def goals_add():
    return jsonify({"id": planner.add_goal(request.get_json(force=True))}), 201


@app.put("/api/goals/<goal_id>")
def goals_update(goal_id):
    planner.update_goal(goal_id, request.get_json(force=True))
    return jsonify({"ok": True})


@app.delete("/api/goals/<goal_id>")
def goals_delete(goal_id):
    planner.delete_goal(goal_id)
    return jsonify({"ok": True})


# ---------- job offers ----------

@app.get("/api/offers")
def offers_list():
    return jsonify(planner.list_offers())


@app.post("/api/offers")
def offers_add():
    return jsonify({"id": planner.add_offer(request.get_json(force=True))}), 201


@app.put("/api/offers/<offer_id>")
def offers_update(offer_id):
    planner.update_offer(offer_id, request.get_json(force=True))
    return jsonify({"ok": True})


@app.delete("/api/offers/<offer_id>")
def offers_delete(offer_id):
    planner.delete_offer(offer_id)
    return jsonify({"ok": True})


# ---------- debts ----------

@app.get("/api/debts")
def debts_list():
    return jsonify(planner.list_debts())


@app.post("/api/debts")
def debts_add():
    return jsonify({"id": planner.add_debt(request.get_json(force=True))}), 201


@app.put("/api/debts/<debt_id>")
def debts_update(debt_id):
    planner.update_debt(debt_id, request.get_json(force=True))
    return jsonify({"ok": True})


@app.post("/api/debts/<debt_id>/overpay")
def debts_overpay(debt_id):
    planner.overpay_debt(debt_id, request.get_json(force=True))
    return jsonify({"ok": True})


@app.delete("/api/debts/<debt_id>")
def debts_delete(debt_id):
    planner.delete_debt(debt_id)
    return jsonify({"ok": True})


# ---------- recommendation ----------

@app.get("/api/cashflow")
def cashflow():
    return jsonify(planner.cashflow(int(request.args.get("months", 15))))


@app.get("/api/stress-test")
def stress_test():
    """Deterministic fire drill: equity −25%, rates +2pp, income stops —
    plus a Guyton-Klinger withdrawal policy with guardrails."""
    import stress
    return jsonify(stress.run())


@app.get("/api/fire-projection")
def fire_projection():
    return jsonify(planner.fire_projection())


@app.get("/api/github-activity")
def github_activity():
    return jsonify(planner.github_activity(int(request.args.get("days", 90))))


@app.get("/api/taxes")
def taxes():
    return jsonify(planner.tax_summary())


@app.get("/api/allocation")
def allocation():
    return jsonify(planner.allocation())


@app.get("/api/health")
def health():
    try:  # scheduled tasks piggyback on health: run at first app-open past due
        import schedules
        schedules.run_due()
    except Exception:
        pass
    return jsonify(planner.health())


@app.get("/api/schedules")
def schedules_get():
    import schedules
    return jsonify(schedules.get_schedules())


@app.post("/api/schedules/<task_id>")
def schedules_set(task_id):
    import schedules
    return jsonify(schedules.set_schedule(task_id, request.get_json(force=True)))


@app.get("/api/data-inventory")
def data_inventory():
    return jsonify(planner.data_inventory())


@app.get("/api/git")
def git_status():
    return jsonify(planner.git_status(do_fetch=request.args.get("fetch", "1") != "0"))


@app.get("/api/security-scan")
def security_scan():
    return jsonify(planner.security_scan())


@app.get("/api/app-config")
def app_config_get():
    cfg = planner.get_app_config()
    rows = eb._rows("select count(*) c from wealth_items")
    cfg["has_data"] = bool(rows and rows[0]["c"] > 0)
    return jsonify(cfg)


@app.post("/api/app-config")
def app_config_save():
    return jsonify(planner.save_app_config(request.get_json(force=True)))


@app.post("/api/data/wipe")
def data_wipe():
    """Fresh start: delete the local database (incl. settings) and re-init —
    the wizard runs again. Requires an explicit confirm flag."""
    if not request.get_json(force=True).get("confirm"):
        return jsonify({"ok": False, "error": "confirm required"}), 400
    import os as _os
    import db as _db
    root = _db.get_finance_dir()
    for f in ("finance.db", "finance.db-wal", "finance.db-shm"):
        try:
            _os.remove(str(root / f))
        except FileNotFoundError:
            pass
    _db.init_db()
    planner.ensure_tables()
    return jsonify({"ok": True})


@app.post("/api/sample-data")
def sample_data():
    """Load the demo persona into a fresh DB (wizard 'just show me around')."""
    import subprocess
    import sys as _sys
    seed = Path(__file__).resolve().parent.parent / "seed.py"
    r = subprocess.run([_sys.executable, str(seed)], capture_output=True, text=True, timeout=60)
    ok = r.returncode == 0
    return jsonify({"ok": ok, "output": (r.stdout + r.stderr)[-400:]}), (200 if ok else 500)


@app.get("/api/llm/status")
def llm_status():
    import llm_local
    return jsonify(llm_local.status())


@app.post("/api/llm/chat")
def llm_chat():
    import llm_local
    b = request.get_json(force=True)
    out = llm_local.chat(b.get("prompt", ""), system=b.get("system"))
    return jsonify({"ok": out is not None, "text": out})


@app.get("/api/llm/config")
def llm_config():
    import llm_local, llm_cloud
    mode = planner.get_setting("ai_mode") or "local"
    return jsonify({"ai_mode": mode, "local": llm_local.status(), "cloud": llm_cloud.status()})


@app.post("/api/llm/config")
def llm_config_save():
    mode = request.get_json(force=True).get("ai_mode", "local")
    if mode not in ("local", "both"):
        mode = "local"
    planner.set_settings({"ai_mode": mode})
    return jsonify({"ai_mode": mode})


@app.post("/api/llm/ask")
def llm_ask():
    """Ask a question per the AI mode: 'local' = local model only;
    'both' = local AND Claude (for comparison — best result from the pair)."""
    b = request.get_json(force=True)
    return jsonify(_ai_answer(b.get("prompt", ""), system=b.get("system"),
                              use_rag=b.get("rag", True)))


def _ai_answer(prompt, system=None, use_rag=True):
    """The app's shared AI pipeline: RAG grounding → local model → (both mode:
    cloud + verdict synthesis) → prompt log. Used by /api/llm/ask AND internal
    analyses (e.g. the AI second opinion on recommendations) — the Control
    Center mode governs all of it."""
    import llm_local, llm_cloud, finance_prompt, rag, llm_log
    system = system or finance_prompt.SYSTEM
    mode = planner.get_setting("ai_mode") or "local"
    if use_rag and planner.get_setting("rag_dirty") == "1":
        try:
            rag.reindex()
            planner.set_settings({"rag_dirty": ""})
        except Exception:
            pass
    ctx = rag.context_for(prompt) if use_rag else ""
    ask = (ctx + "\n\nQuestion: " + prompt) if ctx else prompt
    out = {"mode": mode, "rag_used": bool(ctx)}
    # Local model gets a read-only SQL tool: it can CHECK real numbers in the
    # database instead of guessing from RAG excerpts. Falls back to plain chat
    # when the server has no tool support (or the tool run yields nothing).
    lt, via_tools = None, False
    try:
        import db_tools
        sch = db_tools.schema_summary()
        if sch:
            tools = [{"type": "function", "function": {
                "name": "query_db",
                "description": "Run ONE read-only SQL SELECT against the user's "
                               "local finance database (SQLite) to check real "
                               "numbers before answering. Tables: " + sch,
                "parameters": {"type": "object", "required": ["sql"],
                               "properties": {"sql": {"type": "string",
                                   "description": "a single SELECT statement"}}}}}]
            lt = llm_local.chat_with_tools(ask, tools,
                                           {"query_db": db_tools.run_select},
                                           system=system)
            via_tools = lt is not None
    except Exception:
        lt = None
    if lt is None:
        lt = llm_local.chat(ask, system=system, think=True)
    out["local"] = {"ok": lt is not None, "text": lt, "tools": via_tools,
                    "label": llm_local.status().get("model", "local")}
    if mode == "both":
        ct = llm_cloud.chat(ask, system=system)
        out["cloud"] = {"ok": ct is not None, "text": ct, "label": llm_cloud.status().get("model", "Claude")}
        # Synthesis: reconcile the two answers into ONE verdict (best of both).
        if lt and ct:
            synth = ("Two analysts answered the same personal-finance question. "
                     "Reconcile them into ONE recommendation: where they agree, where "
                     "they differ, then a single bottom-line sentence.\n\n"
                     f"QUESTION:\n{prompt}\n\n[LOCAL]:\n{lt}\n\n[CLAUDE]:\n{ct}")
            sy = llm_cloud.chat(synth, system=system)
            by = "cloud"
            if not sy:
                sy = llm_local.chat(synth, system=system)
                by = "local"
            if sy:
                out["synthesis"] = {"ok": True, "text": sy, "by": by}
    # best single answer (synthesis > cloud > local)
    out["best"] = (out.get("synthesis") or {}).get("text") or \
                  (out.get("cloud") or {}).get("text") or out["local"]["text"]
    llm_log.record(prompt, out)
    return out


@app.get("/api/recommendation/ai")
def recommendation_ai_last():
    import json as _json
    raw = planner.get_setting("ai_recs_opinion")
    return jsonify(_json.loads(raw) if raw else {})


@app.post("/api/recommendation/ai")
def recommendation_ai():
    """AI second opinion on the app's recommendations — the rule engine computes
    them, the AI (local / local+Claude per the Control mode) assesses them,
    suggests changes and points out what's missing. Result is stored."""
    import json as _json
    from datetime import datetime
    rec = planner.recommendation()
    items = "\n".join("- " + (r.get("text") or "") for r in (rec.get("items") or [])[:10])
    facts = _json.dumps(rec.get("facts") or {}, ensure_ascii=False)
    prompt = ("My finance app's rule engine produced the recommendations below. "
              "Assess them: which do you agree with and why, what would you change, "
              "and which ONE recommendation is missing. Be concise.\n\n"
              f"RECOMMENDATIONS:\n{items}\n\nFACTS: {facts}")
    out = _ai_answer(prompt)
    stored = {"at": datetime.now().isoformat(timespec="minutes"), "mode": out["mode"],
              "rag_used": out["rag_used"], "text": out.get("best"),
              "by": "synthesis" if out.get("synthesis") else ("cloud" if (out.get("cloud") or {}).get("ok") else ("local (cloud did not answer)" if out["mode"] == "both" else "local"))}
    if stored["text"]:
        planner.set_settings({"ai_recs_opinion": _json.dumps(stored, ensure_ascii=False)})
    return jsonify(stored if stored["text"] else {"error": "AI offline — start a local model (Control → AI mode)"})


@app.get("/api/llm/log")
def llm_log_view():
    import llm_log
    return jsonify({"stats": llm_log.stats(), "recent": llm_log.recent(int(request.args.get("n", 25)))})


@app.post("/api/experience")
def experience_learn():
    """Distill a good Q+A into a transferable lesson and store it (user-triggered
    'learn from this'). The lesson then grounds future similar questions."""
    import experience
    b = request.get_json(force=True)
    lesson = experience.learn(b.get("question", ""), b.get("answer", ""))
    return jsonify({"ok": True, "lesson": lesson} if lesson else
                   {"ok": False, "error": "no transferable lesson found (or AI offline)"})


@app.get("/api/experiences")
def experiences_list():
    import experience
    return jsonify({"experiences": experience.listing()})


@app.delete("/api/experiences/<eid>")
def experience_delete(eid):
    import experience
    experience.delete(eid)
    return jsonify({"ok": True})


@app.get("/api/rag/status")
def rag_status():
    import rag
    return jsonify(rag.status())


@app.post("/api/rag/reindex")
def rag_reindex():
    import rag
    return jsonify({"chunks": rag.reindex()})


@app.get("/api/backup/status")
def backup_status():
    import data_backup as backup
    return jsonify(backup.status())


@app.post("/api/backup/config")
def backup_config():
    import data_backup as backup
    return jsonify(backup.set_destination(request.get_json(force=True).get("dir", "")))


@app.post("/api/backup/run")
def backup_run():
    import data_backup as backup
    return jsonify(backup.create_backup())


@app.post("/api/backup/restore")
def backup_restore():
    import data_backup as backup
    return jsonify(backup.restore(request.get_json(force=True).get("file", "")))


@app.post("/api/backup/auto")
def backup_auto():
    import data_backup as backup
    return jsonify(backup.set_auto(bool(request.get_json(force=True).get("enabled"))))


@app.get("/api/security-review")
def security_review_last():
    import json as _json
    raw = planner.get_setting("last_security_review")
    try:
        return jsonify(_json.loads(raw) if raw else {})
    except ValueError:
        return jsonify({})


@app.post("/api/security-review/run")
def security_review_run():
    import json as _json
    import security_review as _sr
    report = _sr.run(full=True)
    planner.set_settings({"last_security_review": _json.dumps(report, ensure_ascii=False)})
    return jsonify(report)


@app.get("/api/market-barometer")
def barometer_list():
    return jsonify(planner.list_barometer())


@app.post("/api/market-barometer")
def barometer_add():
    return jsonify({"id": planner.add_barometer_point(request.get_json(force=True))}), 201


@app.delete("/api/market-barometer/<bid>")
def barometer_delete(bid):
    planner.delete_barometer_point(bid)
    return jsonify({"ok": True})


@app.get("/api/reminders")
def reminders_list():
    return jsonify(planner.list_reminders())


@app.post("/api/reminders")
def reminders_add():
    return jsonify({"id": planner.add_reminder(request.get_json(force=True))}), 201


@app.put("/api/reminders/<rid>")
def reminders_update(rid):
    planner.update_reminder(rid, request.get_json(force=True))
    return jsonify({"ok": True})


@app.delete("/api/reminders/<rid>")
def reminders_delete(rid):
    planner.delete_reminder(rid)
    return jsonify({"ok": True})


@app.get("/api/recommendation")
def recommendation():
    return jsonify(planner.recommendation())


@app.get("/api/goal-scenarios")
def goal_scenarios():
    return jsonify(planner.goal_scenarios() or {})


@app.get("/api/recommendation/xtb")
def recommendation_xtb():
    return jsonify(planner.xtb_recommendation() or {})


# ---------- actions ----------

@app.get("/api/actions")
def actions_list():
    return jsonify(planner.list_actions())


@app.post("/api/actions")
def actions_add():
    return jsonify({"id": planner.add_action(request.get_json(force=True))}), 201


@app.put("/api/actions/<action_id>")
def actions_update(action_id):
    planner.update_action(action_id, request.get_json(force=True))
    return jsonify({"ok": True})


@app.delete("/api/actions/<action_id>")
def actions_delete(action_id):
    planner.delete_action(action_id)
    return jsonify({"ok": True})


# ---------- side business ----------

@app.get("/api/business")
def biz_summary():
    return jsonify(planner.biz_summary())


@app.get("/api/business/marketing")
def biz_marketing():
    return jsonify(planner.business_marketing())


@app.post("/api/business")
def biz_add():
    return jsonify({"id": planner.add_biz_entry(request.get_json(force=True))}), 201


@app.delete("/api/business/<entry_id>")
def biz_delete(entry_id):
    planner.delete_biz_entry(entry_id)
    return jsonify({"ok": True})


# ---------- audit ----------

@app.get("/api/audit")
def audit():
    return jsonify(planner.audit_log(
        entity=request.args.get("entity"),
        limit=int(request.args.get("limit", 500))))


# ---------- settings ----------

@app.get("/api/settings")
def settings_get():
    return jsonify(planner.settings())


@app.put("/api/settings")
def settings_put():
    return jsonify(planner.set_settings(request.get_json(force=True)))


# ---------- RSU ----------

@app.get("/api/rsu")
def rsu_get():
    return jsonify(market.get_rsu())


@app.put("/api/rsu")
def rsu_put():
    return jsonify(market.update_rsu(request.get_json(force=True)))


@app.get("/api/rsu/advanced")
def rsu_advanced():
    return jsonify(market.rsu_advanced())


@app.get("/api/rsu/accuracy")
def rsu_accuracy():
    return jsonify(market.rsu_accuracy())


@app.post("/api/rsu/snapshot")
def rsu_snapshot():
    # hittable by a daily automation so predictions accrue without opening the tab
    return jsonify(market.rsu_accuracy())


@app.get("/api/rsu/analysis")
def rsu_analysis():
    return _analysis("rsu_vest_analysis")


@app.get("/api/analysis/<name>")
def analysis(name):
    return _analysis("analysis_" + name)


def _analysis(key):
    import json as _json
    raw = planner.get_setting(key)
    try:
        return jsonify(_json.loads(raw) if raw else {})
    except ValueError:
        return jsonify({})


def main():
    print(f"[budget-app] data dir: {CFG['finance_dir']}")
    print(f"[budget-app] http://127.0.0.1:{CFG['port']}")
    app.run(host="127.0.0.1", port=CFG["port"], debug=False)


if __name__ == "__main__":
    main()
