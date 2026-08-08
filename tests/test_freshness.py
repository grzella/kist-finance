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


def test_debt_pace_contract(client):
    """Every debt carries pace: model vs actual balance + overpayment pace."""
    for d in client.get("/api/debts").get_json()["debts"]:
        p = d["pace"]
        assert "points" in p
        if not p.get("insufficient"):
            assert {"ahead_pln", "pace_monthly", "n_months"} <= set(p)
            for pt in p["points"]:
                assert {"month", "actual", "model"} <= set(pt)


def test_allocation_leverage_contract(client):
    """Allocation carries leverage: debt/assets, LTV and the debt-decline trend."""
    lv = client.get("/api/allocation").get_json()["leverage"]
    assert {"debt_total", "assets_total", "debt_to_assets_pct", "ltv_pct", "trend"} <= set(lv)
    for t in lv["trend"]:
        assert {"month", "debt", "assets", "pct"} <= set(t)


def test_cushion_alert_reacts_to_expenses(client):
    """Cushion alert: present with inflated expenses, gone with negligible ones.
    Creates an explicit cash item — the seed may have none (then cash=0 and
    the alert rightly stays on forever)."""
    client.post("/api/wealth/items", json={
        "name": "Cash buffer (test)", "kind": "cushion", "currency": "PLN"})
    items = client.get("/api/wealth/summary").get_json()["items"]
    it = next(i for i in items if i["name"] == "Cash buffer (test)")
    client.post(f"/api/wealth/items/{it['id']}/values", json={"value": 1000000})
    client.put("/api/settings", json={"monthly_expenses": "999999999"})
    kinds = [r.get("kind") for r in client.get("/api/reminders").get_json()["reminders"]]
    assert "Cushion" in kinds
    client.put("/api/settings", json={"monthly_expenses": "1"})
    kinds = [r.get("kind") for r in client.get("/api/reminders").get_json()["reminders"]]
    assert "Cushion" not in kinds
