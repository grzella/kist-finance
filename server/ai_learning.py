"""AI learning, scored from your own repositories.

Evidence is collected by code (local git repos from `commit_repos` + the repos of the logged-in
`gh` account), the rubric and the score are computed by code, and the local model only writes
the narration. Nothing here calls a cloud model, and the model never sees file contents: only
the short evidence lines and the computed levels.
"""
import os
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
