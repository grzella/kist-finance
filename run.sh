#!/bin/bash
# Local app. By default your data lives OUTSIDE the repo (see README > Data &
# privacy); set FINANCE_PROJECT_DIR to override. An existing ./.finance keeps
# working in place. See README.
set -euo pipefail
APP_DIR="$(cd "$(dirname "$0")" && pwd)"
PORT="${PORT:-8321}"

python3 -c "import flask" 2>/dev/null || pip3 install --user -q -r "$APP_DIR/requirements.txt"

( sleep 1.5 && open "http://127.0.0.1:$PORT" ) &
exec python3 "$APP_DIR/server/app.py"
