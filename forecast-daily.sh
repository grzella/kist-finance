#!/bin/bash
# Daily self-learning cycle for the forecast journal — WITHOUT the app running.
#
# Why this exists: `forecast_cycle` is only triggered from /api/health, i.e.
# whenever you happen to open the app. On the maintainer's instance that left
# multi-day holes (Aug 2026: entries on the 15th, 14th, 11th, 10th, 7th, 3rd,
# 2nd). The bands calibrate themselves on their own past errors, so an
# irregular cycle means irregular calibration.
#
# So this script does NOT talk to the HTTP API — it calls the engine directly
# and works whether or not the server is up. Schedule it once and the journal
# advances every day (see README > Forecasts).
#
# Three steps, in this order:
#   1. fresh quotes  — without them there is nothing to settle matured forecasts against
#   2. learning cycle — settle matured bands, then record today's
#   3. risk radar    — the daily reading, also previously tied to opening the app
#
# Best-effort: no network or a Yahoo hiccup is not a failure — it retries
# tomorrow. Always exits 0 so a scheduler does not flag the job as broken.
#
# Usage:  ./forecast-daily.sh          (honours FINANCE_PROJECT_DIR, like run.sh)
set -uo pipefail
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="${KIST_LOG_DIR:-$APP_DIR/logs}"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/forecast-$(date +%Y-%m-%d).log"

# Prefer the repo venv (matched to CI, see pytest.ini); fall back to system python.
PY="$APP_DIR/.venv/bin/python"
[ -x "$PY" ] || PY="$(command -v python3)"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] start (python: $PY)" >>"$LOG"

cd "$APP_DIR" || exit 0
"$PY" - >>"$LOG" 2>&1 <<'PYEOF'
import sys
sys.path.insert(0, "server")
import config
config.setup()
import engine_bridge  # noqa: F401 — sets sys.path for the engine modules
import market

def step(name, fn):
    try:
        print(f"  {name}: {fn()}")
    except Exception as e:
        print(f"  {name}: ERROR {type(e).__name__}: {str(e)[:120]}")

step("quotes", lambda: {k: v for k, v in market.refresh_cache().items()
                        if k in ("rows", "stale_days", "data_through", "yahoo_topup")})
step("learning cycle", market.record_and_score_forecasts)

def radar():
    import risk_radar
    return risk_radar.snapshot()
step("risk radar", radar)

# Current self-calibration, so the log itself says whether learning is on track.
try:
    s = market.forecast_selfscore()
    for h in s.get("horizons", []):
        print(f"  coverage h={h['days']}d: {h['coverage_pct']}% "
              f"(target {h['target_pct']}%, n={h['scored']}) -> {h['verdict']}")
except Exception as e:
    print(f"  selfscore: ERROR {type(e).__name__}: {str(e)[:120]}")
PYEOF

echo "[$(date '+%Y-%m-%d %H:%M:%S')] done" >>"$LOG"

# Logs older than 30 days serve no purpose.
find "$LOG_DIR" -name "forecast-*.log" -type f -mtime +30 -delete 2>/dev/null

exit 0
