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


# ---------- 3. statuses, score, project grades ----------

def src(name="p", **kw):
    import ai_learning as al
    return al._source(name, kw.pop("origin", "local"), **kw)


def test_empty_evidence_scores_zero_and_everything_is_missing():
    import ai_learning as al
    a = al.assess([src()])
    assert a["score"] == 0.0 and a["level"] == 0 and a["level_name"] == "Observer"
    assert {s["status"] for s in a["skills"]} == {"missing"} and a["projects"] == []
    assert al.assess([])["score"] == 0.0


def test_status_thresholds_partial_on_one_hit_have_on_three_across_two_kinds():
    import ai_learning as al
    one = {s["id"]: s for s in al.assess([src(deps="ragas")])["skills"]}
    assert one["evals"]["status"] == "partial" and one["evals"]["evidence"] == ["p · dep: ragas"]
    one_kind = {s["id"]: s for s in al.assess([src(commits=["eval one", "gold set two", "benchmark three"])])["skills"]}
    assert one_kind["evals"]["status"] == "partial"                  # several hits but a single kind
    strong = {s["id"]: s for s in al.assess([src(deps="ragas", paths=["evals/gold.jsonl"],
                                                 commits=["eval harness"])])["skills"]}
    assert strong["evals"]["status"] == "have"


def test_hits_from_several_repos_add_up_and_evidence_is_capped_and_deduped():
    import ai_learning as al
    a = al.assess([src("one", deps="ragas"), src("two", paths=["evals/a.json"], commits=["eval harness"])])
    ev = {s["id"]: s for s in a["skills"]}["evals"]
    assert ev["status"] == "have"
    assert ev["evidence"] == ["one · dep: ragas", "two · path: evals/a.json", "two · commit: eval harness"]
    many = al.assess([src(paths=[f"evals/{i}.json" for i in range(9)], deps="ragas deepeval promptfoo")])
    assert len({s["id"]: s for s in many["skills"]}["evals"]["evidence"]) <= 3


def test_score_is_the_weighted_share_of_the_scale():
    import ai_learning as al
    total = sum(s["weight"] for s in al.SKILLS)
    a = al.assess([src(deps="ragas", paths=["evals/gold.jsonl"], commits=["eval harness"])])
    st = {s["id"]: s["status"] for s in a["skills"]}
    assert st["evals"] == "have"
    earned = sum(s["weight"] * {"have": 1, "partial": .5, "missing": 0}[st[s["id"]]] for s in al.SKILLS)
    assert a["score"] == round(5 * earned / total, 1) and 0 < a["score"] < 5
    assert a["level"] == int(a["score"]) and a["level_name"] == al.LEVELS[a["level"]]["name"]
    assert a["target"] == min(5, a["level"] + 1)
    assert a["counts"] == {k: sum(1 for v in st.values() if v == k) for k in ("have", "partial", "missing")}


def test_everything_present_caps_at_five():
    import ai_learning as al
    blob = " ".join(f for s in al.SKILLS for f in s.get("dep", []))
    paths = ["docs/a.md", "evals/gold.jsonl", "prompts/a.txt", "rag/a.py", "agents/a.py", "n8n/a.json",
             "llm_log.py", "guardrails.py", "retrieval/e.py"]
    a = al.assess([src(deps=blob, paths=paths, commits=["eval", "rag", "agent", "prompt", "cost", "docs"],
                       readme="llm rag agent injection ollama n8n automation json schema latency guideline")])
    assert a["score"] == 5.0 and a["level"] == 5 and a["target"] == 5


def test_projects_are_graded_by_how_many_skills_they_show_and_empty_ones_dropped():
    import ai_learning as al
    rich = src("rich", deps="chromadb ragas openai langgraph pydantic", paths=["evals/a.json"],
               commits=["prompt tweak"], readme="rag with ollama")
    thin = src("thin", deps="openai")
    nothing = src("nothing")
    a = al.assess([nothing, thin, rich])
    by = {p["name"]: p for p in a["projects"]}
    assert set(by) == {"rich", "thin"}
    assert by["rich"]["grade"] in ("A", "B") and by["thin"]["grade"] == "D"
    assert [p["name"] for p in a["projects"]] == ["rich", "thin"]    # best first
    assert by["thin"]["skills"] == ["Calling models from code"] and by["thin"]["origin"] == "local"
    assert len(al.assess([src(f"p{i}", deps="openai") for i in range(9)])["projects"]) == 6


# ---------- 4. the assembled assessment: model narrates, code decides ----------

RICH = dict(deps="chromadb ragas openai", paths=["evals/gold.jsonl"], commits=["add reranking", "eval harness"])


def test_build_without_a_model_uses_a_template_and_keeps_the_view_shape(monkeypatch):
    import ai_learning as al, llm_local
    monkeypatch.setattr(llm_local, "chat_json", lambda *a, **k: None)
    a = al.build([src("copilot", **RICH)], today="2026-10-23")
    assert a["as_of"] == "2026-10-23" and a["scale"] == al.LEVELS
    assert a["score_label"] == a["scale"][int(a["score"])]["name"] and a["target"] == min(5, int(a["score"]) + 1)
    assert a["generated"] == {"by": "repos", "narration": "template", "sources": {"local": 1, "gh": 0}}
    assert "skills show clear evidence" in a["verdict"] or "show evidence" in a["verdict"]
    p = a["projects"][0]
    assert p["name"] == "copilot" and p["grade"] and p["what"] and p["gap"]
    assert all(s["status"] in ("have", "partial", "missing") and s["how"] for s in a["skills"])
    assert a["sources"]["daily"] and a["routine"] and 1 <= len(a["plan_12m"]) <= 5
    assert a["plan_12m"][0].startswith("Months 1 to 2")


def test_certs_target_open_courses_for_the_gaps_only():
    import ai_learning as al
    a = al.build([src("copilot", **RICH)], today="2026-10-23", narrate=False)
    ids = {c["id"] for c in a["certs"]}
    assert "evals-notes" in ids and "agents-course" in ids           # evals partial, agents missing
    prio = {c["id"]: c["priority"] for c in a["certs"]}
    assert prio["agents-course"] == "high"                           # a missing weight-2 skill
    assert all(c["link"].startswith("https://") and c["format"] == "online" for c in a["certs"])
    full = al.build([src("x", deps=" ".join(f for s in al.SKILLS for f in s.get("dep", [])),
                         paths=["docs/a", "evals/g", "prompts/a", "rag/a", "agents/a", "n8n/a", "llm_log.py", "guardrails.py"],
                         commits=["eval", "rag", "agent", "prompt", "cost", "docs"],
                         readme="llm injection ollama n8n json schema latency guideline")],
                    today="2026-10-23", narrate=False)
    assert full["certs"] == []


def test_model_text_is_used_but_levels_and_grades_stay_computed(monkeypatch):
    import ai_learning as al, llm_local
    seen = {}

    def fake(prompt, schema, **kw):
        seen["prompt"], seen["kw"] = prompt, kw
        return {"verdict": "You build retrieval and measure it. Add a verifier next.",
                "projects": [{"name": "copilot", "what": "Retrieval with an eval set.", "gap": "Log real usage.",
                              "grade": "A", "score": 99}, {"name": "invented", "what": "x", "gap": "y"}]}
    monkeypatch.setattr(llm_local, "chat_json", fake)
    a = al.build([src("copilot", **RICH)], today="2026-10-23")
    assert a["generated"]["narration"] == "local model"
    assert a["verdict"].startswith("You build retrieval")
    assert [p["name"] for p in a["projects"]] == ["copilot"]         # the model cannot add repositories
    assert a["projects"][0]["what"] == "Retrieval with an eval set."
    assert a["projects"][0]["grade"] == al.assess([src("copilot", **RICH)])["projects"][0]["grade"]
    assert a["score"] < 5 and "score" not in a["projects"][0]        # and cannot set grades or scores
    assert seen["kw"].get("think") is False
    assert "dep: chromadb" in seen["prompt"]                          # evidence lines, not files


def test_model_numbers_not_in_the_facts_discard_the_narration(monkeypatch):
    import ai_learning as al, llm_local
    monkeypatch.setattr(llm_local, "chat_json", lambda *a, **k: {
        "verdict": "You are level 4.7 of 5, ranking in the top 3%.", "projects": []})
    a = al.build([src("copilot", **RICH)], today="2026-10-23")
    assert a["generated"]["narration"] == "template" and "3%" not in a["verdict"]


def test_model_garbage_falls_back_to_the_template(monkeypatch):
    import ai_learning as al, llm_local
    for bad in ({"verdict": ""}, {"verdict": 7, "projects": "x"}, [], "text"):
        monkeypatch.setattr(llm_local, "chat_json", lambda *a, _b=bad, **k: _b)
        a = al.build([src("copilot", **RICH)], today="2026-10-23")
        assert a["generated"]["narration"] == "template" and a["verdict"], bad
    monkeypatch.setattr(llm_local, "chat_json", lambda *a, **k: {"verdict": "ok " * 500, "projects": []})
    assert len(al.build([src("c", **RICH)], today="2026-10-23")["verdict"]) <= 900


def test_the_prompt_carries_only_computed_facts_not_file_contents(monkeypatch):
    import ai_learning as al, llm_local
    seen = {}
    monkeypatch.setattr(llm_local, "chat_json", lambda prompt, schema, **k: seen.update(p=prompt) or None)
    al.build([src("copilot", readme="TOP-SECRET-README-BODY rag", **RICH)], today="2026-10-23")
    assert "TOP-SECRET-README-BODY" not in seen["p"] and "copilot" in seen["p"] and "evals" in seen["p"].lower()
    assert len(seen["p"]) < 8000
