"""Pytest fixtures: a throwaway seeded DB + a Flask test client.

Each session gets its own temp FINANCE_PROJECT_DIR (never touches real data),
seeded via seed.py exactly as a fresh clone would be.
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))


@pytest.fixture(scope="session")
def data_dir():
    tmp = tempfile.mkdtemp(prefix="financeapp-test-")
    env = dict(os.environ, FINANCE_PROJECT_DIR=tmp)
    subprocess.run([sys.executable, str(ROOT / "seed.py")],
                   check=True, env=env, capture_output=True)
    os.environ["FINANCE_PROJECT_DIR"] = tmp
    yield tmp
    shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture(scope="session")
def client(data_dir):
    import config
    config.setup()
    import app as flask_app
    flask_app.app.config.update(TESTING=True)
    with flask_app.app.test_client() as c:
        yield c
