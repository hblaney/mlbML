#!/bin/zsh
# Independent publish trigger for the MLB board.
#
# GitHub's cron scheduler is best-effort and has dropped/delayed ticks for weeks.
# This runs from a local launchd agent (see com.mlbedge.publish.plist) on a fixed
# clock and forces the Publish Live Board workflow via workflow_dispatch. The
# heavy pipeline still runs in GitHub's cloud — this is just a reliable trigger.
#
# The GitHub token is read from the macOS keychain at runtime via git's credential
# helper, so no secret is written to disk.

set -u

REPO_DIR="/Users/henryblaney/Desktop/VIP/mlb-edge"
LOG_DIR="${REPO_DIR}/data/ops"
LOG="${LOG_DIR}/publish-trigger.log"
mkdir -p "${LOG_DIR}"

cd "${REPO_DIR}" || { echo "$(date '+%Y-%m-%d %H:%M:%S') FATAL: repo dir missing" >> "${LOG}"; exit 1; }

TOKEN=$(printf "protocol=https\nhost=github.com\n\n" | /usr/bin/git credential fill 2>/dev/null | sed -n 's/^password=//p')
if [ -z "${TOKEN}" ]; then
  echo "$(date '+%Y-%m-%d %H:%M:%S') FAIL: no token in keychain (login keychain locked?)" >> "${LOG}"
  exit 1
fi

CODE=$(/usr/bin/curl -s -o /dev/null -w "%{http_code}" -X POST \
  -H "Accept: application/vnd.github+json" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  "https://api.github.com/repos/hblaney/mlbML/actions/workflows/publish-board.yml/dispatches" \
  -d '{"ref":"main"}')

if [ "${CODE}" = "204" ]; then
  echo "$(date '+%Y-%m-%d %H:%M:%S') OK: workflow_dispatch accepted (204)" >> "${LOG}"
  exit 0
else
  echo "$(date '+%Y-%m-%d %H:%M:%S') FAIL: dispatch HTTP ${CODE}" >> "${LOG}"
  exit 1
fi
