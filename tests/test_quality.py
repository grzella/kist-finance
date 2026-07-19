"""Quality gates: empty-DB behavior (fresh install), property-based checks of
the financial math (hypothesis), and scanner-efficacy tests that PLANT leaks in
a throwaway git repo and assert the security review actually catches them."""
import math
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from hypothesis import given, settings, strategies as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))


# ---------- 1. fresh install: EMPTY database (no seed) ----------

def test_empty_db_every_get_survives_and_wizard_works(client, tmp_path, monkeypatch):
    """A first-run user has NO data: every GET must answer without a 500 and the
    wizard must be able to configure modules on a completely empty DB."""
    import db
    import planner
    monkeypatch.setenv("FINANCE_PROJECT_DIR", str(tmp_path))
    db.init_db()
    planner.ensure_tables()
    import app as flask_app
    import re
    src = open(ROOT / "server" / "app.py").read()
    routes = sorted(set(re.findall(r'@app\.get\("(/api/[^"<]+)"\)', src)))
    bad = []
    for r in routes:
        code = client.get(r).status_code
        if code >= 500:
            bad.append((r, code))
    assert not bad, f"500s on empty DB: {bad}"
    cfg = client.get("/api/app-config").get_json()
    assert cfg["has_data"] is False and cfg["wizard_completed"] is False
    r = client.post("/api/app-config",
                    json={"modules": ["debts", "markets"], "wizard_completed": True}).get_json()
    assert r["wizard_completed"] is True and r["modules"]["debts"] is True


# ---------- 2. property-based financial math (hypothesis) ----------

@settings(max_examples=60, deadline=None)
@given(st.lists(st.floats(min_value=1.0, max_value=1e6, allow_nan=False), min_size=2, max_size=400))
def test_log_returns_properties(closes):
    import forecast_models as fm
    r = fm.log_returns(closes)
    assert len(r) == len(closes) - 1
    assert all(math.isfinite(x) for x in r)


@settings(max_examples=40, deadline=None)
@given(st.lists(st.floats(min_value=0.5, max_value=1e5, allow_nan=False), min_size=45, max_size=300))
def test_short_term_bands_always_ordered(closes):
    import forecast_models as fm
    out = fm.short_term_bands(closes)
    if out is None:
        return  # degenerate series is allowed to refuse
    for h in out["horizons"]:
        assert h["p10"] <= h["p50"] <= h["p90"]
        assert h["p10"] >= 0  # degenerate low-price series may round to 0.0


@settings(max_examples=60, deadline=None)
@given(remaining=st.floats(min_value=100, max_value=5e6),
       pace=st.floats(min_value=50, max_value=1e5))
def test_goal_eta_band_ordered_and_positive(remaining, pace):
    import forecast_models as fm
    b = fm.goal_eta_band(remaining, pace)
    assert 0 <= b["months_fast"] <= b["months_base"] <= b["months_slow"]  # ~done goal → 0.0 months


@settings(max_examples=40, deadline=None)
@given(balance=st.floats(min_value=2e4, max_value=2e6),
       rate_pct=st.floats(min_value=1.0, max_value=11.0),
       months=st.integers(min_value=36, max_value=360),
       over_frac=st.floats(min_value=0.01, max_value=0.5))
def test_mortgage_overpayment_never_hurts(balance, rate_pct, months, over_frac):
    """A one-time overpayment can never increase interest or lengthen the loan."""
    import forecasts
    r = rate_pct / 100 / 12
    payment = balance * r / (1 - (1 + r) ** -months)   # fair annuity
    out = forecasts.mortgage_overpayment({
        "balance": balance, "monthly_payment": payment,
        "months_left": months, "overpayment": balance * over_frac})
    assert out["interest_saved"] >= -0.01
    assert out["months_left_after"] <= out["months_left_now"]
    assert abs(out["implied_annual_rate_pct"] - rate_pct) < 1.0


# ---------- 3. scanner efficacy: planted leaks MUST be caught ----------

def _make_bad_repo(tmp):
    repo = tmp / "badrepo"
    repo.mkdir()
    run = lambda *a: subprocess.run(["git", "-C", str(repo), *a], check=True,
                                    capture_output=True)
    run("init", "-q")
    run("config", "user.email", "t@t.t")
    run("config", "user.name", "T")
    (repo / "leak.py").write_text(
        'aws = "AKIA' + "A" * 16 + '"\npw = "password: supersecret123"\n')
    (repo / ".env").write_text("SECRET_TOKEN=verylongsecretvalue123456\n")
    (repo / "danger.py").write_text("import os\nos.system('ls')\neval('1+1')\n")
    (repo / "pii.py").write_text('author = "Grzella"\n')
    run("add", "-A")
    run("commit", "-qm", "bad")
    return str(repo)


def test_security_review_catches_planted_leaks(tmp_path):
    import security_review as sr
    repo = _make_bad_repo(tmp_path)
    tracked = subprocess.run(["git", "-C", repo, "ls-files"], capture_output=True,
                             text=True).stdout.splitlines()
    leaks = sr._check_repo_leaks(repo, tracked)
    fails = [x for x in leaks if x["status"] == "fail"]
    assert any(".env" in (x["detail"] or "") for x in fails), "tracked .env not caught"
    assert any("AKIA" in (x["detail"] or "") or "secret" in (x["detail"] or "").lower()
               for x in fails), "secret patterns not caught"

    code = sr._check_code(repo)
    titles = " | ".join(x["title"] for x in code)
    assert "eval" in titles.lower(), "eval() not caught"
    assert "os.system" in titles, "os.system not caught"

    pii = sr._check_personal_data(repo)
    assert any(x["status"] == "fail" for x in pii), "personal marker not caught"


def test_security_review_clean_repo_stays_clean(tmp_path):
    """No false positives on an innocent repo (the inverse property)."""
    import security_review as sr
    repo = tmp_path / "cleanrepo"
    repo.mkdir()
    run = lambda *a: subprocess.run(["git", "-C", str(repo), *a], check=True,
                                    capture_output=True)
    run("init", "-q")
    run("config", "user.email", "t@t.t")
    run("config", "user.name", "T")
    (repo / "ok.py").write_text("import json\nx = json.loads('{}')\n")
    (repo / ".gitignore").write_text(".env\n.finance/\nbackups/\nvault/\n")
    run("add", "-A")
    run("commit", "-qm", "clean")
    tracked = subprocess.run(["git", "-C", str(repo), "ls-files"], capture_output=True,
                             text=True).stdout.splitlines()
    assert not [x for x in sr._check_repo_leaks(str(repo), tracked) if x["status"] == "fail"]
    assert not [x for x in sr._check_personal_data(str(repo)) if x["status"] == "fail"]
