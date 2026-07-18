"""App configuration: .env parsing and path resolution."""
import os
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent          # financeapp root (server/..)


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
    stage your finances). macOS: ~/Library/Application Support/financeapp;
    Linux: $XDG_DATA_HOME or ~/.local/share/financeapp."""
    home = Path.home()
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "financeapp"
    return Path(os.environ.get("XDG_DATA_HOME", home / ".local" / "share")) / "financeapp"


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
