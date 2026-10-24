"""Offers: the pay delta is gross while the goal pace is net, so goal_impact uses the delta times the net factor."""


def test_offer_goal_impact_uses_net_delta(client):
    import planner, planner_career
    prev = {k: planner.settings().get(k) for k in ("tax_salary_gross_annual", "monthly_savings")}
    planner.set_settings({"tax_salary_gross_annual": 120000, "monthly_savings": 5000})
    try:
        _check(client, planner, planner_career)
    finally:
        # fixture bazy jest sesyjna: oferta z dzisiejszą datą wydłużyłaby oś barometru w test_units
        planner.set_settings(prev)
        for o in client.get("/api/offers").get_json()["offers"]:
            if o["company"] == "Acme":
                client.delete(f"/api/offers/{o['id']}")
        for g in client.get("/api/goals").get_json():
            if isinstance(g, dict) and g.get("name") == "Test goal":
                client.delete(f"/api/goals/{g['id']}")


def _check(client, planner, planner_career):
    nf = planner_career.P._annual_extras()["payroll_net_factor"]
    assert client.post("/api/goals", json={"name": "Test goal", "target_amount": 60000, "current_amount": 0,
                                           "monthly_contribution": 5000, "status": "active"}).status_code in (200, 201)
    current = planner_career._current_total_monthly()  # the test seed may include RSU and bonus, only the delta matters
    assert current
    r = client.post("/api/offers", json={"company": "Acme", "role": "EM", "total_monthly": current + 10000})
    assert r.status_code in (200, 201), r.get_json()
    offers = client.get("/api/offers").get_json()["offers"]
    o = next(x for x in offers if x["company"] == "Acme")
    assert o["delta_monthly"] == 10000 and o["delta_monthly_net"] == round(10000 * nf)
    gi = next(g for g in o["goal_impact"] if g["goal"] == "Test goal")
    assert gi["new_months"] == round(60000 / (5000 + 10000 * nf), 1)
