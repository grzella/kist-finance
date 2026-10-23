"""AI learning: scoring from your own repositories (repos config, rubric, evidence, score, history).
No network, no live model: git runs on throwaway repos, `gh` and the local LLM are stubbed."""
import json
import subprocess

import pytest


def _git(path, *args):
    subprocess.run(["git", "-C", str(path), "-c", "user.name=T", "-c", "user.email=t@example.com", *args],
                   check=True, capture_output=True)


def make_repo(path, files, commits=("initial commit",)):
    """A throwaway git repo with `files` {relative path: text} and one empty commit per message."""
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True, capture_output=True)
    for rel, text in files.items():
        f = path / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text, encoding="utf-8")
    _git(path, "add", "-A")
    first, *rest = commits
    _git(path, "commit", "-q", "-m", first)
    for msg in rest:
        _git(path, "commit", "-q", "--allow-empty", "-m", msg)
    return path


@pytest.fixture
def clean_settings(client):
    import planner
    keys = ("commit_repos", "commit_author", "analysis_ai_learning", "ai_learning_state", "ai_learning_history")
    planner.set_settings({k: "" for k in keys})
    yield
    planner.set_settings({k: "" for k in keys})


# ---------- 1. repo config endpoint ----------

def test_repos_get_is_empty_on_a_fresh_install(client, clean_settings):
    d = client.get("/api/ai-learning/repos").get_json()
    assert d["repos"] == [] and d["author"] == ""


def test_repos_put_saves_valid_git_repos_and_reports_the_rest(client, clean_settings, tmp_path):
    good = make_repo(tmp_path / "good", {"README.md": "hi"})
    plain = tmp_path / "plain"
    plain.mkdir()
    r = client.put("/api/ai-learning/repos", json={
        "repos": [str(good), str(good), str(plain), "relative/path", str(tmp_path / "missing"), 42, "a,b"],
        "author": "  Alex Demo "})
    assert r.status_code == 200
    d = r.get_json()
    assert d["repos"] == [str(good.resolve())]                      # deduped, resolved
    assert d["author"] == "Alex Demo"
    why = {x["path"]: x["reason"] for x in d["rejected"]}
    assert "not a git repository" in why[str(plain)]
    assert "absolute" in why["relative/path"]
    assert "does not exist" in why[str(tmp_path / "missing")]
    assert len(d["rejected"]) == 5                                   # 42, "a,b", relative, missing, plain
    # the same value is what the commit tracker reads
    import planner
    assert planner.get_setting("commit_repos") == str(good.resolve())
    assert client.get("/api/ai-learning/repos").get_json()["repos"] == [str(good.resolve())]


def test_repos_put_rejects_a_bad_body_and_too_many_repos(client, clean_settings, tmp_path):
    assert client.put("/api/ai-learning/repos", json=[1]).status_code == 400
    assert client.put("/api/ai-learning/repos", json={"repos": "nope"}).status_code == 400
    many = [make_repo(tmp_path / f"r{i}", {"a.txt": "x"}) for i in range(21)]
    r = client.put("/api/ai-learning/repos", json={"repos": [str(p) for p in many]})
    assert r.status_code == 400 and "at most 20" in r.get_json()["error"]


def test_repos_put_author_cannot_smuggle_options_or_newlines(client, clean_settings):
    for bad in ("--exec=evil", "a\nb", "x" * 101):
        r = client.put("/api/ai-learning/repos", json={"repos": [], "author": bad})
        assert r.status_code == 400, bad
    import planner
    assert not planner.get_setting("commit_author")


def test_repos_put_is_blocked_cross_origin(client, clean_settings):
    r = client.put("/api/ai-learning/repos", json={"repos": []}, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403


def test_generic_settings_writer_still_cannot_set_commit_repos(client, clean_settings):
    client.put("/api/settings", json={"commit_repos": "/etc"})
    import planner
    assert not planner.get_setting("commit_repos")
