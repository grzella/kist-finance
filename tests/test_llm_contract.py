"""LLM contract tests — a new kind of test for the AI surface.

The model's output is non-deterministic and often unavailable, so we don't assert
*what* it says. Instead we **mock the model and assert the invariants the app
guarantees around it** — the harness contract, which the book (AI Agents in Depth)
frames as "the harness is the real product." These stay deterministic and fast
while still exercising the integration:

  1. Graceful degradation — every AI feature must return a well-formed "offline"
     result when the model is down (kist's ethos: the AI is never *required*).
  2. The shared pipeline (`_ai_answer`) always logs and always yields a `best`.
  3. Structured generation never corrupts saved state (a failed brief keeps the
     last good one).

Run: python -m pytest tests/test_llm_contract.py -q
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))


def test_ai_answer_degrades_gracefully_when_offline(client, monkeypatch):
    """Model fully offline → no crash, a structured result, and it's still logged."""
    import app, llm_local, llm_cloud, llm_log
    monkeypatch.setattr(llm_local, "chat", lambda *a, **k: None)
    monkeypatch.setattr(llm_local, "chat_with_tools", lambda *a, **k: None)
    monkeypatch.setattr(llm_cloud, "chat", lambda *a, **k: None)
    out = app._ai_answer("a question with the model down", use_rag=False)
    assert out["local"]["ok"] is False           # degraded, not crashed
    assert "best" in out                          # the contract field always exists
    # observability holds even when the model is unavailable
    assert any(e["prompt"] == "a question with the model down" for e in llm_log.recent(5))


def test_ai_answer_logs_and_returns_best(client, monkeypatch):
    """When the model answers, `best` carries it and the call is recorded."""
    import app, llm_local, llm_log
    monkeypatch.setattr(llm_local, "chat", lambda *a, **k: "the answer")
    monkeypatch.setattr(llm_local, "chat_with_tools", lambda *a, **k: None)
    before = llm_log.stats()["total"]
    out = app._ai_answer("what should I do?", use_rag=False)
    assert out["local"]["ok"] is True and out["best"] == "the answer"
    assert llm_log.stats()["total"] == before + 1


def test_failed_brief_never_overwrites_a_saved_one(client, monkeypatch):
    """A failed generation must not wipe the last good brief (offline resilience)."""
    import market, planner, llm_local
    planner.set_settings({"analysis_market_brief_daily": '{"headline": "kept"}'})
    monkeypatch.setattr(market, "_brief_facts", lambda days: ["AAPL close 100"])
    monkeypatch.setattr(llm_local, "chat_json", lambda *a, **k: None)  # model offline
    r = market.generate_brief("daily")
    assert r["ok"] is False
    assert planner.get_setting("analysis_market_brief_daily") == '{"headline": "kept"}'


def test_ai_mode_only_local_never_calls_cloud(client, monkeypatch):
    """In the default 'local' mode the cloud model must never be invoked (privacy
    invariant: nothing leaves the machine unless the user opts into 'both')."""
    import app, planner, llm_local, llm_cloud
    planner.set_settings({"ai_mode": "local"})
    called = {"cloud": False}

    def _cloud(*a, **k):
        called["cloud"] = True
        return "SHOULD NOT BE CALLED"

    monkeypatch.setattr(llm_cloud, "chat", _cloud)
    monkeypatch.setattr(llm_local, "chat", lambda *a, **k: "local only")
    monkeypatch.setattr(llm_local, "chat_with_tools", lambda *a, **k: None)
    out = app._ai_answer("stay local", use_rag=False)
    assert called["cloud"] is False and out["best"] == "local only"
