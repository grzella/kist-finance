"""Batch E (2026-09-05): ratios as a monthly series + wealth points, trajectory cone with
scenarios, calibration per ticker × horizon (Winkler/PIT, VIX regime, rolling window), RAG over
markdown notes with citations, the leader's evidence log, recommendation outcomes + review,
the new scheduler task."""
import json
import math
import random


def _closes(n=400, seed=3):
    rng = random.Random(seed); px = 100.0; out = []
    for _ in range(n):
        px *= math.exp(rng.gauss(0, 0.02)); out.append(px)
    return out


def test_metrics_summary_shape_and_lights(client):
    import metrics
    r = client.get("/api/metrics")
    assert r.status_code == 200
    d = r.get_json()
    keys = [i["key"] for i in d["current"]["items"]]
    assert keys == [t[0] for t in metrics.TARGETS]
    for it in d["current"]["items"]:
        assert it["light"] in ("green", "amber", "red", "grey")
        assert it["target"] and it["note"]
    assert isinstance(d["history"], list) and isinstance(d["points"], list)


def test_metrics_snapshot_is_idempotent_per_day(client):
    import metrics
    a = client.post("/api/metrics/snapshot").get_json()
    b = client.post("/api/metrics/snapshot").get_json()
    assert a["point"]["date"] == b["point"]["date"]
    pts = [p for p in metrics.points() if not p.get("legacy")]
    assert sum(1 for p in pts if p["date"] == a["point"]["date"]) == 1
    assert len(metrics.history()) >= 1
    assert "savings_rate_pct" in b["month"]


def test_light_thresholds():
    import metrics
    assert metrics._light(7, "high", 6, 3) == "green"
    assert metrics._light(4, "high", 6, 3) == "amber"
    assert metrics._light(1, "high", 6, 3) == "red"
    assert metrics._light(50, "low", 60, 75) == "green"
    assert metrics._light(80, "low", 60, 75) == "red"
    assert metrics._light(None, "low", 60, 75) == "grey"


def test_trajectory_quantiles_ordered_and_variants(client):
    r = client.get("/api/trajectory?months=12")
    assert r.status_code == 200
    t = r.get_json()
    assert len(t["labels"]) == 12 == len(t["p50"])
    for lo, mid, hi in zip(t["p10"], t["p50"], t["p90"]):
        assert lo <= mid <= hi
    assert {v["key"] for v in t["variants"]} >= {"base", "no_bonus", "team_down", "all_bad"}
    base = next(v for v in t["variants"] if v["key"] == "base")
    assert base["delta_vs_base"] == 0
    real = client.get("/api/trajectory?months=12&real=1").get_json()
    assert real["assumptions"]["real"] is True
    assert real["p50"][-1] <= t["p50"][-1]
    assert client.get("/api/trajectory?months=abc").status_code == 200   # bad param → defaults


def test_interval_scores_verdicts_and_winkler():
    import forecast_models as fm
    inside = [{"p10": 90, "p90": 110, "realized_close": 100, "base_close": 100}] * 20
    s = fm.interval_scores(inside)
    assert s["coverage_pct"] == 100 and s["verdict"] == "too wide" and s["winkler_pct"] == 20
    below = [{"p10": 90, "p90": 110, "realized_close": 80, "base_close": 100}] * 10 + inside[:10]
    s2 = fm.interval_scores(below)
    assert s2["coverage_pct"] == 50 and s2["verdict"].startswith("too narrow") and "low" in s2["verdict"]
    assert s2["winkler_pct"] > 20          # 2/α penalty per miss
    ok = inside[:8] + [{"p10": 90, "p90": 110, "realized_close": 120, "base_close": 100}] * 2
    assert fm.interval_scores(ok)["verdict"] == "ok"
    assert fm.interval_scores([]) is None


def test_vol_regime_widens_longer_horizons_only():
    import forecast_models as fm
    c = _closes()
    a = fm.short_term_bands_calibrated(c)
    b = fm.short_term_bands_calibrated(c, vol_regime=1.3)
    assert b["vol_regime"] == 1.3
    ah = {h["days"]: h for h in a["horizons"]}; bh = {h["days"]: h for h in b["horizons"]}
    assert bh[5]["p10"] == ah[5]["p10"] and bh[5]["p90"] == ah[5]["p90"]
    for d in (21, 63):
        assert bh[d]["p10"] < ah[d]["p10"] and bh[d]["p90"] > ah[d]["p90"]
    res = {21: [random.Random(1).gauss(0, 1.5) for _ in range(60)]}
    cal = fm.short_term_bands_calibrated(c, res, vol_regime=1.0)
    assert any(h.get("calibrated") for h in cal["horizons"])


def test_forecast_residuals_rolling_window_and_calibration_endpoint(client):
    import market, db
    with db.get_conn() as conn:
        for i in range(150):
            conn.execute("insert or ignore into forecast_track (made_on, ticker, horizon_days, base_close, sigma_daily, "
                         "p10, p50, p90, realized_close, realized_on, inside, resid_z, calibrated) "
                         "values (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                         (f"2025-{(i // 28) % 12 + 1:02d}-{i % 28 + 1:02d}", "TSTX", 21, 100, 0.02, 90, 100, 110,
                          100 + (i % 7) - 3, "2026-01-01", 1, (i % 5 - 2) / 2.0, i % 2))
        conn.commit()
    res = market.forecast_residuals("TSTX", window=50)
    assert len(res[21]) == 50
    assert len(market.forecast_residuals("TSTX", window=500)[21]) == 150
    reg = market.vol_regime()
    assert reg["factor"] in (1.0, 1.15, 1.3)
    d = client.get("/api/forecast/calibration").get_json()
    assert d["target_pct"] == 80 and d["regime"]["factor"] == reg["factor"]
    row = next(r for r in d["by_ticker"] if r["ticker"] == "TSTX")
    assert row["n"] == 150 and row["coverage_pct"] == 100 and row["calibrated_n"] == 75
    assert any(h["horizon_days"] == 21 for h in d["by_horizon"])


def test_rag_indexes_markdown_dirs_with_citations(client, tmp_path):
    import planner, rag
    notes = tmp_path / "knowledge"
    notes.mkdir()
    (notes / "offer-triage.md").write_text("# Offer triage threshold\n\n## Rule\n\nThe job offer triage threshold is one hundred ten thousand monthly total plus full remote, otherwise we do not reply.\n", encoding="utf-8")
    (notes / "refinance.md").write_text("# Loan refinance\n\nWe negotiate the mortgage annex after a certificate from another bank; playbook: real offers, retention desk.\n" * 3, encoding="utf-8")
    (notes / ".hidden.md").write_text("# secret\n\ndo not index this ever at all\n", encoding="utf-8")
    planner.set_settings({"rag_dirs": json.dumps([str(notes)])})
    n = rag.reindex()
    st = rag.status()
    assert n >= 2 and st["by_source"].get("note:knowledge", 0) >= 2
    assert str(notes) in st["dirs"]
    ctx, src = rag.context_with_sources("what is the job offer triage threshold")
    assert src and src[0]["ref"].startswith("offer-triage.md") and src[0]["date"]
    assert "UNTRUSTED" in ctx and "offer-triage" in ctx
    assert not any("hidden" in h["ref"] for h in rag.search("secret do not index", k=5))
    evalset = [("offer triage threshold", "offer-triage"), ("mortgage annex certificate", "refinance")]
    hits = sum(1 for q, ref in evalset if any(ref in h["ref"] for h in rag.search(q, k=3)))
    assert hits == len(evalset)
    planner.set_settings({"rag_dirs": ""})


def test_em_log_week_and_plan(client):
    r = client.post("/api/em/log", json={"kind": "impact", "text": "PR review time down 30%", "metric": "review h", "value": "12"})
    assert r.status_code == 201
    eid = r.get_json()["id"]
    assert client.post("/api/em/log", json={"kind": "xxx", "text": "a"}).status_code == 400
    assert client.post("/api/em/log", json={"kind": "learning", "text": " "}).status_code == 400
    w = client.put("/api/em/week", json={"energy": 9, "deep_hours": "14", "one_on_ones": 6, "decisions": 3, "note": "ok"}).get_json()
    assert w["energy"] == 5.0 and w["deep_hours"] == 14.0 and w["week"]
    p = client.put("/api/em/plan", json={"idx": 2, "status": "done", "note": "done"}).get_json()
    assert p["2"]["status"] == "done"
    assert client.put("/api/em/plan", json={"idx": 0, "status": "meh"}).status_code == 400
    s = client.get("/api/em").get_json()
    assert s["counts"]["impact"] >= 1 and s["this_week"] == w["week"] and s["plan"]["2"]["status"] == "done"
    assert any(x["week"] == w["week"] for x in s["weeks"])
    assert client.delete("/api/em/log/" + eid).get_json()["ok"]
    assert all(x["id"] != eid for x in client.get("/api/em").get_json()["log"])


def test_recommendation_outcome_and_review(client):
    rec = client.get("/api/recommendation").get_json()
    assert client.put("/api/recommendation/outcome", json={"key": "nope", "outcome": "done"}).status_code == 404
    if rec["items"]:
        key = rec["items"][0]["key"]
        assert key.startswith(rec["items"][0]["area"] + ":")
        assert client.put("/api/recommendation/outcome", json={"key": key, "outcome": "bad"}).status_code == 400
        r = client.put("/api/recommendation/outcome", json={"key": key, "outcome": "done", "note": "overpaid"}).get_json()
        assert r["outcome"] == "done"
        again = client.get("/api/recommendation").get_json()
        assert next(i for i in again["items"] if i["key"] == key)["outcome"] == "done"
    rv = client.get("/api/recommendation/review").get_json()
    assert {"months", "pending", "total", "executed", "execution_rate_pct"} <= set(rv)
    if rec["items"]:
        assert rv["executed"] >= 1


def test_schedule_registry_has_weekly_points(client):
    ids = {t["id"] for t in client.get("/api/schedules").get_json()["tasks"]}
    assert {"wealth_points", "wealth_snapshot", "forecast_cycle"} <= ids


def test_refresh_derived_records_metrics(client):
    out = client.post("/api/freshness/derived").get_json()
    assert out.get("metrics") == "ok"
