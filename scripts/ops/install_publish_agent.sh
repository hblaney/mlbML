#!/bin/zsh
# Install / refresh local MLB Edge publish + watchdog LaunchAgents.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SUPPORT="${HOME}/Library/Application Support/mlbedge"
AGENTS="${HOME}/Library/LaunchAgents"
uid="$(id -u)"

mkdir -p "${SUPPORT}" "${AGENTS}"

install_script() {
  local src="$1" name="$2"
  cp "${src}" "${SUPPORT}/${name}"
  chmod +x "${SUPPORT}/${name}"
  if [ -d "${HOME}/mlbedge-bot/scripts/ops" ]; then
    cp "${src}" "${HOME}/mlbedge-bot/scripts/ops/${name}"
    chmod +x "${HOME}/mlbedge-bot/scripts/ops/${name}"
  fi
}

install_script "${ROOT}/scripts/ops/publish_bot.sh" "publish_bot.sh"
install_script "${ROOT}/scripts/ops/publish_watchdog.sh" "publish_watchdog.sh"
install_script "${ROOT}/scripts/ops/trigger_publish.sh" "trigger_publish.sh"

# --- primary publisher --------------------------------------------------------
# SLA: site FULLY refreshed by 11:00 AM local (CT). Start ~9:00 so moneyline+props
# finish and push before 11 — never treat 11:00 as the start time.
cat > "${AGENTS}/com.mlbedge.publish.plist" <<'EOF'
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
  <key>StartCalendarInterval</key>
  <array>
    <dict><key>Hour</key><integer>9</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Hour</key><integer>9</integer><key>Minute</key><integer>20</integer></dict>
    <dict><key>Hour</key><integer>9</integer><key>Minute</key><integer>40</integer></dict>
    <dict><key>Hour</key><integer>10</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Hour</key><integer>10</integer><key>Minute</key><integer>20</integer></dict>
    <dict><key>Hour</key><integer>10</integer><key>Minute</key><integer>40</integer></dict>
    <dict><key>Hour</key><integer>11</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Hour</key><integer>11</integer><key>Minute</key><integer>30</integer></dict>
    <dict><key>Hour</key><integer>12</integer><key>Minute</key><integer>0</integer></dict>
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

# --- watchdog every 10 min during morning ------------------------------------
# Police 9:00–12:00 so a hung 9 AM start cannot miss the 11 AM live deadline.
python3 - <<'PY' > "${AGENTS}/com.mlbedge.publish-watchdog.plist"
from pathlib import Path
intervals = []
for hour in (9, 10, 11, 12):
    for minute in (0, 10, 20, 30, 40, 50):
        intervals.append(
            f"""    <dict>
      <key>Hour</key><integer>{hour}</integer>
      <key>Minute</key><integer>{minute}</integer>
    </dict>"""
        )
body = "\n".join(intervals)
print(f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.mlbedge.publish-watchdog</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/zsh</string>
    <string>/Users/henryblaney/Library/Application Support/mlbedge/publish_watchdog.sh</string>
  </array>
  <key>StartCalendarInterval</key>
  <array>
{body}
  </array>
  <key>RunAtLoad</key>
  <false/>
  <key>StandardOutPath</key>
  <string>/Users/henryblaney/Library/Application Support/mlbedge/watchdog.out.log</string>
  <key>StandardErrorPath</key>
  <string>/Users/henryblaney/Library/Application Support/mlbedge/watchdog.err.log</string>
</dict>
</plist>
""")
PY

for label in com.mlbedge.publish com.mlbedge.publish-watchdog; do
  launchctl bootout "gui/${uid}/${label}" 2>/dev/null || true
  launchctl bootstrap "gui/${uid}" "${AGENTS}/${label}.plist"
  launchctl enable "gui/${uid}/${label}" 2>/dev/null || true
  echo "Installed ${label}"
done

launchctl print "gui/${uid}/com.mlbedge.publish" 2>&1 | grep -E 'state|Hour' | head -20
launchctl print "gui/${uid}/com.mlbedge.publish-watchdog" 2>&1 | grep -E 'state|runs' | head -10
