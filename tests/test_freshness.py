"""Contract of /api/freshness: response shape + cadence rules.

The engine derives 'what to refresh' from data timestamps — the test guards
the contract (fields, statuses) and the exclusion rules (income items and
deposits never nag monthly), not specific seed rows.
"""


def test_freshness_contract(client):
    d = client.get("/api/freshness").get_json()
    assert set(d) >= {"month", "due", "ok", "complete", "total_minutes"}
    assert d["complete"] == (len(d["due"]) == 0)
    for e in d["due"] + d["ok"]:
        assert set(e) >= {"key", "label", "group", "cadence", "status", "action"}
        assert e["status"] in ("due", "ok")
        assert e["action"]["type"] in ("wealth_value", "goal_amount", "debt_balance", "rsu_shares", "biz_month")
    assert d["total_minutes"] == sum(e.get("minutes", 1) for e in d["due"])


def test_freshness_skips_event_driven_items(client):
    d = client.get("/api/freshness").get_json()
    # wealth items only — a goal "saving for a deposit" is a different thing
    labels = [e["label"].lower() for e in d["due"] + d["ok"]
              if e["key"].startswith("wealth:")]
    assert not any("kaucj" in l or "deposit" in l for l in labels)


def test_ticker_item_valued_live_and_skipped_in_rhythm(client):
    """A ticker-linked item is valued from the cached quote (units × close × FX),
    not from manual entries — and never nags in the monthly rhythm."""
    import json
    r = client.post("/api/wealth/items", json={
        "name": "Test ETF (auto)", "kind": "investment", "currency": "PLN"})
    assert r.status_code in (200, 201)
    items = client.get("/api/wealth/summary").get_json()["items"]
    it = next(i for i in items if i["name"] == "Test ETF (auto)")
    # seed a quote into the cache (test DB), then link the ticker
    import market
    with __import__("db").get_conn() as con:
        con.execute("insert or replace into market_prices_cache "
                    "(ticker,date,close,currency) values ('TSTX','2099-01-01',10.0,'PLN')")
        con.commit()
    client.put(f"/api/wealth/items/{it['id']}", json={"ticker": "TSTX", "units": 5})
    it2 = next(i for i in client.get("/api/wealth/summary").get_json()["items"]
               if i["id"] == it["id"])
    assert it2.get("live") and it2["latest_value"] == 50.0
    fresh = client.get("/api/freshness").get_json()
    assert not any(e["key"] == "wealth:" + it["id"] for e in fresh["due"])
