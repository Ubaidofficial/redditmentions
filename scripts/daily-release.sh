#!/usr/bin/env bash
# Deploys the site at most once per UTC day, so the daily release plan advances without you.
# Meant to be woken every hour by launchd (scripts/install-daily-release.sh): it does nothing until a new UTC day has
# started, then builds, runs the affiliate-link check, deploys, and verifies the live site against the release plan.
# If the Mac was asleep at midnight UTC it simply runs at the next wake-up.
#
#   scripts/daily-release.sh            normal run
#   touch site/.release-paused          pause (delete the file to resume)
#
# Test hooks (environment): DEPLOY_CMD (default "npm run deploy"), SITE_URL, VERIFY=0, ASKTHESUBS_STATE_DIR.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STATE_DIR="${ASKTHESUBS_STATE_DIR:-$HOME/.askthesubs}"
SITE_URL="${SITE_URL:-https://askthesubs.com}"
DEPLOY_CMD="${DEPLOY_CMD:-npm run deploy}"
mkdir -p "$STATE_DIR"
LOG="$STATE_DIR/release.log"
TODAY="$(date -u +%F)"

log() { echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) $*" >> "$LOG"; echo "$*"; }
notify() {  # one macOS notification per distinct message per day (an hourly job must not nag)
  local key; key="$(printf '%s' "$1" | cksum | cut -d' ' -f1)"
  [ -f "$STATE_DIR/notified-$TODAY-$key" ] && return 0
  : > "$STATE_DIR/notified-$TODAY-$key"
  osascript -e "display notification \"${1//\"/\'}\" with title \"AskTheSubs release\"" >/dev/null 2>&1 || true
}
trim_log() { [ -f "$LOG" ] && [ "$(wc -c < "$LOG")" -gt 400000 ] && tail -n 1500 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"; return 0; }
find "$STATE_DIR" -name 'notified-*' -mtime +3 -delete 2>/dev/null || true

# 1. nothing to do?
[ -f "$ROOT/site/.release-paused" ] && exit 0
[ "$(cat "$STATE_DIR/last-deployed" 2>/dev/null || true)" = "$TODAY" ] && exit 0

# 2. one run at a time
LOCK="$STATE_DIR/lock"
if ! mkdir "$LOCK" 2>/dev/null; then
  if [ -n "$(find "$LOCK" -maxdepth 0 -mmin +90 2>/dev/null)" ]; then rmdir "$LOCK" 2>/dev/null; mkdir "$LOCK" 2>/dev/null || exit 0; else exit 0; fi
fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT
trim_log

# 3. never deploy half-edited code unattended (ignored files such as .env and the generated data do not count)
cd "$ROOT" || exit 1
if [ -n "$(git status --porcelain --untracked-files=no 2>/dev/null)" ]; then
  log "SKIPPED $TODAY: uncommitted changes in the project (commit or stash them, or run scripts/publish.sh by hand)"
  notify "Daily release skipped: the project has uncommitted changes."
  exit 0
fi
[ -f "$ROOT/site/src/data/generated/categories.json" ] || { log "SKIPPED $TODAY: site data not built (run python3 scripts/build_site_data.py)"; notify "Daily release skipped: site data is missing."; exit 0; }

# 4. build, check and deploy (npm run deploy = astro build + affiliate-link check + wrangler deploy)
log "deploying release for $TODAY (expected pages live: $(node "$ROOT/scripts/release-plan.mjs" 0 2>/dev/null | sed -n 3p | sed -E 's/.*live: *([0-9]+).*/\1/'))"
OUT="$(mktemp)"
if ! ( cd "$ROOT/site" && eval "$DEPLOY_CMD" ) > "$OUT" 2>&1; then
  { echo "--- last lines of the failed deploy:"; tail -n 25 "$OUT"; } >> "$LOG"
  rm -f "$OUT"
  log "FAILED $TODAY: deploy did not complete (will retry next hour); see $LOG"
  notify "Daily release FAILED. See ~/.askthesubs/release.log"
  exit 1
fi
{ echo "--- last lines of the deploy:"; tail -n 6 "$OUT"; } >> "$LOG"
rm -f "$OUT"
echo "$TODAY" > "$STATE_DIR/last-deployed"
log "deployed $TODAY"

# 5. verify the live site matches the plan (warn only: the deploy itself succeeded)
if [ "${VERIFY:-1}" = "1" ]; then
  expected="$(node "$ROOT/scripts/release-plan.mjs" 0 2>/dev/null | sed -n 3p | sed -E 's/.*live: *([0-9]+).*/\1/')"
  live=""; for _ in 1 2 3 4; do
    live="$(curl -fsS --max-time 30 "$SITE_URL/sitemap-0.xml" 2>/dev/null | grep -o '<loc>' | wc -l | tr -d ' ')"
    [ "$live" = "$expected" ] && break; sleep 20
  done
  robots="$(curl -fsS --max-time 30 "$SITE_URL/" 2>/dev/null | grep -o '<meta name="robots" content="[^"]*"' | head -1)"
  if [ "$live" = "$expected" ] && printf '%s' "$robots" | grep -q 'content="index'; then
    log "verified: sitemap has $live URLs (plan: $expected) and the home page is indexable"
  else
    log "WARNING $TODAY: live sitemap has ${live:-?} URLs but the plan says $expected, robots: ${robots:-none}"
    notify "Release deployed but the live check disagrees (sitemap ${live:-?} vs plan $expected). See the log."
  fi
fi
exit 0
