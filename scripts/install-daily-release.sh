#!/usr/bin/env bash
# Installs (or removes) a macOS launchd job that runs scripts/daily-release.sh every hour.
#   scripts/install-daily-release.sh              install and start
#   scripts/install-daily-release.sh uninstall    stop and remove
#   scripts/install-daily-release.sh status       show state and the last log lines
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.askthesubs.release"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
STATE_DIR="$HOME/.askthesubs"
UIDN="$(id -u)"

case "${1:-install}" in
  uninstall)
    launchctl bootout "gui/$UIDN/$LABEL" 2>/dev/null || true
    rm -f "$PLIST"; echo "Removed the daily release job."; exit 0 ;;
  status)
    launchctl print "gui/$UIDN/$LABEL" 2>/dev/null | grep -E "state|last exit|runs" || echo "not installed"
    echo "last deployed: $(cat "$STATE_DIR/last-deployed" 2>/dev/null || echo never)"
    [ -f "$ROOT/site/.release-paused" ] && echo "PAUSED (delete site/.release-paused to resume)"
    tail -n 12 "$STATE_DIR/release.log" 2>/dev/null || true; exit 0 ;;
esac

command -v node >/dev/null || { echo "node not found in PATH"; exit 1; }
command -v npx  >/dev/null || { echo "npx not found in PATH"; exit 1; }
mkdir -p "$HOME/Library/LaunchAgents" "$STATE_DIR"
# launchd starts jobs with a minimal PATH, so record the PATH this shell uses (it finds node, npm, python, git, wrangler).
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array><string>/bin/bash</string><string>$ROOT/scripts/daily-release.sh</string></array>
  <key>EnvironmentVariables</key>
  <dict><key>PATH</key><string>$PATH</string><key>HOME</key><string>$HOME</string></dict>
  <key>StartInterval</key><integer>3600</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>$STATE_DIR/launchd.out</string>
  <key>StandardErrorPath</key><string>$STATE_DIR/launchd.err</string>
</dict>
</plist>
EOF
launchctl bootout "gui/$UIDN/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$UIDN" "$PLIST"
echo "Installed. It wakes every hour and deploys at most once per UTC day."
echo "  status:    scripts/install-daily-release.sh status"
echo "  pause:     touch site/.release-paused"
echo "  uninstall: scripts/install-daily-release.sh uninstall"
echo "The first run starts now; watch: tail -f $STATE_DIR/release.log"
