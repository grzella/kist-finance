"""Ported from the private instance (batch tests)."""
import io, json


def test_expense_in_foreign_currency_is_converted(client, monkeypatch):
    import market, planner
    monkeypatch.setattr(market, "fx_to_base", lambda ccy, days=10: {"PLN": 1.0, "EUR": 4.0, "USD": 3.5}.get((ccy or "PLN").upper()))
    iid = client.post("/api/expenses/items", json={"name": "EUR sub test", "currency": "EUR", "amount": 15, "month": "2026-09",
                                                    "category": "subscription-health"}).get_json()["id"]
    it = next(i for i in client.get("/api/expenses/summary").get_json()["items"] if i["id"] == iid)
    assert it["latest_amount_ccy"] == 15 and it["latest_amount"] == 60 and it["fx_rate"] == 4.0 and it["fx_missing"] is False
    client.delete(f"/api/expenses/items/{iid}")


def test_refresh_market_rates_parses_sources_without_network(client, monkeypatch):
    import market, planner
    planner.set_settings({"base_currency": "PLN", "market_rates": json.dumps({"wibor_forecast": 3.5, "typical_margin": 2.0})})
    nbp = b'<stopy_procentowe><tabela><pozycja id="ref" nazwa="Stopa referencyjna" oprocentowanie="4,75" obowiazuje_od="2026-07-03"/></tabela></stopy_procentowe>'
    stooq = b"Symbol,Data,Czas,Otwarcie,Najwyzszy,Najnizszy,Zamkniecie,Wolumen\nPLOPLN3M,2026-09-04,00:00:00,4.86,4.86,4.86,4.86,0\n"

    class R:
        def __init__(self, b): self.b = b
        def read(self): return self.b
    def fake_open(req, timeout=10):
        return R(nbp if "nbp.pl" in req.full_url else stooq)
    monkeypatch.setattr(market.urllib.request, "urlopen", fake_open)
    out = market.refresh_market_rates()
    assert out["ok"] and out["rates"]["nbp_ref"] == 4.75 and out["rates"]["wibor3m"] == 4.86
    saved = json.loads(planner.get_setting("market_rates"))
    assert saved["asof"] and saved["wibor_forecast"] == 3.5  # stare klucze zachowane
    def only_nbp(req, timeout=10):
        if "nbp.pl" in req.full_url:
            return R(nbp)
        raise OSError("404")
    monkeypatch.setattr(market.urllib.request, "urlopen", only_nbp)
    planner.set_settings({"market_rates": json.dumps({"typical_margin": 2.0})})
    out2 = market.refresh_market_rates()
    assert out2["ok"] and out2["rates"]["wibor3m"] == 4.9 and "warning" in out2
    import schedules
    assert any(t["id"] == "rates_refresh" for t in schedules.REGISTRY)


def test_analysis_marks_stale_when_data_changed_after_as_of(client):
    import planner
    planner.set_settings({"analysis_test_stale": json.dumps({"as_of": "2020-01-01", "headline": "x"})})
    a = client.get("/api/analysis/test_stale").get_json()
    assert a.get("stale") and a["stale"]["as_of"] == "2020-01-01"
    planner.set_settings({"analysis_test_fresh": json.dumps({"as_of": "2999-01-01", "headline": "x"})})
    assert "stale" not in client.get("/api/analysis/test_fresh").get_json()


def test_debt_history_has_event_kinds(client):
    import planner
    did = planner.add_debt({"name": "Test loan", "balance": 100000, "interest_rate": 5, "minimum_payment": 1000})
    planner.overpay_debt(did, {"amount": 5000})
    planner.update_debt(did, {"balance": 94000})
    d = next(x for x in planner.list_debts()["debts"] if x["id"] == did)
    kinds = [h["kind"] for h in d["history"]]
    assert kinds[0] == "start" and "overpayment" in kinds and "correction" in kinds
    planner.delete_debt(did)
