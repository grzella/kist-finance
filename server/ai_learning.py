"""AI learning, scored from your own repositories.

Evidence is collected by code (local git repos from `commit_repos` + the repos of the logged-in
`gh` account), the rubric and the score are computed by code, and the local model only writes
the narration. Nothing here calls a cloud model, and the model never sees file contents: only
the short evidence lines and the computed levels.
"""
import json
import os
import re
import subprocess
from pathlib import Path

import planner

MAX_REPOS = 20
MAX_AUTHOR = 100


# ---------- repositories you point the scoring (and the Committing tab) at ----------

def configured_repos():
    """Paths from the `commit_repos` setting (env COMMIT_REPOS as the fallback, like the tracker)."""
    raw = (planner.get_setting("commit_repos") or os.environ.get("COMMIT_REPOS", "")).strip()
    return [p.strip() for p in raw.split(",") if p.strip()]


def repos_config():
    return {"repos": configured_repos(),
            "author": (planner.get_setting("commit_author") or os.environ.get("COMMIT_AUTHOR", "")).strip()}


def _check_repo_path(raw):
    """(resolved path, None) or (None, reason). Only existing git working copies are accepted,
    and no comma (the setting is a comma-separated list)."""
    if not isinstance(raw, str) or not raw.strip():
        return None, "not a path string"
    if "," in raw or "\n" in raw or "\x00" in raw:
        return None, "commas, newlines and NUL are not allowed in a path"
    p = Path(raw.strip()).expanduser()
    if not p.is_absolute():
        return None, "must be an absolute path"
    if not p.exists():
        return None, "path does not exist"
    if not p.is_dir() or not (p / ".git").exists():
        return None, "not a git repository (no .git inside)"
    return str(p.resolve()), None


def set_repos(body):
    """Validate and store `repos` (list of absolute paths of git repos) and `author` (a git
    --author filter). Returns (result, error); error is a message for a 400."""
    if not isinstance(body, dict):
        return None, "body must be an object"
    repos = body.get("repos", [])
    if not isinstance(repos, list):
        return None, "repos must be a list of paths"
    if len(repos) > MAX_REPOS:
        return None, f"at most {MAX_REPOS} repositories"
    author = body.get("author", "")
    author = author.strip() if isinstance(author, str) else None
    if author is None or len(author) > MAX_AUTHOR or author.startswith("-") or "\n" in author or "\x00" in author:
        return None, "author must be a short text without newlines that does not start with '-'"
    good, rejected = [], []
    for raw in repos:
        path, why = _check_repo_path(raw)
        if why:
            rejected.append({"path": str(raw)[:200], "reason": why})
        elif path not in good:
            good.append(path)
    planner.set_settings({"commit_repos": ",".join(good), "commit_author": author})
    return {**repos_config(), "rejected": rejected}, None


# ---------- the rubric: fixed, so a score from March and one from June are comparable ----------

LEVELS = [
    {"lvl": 0, "name": "Observer", "desc": "Reads about AI, has not changed how they work."},
    {"lvl": 1, "name": "User", "desc": "Uses chat assistants for drafting and research."},
    {"lvl": 2, "name": "Practitioner", "desc": "Calls models from code, keeps prompts and small automations, checks outputs."},
    {"lvl": 3, "name": "Orchestrator", "desc": "Chains models, retrieval and tools into workflows with evals and logging."},
    {"lvl": 4, "name": "Architect", "desc": "Designs AI systems end to end: data, retrieval, evals, cost, failure modes."},
    {"lvl": 5, "name": "Authority", "desc": "Others reuse their methods; shapes the practice beyond their own team."},
]

# Each skill is looked for in three places: dependency manifests (`dep`), file paths (`path`)
# and text (`text`: commit subjects, README, repo description and topics). Patterns are regexes
# on lowercase text. weight: how much the skill counts toward the level.
SKILLS = [
    {"id": "prompting", "area": "Foundations", "name": "Prompts as versioned assets", "weight": 1,
     "how": "Keep prompts in files, version them and score the best ones as tested templates.",
     "link": "https://www.promptingguide.ai/",
     "dep": ["promptflow", "guidance", "dspy"], "path": [r"prompts?[/_.-]", r"\.prompt\b"], "text": [r"\bprompts?\b"]},
    {"id": "llm-api", "area": "Foundations", "name": "Calling models from code", "weight": 1,
     "how": "Call a hosted and a local model from code on the same task and compare the results.",
     "dep": ["openai", "anthropic", "litellm", "google-generativeai", "mistralai", "cohere", "ollama", "transformers"],
     "text": [r"\bllm\b", r"\b(openai|anthropic|claude|gpt)\b"]},
    {"id": "structured", "area": "Foundations", "name": "Structured output", "weight": 1,
     "how": "Constrain model output with a schema and validate it before using it.",
     "dep": ["pydantic", "instructor", "outlines", "jsonschema"], "text": [r"json[ _-]?schema", r"structured output", r"grammar"]},
    {"id": "rag", "area": "Building", "name": "Retrieval (RAG)", "weight": 2,
     "how": "Build one retrieval pipeline, then try chunking and hybrid keyword + embedding search.",
     "link": "https://github.com/mlabonne/llm-course",
     "dep": ["faiss", "chromadb", "qdrant", "lancedb", "pgvector", "sentence-transformers", "rank-bm25", "rank_bm25",
             "llama-index", "llama_index", "weaviate", "pinecone", "sqlite-vec"],
     "path": [r"(^|/)rag[/_.-]", r"retriev", r"embed"], "text": [r"\brag\b", r"retriev", r"embedding", r"\bbm25\b", r"rerank"]},
    {"id": "agents", "area": "Building", "name": "Tool use and agents", "weight": 2,
     "how": "Wire a model to two real tools with a hard step limit and logged calls.",
     "link": "https://github.com/huggingface/agents-course",
     "dep": ["langgraph", "autogen", "crewai", "mcp", "fastmcp", "smolagents", "pydantic-ai", "openai-agents"],
     "path": [r"(^|/)agents?[/_.-]", r"(^|/)tools?[/_.-]", r"\bmcp\b"],
     "text": [r"\bagents?\b", r"tool[ -]?(use|call)", r"\bmcp\b", r"function call"]},
    {"id": "local", "area": "Building", "name": "Running a local model", "weight": 1,
     "how": "Run a quantised model locally for private data and measure it against a hosted one.",
     "link": "https://github.com/ggml-org/llama.cpp",
     "dep": ["llama-cpp-python", "ollama", "vllm", "mlx", "mlx-lm", "gguf", "onnxruntime", "ctransformers"],
     "text": [r"llama\.cpp", r"\bollama\b", r"\bgguf\b", r"quantiz", r"local (llm|model)"]},
    {"id": "workflows", "area": "Building", "name": "Workflow automation", "weight": 1,
     "how": "Automate one recurring task as a workflow with a model step and a human check.",
     "dep": ["n8n", "prefect", "airflow", "dagster", "temporalio"], "path": [r"n8n", r"workflows?\.json"],
     "text": [r"\bn8n\b", r"automation"]},
    {"id": "evals", "area": "Quality", "name": "Evals and regression sets", "weight": 3,
     "how": "A gold set of 30 to 50 cases per workflow, scored on every prompt or model change.",
     "link": "https://hamel.dev/blog/posts/evals/",
     "dep": ["ragas", "deepeval", "promptfoo", "lm-eval", "lm_eval", "trulens", "inspect-ai", "langsmith"],
     "path": [r"(^|/)evals?[/_.-]", r"gold", r"benchmark"],
     "text": [r"\bevals?\b", r"gold set", r"benchmark", r"regression (set|test)", r"recall@", r"\bmrr\b"]},
    {"id": "observability", "area": "Quality", "name": "Logging and review of real usage", "weight": 1,
     "how": "Log prompts and answers with ratings and review the ten worst ones every month.",
     "dep": ["langfuse", "opentelemetry-api", "arize-phoenix", "helicone", "wandb", "mlflow", "structlog"],
     "path": [r"llm[_-]?log", r"tracing"], "text": [r"llm log", r"prompt log", r"tracing", r"observab", r"langfuse"]},
    {"id": "safety", "area": "Quality", "name": "Privacy and prompt injection", "weight": 1,
     "how": "Keep private data local and treat retrieved text as untrusted input.",
     "dep": ["presidio-analyzer", "guardrails-ai", "nemo-guardrails", "llm-guard"],
     "path": [r"guardrail", r"sanitiz"], "text": [r"injection", r"guardrail", r"\bpii\b", r"redact", r"sanitiz", r"threat model"]},
    {"id": "cost", "area": "Quality", "name": "Cost and latency budgeting", "weight": 1,
     "how": "Estimate cost per task before building and measure latency on the real workflow.",
     "dep": ["tiktoken"], "text": [r"\bcost\b", r"latency", r"\btokens?\b", r"cache", r"batch"]},
    {"id": "docs", "area": "Leadership", "name": "Writing it down: docs and guidelines", "weight": 1,
     "how": "A one-page guideline: what data may go where, what must be verified, who reviews.",
     "path": [r"^docs?/", r"decisions", r"guideline", r"policy", r"playbook", r"(^|/)adr"],
     "text": [r"guideline", r"playbook", r"workshop", r"\bdocs?\b"]},
]

# Free, openly licensed courses (links only, nothing is copied). `skills`: the gaps they close.
COURSES = [
    {"id": "genai-beginners", "name": "Generative AI for Beginners (21 lessons)", "provider": "Microsoft (MIT)",
     "cost": "free", "time": "self-paced", "format": "online", "skills": ["llm-api", "prompting", "structured"],
     "why": "Hands-on lessons from prompting to apps; the quickest way to fill the foundations.",
     "link": "https://github.com/microsoft/generative-ai-for-beginners"},
    {"id": "llm-course", "name": "LLM Course: fundamentals, scientist and engineer tracks", "provider": "Maxime Labonne (Apache 2.0)",
     "cost": "free", "time": "self-paced", "format": "online", "skills": ["rag", "local", "cost"],
     "why": "Roadmap plus notebooks for retrieval, quantisation and serving.",
     "link": "https://github.com/mlabonne/llm-course"},
    {"id": "agents-course", "name": "AI Agents Course", "provider": "Hugging Face (Apache 2.0)",
     "cost": "free", "time": "self-paced", "format": "online", "skills": ["agents", "workflows"],
     "why": "Builds agents with tools step by step.",
     "link": "https://github.com/huggingface/agents-course"},
    {"id": "evals-notes", "name": "Your AI product needs evals", "provider": "Hamel Husain",
     "cost": "free", "time": "1 to 2 h", "format": "online", "skills": ["evals", "observability"],
     "why": "The shortest practical route from no evals to a regression set you trust.",
     "link": "https://hamel.dev/blog/posts/evals/"},
    {"id": "short-courses", "name": "Short courses on agents, evals and safety", "provider": "DeepLearning.AI",
     "cost": "free", "time": "1 to 3 h each", "format": "online", "skills": ["evals", "safety", "agents"],
     "why": "Small, focused notebooks for the quality and safety gaps.",
     "link": "https://www.deeplearning.ai/short-courses/"},
]

SOURCES = {
    "method": "Three layers so that staying current costs minutes, not evenings: a daily skim, a weekly deep read, a quarterly reset.",
    "daily": [{"name": "Simon Willison's weblog", "link": "https://simonwillison.net/",
               "what": "Hands-on notes on new models and tools, with working examples."}],
    "weekly": [{"name": "Latent Space", "link": "https://www.latent.space/",
                "what": "Interviews and write-ups from people shipping AI systems."},
               {"name": "Hamel Husain's blog", "link": "https://hamel.dev/blog/",
                "what": "Practical evals and debugging of LLM applications."}],
    "quarterly": [{"name": "Prompting Guide", "link": "https://www.promptingguide.ai/",
                   "what": "Re-read the techniques list and retire what newer models made unnecessary."}],
    "services": [{"name": "Hugging Face papers", "link": "https://huggingface.co/papers",
                  "what": "Daily curated research papers, upvoted by practitioners."},
                 {"name": "GitHub trending (Python)", "link": "https://github.com/trending/python",
                  "what": "What the open-source community is building this week."}],
}

ROUTINE = [
    "Monday: pick one workflow to measure this week.",
    "Friday: write the log entry, even if the result was negative.",
    "Monthly: review the ten worst answers from your prompt log.",
    "Quarterly: score again from your repositories and archive what stopped mattering.",
]


# ---------- evidence: deterministic, from git and gh; contents are matched, never sent anywhere ----------

MAX_FILES = 5000          # paths read per repo
MAX_COMMITS = 30
MAX_TEXT = 20000          # chars read from the README and from each dependency manifest
MANIFESTS = {"requirements.txt", "requirements-dev.txt", "pyproject.toml", "package.json", "pipfile",
             "cargo.toml", "go.mod"}
README_NAMES = ("README.md", "README.rst", "README.txt", "README")


def _run(cmd, timeout=15):
    """stdout of a command, or None on any failure (missing binary, not logged in, timeout)."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout if r.returncode == 0 else None
    except Exception:
        return None


def _read_inside(repo, rel):
    """Text of a regular file inside the repo; symlinks are skipped so a link can't pull in
    anything from outside the working copy."""
    p = Path(repo) / rel
    try:
        if p.is_symlink() or not p.is_file():
            return ""
        return p.read_text(encoding="utf-8", errors="ignore")[:MAX_TEXT]
    except Exception:
        return ""


def _source(name, origin, **kw):
    return {"name": name, "origin": origin, "deps": "", "paths": [], "commits": [], "readme": "", "meta": "", **kw}


def collect_local(repo, author=""):
    git = ["git", "-c", "core.fsmonitor=false", "-C", repo]
    paths = [x for x in (_run(git + ["ls-files"], 20) or "").splitlines()][:MAX_FILES]
    log = git + ["log", f"-n{MAX_COMMITS}", "--format=%s"]
    if author:
        log.insert(len(git) + 1, f"--author={author}")
    commits = [x.strip() for x in (_run(log, 20) or "").splitlines() if x.strip()]
    manifests = [p for p in paths if p.count("/") <= 2 and p.rsplit("/", 1)[-1].lower() in MANIFESTS][:5]
    readme = next((t for t in (_read_inside(repo, n) for n in README_NAMES) if t), "")
    return _source(Path(repo).name, "local", paths=paths, commits=commits, readme=readme.lower(),
                   deps="\n".join(_read_inside(repo, m) for m in manifests).lower())


def collect_gh():
    """Your own non-fork repos on the logged-in GitHub account: name, description, topics and
    language only (no code). Empty when `gh` is missing, logged out or offline."""
    out = _run(["gh", "repo", "list", "--limit", "30", "--json",
                "name,description,isFork,repositoryTopics,primaryLanguage"])
    try:
        rows = json.loads(out) if out else []
    except ValueError:
        return []
    found = []
    for r in rows if isinstance(rows, list) else []:
        if not isinstance(r, dict) or r.get("isFork") or not r.get("name"):
            continue
        topics = " ".join(str((t or {}).get("name", "")) for t in (r.get("repositoryTopics") or []))
        lang = (r.get("primaryLanguage") or {}).get("name", "")
        meta = f"{r['name']} {r.get('description') or ''} {topics} {lang}".lower()
        found.append(_source(str(r["name"]), "gh", meta=meta))
    return found


def collect_sources():
    """Local repos first; a GitHub repo with the same name as a local one is the same project."""
    cfg = repos_config()
    local = [collect_local(p, cfg["author"]) for p in cfg["repos"]]
    seen = {s["name"].lower() for s in local}
    return local + [g for g in collect_gh() if g["name"].lower() not in seen]


def _first(rx, text):
    m = re.search(rx, text)
    return m.group(0) if m else None


def match(source):
    """{skill id: [(kind, detail), ...]} for one source. Details are short and are the only
    thing that is stored, shown or handed to the model."""
    hits = {}
    paths = [p.lower() for p in source["paths"]]
    for sk in SKILLS:
        found = []
        for frag in sk.get("dep", []):
            if re.search(r"(?<![a-z0-9])" + re.escape(frag) + r"(?![a-z0-9])", source["deps"]):
                found.append(("dep", frag))
        for rx in sk.get("path", []):
            hit = next((p for p in paths if re.search(rx, p)), None)
            if hit:
                found.append(("path", hit[:90]))
        for rx in sk.get("text", []):
            commit = next((c for c in source["commits"] if re.search(rx, c.lower())), None)
            if commit:
                found.append(("commit", commit[:90]))
            word = _first(rx, source["readme"])
            if word:
                found.append(("readme", word[:90]))
            word = _first(rx, source["meta"])
            if word:
                found.append(("repo info", word[:90]))
        if found:
            hits[sk["id"]] = found
    return hits


# ---------- statuses, score, project grades: all arithmetic, no model ----------

KIND_ORDER = ("dep", "path", "commit", "readme", "repo info")
POINTS = {"have": 1.0, "partial": 0.5, "missing": 0.0}
MAX_EVIDENCE = 3
MAX_PROJECTS = 6


def _status(hits):
    """have: at least three distinct hits from at least two kinds of evidence (a dependency
    plus a folder plus a commit is a habit, three commit messages are a mention);
    partial: any hit; missing: none."""
    if len(hits) >= 3 and len({h[1] for h in hits}) >= 2:
        return "have"
    return "partial" if hits else "missing"


def _grade(n):
    return "A" if n >= 6 else "B" if n >= 4 else "C" if n >= 2 else "D"


def assess(sources):
    """The whole assessment minus the narration. Same repos, same answer."""
    per_skill = {s["id"]: [] for s in SKILLS}
    projects = []
    for src in sources:
        hits = match(src)
        for sid, found in hits.items():
            per_skill[sid] += [(src["name"], kind, detail) for kind, detail in found]
        if hits:
            projects.append({"name": src["name"], "origin": src["origin"], "n": len(hits),
                             "skills": [s["name"] for s in SKILLS if s["id"] in hits]})
    skills, earned = [], 0.0
    for sk in SKILLS:
        hits = list(dict.fromkeys(per_skill[sk["id"]]))
        hits.sort(key=lambda h: KIND_ORDER.index(h[1]))
        status = _status(hits)
        earned += sk["weight"] * POINTS[status]
        skills.append({"id": sk["id"], "area": sk["area"], "name": sk["name"], "status": status,
                       "how": sk["how"], **({"link": sk["link"]} if sk.get("link") else {}),
                       "evidence": [f"{n} · {k}: {d}"[:140] for n, k, d in hits[:MAX_EVIDENCE]]})
    score = round(5 * earned / sum(s["weight"] for s in SKILLS), 1)
    level = int(score)
    projects.sort(key=lambda p: -p["n"])
    return {
        "score": score, "level": level, "level_name": LEVELS[level]["name"], "target": min(5, level + 1),
        "counts": {k: sum(1 for s in skills if s["status"] == k) for k in POINTS},
        "skills": skills,
        "projects": [{"name": p["name"], "origin": p["origin"], "grade": _grade(p["n"]), "skills": p["skills"]}
                     for p in projects[:MAX_PROJECTS]],
    }
