"""Fixed expenses: billing cadence (monthly/yearly) + health/sport category.
The `billing` field is the source of truth for the "annual plan is cheaper" tip —
previously guessed from the item name."""


def _add(client, **kw):
    body = {"name": "X", "category": "subscription-entertainment", "amount": 10, "month": "2026-09"}
    body.update(kw)
    return client.post("/api/expenses/items", json=body).get_json()["id"]


def _item(client, item_id):
    return next(i for i in client.get("/api/expenses/summary").get_json()["items"]
                if i["id"] == item_id)


def test_billing_defaults_to_monthly_and_accepts_yearly(client):
    a = _add(client, name="Sub A")
    b = _add(client, name="Sub B", billing="yearly")
    c = _add(client, name="Sub C", billing="whatever")  # unknown value → monthly
    assert _item(client, a)["billing"] == "monthly"
    assert _item(client, b)["billing"] == "yearly"
    assert _item(client, c)["billing"] == "monthly"
    for i in (a, b, c):
        client.delete(f"/api/expenses/items/{i}")


def test_billing_toggle_via_put(client):
    a = _add(client, name="Sub toggle")
    client.put(f"/api/expenses/items/{a}", json={"billing": "yearly"})
    assert _item(client, a)["billing"] == "yearly"
    client.put(f"/api/expenses/items/{a}", json={"billing": "monthly"})
    assert _item(client, a)["billing"] == "monthly"
    client.delete(f"/api/expenses/items/{a}")


def test_annual_tip_lists_only_monthly_subscriptions(client):
    m = _add(client, name="Cycling app monthly", category="subscription-health", amount=20)
    y = _add(client, name="Yearly plan", category="subscription-health", amount=15,
             billing="yearly")
    s = client.get("/api/expenses/summary").get_json()
    tip = next(t for t in s["optimizations"] if t["kind"] == "annual")
    assert "Cycling app monthly" in tip["text"]
    assert "Yearly plan" not in tip["text"]
    assert "/yr" in tip["text"]
    assert any(c["category"] == "Subscriptions: health / sport" for c in s["by_category"])
    for i in (m, y):
        client.delete(f"/api/expenses/items/{i}")
