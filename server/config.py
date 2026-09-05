"""App configuration: .env parsing and path resolution."""
import os
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent          # Kist repo root (server/..)


def rag_default_dirs():
    """Markdown notes for the local RAG (beyond the app's tables): a `notes/` folder inside
    the DATA directory (`<FINANCE_PROJECT_DIR>/notes`), if present — private notes live with
    private data, and tests (temporary data dir) never index your real notes.
    Override with the `rag_dirs` setting (JSON list of paths)."""
    proj = os.environ.get("FINANCE_PROJECT_DIR")
    if not proj:
        return []
    d = Path(proj) / "notes"
    return [d] if d.is_dir() else []


def load_env():
    """Parse .env into os.environ (stdlib, no python-dotenv)."""
    env_file = APP_DIR / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def _external_data_dir():
    """A per-user app-data dir OUTSIDE the repo (so a stray `git add` can never
    stage your finances). macOS: ~/Library/Application Support/Kist;
    Linux: $XDG_DATA_HOME or ~/.local/share/kist."""
    home = Path.home()
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "Kist"
    return Path(os.environ.get("XDG_DATA_HOME", home / ".local" / "share")) / "kist"


def default_project_dir():
    """Where data lives when FINANCE_PROJECT_DIR isn't set explicitly.

    Backward-compatible: an existing install (repo has a `.finance/`) keeps its
    data in place; a fresh clone stores data outside the repo. Override anytime
    with the FINANCE_PROJECT_DIR env var."""
    if (APP_DIR / ".finance").exists():
        return str(APP_DIR)
    return str(_external_data_dir())


def setup():
    """Set FINANCE_PROJECT_DIR and load .env. Call before importing engines."""
    os.environ.setdefault("FINANCE_PROJECT_DIR", default_project_dir())
    load_env()
    return {
        "port": int(os.environ.get("PORT", "8321")),
        "supabase_url": os.environ.get("SUPABASE_URL", ""),
        "supabase_key": os.environ.get("SUPABASE_ANON_KEY", ""),
        "finance_dir": os.environ["FINANCE_PROJECT_DIR"] + "/.finance",
    }
