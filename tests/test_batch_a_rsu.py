"""Ported from the private instance (batch tests)."""
import json


def _hist(n=300, px=100.0):
    from datetime import date, timedelta
    d0 = date(2026, 1, 1)
    return [{"date": (d0 + timedelta(days=i)).isoformat(), "close": px, "currency": "USD"} for i in range(n)]


def test_vest_schedule_expires_legacy_and_starts_new_grants(client, monkeypatch):
    import market
    grant = {**market._RSU_DEFAULT, "ticker": "ACME", "grant_value_usd": 16000, "pricing_window": "2026-08",
             "grant_month": "2026-09", "first_vest": "2026-11", "vesting_years": 4, "vests_per_year": 4,
             "legacy_shares_per_vest": 100, "legacy_until": "2027-02", "shares_next_vest": 0,
             "cash_vest_usd_per_quarter": 1000,
             "extra_grants": [{"label": "special", "value_usd": 8000, "pricing_window": "2026-08", "first_vest": "2027-05"}]}
    from datetime import date
    sch = market.vest_schedule(grant, _hist(), months=48, today=date(2026, 9, 5))
    by = {m["month"]: m for m in sch["months"]}
    assert by["2026-11"]["shares"] == 110 and by["2026-11"]["cash_usd"] == 1000   # legacy 100 + main 10
    assert by["2027-02"]["shares"] == 110                                          # ostatni vest legacy
    assert by["2027-05"]["shares"] == 15                                           # legacy expired, special started
    assert by["2030-08"]["shares"] == 15 and "2030-11" not in by or by.get("2030-11", {}).get("shares", 0) == 0
    assert sch["legacy_open_ended"] is False
    assert [s["label"] for s in sch["sources"]][:2] == ["legacy grants", "grant 2026-09"]


def test_vest_schedule_broker_override_only_until_new_grants_vest(client, monkeypatch):
    import market
    from datetime import date
    base = {**market._RSU_DEFAULT, "_today": date(2026, 9, 5), "grant_value_usd": 16000, "pricing_window": "2026-08", "first_vest": "2026-11",
            "legacy_shares_per_vest": 100, "shares_next_vest": 168}
    sch = market.vest_schedule(base, _hist())
    assert sch["months"][0]["shares"] == 168 and sch["months"][1]["shares"] == 110   # broker bije model tylko raz
    sch2 = market.vest_schedule({**base, "new_grants_vesting": True}, _hist())
    assert sch2["months"][0]["shares"] == 110
    assert sch2["legacy_open_ended"] is True  # brak legacy_until → flaga dla UI


def test_rsu_sale_logs_tax_and_reduces_holdings(client):
    import market, planner
    market.update_rsu({"shares_held": 50})
    r = client.post("/api/rsu/sales", json={"date": "2026-09-04", "shares": 20, "price_usd": 100, "usdpln": 4.0}).get_json()
    assert r["gross_pln"] == 8000
    tax = client.get("/api/rsu/sales").get_json()["tax"]
    assert tax["tax_due_pln"] == 1520 and tax["deadline"] == "2027-04-30" and tax["shares_sold"] == 20
    assert client.get("/api/rsu").get_json()["shares_held"] == 30
    w = planner.wealth_summary()
    assert w["tax_reserve"] == 1520 and abs(w["debt_total"] - (w["loans_total"] + 1520)) < 0.01
    t = client.get("/api/taxes").get_json()
    row = next(i for i in t["items"] if i["source"].startswith("RSU"))
    assert row["tax"] == 1520 and any("RSU" in c["what"] for c in t["calendar"])
    client.delete("/api/rsu/sales/" + r["id"])
    assert client.get("/api/rsu/sales").get_json()["tax"]["tax_due_pln"] == 0


def test_annual_extras_are_net_and_include_cash_vest(client, monkeypatch):
    import planner
    fake = {"vest_schedule": [{"month": m, "shares": 100, "cash_usd": 1000} for m in ("2026-11", "2027-02", "2027-05", "2027-08")],
            "last_close": 10.0, "usdpln": 4.0, "net_factor": 0.81, "cash_vest_net_factor": 0.5}
    import market
    from datetime import date
    monkeypatch.setattr(market, "get_rsu", lambda: fake)
    planner.set_settings({"annual_bonus_net": 0, "extras_to_goal_pct": 100})
    ex = planner._annual_extras(today=date(2026, 9, 5))
    assert ex["rsu_annual_gross"] == 16000 and ex["rsu_annual"] == 12960 and ex["cash_vest_annual_net"] == 8000
    assert ex["monthly_equivalent"] == round((12960 + 8000) / 12, 2)


def test_cashflow_uses_net_vests_reserve_and_sweep_setting(client, monkeypatch):
    import planner, market
    fake = {"vest_schedule": [{"month": "2026-10", "shares": 100, "cash_usd": 0}], "last_close": 10.0, "usdpln": 4.0,
            "net_factor": 0.81, "cash_vest_net_factor": 0.5, "tax_pct": 19, "vest_months": [10],
            "next_vest_value_net_pln": 3240}
    from datetime import date
    monkeypatch.setattr(market, "get_rsu", lambda: fake)
    planner.set_settings({"cf_monthly_surplus": 1000, "cf_safety_buffer": 0, "cf_liquid_start": "",
                          "annual_bonus_net": 0, "cf_bonus_month": 1, "cf_sweep_target": "none"})
    cf = planner.cashflow(3, today=date(2026, 9, 5))
    assert cf["sweep_mode"] == "accumulate" and cf["liquid_start_source"] == "wealth"
    oct_ = next(r for r in cf["rows"] if r["month"] == "2026-10")
    assert oct_["vest_net"] == 3240 and oct_["tax_reserve"] == 760 and oct_["overpay"] == 0
    # jedno tempo: monthly_savings lustrzy cf_monthly_surplus
    planner.set_settings({"monthly_savings": 2500})
    assert planner.monthly_surplus() == 2500 and planner.settings()["cf_monthly_surplus"] == 2500
