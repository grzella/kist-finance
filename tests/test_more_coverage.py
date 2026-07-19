"""Deeper coverage: AI pipeline with mocked engines, LLM clients over a fake
HTTP layer, market analytics on seeded cache, and the full security review."""
import io
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))


class _FakeResp(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _fake_urlopen_factory(payload):
    def fake(req, timeout=None):
        return _FakeResp(json.dumps(payload).encode())
    return fake


# ---------- AI pipeline (both mode + synthesis) with mocked engines ----------

def test_ai_pipeline_both_mode_synthesis(client, monkeypatch):
    import llm_local
    import llm_cloud
    monkeypatch.setattr(llm_local, "chat", lambda *a, **k: "local answer")
    monkeypatch.setattr(llm_local, "status", lambda: {"online": True, "model": "fake-local"})
    monkeypatch.setattr(llm_cloud, "chat", lambda *a, **k: "cloud answer")
    monkeypatch.setattr(llm_cloud, "status", lambda: {"online": True, "model": "fake-cloud"})
    client.post("/api/llm/config", json={"ai_mode": "both"})
    try:
        d = client.post("/api/llm/ask", json={"prompt": "should I overpay the mortgage?"}).get_json()
        assert d["local"]["ok"] and d["cloud"]["ok"]
        assert d["synthesis"]["ok"] and d["best"] == d["synthesis"]["text"]
    finally:
        client.post("/api/llm/config", json={"ai_mode": "local"})


def test_recommendation_ai_stores_opinion(client, monkeypatch):
    import llm_local
    monkeypatch.setattr(llm_local, "chat", lambda *a, **k: "solid recommendations; add an emergency-fund one")
    monkeypatch.setattr(llm_local, "status", lambda: {"online": True, "model": "fake-local"})
    d = client.post("/api/recommendation/ai").get_json()
    assert d.get("text") and d.get("at")
    again = client.get("/api/recommendation/ai").get_json()
    assert again["text"] == d["text"]


# ---------- LLM clients over a fake HTTP layer ----------

def test_llm_local_chat_and_embed_over_fake_http(monkeypatch):
    import llm_local
    monkeypatch.setattr(llm_local.urllib.request, "urlopen", _fake_urlopen_factory(
        {"choices": [{"message": {"content": "Groceries"}}]}))
    assert llm_local.chat("categorize") == "Groceries"
    monkeypatch.setattr(llm_local.urllib.request, "urlopen", _fake_urlopen_factory(
        {"data": [{"embedding": [0.6, 0.8]}]}))
    assert llm_local.embed("pension") == [0.6, 0.8]


def test_llm_local_categorize_uses_schema(monkeypatch):
    import llm_local
    monkeypatch.setattr(llm_local.urllib.request, "urlopen", _fake_urlopen_factory(
        {"choices": [{"message": {"content": '{"category": "Groceries"}'}}]}))
    assert llm_local.categorize_transaction("STORE 42", 100, ["Groceries", "Transport"]) == "Groceries"


def test_llm_cloud_chat_and_refusal(monkeypatch):
    import llm_cloud
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(llm_cloud.urllib.request, "urlopen", _fake_urlopen_factory(
        {"stop_reason": "end_turn", "content": [{"type": "text", "text": "overpay"}]}))
    assert llm_cloud.chat("q") == "overpay"
    monkeypatch.setattr(llm_cloud.urllib.request, "urlopen", _fake_urlopen_factory(
        {"stop_reason": "refusal", "content": []}))
    assert llm_cloud.chat("q") is None
    assert llm_cloud.status()["online"] is True


# ---------- market analytics on a seeded local cache ----------

def _seed_prices(ticker, n=120):
    import db
    with db.get_conn() as conn:
        conn.execute("""create table if not exists market_prices_cache (
            ticker text not null, date text not null, close real not null,
            currency text default 'USD', primary key (ticker, date))""")
        from datetime import date, timedelta
        d0 = date.today() - timedelta(days=n)
        for i in range(n):
            close = 100 * math.exp(0.0005 * i + 0.01 * math.sin(i / 3))
            conn.execute("insert or replace into market_prices_cache values (?,?,?,?)",
                         (ticker, (d0 + timedelta(days=i)).isoformat(), close, "USD"))


def test_market_prices_analytics_and_bands(client):
    import market
    _seed_prices("TST")
    px = market.prices("TST", days=90)
    assert px and px[-1]["close"] > 0
    a = market.analytics("TST")
    assert a.get("last_close") and a.get("sma50") is not None
    b = market.ticker_bands("TST")
    assert b and (b.get("horizons") or b.get("error") is None)


def test_market_endpoints_over_http(client):
    _seed_prices("TST2")
    assert client.get("/api/market/prices/TST2?days=30").status_code == 200
    assert client.get("/api/market/analytics/TST2").status_code == 200
    assert client.get("/api/forecast/bands/TST2").status_code == 200


# ---------- security review, full pass (functional checks included) ----------

def test_security_review_full_pass(client):
    import security_review as sr
    rep = sr.run(full=True)
    assert rep["verdict"] in ("ok", "warn", "error")
    areas = {a["area"] for a in rep["areas"]}
    assert any("FUNCTIONAL" in a or "FUNKCJONALNE" in a for a in areas)


# ---------- risk radar ----------

def test_risk_radar_scoring_on_seeded_prices(client):
    import db
    import risk_radar
    from datetime import date, timedelta
    y, t = (date.today() - timedelta(days=1)).isoformat(), date.today().isoformat()
    with db.get_conn() as conn:
        rows = [  # VIX hot (32, +14%), gold elevated (+1.4%), oil calm, EURUSD hot (-1.5%)
            ("^VIX", y, 28.0), ("^VIX", t, 32.0),
            ("GC=F", y, 2400.0), ("GC=F", t, 2433.6),
            ("CL=F", y, 80.0), ("CL=F", t, 80.8),
            ("EURUSD=X", y, 1.10), ("EURUSD=X", t, 1.0835),
        ]
        for r in rows:
            conn.execute("insert or replace into market_prices_cache values (?,?,?,?)",
                         (*r, "USD"))
    d = risk_radar.compute()
    by = {c["ticker"]: c for c in d["components"]}
    assert by["^VIX"]["score"] == 2
    assert by["GC=F"]["score"] == 1
    assert by["CL=F"]["score"] == 0
    assert by["EURUSD=X"]["score"] == 2
    assert d["score"] == 5 and "🔴" in d["state"]
    assert not d["missing"]


def test_risk_radar_endpoint_and_snapshot(client, monkeypatch):
    import llm_local
    monkeypatch.setattr(llm_local, "chat", lambda *a, **k: "elevated risk, stay the course")
    r = client.get("/api/risk-radar").get_json()
    assert "score" in r and "components" in r and "history" in r
    s1 = client.post("/api/risk-radar/snapshot").get_json()
    assert s1["ok"] is True
    s2 = client.post("/api/risk-radar/snapshot").get_json()   # idempotent per day
    assert s2["ok"] is True
    h = client.get("/api/risk-radar").get_json()["history"]
    assert len(h) >= 1 and h[-1]["comment"]
