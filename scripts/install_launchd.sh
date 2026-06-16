#!/usr/bin/env bash
# Install (or reinstall) the daily macOS launchd schedule.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LABEL="com.zeeshan.linkedin-autopost"
SRC="$DIR/launchd/$LABEL.plist"
DEST_DIR="$HOME/Library/LaunchAgents"
DEST="$DEST_DIR/$LABEL.plist"

mkdir -p "$DEST_DIR"

# Substitute the project path into the plist.
sed "s|__PROJECT_DIR__|$DIR|g" "$SRC" > "$DEST"

# Reload if already installed.
launchctl unload "$DEST" 2>/dev/null || true
launchctl load "$DEST"

echo "Installed launchd job '$LABEL'."
echo "  Schedule: daily at 09:30 local time."
echo "  Plist:    $DEST"
echo
echo "Useful commands:"
echo "  launchctl list | grep linkedin-autopost     # confirm it's loaded"
echo "  launchctl start $LABEL                       # run it now (real post!)"
echo "  launchctl unload \"$DEST\"                     # disable"
echo "  tail -f \"$DIR/logs/bot.log\"                  # watch logs"
