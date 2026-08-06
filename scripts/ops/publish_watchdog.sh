#!/bin/zsh
# Morning watchdog: if today's board is missing, force a publish (and kill hangs).
# Runs every 10 minutes 9:00–12:00 local. SLA: site fully live by 11:00 AM CT —
# publish must already be done (or finishing) by then, not starting.

set -u

REPO_DIR="${HOME}/mlbedge-bot"
SUPPORT="${HOME}/Library/Application Support/mlbedge"
LOG="${SUPPORT}/publish-watchdog.log"
BOT="${SUPPORT}/publish_bot.sh"
PY="/Library/Frameworks/Python.framework/Versions/3.14/bin/python3"
LOCK="${SUPPORT}/publish-bot.pid"

mkdir -p "${SUPPORT}"
log(){ echo "$(date '+%F %T') $*" >> "${LOG}"; }

HOUR="$(date +%H)"
# Only police the morning window (9 AM start → 11 AM live deadline + noon catch-up).
if [ "${HOUR}" -lt 9 ] || [ "${HOUR}" -gt 12 ]; then
  exit 0
fi

TODAY="$(date +%F)"
BOARD_DAY=""
if [ -f "${REPO_DIR}/public/predictions.json" ]; then
  BOARD_DAY="$(${PY} -c "import json; print(json.load(open('${REPO_DIR}/public/predictions.json')).get('generated_at',''))" 2>/dev/null || echo "")"
fi

# Also check origin tip via local Desktop clone if bot clone missing board.
if [ -z "${BOARD_DAY}" ] && [ -f "${HOME}/Desktop/VIP/mlb-edge/public/predictions.json" ]; then
  BOARD_DAY="$(${PY} -c "import json; print(json.load(open('${HOME}/Desktop/VIP/mlb-edge/public/predictions.json')).get('generated_at',''))" 2>/dev/null || echo "")"
fi

if [ "${BOARD_DAY}" = "${TODAY}" ]; then
  # Board is good — still reap zombie pipeline procs older than 30m if lock is stale.
  if [ -f "${LOCK}" ]; then
    age=$(( $(date +%s) - $(stat -f %m "${LOCK}") ))
    if [ "${age}" -gt 1800 ]; then
      log "reaping stale lock age=${age}s even though board is today"
      old_pid="$(cat "${LOCK}" 2>/dev/null || true)"
      [ -n "${old_pid}" ] && kill -9 "${old_pid}" 2>/dev/null || true
      pkill -9 -f "${REPO_DIR}/scripts/model/generate_" 2>/dev/null || true
      rm -f "${LOCK}"
    fi
  fi
  exit 0
fi

log "STALE board_day='${BOARD_DAY}' today='${TODAY}' — forcing publish"

# Clear hangs so publish_bot can start.
if [ -f "${LOCK}" ]; then
  old_pid="$(cat "${LOCK}" 2>/dev/null || true)"
  log "killing lock pid ${old_pid}"
  [ -n "${old_pid}" ] && kill -9 "${old_pid}" 2>/dev/null || true
  rm -f "${LOCK}"
fi
pkill -9 -f "${REPO_DIR}/scripts/model/generate_today_board.py" 2>/dev/null || true
pkill -9 -f "${REPO_DIR}/scripts/model/generate_prop_predictions.py" 2>/dev/null || true

if [ ! -x "${BOT}" ]; then
  log "FATAL: missing ${BOT}"
  exit 1
fi

/bin/zsh "${BOT}" >> "${LOG}" 2>&1
log "forced publish_bot finished rc=$?"
exit 0
