"""Endpoint / integration tests against a seeded throwaway DB."""
import sqlite3
from pathlib import Path


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert "summary" in r.get_json()


def test_dashboard_summary(client):
    d = client.get("/api/dashboard/summary").get_json()
    assert "net_worth" in d and "cash_total" in d


def test_goals_crud(client):
    before = len(client.get("/api/goals").get_json())
    gid = client.post("/api/goals", json={"name": "Test goal", "target_amount": 12345}).get_json()["id"]
    goals = client.get("/api/goals").get_json()
    assert len(goals) == before + 1
    assert any(g["id"] == gid and g["name"] == "Test goal" for g in goals)
    assert client.delete(f"/api/goals/{gid}").status_code == 200
    assert len(client.get("/api/goals").get_json()) == before


def test_business_endpoint(client):
    # regression: /api/business exists after the firma->business rename
    d = client.get("/api/business").get_json()
    assert "months" in d and "categories" in d


def test_analysis_property_route(client):
    # regression: /api/analysis/property replaces /api/analysis/property_location
    r = client.get("/api/analysis/property")
    assert r.status_code == 200  # empty {} is fine; must not 404


def test_fire_projection_uses_property_key(client):
    d = client.get("/api/fire-projection").get_json()
    assert "property" in d          # the new key
    assert ("it" + "aly") not in d  # the old key is gone (split literal: history-rewrite-proof)


def test_cashflow_uses_loan_keys(client):
    d = client.get("/api/cashflow").get_json()
    assert "loan_paid_month" in d   # renamed from 'loan_paid_month'


def test_llm_config_defaults_local(client):
    d = client.get("/api/llm/config").get_json()
    assert d["ai_mode"] == "local"
    assert "local" in d and "cloud" in d


def test_llm_config_toggle(client):
    assert client.post("/api/llm/config", json={"ai_mode": "both"}).get_json()["ai_mode"] == "both"
    # invalid values fall back to local
    assert client.post("/api/llm/config", json={"ai_mode": "bogus"}).get_json()["ai_mode"] == "local"


def test_llm_ask_shape(client):
    d = client.post("/api/llm/ask", json={"prompt": "hello"}).get_json()
    assert "local" in d and "rag_used" in d and "mode" in d
    assert set(("ok", "text", "label")) <= set(d["local"].keys())


def test_rag_reindex_and_status(client):
    n = client.post("/api/rag/reindex").get_json()["chunks"]
    assert n > 0
    assert client.get("/api/rag/status").get_json()["chunks"] == n


def test_all_get_endpoints_no_server_error(client):
    # exercise every parameter-free GET route; none may 500 (offline is fine)
    import app as flask_app
    rules = [r for r in flask_app.app.url_map.iter_rules()
             if "GET" in r.methods and "<" not in r.rule and not r.rule.startswith("/static")]
    assert len(rules) > 10
    for r in rules:
        assert client.get(r.rule).status_code != 500, r.rule


def test_mortgage_overpayment_endpoint(client):
    r = client.post("/api/forecast/mortgage", json={
        "balance": 300000, "monthly_payment": 3500, "months_left": 240, "overpayment": 50000})
    assert r.status_code == 200
    assert isinstance(r.get_json(), dict)


def test_app_config_accepts_dict_and_list_modules(client):
    # the wizard sends {id: bool}; API consumers naturally send a list of ids —
    # both must work (regression: the list shape used to 500)
    r1 = client.post("/api/app-config", json={"modules": {"debts": True, "taxes": False}})
    assert r1.status_code == 200 and r1.get_json()["modules"]["taxes"] is False
    r2 = client.post("/api/app-config", json={"modules": ["debts", "markets"], "wizard_completed": True})
    assert r2.status_code == 200
    d = r2.get_json()
    assert d["modules"]["debts"] is True and d["modules"]["taxes"] is False
    assert d["wizard_completed"] is True
    # restore defaults so other tests see all views
    client.post("/api/app-config", json={"modules": {m["id"]: True for m in d["registry"]}})


def test_wealth_item_crud(client):
    iid = client.post("/api/wealth/items",
                      json={"name": "Test asset", "kind": "investment", "value": 1000}).get_json()["id"]
    client.post(f"/api/wealth/items/{iid}/values", json={"date": "2026-01-01", "value": 1100})
    hist = client.get(f"/api/wealth/items/{iid}/history").get_json()
    assert isinstance(hist, (list, dict))
    assert client.delete(f"/api/wealth/items/{iid}").status_code == 200


def test_backup_roundtrip(client, tmp_path):
    st = client.get("/api/backup/status").get_json()
    assert "destinations" in st
    client.post("/api/backup/config", json={"dir": str(tmp_path)})
    r = client.post("/api/backup/run").get_json()
    assert r["ok"] is True
    snap = Path(r["dir"]) / r["file"]
    assert snap.exists()
    # the snapshot is a valid SQLite database with our seeded data
    con = sqlite3.connect(str(snap))
    assert con.execute("select count(*) from goals").fetchone()[0] >= 1
    con.close()


def test_recommendation_ai_endpoint(client):
    # works with AI offline too: returns either a stored opinion or a clear error
    r = client.post("/api/recommendation/ai")
    assert r.status_code == 200
    d = r.get_json()
    assert ("text" in d) or ("error" in d)
    assert client.get("/api/recommendation/ai").status_code == 200


# ---------- schedules ----------

def test_schedules_get_and_set_roundtrip(client):
    d = client.get("/api/schedules").get_json()
    assert d["tasks"] and all(k in d["tasks"][0] for k in ("id", "freq", "day", "hour"))
    tid = d["tasks"][0]["id"]
    r = client.post(f"/api/schedules/{tid}", json={"freq": "weekly", "day": 4, "hour": 18}).get_json()
    assert r["ok"] and r["freq"] == "weekly" and r["day"] == 4 and r["hour"] == 18
    d2 = client.get("/api/schedules").get_json()
    t = next(t for t in d2["tasks"] if t["id"] == tid)
    assert (t["freq"], t["day"], t["hour"]) == ("weekly", 4, 18)
    assert client.post(f"/api/schedules/{tid}", json={"freq": "hourly"}).get_json()["ok"] is False
    assert client.post("/api/schedules/nope", json={"freq": "daily"}).get_json()["ok"] is False
    client.post(f"/api/schedules/{tid}", json={"freq": "daily", "day": 0, "hour": 10})


def test_schedules_is_due_logic():
    from datetime import datetime
    import schedules as sc
    mon10 = datetime(2026, 7, 13, 10, 0)   # Monday
    assert sc._is_due({"freq": "daily", "day": 0, "hour": 9}, None, mon10) is True
    assert sc._is_due({"freq": "daily", "day": 0, "hour": 11}, None, mon10) is False
    assert sc._is_due({"freq": "daily", "day": 0, "hour": 9}, "2026-07-13", mon10) is False
    assert sc._is_due({"freq": "weekly", "day": 0, "hour": 9}, None, mon10) is True
    assert sc._is_due({"freq": "weekly", "day": 2, "hour": 9}, None, mon10) is False
    assert sc._is_due({"freq": "weekly", "day": 0, "hour": 9}, "2026-W29", mon10) is False
    assert sc._is_due({"freq": "monthly", "day": 13, "hour": 9}, None, mon10) is True
    assert sc._is_due({"freq": "monthly", "day": 20, "hour": 9}, None, mon10) is False


def test_schedules_run_due_records_period(client, monkeypatch):
    import schedules as sc
    import planner
    ran = {"n": 0}
    task = next(t for t in sc.REGISTRY if t["kind"] == "app")
    monkeypatch.setitem(task, "runner", lambda: ran.__setitem__("n", ran["n"] + 1) or True)
    planner.set_settings({f"sched_last.{task['id']}": ""})
    from datetime import datetime
    out = sc.run_due(datetime(2026, 7, 13, 23, 0))
    assert task["id"] in out and ran["n"] == 1
    out2 = sc.run_due(datetime(2026, 7, 13, 23, 30))
    assert task["id"] not in out2 and ran["n"] == 1   # once per period


def test_watchlist_without_supabase_is_graceful(client):
    # a fresh user with no Supabase must get a friendly error, not a 500
    r = client.post("/api/watchlist/NVDA")
    assert r.status_code == 200
    d = r.get_json()
    assert d.get("ok") is False and "Supabase" in (d.get("error") or "")


def test_data_wipe_requires_confirm_and_resets(client):
    assert client.post("/api/data/wipe", json={}).status_code == 400
    r = client.post("/api/data/wipe", json={"confirm": True}).get_json()
    assert r["ok"] is True
    cfg = client.get("/api/app-config").get_json()
    assert cfg["has_data"] is False and cfg["wizard_completed"] is False


def test_stress_test_endpoint(client):
    d = client.get("/api/stress-test").get_json()
    assert len(d["scenarios"]) == 3
    assert "policy" in d and "verdict" in d["policy"]
