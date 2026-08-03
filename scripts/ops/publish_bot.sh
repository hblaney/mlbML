#!/bin/zsh
# Full local publish pipeline from ~/mlbedge-bot (outside TCC-protected Desktop).
#
# Primary morning path for the live site. GitHub Actions cron is backup only —
# it routinely delays or drops 10 AM ticks.
#
# Hardening (Aug 2026):
# - PID lock so a hung prior run cannot block the next scheduled 10 AM slot
# - Per-step timeouts + moneyline retries
# - Abort if moneyline fails (do not hang forever on props)
# - Fallback: dispatch Publish Live Board on GitHub if local board is still stale

set -u

REPO_DIR="${HOME}/mlbedge-bot"
LOG_DIR="${HOME}/Library/Application Support/mlbedge"
mkdir -p "${LOG_DIR}"
LOG="${LOG_DIR}/publish-bot.log"
LOCK="${LOG_DIR}/publish-bot.pid"
TRIGGER="${REPO_DIR}/scripts/ops/trigger_publish.sh"

PY="/Library/Frameworks/Python.framework/Versions/3.14/bin/python3"
export PATH="/Library/Frameworks/Python.framework/Versions/3.14/bin:/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin:${PATH}"
export PYTHONPATH="${REPO_DIR}/scripts/model"

# Whole agent must finish well under the next launchd retry gap (20m).
MONEYLINE_TIMEOUT_SEC=900   # 15m
PROPS_TIMEOUT_SEC=1200      # 20m
LOCK_TIMEOUT_SEC=120
MONEYLINE_RETRIES=3
STALE_LOCK_SEC=2400         # 40m — kill leftover runs so 10:20/10:40 can fire

log(){ echo "$(date '+%F %T') $*" >> "${LOG}"; }

release_lock() {
  if [ -f "${LOCK}" ] && [ "$(cat "${LOCK}" 2>/dev/null)" = "$$" ]; then
    rm -f "${LOCK}"
  fi
}
trap release_lock EXIT

# --- single-flight lock -------------------------------------------------------
if [ -f "${LOCK}" ]; then
  old_pid="$(cat "${LOCK}" 2>/dev/null || true)"
  if [ -n "${old_pid}" ] && kill -0 "${old_pid}" 2>/dev/null; then
    age=99999
    if stat -f %m "${LOCK}" >/dev/null 2>&1; then
      age=$(( $(date +%s) - $(stat -f %m "${LOCK}") ))
    fi
    if [ "${age}" -lt "${STALE_LOCK_SEC}" ]; then
      log "SKIP: publish_bot already running (pid ${old_pid}, age ${age}s)"
      exit 0
    fi
    log "WARN: stale publish_bot pid ${old_pid} (age ${age}s) — killing"
    kill "${old_pid}" 2>/dev/null || true
    sleep 2
    kill -9 "${old_pid}" 2>/dev/null || true
    # Also reap orphaned pipeline children from that run.
    pkill -f "${REPO_DIR}/scripts/model/generate_today_board.py" 2>/dev/null || true
    pkill -f "${REPO_DIR}/scripts/model/generate_prop_predictions.py" 2>/dev/null || true
  fi
  rm -f "${LOCK}"
fi
echo "$$" > "${LOCK}"

run_py() {
  # run_py LABEL TIMEOUT_SEC arg...
  local label="$1"
  local timeout_sec="$2"
  shift 2
  log "START ${label} (timeout ${timeout_sec}s)"
  "${PY}" - "${timeout_sec}" "$@" <<'PY' >> "${LOG}" 2>&1
import subprocess, sys
timeout = int(sys.argv[1])
cmd = [sys.argv[2], *sys.argv[3:]]
try:
    completed = subprocess.run(cmd, timeout=timeout)
    sys.exit(completed.returncode)
except subprocess.TimeoutExpired:
    print(f"TIMEOUT after {timeout}s: {' '.join(cmd)}", file=sys.stderr)
    sys.exit(124)
PY
  local rc=$?
  if [ "${rc}" -eq 0 ]; then
    log "OK ${label}"
  else
    log "FAIL ${label} exit ${rc}"
  fi
  return "${rc}"
}

dispatch_github_fallback() {
  log "FALLBACK: dispatching GitHub Publish Live Board"
  if [ -x "${TRIGGER}" ]; then
    REPO_DIR="${REPO_DIR}" /bin/zsh "${TRIGGER}" >> "${LOG}" 2>&1 || log "FALLBACK trigger exit $?"
  elif [ -x "${HOME}/Desktop/VIP/mlb-edge/scripts/ops/trigger_publish.sh" ]; then
    /bin/zsh "${HOME}/Desktop/VIP/mlb-edge/scripts/ops/trigger_publish.sh" >> "${LOG}" 2>&1 || log "FALLBACK desktop trigger exit $?"
  else
    log "FALLBACK: no trigger_publish.sh found"
  fi
}

cd "${REPO_DIR}" || { log "FATAL: no repo at ${REPO_DIR}"; exit 1; }
log "=== publish_bot start ==="

git fetch origin main >> "${LOG}" 2>&1 || log "WARN: git fetch failed"
git reset --hard origin/main >> "${LOG}" 2>&1 || log "WARN: git reset failed"

# Moneyline is required. Retry transient MLB API resets/timeouts.
ml_ok=0
i=1
while [ "${i}" -le "${MONEYLINE_RETRIES}" ]; do
  if run_py "moneyline attempt ${i}/${MONEYLINE_RETRIES}" "${MONEYLINE_TIMEOUT_SEC}" \
      "${PY}" scripts/model/generate_today_board.py; then
    ml_ok=1
    break
  fi
  sleep $(( i * 15 ))
  i=$(( i + 1 ))
done

if [ "${ml_ok}" -ne 1 ]; then
  log "ABORT: moneyline failed after ${MONEYLINE_RETRIES} attempts"
  dispatch_github_fallback
  exit 1
fi

# Props are best-effort for the moneyline board publish, but we still try.
if ! run_py "props" "${PROPS_TIMEOUT_SEC}" "${PY}" scripts/model/generate_prop_predictions.py; then
  log "WARN: props failed — continuing with moneyline board"
fi

run_py "lock" "${LOCK_TIMEOUT_SEC}" "${PY}" scripts/model/lock_daily_ticket.py || log "WARN: lock failed"

# Accuracy / Record — evening publishes + stale rebuilds.
if [ -x "${REPO_DIR}/scripts/ops/refresh_record.sh" ]; then
  HOUR="$(date +%H)"
  ACC_AGE_H="$(${PY} -c "import time,pathlib; p=pathlib.Path('public/accuracy.json'); print(999 if not p.exists() else (time.time()-p.stat().st_mtime)/3600)" 2>/dev/null || echo 999)"
  if [ "${HOUR}" -ge 19 ] || [ "${FORCE_RECORD:-0}" = "1" ] || awk "BEGIN{exit !(${ACC_AGE_H}+0 > 36)}" ; then
    log "refreshing accuracy/record (acc_age_h=${ACC_AGE_H})"
    FORCE="${FORCE_RECORD:-0}" "${REPO_DIR}/scripts/ops/refresh_record.sh" "${REPO_DIR}" >> "${LOG}" 2>&1 || log "record refresh exit $?"
  else
    log "skipping record refresh (hour=${HOUR} acc_age_h=${ACC_AGE_H})"
  fi
fi

TODAY="$(date +%F)"
MLDATE="$(${PY} -c "import json; print(json.load(open('public/predictions.json')).get('generated_at',''))" 2>/dev/null)"
if [ "${MLDATE}" != "${TODAY}" ]; then
  log "ABORT: board date '${MLDATE}' != today '${TODAY}' (not publishing stale board)"
  dispatch_github_fallback
  exit 1
fi

git add \
  public/predictions.json \
  public/prop-predictions.json \
  public/locked-ticket.json \
  public/prizepicks-slip.json \
  public/prop-bet-cards.json \
  public/prop-leans.json \
  public/prop-track-record.json \
  public/accuracy.json \
  public/prediction-history.json \
  public/model-live-performance.json \
  public/model-health.json \
  public/live-bankroll.json \
  public/live-strategy-metrics.json \
  public/clv.json \
  public/strategy-guard.json \
  data/locked-tickets/*.json \
  data/prop-predictions/*.json \
  data/live-bankroll-state.json \
  data/model/daily_edge.pkl 2>/dev/null

if git diff --staged --quiet; then
  log "no board changes to publish"
  log "=== publish_bot done (noop) ==="
  exit 0
fi

git commit -m "Auto-publish board ${TODAY} $(date '+%I:%M %p %Z') (local bot)" >> "${LOG}" 2>&1
git pull --rebase --autostash origin main >> "${LOG}" 2>&1

if git push origin main >> "${LOG}" 2>&1; then
  log "PUSHED board ${TODAY}"
else
  log "PUSH FAILED"
  dispatch_github_fallback
  exit 1
fi
log "=== publish_bot done ==="
