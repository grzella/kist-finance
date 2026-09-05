"""Ported from the private instance (batch tests)."""
import math, random


def _closes(n=400, seed=1):
    rng = random.Random(seed); px = 100.0; out = []
    for _ in range(n):
        px *= math.exp(rng.gauss(0, 0.02)); out.append(px)
    return out


def test_bootstrap_paths_deterministic_and_ordered(client):
    import market
    c = _closes()
    a = market._bootstrap_price_paths(c, 63, 200, [20, 62], drift_annual=0.0, seed=7)
    b = market._bootstrap_price_paths(c, 63, 200, [20, 62], drift_annual=0.0, seed=7)
    assert a == b and len(a) == 2 and len(a[0]) == 200 and len(a[1]) == 200
    q = market._bootstrap_quantiles(c, 21, sims=300)
    assert q[0.10] < q[0.50] < q[0.90]
    assert abs(q[0.50] / c[-1] - 1) < 0.15          # drift ~0: median close to today
    assert market._bootstrap_price_paths(c[:30], 21, 10, [20]) is None   # too little history → GBM fallback


def test_backtest_and_advanced_use_bootstrap(client):
    import market
    grant = dict(market._RSU_DEFAULT)
    bt = market.rsu_backtest(grant)
    assert "method" not in bt or "bootstrap" in bt["method"]
    adv = market.rsu_advanced()
    if not adv.get("error"):
        assert adv["method"].startswith("bootstrap") or adv["method"].startswith("GBM")
        for p in adv["projection"]:
            assert p["p10_price"] <= p["p50_price"] <= p["p90_price"]


def test_fire_inflation_tax_and_cone_fields(client):
    import planner
    planner.set_settings({"inflation_pct": 3, "income_growth_pct": 3, "capital_gains_tax_pct": 19})
    f = planner.fire_projection()
    assert f["inflation_pct"] == 3 and f["tax_pct"] == 19 and "series_net" in f and "cone" in f
    assert len(f["series_net"]) == len(f["labels"])
    # netto po podatku nigdy nie przekracza brutto
    base = f["series"]["base (6.5%)"]
    assert all(n <= b + 1 for n, b in zip(f["series_net"], base))
    planner.set_settings({"inflation_pct": 12})
    f2 = planner.fire_projection()
    c1, c2 = f["crossover"].get("base (6.5%)"), f2["crossover"].get("base (6.5%)")
    assert c1 is None or c2 is None or c2 >= c1
    planner.set_settings({"inflation_pct": 3})


def test_goal_simulation_indexes_target(client):
    import planner
    planner.set_settings({"inflation_pct": 0})
    a = planner._simulate_path(120000, 10000, [])
    planner.set_settings({"inflation_pct": 50})
    b = planner._simulate_path(120000, 10000, [])
    assert a["months"] == 12 and (b["months"] is None or b["months"] > 12)
    planner.set_settings({"inflation_pct": 3})
