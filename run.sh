#!/bin/bash
# Local app. By default your data lives OUTSIDE the repo (see README > Data &
# privacy); set FINANCE_PROJECT_DIR to override. An existing ./.finance keeps
# working in place. See README.
set -euo pipefail
APP_DIR="$(cd "$(dirname "$0")" && pwd)"
PORT="${PORT:-8321}"

# Interpreter: prefer .venv (has EVERY dependency, incl. pytrends for the barometer)
# over the system python3 — a system interpreter without pytrends silently loses
# the monthly barometer point (collector returns ok:False).
if [ -x "$APP_DIR/.venv/bin/python" ]; then
  PY="$APP_DIR/.venv/bin/python"
else
  PY="python3"
fi
"$PY" -c "import flask, pytrends" 2>/dev/null || "$PY" -m pip install -q -r "$APP_DIR/requirements.txt"

# A previous instance (nohup, another terminal) keeps the port and Flask dies with
# "Address already in use"; ./run.sh means "run the current code", so stop it first.
if pkill -f "$APP_DIR/server/app.py" 2>/dev/null; then
  for _ in $(seq 1 20); do lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1 || break; sleep 0.25; done
  echo "[kist] previous instance stopped"
fi

( sleep 1.5 && open "http://127.0.0.1:$PORT" ) &
exec "$PY" "$APP_DIR/server/app.py"
