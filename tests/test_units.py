"""Unit tests for pure logic: RAG BM25, forecast models, security scan."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))


def test_rag_tokenizer_drops_stopwords_and_short():
    import rag
    toks = rag._tok("The mortgage on the house is 300000 EUR")
    assert "mortgage" in toks and "house" in toks and "300000" in toks
    assert "the" not in toks and "on" not in toks  # stopwords/short removed


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
    assert recent and recent[0]["prompt"] == "test question?"
    assert llm_log.stats()["total"] >= 1


def test_security_review_runs_and_reports(client):
    import security_review as sr
    rep = sr.run(full=False)  # static checks only (fast, no server needed)
    assert set(("verdict", "score", "findings", "counts")) <= set(rep)
    assert 0 <= rep["score"] <= 100
    assert isinstance(rep["findings"], list) and rep["findings"]
