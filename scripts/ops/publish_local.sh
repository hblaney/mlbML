#!/bin/zsh
# Local-first board publish for vacation reliability.
#
# GitHub's hosted runner is throttled on the MLB stats API (30+ min, timeouts),
# while this Mac generates the same board in ~3 min. So the primary automation
# runs the pipeline HERE and pushes directly; the GitHub cron stays as backup.
#
# Safe to run unattended: it only stages known board files, aborts if the board
# isn't today's, and uses --autostash so it never disturbs uncommitted WIP.

set -u

REPO_DIR="/Users/henryblaney/Desktop/VIP/mlb-edge"
LOG_DIR="${REPO_DIR}/data/ops"
LOG="${LOG_DIR}/publish-local.log"
mkdir -p "${LOG_DIR}"

export PATH="/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin:${PATH}"
export PYTHONPATH="${REPO_DIR}/scripts/model"

cd "${REPO_DIR}" || { echo "$(date '+%F %T') FATAL: no repo dir" >> "${LOG}"; exit 1; }
PY="$(command -v python3)"
log() { echo "$(date '+%F %T') $*" >> "${LOG}"; }

log "=== publish_local start ==="

"${PY}" scripts/model/generate_today_board.py >> "${LOG}" 2>&1 || log "moneyline gen nonzero exit $?"
"${PY}" scripts/model/generate_prop_predictions.py >> "${LOG}" 2>&1 || log "props gen nonzero exit $?"
"${PY}" scripts/model/lock_daily_ticket.py >> "${LOG}" 2>&1 || log "lock nonzero exit $?"

TODAY="$(date +%F)"
MLDATE="$(${PY} -c "import json; print(json.load(open('public/predictions.json')).get('generated_at',''))" 2>/dev/null)"
if [ "${MLDATE}" != "${TODAY}" ]; then
  log "ABORT: moneyline board date '${MLDATE}' != today '${TODAY}' — not pushing stale board"
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
  data/locked-tickets/*.json \
  data/prop-predictions/*.json \
  data/model/daily_edge.pkl \
  2>/dev/null

if git diff --staged --quiet; then
  log "no board changes to commit"
  exit 0
fi

git commit -m "Auto-publish board ${TODAY} $(date '+%I:%M %p %Z') (local)" >> "${LOG}" 2>&1
git pull --rebase --autostash origin main >> "${LOG}" 2>&1
if git push origin main >> "${LOG}" 2>&1; then
  log "PUSHED board ${TODAY}"
else
  log "PUSH FAILED"
  exit 1
fi
log "=== publish_local done ==="
