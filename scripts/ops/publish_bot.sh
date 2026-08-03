#!/bin/zsh
# Full local publish pipeline from ~/mlbedge-bot (outside TCC-protected Desktop).
#
# Contract: this script MUST exit. It must not hang launchd.
# - Process-group kills on timeout (no orphaned python children)
# - Moneyline publishes even when props fail
# - GitHub workflow_dispatch fallback whenever today's board is still missing

set -u

REPO_DIR="${HOME}/mlbedge-bot"
LOG_DIR="${HOME}/Library/Application Support/mlbedge"
mkdir -p "${LOG_DIR}"
LOG="${LOG_DIR}/publish-bot.log"
LOCK="${LOG_DIR}/publish-bot.pid"
TRIGGER="${REPO_DIR}/scripts/ops/trigger_publish.sh"
DESKTOP_TRIGGER="${HOME}/Desktop/VIP/mlb-edge/scripts/ops/trigger_publish.sh"

PY="/Library/Frameworks/Python.framework/Versions/3.14/bin/python3"
export PATH="/Library/Frameworks/Python.framework/Versions/3.14/bin:/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin:${PATH}"
export PYTHONPATH="${REPO_DIR}/scripts/model"

MONEYLINE_TIMEOUT_SEC=720    # 12m hard cap
PROPS_TIMEOUT_SEC=600        # 10m — never block the moneyline push longer than this
LOCK_TIMEOUT_SEC=90
MONEYLINE_RETRIES=3
STALE_LOCK_SEC=1500          # 25m — next 10:20/10:40 slot can always reclaim

log(){ echo "$(date '+%F %T') $*" >> "${LOG}"; }

release_lock() {
  if [ -f "${LOCK}" ] && [ "$(cat "${LOCK}" 2>/dev/null)" = "$$" ]; then
    rm -f "${LOCK}"
  fi
}
trap release_lock EXIT INT TERM

reap_pipeline() {
  pkill -9 -f "${REPO_DIR}/scripts/model/generate_today_board.py" 2>/dev/null || true
  pkill -9 -f "${REPO_DIR}/scripts/model/generate_prop_predictions.py" 2>/dev/null || true
  pkill -9 -f "${REPO_DIR}/scripts/model/lock_daily_ticket.py" 2>/dev/null || true
}

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
    log "WARN: stale publish_bot pid ${old_pid} (age ${age}s) — killing tree"
    kill "${old_pid}" 2>/dev/null || true
    sleep 1
    kill -9 "${old_pid}" 2>/dev/null || true
    reap_pipeline
  fi
  rm -f "${LOCK}"
fi
echo "$$" > "${LOCK}"

run_py() {
  # run_py LABEL TIMEOUT_SEC arg...
  # Uses a new session so timeout can SIGKILL the whole process group.
  local label="$1"
  local timeout_sec="$2"
  shift 2
  log "START ${label} (timeout ${timeout_sec}s)"
  "${PY}" - "${timeout_sec}" "$@" <<'PY' >> "${LOG}" 2>&1
import os, signal, subprocess, sys, time

timeout = int(sys.argv[1])
cmd = [sys.argv[2], *sys.argv[3:]]
proc = subprocess.Popen(
    cmd,
    start_new_session=True,
    stdout=sys.stdout,
    stderr=sys.stderr,
)
try:
    rc = proc.wait(timeout=timeout)
    sys.exit(rc)
except subprocess.TimeoutExpired:
    print(f"TIMEOUT after {timeout}s — killing process group: {' '.join(cmd)}", file=sys.stderr)
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    try:
        proc.kill()
    except ProcessLookupError:
        pass
    time.sleep(0.5)
    sys.exit(124)
PY
  local rc=$?
  if [ "${rc}" -eq 0 ]; then
    log "OK ${label}"
  else
    log "FAIL ${label} exit ${rc}"
    # Belt-and-suspenders: reap anything left behind.
    reap_pipeline
  fi
  return "${rc}"
}

board_is_today() {
  local today board_day
  today="$(date +%F)"
  board_day="$(${PY} -c "import json; print(json.load(open('public/predictions.json')).get('generated_at',''))" 2>/dev/null || echo "")"
  [ "${board_day}" = "${today}" ]
}

dispatch_github_fallback() {
  log "FALLBACK: dispatching GitHub Publish Live Board"
  if [ -x "${TRIGGER}" ]; then
    REPO_DIR="${REPO_DIR}" /bin/zsh "${TRIGGER}" >> "${LOG}" 2>&1 || log "FALLBACK trigger exit $?"
  elif [ -x "${DESKTOP_TRIGGER}" ]; then
    /bin/zsh "${DESKTOP_TRIGGER}" >> "${LOG}" 2>&1 || log "FALLBACK desktop trigger exit $?"
  else
    log "FALLBACK: no trigger_publish.sh found"
  fi
}

commit_and_push() {
  local tag="$1"
  local today
  today="$(date +%F)"

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
    log "no board changes to publish (${tag})"
    return 0
  fi

  git commit -m "Auto-publish board ${today} $(date '+%I:%M %p %Z') (local bot ${tag})" >> "${LOG}" 2>&1
  git pull --rebase --autostash origin main >> "${LOG}" 2>&1
  if git push origin main >> "${LOG}" 2>&1; then
    log "PUSHED board ${today} (${tag})"
    return 0
  fi
  log "PUSH FAILED (${tag})"
  return 1
}

cd "${REPO_DIR}" || { log "FATAL: no repo at ${REPO_DIR}"; dispatch_github_fallback; exit 1; }
log "=== publish_bot start ==="

git fetch origin main >> "${LOG}" 2>&1 || log "WARN: git fetch failed"
git reset --hard origin/main >> "${LOG}" 2>&1 || log "WARN: git reset failed"

# --- moneyline (required) -----------------------------------------------------
ml_ok=0
i=1
while [ "${i}" -le "${MONEYLINE_RETRIES}" ]; do
  if run_py "moneyline attempt ${i}/${MONEYLINE_RETRIES}" "${MONEYLINE_TIMEOUT_SEC}" \
      "${PY}" scripts/model/generate_today_board.py; then
    ml_ok=1
    break
  fi
  sleep $(( i * 10 ))
  i=$(( i + 1 ))
done

if [ "${ml_ok}" -ne 1 ]; then
  log "ABORT: moneyline failed after ${MONEYLINE_RETRIES} attempts"
  dispatch_github_fallback
  exit 1
fi

run_py "lock" "${LOCK_TIMEOUT_SEC}" "${PY}" scripts/model/lock_daily_ticket.py || log "WARN: lock failed"

if ! board_is_today; then
  log "ABORT: moneyline ran but board date is not today"
  dispatch_github_fallback
  exit 1
fi

# Push moneyline ASAP — do not wait on props.
if ! commit_and_push "moneyline"; then
  dispatch_github_fallback
fi

# --- props (best-effort, hard-capped) ----------------------------------------
if run_py "props" "${PROPS_TIMEOUT_SEC}" "${PY}" scripts/model/generate_prop_predictions.py; then
  run_py "lock-after-props" "${LOCK_TIMEOUT_SEC}" "${PY}" scripts/model/lock_daily_ticket.py || true
  commit_and_push "props" || true
else
  log "WARN: props failed/timed out — moneyline board already shipped"
fi

# Accuracy / Record — evening + stale only (never blocks morning).
if [ -x "${REPO_DIR}/scripts/ops/refresh_record.sh" ]; then
  HOUR="$(date +%H)"
  ACC_AGE_H="$(${PY} -c "import time,pathlib; p=pathlib.Path('public/accuracy.json'); print(999 if not p.exists() else (time.time()-p.stat().st_mtime)/3600)" 2>/dev/null || echo 999)"
  if [ "${HOUR}" -ge 19 ] || [ "${FORCE_RECORD:-0}" = "1" ] || awk "BEGIN{exit !(${ACC_AGE_H}+0 > 36)}" ; then
    log "refreshing accuracy/record (acc_age_h=${ACC_AGE_H})"
    FORCE="${FORCE_RECORD:-0}" "${REPO_DIR}/scripts/ops/refresh_record.sh" "${REPO_DIR}" >> "${LOG}" 2>&1 || log "record refresh exit $?"
    commit_and_push "record" || true
  else
    log "skipping record refresh (hour=${HOUR} acc_age_h=${ACC_AGE_H})"
  fi
fi

if ! board_is_today; then
  log "FINAL: board still not today — GitHub fallback"
  dispatch_github_fallback
  exit 1
fi

log "=== publish_bot done ==="
exit 0
