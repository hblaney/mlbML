#!/bin/zsh
# Install / refresh the local MLB Edge publish LaunchAgent.
# Copies the hardened bot into ~/Library/Application Support/mlbedge and
# schedules morning retries so a single hang cannot wipe the 10 AM window.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SUPPORT="${HOME}/Library/Application Support/mlbedge"
PLIST="${HOME}/Library/LaunchAgents/com.mlbedge.publish.plist"
LABEL="com.mlbedge.publish"

mkdir -p "${SUPPORT}" "${HOME}/Library/LaunchAgents"
cp "${ROOT}/scripts/ops/publish_bot.sh" "${SUPPORT}/publish_bot.sh"
chmod +x "${SUPPORT}/publish_bot.sh"

# Also keep a copy inside the dedicated clone when present.
if [ -d "${HOME}/mlbedge-bot/scripts/ops" ]; then
  cp "${ROOT}/scripts/ops/publish_bot.sh" "${HOME}/mlbedge-bot/scripts/ops/publish_bot.sh"
  chmod +x "${HOME}/mlbedge-bot/scripts/ops/publish_bot.sh"
fi

cat > "${PLIST}" <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.mlbedge.publish</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/zsh</string>
    <string>/Users/henryblaney/Library/Application Support/mlbedge/publish_bot.sh</string>
  </array>
  <!-- Local CT: dense morning retries, then 3 PM / 8 PM. -->
  <key>StartCalendarInterval</key>
  <array>
    <dict><key>Hour</key><integer>10</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Hour</key><integer>10</integer><key>Minute</key><integer>20</integer></dict>
    <dict><key>Hour</key><integer>10</integer><key>Minute</key><integer>40</integer></dict>
    <dict><key>Hour</key><integer>11</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Hour</key><integer>15</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Hour</key><integer>20</integer><key>Minute</key><integer>0</integer></dict>
  </array>
  <key>RunAtLoad</key>
  <false/>
  <key>StandardOutPath</key>
  <string>/Users/henryblaney/Library/Application Support/mlbedge/launchd.out.log</string>
  <key>StandardErrorPath</key>
  <string>/Users/henryblaney/Library/Application Support/mlbedge/launchd.err.log</string>
</dict>
</plist>
EOF

uid="$(id -u)"
launchctl bootout "gui/${uid}/${LABEL}" 2>/dev/null || true
launchctl bootstrap "gui/${uid}" "${PLIST}"
launchctl enable "gui/${uid}/${LABEL}" 2>/dev/null || true

echo "Installed ${LABEL}"
launchctl print "gui/${uid}/${LABEL}" 2>&1 | grep -E 'state|path|Hour|Minute' | head -30
