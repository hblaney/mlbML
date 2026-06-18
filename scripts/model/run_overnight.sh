#!/usr/bin/env bash
# Overnight improvement loop — runs until 9:00 AM America/Chicago.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
LOG="$ROOT/data/overnight-improve.log"
mkdir -p "$ROOT/data"

end_epoch="$(python3 - <<'PY'
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
z = ZoneInfo("America/Chicago")
now = datetime.now(z)
target = now.replace(hour=9, minute=0, second=0, microsecond=0)
if now >= target:
    target += timedelta(days=1)
print(int(target.timestamp()))
PY
)"

echo "=== overnight loop start $(date) until CT 9am epoch=$end_epoch ===" | tee -a "$LOG"

cycle=0
while [ "$(date +%s)" -lt "$end_epoch" ]; do
  cycle=$((cycle + 1))
  echo "--- cycle $cycle $(date) ---" | tee -a "$LOG"
  (
    cd "$ROOT/scripts/model"
    python3 generate_today_board.py
    python3 update_live_bankroll.py --wallet 23.28
    python3 overnight_improve_live.py
    python3 backtest_best_tickets_walkforward.py
  ) >>"$LOG" 2>&1 || echo "cycle $cycle failed" | tee -a "$LOG"
  sleep 1800
done

echo "=== overnight loop done $(date) ===" | tee -a "$LOG"
