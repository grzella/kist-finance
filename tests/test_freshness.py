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
        assert e["action"]["type"] in ("wealth_value", "link")
    assert d["total_minutes"] == sum(e.get("minutes", 1) for e in d["due"])


def test_freshness_skips_event_driven_items(client):
    d = client.get("/api/freshness").get_json()
    labels = [e["label"].lower() for e in d["due"] + d["ok"]]
    assert not any("kaucj" in l or "deposit" in l for l in labels)
