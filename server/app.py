"""Home Budget — local Flask app. Personal data never leaves this machine."""
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


@app.after_request
def _no_cache(resp):
    # local single-user app in active development — always serve fresh JS/CSS/HTML
    p = request.path
    if p == "/" or p.endswith((".js", ".css", ".html")):
        resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
    return resp


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
            mine = sorted((i for i in items if i.get("payer") == "ja"),
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


@app.get("/api/fx-analysis")
def fx_analysis():
    return jsonify(market.fx_analysis())


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
    return jsonify(planner.health())


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
    import llm_local, llm_cloud, finance_prompt
    b = request.get_json(force=True)
    prompt = b.get("prompt", "")
    system = b.get("system") or finance_prompt.SYSTEM
    mode = planner.get_setting("ai_mode") or "local"
    out = {"mode": mode}
    lt = llm_local.chat(prompt, system=system)
    out["local"] = {"ok": lt is not None, "text": lt, "label": llm_local.status().get("model", "local")}
    if mode == "both":
        ct = llm_cloud.chat(prompt, system=system)
        out["cloud"] = {"ok": ct is not None, "text": ct, "label": llm_cloud.status().get("model", "Claude")}
    return jsonify(out)


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
