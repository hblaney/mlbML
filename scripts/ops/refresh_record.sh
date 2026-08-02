#!/bin/zsh
# Refresh Accuracy / Record artifacts (prediction history → accuracy → health →
# CLV → live bankroll → prop track record). Safe to run daily after games settle.
#
# Usage:
#   scripts/ops/refresh_record.sh [REPO_DIR]
# Env:
#   FORCE=1           regenerate history even if already through yesterday
#   SKIP_HISTORY=1    reuse existing prediction-history.json
#   WALLET=<amount>   optional wallet sync for update_live_bankroll.py

set -u

REPO_DIR="${1:-$(cd "$(dirname "$0")/../.." && pwd)}"
LOG_DIR="${REPO_DIR}/data/ops"
mkdir -p "${LOG_DIR}"
LOG="${LOG_DIR}/refresh-record.log"

PY="${PYTHON_BIN:-}"
if [ -z "${PY}" ]; then
  if [ -x "/Library/Frameworks/Python.framework/Versions/3.14/bin/python3" ]; then
    PY="/Library/Frameworks/Python.framework/Versions/3.14/bin/python3"
  else
    PY="$(command -v python3)"
  fi
fi

export PATH="$(dirname "${PY}"):/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin:${PATH}"
export PYTHONPATH="${REPO_DIR}/scripts/model"

cd "${REPO_DIR}" || exit 1
log(){ echo "$(date '+%F %T') $*" | tee -a "${LOG}"; }

log "=== refresh_record start ==="

YESTERDAY="$(${PY} -c 'from datetime import date,timedelta; print((date.today()-timedelta(days=1)).isoformat())')"
TRAINED=""
if [ -f public/prediction-history.json ]; then
  TRAINED="$(${PY} -c "import json; print(json.load(open('public/prediction-history.json')).get('trained_through',''))" 2>/dev/null || true)"
fi

if [ "${SKIP_HISTORY:-0}" != "1" ]; then
  if [ "${FORCE:-0}" = "1" ] || [ "${TRAINED}" != "${YESTERDAY}" ]; then
    log "generating prediction history (trained_through=${TRAINED:-none} → ${YESTERDAY})"
    "${PY}" -u scripts/model/generate_prediction_history.py --current-season-only >> "${LOG}" 2>&1 \
      || { log "FATAL: prediction history failed"; exit 1; }
  else
    log "prediction history already through ${YESTERDAY} — skipping walk-forward"
  fi
else
  log "SKIP_HISTORY=1 — reusing prediction-history.json"
fi

log "accuracy + live performance"
"${PY}" scripts/model/generate_accuracy_output.py >> "${LOG}" 2>&1 || log "WARN accuracy exit $?"

log "model health"
"${PY}" scripts/model/model_health.py >> "${LOG}" 2>&1 || log "WARN health exit $?"

log "CLV"
"${PY}" scripts/model/clv_tracker.py >> "${LOG}" 2>&1 || log "WARN clv exit $?"

log "live strategy metrics"
"${PY}" scripts/model/generate_live_strategy_metrics.py >> "${LOG}" 2>&1 || log "WARN strategy metrics exit $?"

log "rolling strategy guard"
"${PY}" scripts/model/rolling_strategy_guard.py >> "${LOG}" 2>&1 || log "WARN strategy guard exit $?"

log "live bankroll / locked-ticket record"
if [ -n "${WALLET:-}" ]; then
  "${PY}" scripts/model/update_live_bankroll.py --wallet "${WALLET}" >> "${LOG}" 2>&1 || log "WARN bankroll exit $?"
else
  "${PY}" scripts/model/update_live_bankroll.py >> "${LOG}" 2>&1 || log "WARN bankroll exit $?"
fi

log "prop track record"
# Full prop regrade can hang on cold MLB caches — bound it so board publish still ships.
"${PY}" -c "
import subprocess, sys
try:
    raise SystemExit(subprocess.call([sys.executable, 'scripts/model/grade_prop_predictions.py'], timeout=240))
except subprocess.TimeoutExpired:
    print('prop_grade_timeout — leaving existing prop-track-record.json')
" >> "${LOG}" 2>&1 || log "WARN prop grade exit $?"

log "consistency audit"
"${PY}" scripts/model/consistency_audit.py >> "${LOG}" 2>&1 || log "WARN consistency exit $?"

ACC="$(${PY} -c "import json; d=json.load(open('public/accuracy.json')); cs=d.get('current_season',{}); print(f\"trained={d.get('trained_through')} acc={cs.get('market_backed_accuracy')} games={cs.get('market_backed_games')} last7={d.get('last_7_days')}\")" 2>/dev/null || echo unknown)"
BANK="$(${PY} -c "import json; d=json.load(open('public/live-bankroll.json')); print(f\"record={d.get('record')} last_settled={d.get('last_settled_date')} tickets={len(d.get('tickets',[]))} wallet={d.get('wallet_balance')}\")" 2>/dev/null || echo unknown)"
log "accuracy summary: ${ACC}"
log "bankroll summary: ${BANK}"
log "=== refresh_record done ==="
