"""Ported from the private instance (batch tests)."""


def test_expected_return_after_tax_and_single_essential(client):
    import planner, stress
    planner.set_settings({"capital_gains_tax_pct": 19})
    assert planner.expected_return_after_tax() == round(6.5 * 0.81, 2)
    e1, d1 = planner.essential_monthly()
    e2, d2 = stress._essential_monthly()
    assert (e1, d1) == (e2, d2)


def test_liquid_cushion_haircuts_brokerage_and_excludes_retirement(client):
    import planner
    ids = []
    for name, kind, val in (("Cash test", "cushion", 1000), ("Broker test ETF", "investment", 1000), ("Pension test", "investment", 500)):
        ids.append(planner.add_wealth_item({"name": name, "kind": kind, "value": val}))
    lc = planner.liquid_cushion()
    assert lc["cash"] >= 1000 and lc["brokerage_counted"] >= 800 and lc["retirement"] >= 500
    assert lc["total"] == lc["cash"] + round(lc["brokerage"] * 0.8)
    for i in ids:
        planner.delete_wealth_item(i)


def test_recommendation_memory_and_after_tax_text(client):
    import planner
    rec = client.get("/api/recommendation").get_json()
    assert "history" in rec and all("since" in r for r in rec["items"])
    dl = [r for r in rec["items"] if r["area"] == "debts"]
    if dl:
        assert "after tax" in dl[0]["text"].lower()
    # ta sama rekomendacja drugi raz → to samo 'since'; nowa strategia → znacznik czasu i staleness po zdarzeniu
    rec2 = client.get("/api/recommendation").get_json()
    assert [r["since"] for r in rec["items"]] == [r["since"] for r in rec2["items"]]
    planner.set_settings({"debt_strategy": "TEST strategia"})
    assert planner.get_setting("debt_strategy_at")
    planner.set_settings({"debt_strategy": ""})
