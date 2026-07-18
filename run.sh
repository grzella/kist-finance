#!/bin/bash
# Home Budget — local app. Personal data stays in ./.finance (gitignored). See README.
set -euo pipefail
APP_DIR="$(cd "$(dirname "$0")" && pwd)"
export FINANCE_PROJECT_DIR="$APP_DIR"
PORT="${PORT:-8321}"

python3 -c "import flask" 2>/dev/null || pip3 install --user -q -r "$APP_DIR/requirements.txt"

( sleep 1.5 && open "http://127.0.0.1:$PORT" ) &
exec python3 "$APP_DIR/server/app.py"
