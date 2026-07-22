"""Unit tests for pure logic: RAG BM25, forecast models, security scan."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))


def test_commit_streak_grace_and_break():
    """Regression: the streak must not reset just because there's no commit
    today yet (grace until end of day). The old code started the loop at today
    and returned 0 despite commits yesterday/the day before."""
    import planner
    from datetime import date
    today = date(2026, 7, 20)
    counts = {"2026-07-19": 57, "2026-07-18": 27}  # nothing today, but streak is alive
    assert planner._commit_streak(counts, today) == 2
    assert planner._commit_streak({**counts, "2026-07-20": 1}, today) == 3  # commit today → 3
    assert planner._commit_streak({"2026-07-18": 5}, today) == 0  # empty yesterday+today breaks
    assert planner._commit_streak({}, today) == 0  # no commits at all


def test_rag_tokenizer_drops_stopwords_and_short():
    import rag
    toks = rag._tok("The mortgage on the house is 300000 EUR")
    assert "300000" in toks and len(toks) >= 3
    assert "the" not in toks and "on" not in toks  # stopwords/short removed
    # light stemming: inflection doesn't block matches (goals→goal, houses→house)
    assert rag._tok("goals")[0] == rag._tok("goal")[0]
    assert rag._tok("mortgages")[0] == rag._tok("mortgage")[0]
    assert rag._tok("houses")[0] == rag._tok("house")[0]


def test_rag_bm25_ranks_relevant_first(client):
    # client fixture ensures the seeded DB / env is set up
    import rag
    rag.reindex()
    hits = rag.search("mortgage down payment property goal", k=5)
    assert hits, "expected at least one hit"
    # scores are sorted descending
    scores = [h["score"] for h in hits]
    assert scores == sorted(scores, reverse=True)
    assert all(h["score"] > 0 for h in hits)


def test_rag_empty_query_returns_nothing(client):
    import rag
    assert rag.search("   ") == []


def test_forecast_bands_are_ordered():
    import forecast_models as fm
    # 80 sessions of gently trending noise → bands must satisfy p10 <= p50 <= p90
    import math
    closes = [100 * math.exp(0.0004 * i + 0.01 * math.sin(i)) for i in range(80)]
    out = fm.short_term_bands(closes)
    assert out and out["horizons"], "expected bands for a decent series"
    for h in out["horizons"]:
        assert h["p10"] <= h["p50"] <= h["p90"]
    assert out["ewma_vol_annual_pct"] >= 0


def test_forecast_goal_eta_band():
    import forecast_models as fm
    band = fm.goal_eta_band(remaining=120000, pace=5000)
    assert band is not None  # ~24 months at 5k/mo, returned as a range


def test_forecast_model_primitives():
    import forecast_models as fm
    closes = [100, 101, 100.5, 102, 101.5, 103, 102.5, 104]
    lr = fm.log_returns(closes)
    assert len(lr) == len(closes) - 1
    vol = fm.ewma_vol_daily(lr)
    assert vol is not None and vol >= 0
    assert fm.ewma_vol_daily([]) is None
    qs = fm.empirical_nday_quantiles(closes, n=2)
    assert qs is None or (qs[0.10] <= qs[0.50] <= qs[0.90])
    assert fm.conformal_quantiles([0.1, -0.2, 0.3], min_n=40) is None  # too few obs


def test_backup_snapshot_is_consistent(client, tmp_path):
    import data_backup as backup
    backup.set_destination(str(tmp_path))
    r = backup.create_backup()
    assert r["ok"] and r["size_kb"] > 0


def test_backup_restore_reverts_changes(client, tmp_path):
    import data_backup as backup
    backup.set_destination(str(tmp_path))
    before = len(client.get("/api/goals").get_json())
    snap = backup.create_backup()["file"]
    gid = client.post("/api/goals", json={"name": "temp", "target_amount": 1}).get_json()["id"]
    assert len(client.get("/api/goals").get_json()) == before + 1
    res = backup.restore(snap)
    assert res["ok"] and res["safety_copy"]
    assert len(client.get("/api/goals").get_json()) == before  # reverted
    # guard against path traversal
    assert backup.restore("../../etc/passwd")["ok"] is False


def test_rag_semantic_hybrid_finds_without_lexical_overlap(client, monkeypatch):
    """With embeddings present, a query semantically close but sharing NO words
    still surfaces the right chunk — what pure BM25 cannot do."""
    import json
    import uuid
    import rag
    import llm_local
    import engine_bridge as eb

    # toy embedder: "retirement" ~ "pension" (close), "car" far away
    vocab = {"pension": [1.0, 0, 0], "retirement": [0.95, 0.1, 0],
             "car": [0, 1.0, 0], "loan": [0, 0.95, 0.1]}

    def fake_embed(text):
        v = [0.0, 0.0, 0.0]
        for w, vec in vocab.items():
            if w in text.lower():
                v = [a + b for a, b in zip(v, vec)]
        return v if any(v) else [0.01, 0.01, 0.01]

    monkeypatch.setattr(llm_local, "embed", fake_embed)
    rag.ensure_tables()
    eb._exec("delete from rag_chunks")
    for src, txt in [("a", "my pension account balance"), ("b", "the car loan payment")]:
        emb = json.dumps(rag._normalize(fake_embed(txt)))
        eb._exec("insert into rag_chunks (id, source, ref, text, created_at, embedding) "
                 "values (?,?,?,?,?,?)", (uuid.uuid4().hex, src, "", txt, "now", emb))

    hits = rag.search("saving for retirement", k=2)  # no word overlap with "pension"
    assert hits and hits[0]["text"] == "my pension account balance"


def test_rag_reindex_embeds_new_data_and_degrades_without_server(client, monkeypatch):
    """Embedding lifecycle: (1) reindex with a live server embeds EVERY chunk
    (new data grows together with semantics, no manual step), (2) reindex with
    the server down doesn't blow up — index rebuilt, embedded=0, engine degrades
    to BM25, (3) server back + reindex recovers semantics fully. Guards the
    'self-healing, gracefully degrading' contract."""
    import rag
    import llm_local

    # (1) server alive → everything embedded, status = hybrid
    monkeypatch.setattr(llm_local, "embed", lambda t: [0.1, 0.2, 0.3] if t else None)
    n = rag.reindex()
    st = rag.status()
    assert n > 0 and st["embedded"] == st["chunks"] == n
    assert "hybrid" in st["engine"]

    # (2) server down → reindex passes, zero embeddings, engine = BM25 + hint
    monkeypatch.setattr(llm_local, "embed", lambda t: None)
    n2 = rag.reindex()
    st2 = rag.status()
    assert n2 == n and st2["embedded"] == 0
    assert "BM25" in st2["engine"] and "hybrid" not in st2["engine"]
    assert st2["hint"]  # UI explains how to enable semantics
    assert rag.search("wealth goal loan", k=3)  # search still works (lexically)

    # (3) server back → reindex recovers semantics in full
    monkeypatch.setattr(llm_local, "embed", lambda t: [0.3, 0.2, 0.1] if t else None)
    rag.reindex()
    st3 = rag.status()
    assert st3["embedded"] == st3["chunks"] and "hybrid" in st3["engine"]


def test_rag_indexes_derived_sources(client):
    import rag
    rag.reindex()
    import engine_bridge as eb
    sources = {r["source"] for r in eb._rows("select source from rag_chunks")}
    assert "reminder" in sources  # derived data now indexed, not just tables


def test_llm_log_records_and_reads(client):
    import llm_log
    llm_log.record("test question?", {"mode": "local", "rag_used": True,
                                       "local": {"ok": True, "text": "answer"}})
    recent = llm_log.recent(5)
    assert any(r["prompt"] == "test question?" for r in recent)
    assert llm_log.stats()["total"] >= 1


def test_security_review_runs_and_reports(client):
    import security_review as sr
    rep = sr.run(full=False)  # static checks only (fast, no server needed)
    assert set(("verdict", "score", "findings", "counts")) <= set(rep)
    assert 0 <= rep["score"] <= 100
    assert isinstance(rep["findings"], list) and rep["findings"]


def test_fetch_yahoo_history_stores_rows(client, monkeypatch):
    """Regression: the cache-write path once crashed with a NameError (eb
    undefined) that the offline `return 0` fallback silently hid — so mock the
    Yahoo response and make sure rows actually land in market_prices_cache."""
    import io
    import json as _json
    import urllib.request
    import market

    payload = {"chart": {"result": [{
        "timestamp": [1752624000, 1752710400],
        "indicators": {"quote": [{"close": [101.5, None]}]},
        "meta": {"currency": "USD"}}]}}

    class FakeResp(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False

    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda *a, **kw: FakeResp(_json.dumps(payload).encode()))
    assert market.fetch_yahoo_history("TESTX") == 1  # None close skipped
    hist = market.prices("TESTX", days=10)
    assert any(abs(h["close"] - 101.5) < 1e-9 for h in hist)


def test_experience_distillation_roundtrip(client, monkeypatch):
    """A distilled lesson is stored, indexed into RAG, retrieved as guidance on a
    similar question, and prunable — self-evolution without retraining (book ch.8)."""
    import experience, rag, llm_local
    # gate: refusals / too-short replies are NOT stored (transferability caveat)
    monkeypatch.setattr(llm_local, "chat", lambda *a, **k: "NONE")
    assert experience.learn("q", "a") is None
    assert experience.listing() == []
    # a real transferable lesson is stored + marks the index stale
    monkeypatch.setattr(llm_local, "chat", lambda *a, **k:
                        "Compare the loan rate to the market return AFTER capital-gains tax, not gross.")
    assert experience.learn("Overpay mortgage or invest?", "answer") is not None
    assert len(experience.listing()) == 1
    # RAG reindex surfaces it as an 'experience' chunk, retrievable by meaning-adjacent words
    rag.reindex()
    hits = rag.search("should I overpay the loan or invest in an ETF", k=6)
    assert any(h["source"] == "experience" for h in hits)
    # pruning removes it from the knowledge base
    experience.delete(experience.listing()[0]["id"])
    assert experience.listing() == []
    rag.reindex()
    assert not any(h["source"] == "experience" for h in rag.search("overpay loan invest", k=6))


def test_usd_base_rate_respects_base_currency(client, monkeypatch):
    """RSU/market values convert via the base currency: USD base → 1.0 (no FX pair
    needed), otherwise the USD<base>=X rate from the cache."""
    import market, planner
    planner.set_settings({"base_currency": "USD"})
    assert market._usd_base_rate()[0] == 1.0
    planner.set_settings({"base_currency": "PLN"})
    monkeypatch.setattr(market, "prices", lambda t, days=10:
                        [{"date": "2026-07-01", "close": 3.9}] if t == "USDPLN=X" else [])
    rate, d = market._usd_base_rate()
    assert rate == 3.9 and d == "2026-07-01"
    planner.set_settings({"base_currency": "PLN"})  # leave a known state


def test_github_activity_unconfigured_returns_empty(client, monkeypatch):
    """A fresh clone with no commit_repos and no gh must NOT scrape the home folder —
    it returns configured:false with zeros so the UI shows setup steps, never someone
    else's numbers."""
    import planner
    monkeypatch.setattr(planner, "_github_contribution_calendar", lambda days=90: None)
    ga = planner.github_activity(days=30)
    assert ga["configured"] is False
    assert ga["today"] == 0 and ga["repos"] == 0 and len(ga["series"]) == 30


def test_analytics_rounds_displayed_price(client, monkeypatch):
    """Displayed prices are rounded to 2dp at source (no raw Yahoo float like
    333.739990234375 leaking into the UI)."""
    import market
    series = [{"date": f"2026-0{1 + i // 28}-{1 + i % 28:02d}", "close": 100.0 + i,
               "currency": "USD"} for i in range(60)]
    series[-1]["close"] = 333.739990234375
    monkeypatch.setattr(market, "prices", lambda t, days=365: series)
    a = market.analytics("TESTX")
    assert a["last_close"] == 333.74
    assert a["high_52w"] == round(a["high_52w"], 2)


def test_barometer_index_trend_config_and_backcompat(client):
    """The barometer is configurable (roles/geo), computes an index (base 100) +
    3-month % + a direction reading, accepts both the legacy em/head shape and the
    new per-role counts shape, and re-keys its series when roles are reconfigured."""
    import planner, json
    # default config (public: from career_role_a/b)
    cfg = planner.barometer_config()
    keys = [r["key"] for r in cfg["roles"]]
    assert len(keys) == 2
    # legacy shape (back-compat) + new counts shape (n8n collector)
    planner.add_barometer_point({"month": "2026-04", "em_openings": 40, "head_openings": 10})
    planner.add_barometer_point({"month": "2026-05", "em_openings": 44, "head_openings": 11})
    planner.add_barometer_point({"month": "2026-06", "em_openings": 52, "head_openings": 9})
    planner.add_barometer_point({"month": "2026-07",
                                 "counts": {keys[0]: 60, keys[1]: 12},
                                 "sources": "JSearch", "geo": "Remote", "as_of": "2026-07-19"})
    b = planner.list_barometer()
    # after the two-stream rework, series are keyed "role|stream"
    # (points without a stream field fall into the default "trends")
    assert b["streams"] == ["trends"]
    s0 = b["series"][f"{keys[0]}|trends"]
    assert s0["index"][0] == 100.0 and s0["index"][-1] == 150.0   # 40 -> 60 = 150
    assert s0["q_pct"] == 50.0 and s0["reading"] == "growing"
    assert b["points"][-1]["sources"] == "JSearch" and b["points"][-1]["counts"][keys[0]] == 60
    # reconfigure roles -> series re-keys
    planner.set_settings({"barometer_config": json.dumps(
        {"geo": ["US"], "roles": [{"key": "pm", "label": "Product Manager", "query": "product manager"}]})})
    b2 = planner.list_barometer()
    assert list(b2["series"]) == ["pm|trends"] and b2["geo"] == ["US"]


def test_view_js_global_helpers_are_defined():
    """Guard the 'esc is not defined' class: a view calls a shared global helper
    that isn't defined in api.js/app.js (it slipped in when esc() was added to one
    repo's api.js but not the other's). Pure text check — no browser needed."""
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    defined = (root / "static/js/api.js").read_text() + (root / "static/js/app.js").read_text()
    views = list((root / "static/js/views").glob("*.js"))
    for name in ("esc", "fmt", "api", "demoOn", "parseNum"):
        assert any(t in defined for t in (f"function {name}", f"const {name}", f"{name} =")), \
            f"global helper `{name}` used by views is not defined in api.js/app.js"
    # any view calling esc( must have esc defined (the exact regression)
    if any("esc(" in v.read_text() for v in views):
        assert "function esc" in defined, "views call esc() but api.js/app.js has no `function esc`"
