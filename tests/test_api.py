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
    assert "property" in d          # renamed from 'property'
    assert "property" not in d


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
