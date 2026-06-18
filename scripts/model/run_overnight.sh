#!/usr/bin/env bash
# Rigorous overnight — every strategy × every stake combo until 9 AM CT.
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

echo "=== overnight RIGOROUS start $(date) until CT 9am ===" | tee -a "$LOG"

cycle=0
while [ "$(date +%s)" -lt "$end_epoch" ]; do
  cycle=$((cycle + 1))
  echo "--- rigorous cycle $cycle $(date) ---" | tee -a "$LOG"
  (
    cd "$ROOT/scripts/model"
    python3 overnight_rigorous.py --batch-size 250
    if [ $((cycle % 3)) -eq 1 ]; then
      python3 overnight_model_research.py --cycle "$cycle"
    fi
    if [ $((cycle % 4)) -eq 0 ]; then
      python3 generate_today_board.py
      python3 update_live_bankroll.py --wallet 23.28
    fi
  ) >>"$LOG" 2>&1 || echo "cycle $cycle failed" | tee -a "$LOG"
  sleep 900
done

(
  cd "$ROOT/scripts/model"
  python3 overnight_rigorous.py --full
  python3 overnight_finalize.py
) >>"$LOG" 2>&1 || true

echo "=== overnight RIGOROUS done — public/overnight-rigorous-report.json ===" | tee -a "$LOG"
