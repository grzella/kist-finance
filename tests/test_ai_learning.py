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


# ---------- 2. rubric and evidence ----------

def test_rubric_is_well_formed():
    import ai_learning as al
    assert [l["lvl"] for l in al.LEVELS] == [0, 1, 2, 3, 4, 5]
    ids = [s["id"] for s in al.SKILLS]
    assert len(ids) == len(set(ids)) >= 10
    for s in al.SKILLS:
        assert s["weight"] in (1, 2, 3) and s["how"] and s["area"] and s["name"]
        assert any(s.get(k) for k in ("dep", "path", "text")), s["id"]
        assert not s.get("link") or s["link"].startswith("https://")
    for c in al.COURSES:
        assert c["link"].startswith("https://") and set(c["skills"]) <= set(ids)


def test_collect_local_reads_deps_paths_commits_and_readme(tmp_path):
    import ai_learning as al
    repo = make_repo(tmp_path / "copilot", {
        "README.md": "A small copilot with retrieval over notes.",
        "requirements.txt": "flask\nchromadb==0.5\nopenai\n",
        "evals/gold.jsonl": "{}",
        "src/app.py": "print(1)"}, commits=("first", "add bm25 reranking", "fix typo"))
    s = al.collect_local(str(repo))
    assert s["name"] == "copilot" and s["origin"] == "local"
    assert "chromadb" in s["deps"] and "evals/gold.jsonl" in s["paths"]
    assert "add bm25 reranking" in s["commits"]
    assert "retrieval" in s["readme"]


def test_collect_local_author_filter_and_limits(tmp_path):
    import ai_learning as al
    repo = make_repo(tmp_path / "r", {"a.txt": "x"}, commits=("mine",))
    assert al.collect_local(str(repo), author="T")["commits"] == ["mine"]
    assert al.collect_local(str(repo), author="Nobody Else")["commits"] == []


def test_collect_local_never_follows_a_symlinked_readme_or_manifest(tmp_path):
    import ai_learning as al
    secret = tmp_path / "outside.txt"
    secret.write_text("chromadb openai langfuse", encoding="utf-8")
    repo = make_repo(tmp_path / "r", {"a.txt": "x"})
    (repo / "README.md").symlink_to(secret)
    (repo / "requirements.txt").symlink_to(secret)
    _git(repo, "add", "-A")
    s = al.collect_local(str(repo))
    assert s["readme"] == "" and s["deps"] == ""


def test_collect_local_survives_a_broken_repo(tmp_path):
    import ai_learning as al
    s = al.collect_local(str(tmp_path / "gone"))
    assert s["paths"] == [] and s["commits"] == []


def test_collect_gh_maps_repos_and_skips_forks_and_failures(monkeypatch):
    import ai_learning as al
    payload = json.dumps([
        {"name": "rag-notes", "description": "Retrieval over my notes", "isFork": False,
         "repositoryTopics": [{"name": "llm"}], "primaryLanguage": {"name": "Python"}},
        {"name": "someone-elses", "description": "x", "isFork": True, "repositoryTopics": None}])
    monkeypatch.setattr(al, "_run", lambda cmd, timeout=15: payload)
    got = al.collect_gh()
    assert [g["name"] for g in got] == ["rag-notes"] and got[0]["origin"] == "gh"
    assert "retrieval" in got[0]["meta"] and "llm" in got[0]["meta"]
    monkeypatch.setattr(al, "_run", lambda cmd, timeout=15: None)    # gh missing or logged out
    assert al.collect_gh() == []
    monkeypatch.setattr(al, "_run", lambda cmd, timeout=15: "not json")
    assert al.collect_gh() == []


def test_collect_sources_merges_local_and_gh_without_double_counting(client, clean_settings, tmp_path, monkeypatch):
    import ai_learning as al
    repo = make_repo(tmp_path / "rag-notes", {"a.txt": "x"})
    client.put("/api/ai-learning/repos", json={"repos": [str(repo)]})
    monkeypatch.setattr(al, "_run", lambda cmd, timeout=15: json.dumps(
        [{"name": "rag-notes", "description": "", "isFork": False, "repositoryTopics": [], "primaryLanguage": None},
         {"name": "other", "description": "", "isFork": False, "repositoryTopics": [], "primaryLanguage": None}]))
    names = [(s["name"], s["origin"]) for s in al.collect_sources()]
    assert names == [("rag-notes", "local"), ("other", "gh")]


def test_match_finds_evidence_per_skill_and_keeps_lines_short(tmp_path):
    import ai_learning as al
    repo = make_repo(tmp_path / "copilot", {
        "README.md": "Uses retrieval.", "requirements.txt": "chromadb\nragas\n",
        "evals/gold.jsonl": "{}"}, commits=("first", "x" * 300 + " eval harness"))
    hits = al.match(al.collect_local(str(repo)))
    assert {"rag", "evals"} <= set(hits)
    kinds = {k for k, _ in hits["evals"]}
    assert {"dep", "path"} <= kinds
    assert all(len(d) <= 100 for _, d in hits["evals"] + hits["rag"])
    assert "prompting" not in hits                                   # nothing to see there
