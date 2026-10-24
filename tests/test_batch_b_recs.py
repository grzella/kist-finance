"""Ported from the private instance (batch tests)."""


def test_expected_return_after_tax_and_single_essential(client):
    import planner
    planner.set_settings({"capital_gains_tax_pct": 19})
    assert planner.expected_return_after_tax() == round(6.5 * 0.81, 2)
    e, d = planner.essential_monthly()
    assert e >= 0 and d >= 0


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


def test_liquid_cushion_excludes_tax_reserve(client):
    import planner
    w = {"items": [{"name": "Cash", "kind": "cushion", "latest_value": 100000}], "tax_reserve": 63310}
    assert planner.liquid_cushion(w)["cash"] == 36690
    w["tax_reserve"] = 150000
    assert planner.liquid_cushion(w)["cash"] == 0


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


def test_recommendation_with_new_numbers_supersedes_old(client):
    import engine_bridge as eb
    import planner_recs as R
    # new numbers in the same area = the same recommendation: keeps its age, the old row is superseded, not 'resolved'
    R._rec_memory([{"area": "zz-test", "text": "rate 8.03%"}, {"area": "zz-gone", "text": "x"}])
    first = eb._rows("select first_seen from rec_log where area='zz-test'")[0]["first_seen"]
    items = [{"area": "zz-test", "text": "rate 8.04%"}]
    R._rec_memory(items)
    rows = {r["text"]: r for r in eb._rows("select * from rec_log where area in ('zz-test','zz-gone')")}
    assert rows["rate 8.03%"]["outcome"] == "obsolete" and rows["rate 8.03%"]["resolved_at"]
    assert rows["rate 8.04%"]["first_seen"] == first and items[0]["since"] == first[:10]
    assert rows["x"]["resolved_at"] and rows["x"]["outcome"] is None   # really gone: left for the user to judge
    eb._exec("delete from rec_log where area in ('zz-test','zz-gone')")


def _wealth(items, reserve=0):
    return {"items": items, "tax_reserve": reserve, "debts": [], "totals": {}, "total": sum(i["latest_value"] for i in items), "trend": [], "debt_total": 0}


def test_stress_liquid_is_the_metrics_cushion(client, monkeypatch):
    import planner, stress
    base = [{"name": "Cash PLN", "kind": "cushion", "latest_value": 60000},
            {"name": "ETF VWCE", "kind": "investment", "latest_value": 100000}]
    monkeypatch.setattr(planner, "wealth_summary", lambda: _wealth(base))
    liquid, equity, _ = stress._liquid_and_equity()
    assert liquid == planner.liquid_cushion(_wealth(base))["total"] == 60000 + 80000
    with_deposit = base + [{"name": "Tenant deposit", "kind": "savings", "latest_value": 5000}]
    monkeypatch.setattr(planner, "wealth_summary", lambda: _wealth(with_deposit))
    assert stress._liquid_and_equity()[0] == liquid  # a tenant deposit is not a cushion


def test_allocation_subtracts_uncovered_tax_reserve(client, monkeypatch):
    import planner
    monkeypatch.setattr(planner, "wealth_summary", lambda: _wealth([{"name": "Cash PLN", "kind": "cushion", "latest_value": 100000}], reserve=60000))
    cash = next(r for r in planner.allocation()["rows"] if r["key"] == "cash")
    assert cash["value"] == 40000
    monkeypatch.setattr(planner, "wealth_summary", lambda: _wealth([{"name": "Cash PLN", "kind": "cushion", "latest_value": 100000},
                                                                  {"name": "Tax reserve: bonds", "kind": "cushion", "latest_value": 60000}], reserve=60000))
    cash = next(r for r in planner.allocation()["rows"] if r["key"] == "cash")
    assert cash["value"] == 100000  # the reserve is covered by its own item, which stays out of the allocation


def test_wealth_tile_percent_uses_the_metrics_cushion():
    from pathlib import Path
    js = Path(__file__).resolve().parent.parent / "static" / "js" / "views" / "wealth.js"
    assert "o.cushion.total / target" in js.read_text(encoding="utf-8")


def test_wealth_stage_milestones():
    import planner_recs as R
    lc = {"cash": 60000, "brokerage": 1000}
    ok, off = [{"flag": "ok"}], [{"label": "Core", "pct": 11, "target": 50, "flag": "top up"}]
    assert R.wealth_stage([{"balance": 1, "type": "card"}], lc, 8000, True, ok, 0, 1)[0] == 2
    assert R.wealth_stage([], {"cash": 4000, "brokerage": 0}, 8000, True, ok, 0, 1)[0] == 3
    assert R.wealth_stage([], {"cash": 40000, "brokerage": 0}, 8000, True, ok, 0, 1)[0] == 4
    assert R.wealth_stage([], {"cash": 60000, "brokerage": 0}, 8000, True, ok, 0, 1)[0] == 6
    assert R.wealth_stage([{"balance": 9, "type": "mortgage"}], lc, 8000, True, off, 0, 1)[0] == 7
    assert R.wealth_stage([], lc, 8000, False, ok, 0, 1)[0] == 7
    assert [R.wealth_stage([], lc, 8000, True, ok, v, 100)[0] for v in (79, 80, 100)] == [8, 9, 10]
    assert set(R.WEALTH_STAGES) == set(range(1, 11))


def test_wealth_stage_endpoint_ladder(client):
    ws = client.get("/api/wealth-stage").get_json()
    assert [s["stage"] for s in ws["ladder"]] == list(range(1, 11))
    assert [s["status"] for s in ws["ladder"]].count("now") == 1
    assert ws["ladder"][ws["stage"] - 1]["status"] == "now"
