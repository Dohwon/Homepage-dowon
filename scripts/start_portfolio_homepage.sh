#!/bin/bash
set -euo pipefail

ROOT="/home/dowon/securedir/git/codex/portfolio-homepage"
NODE_BIN="/home/dowon/.nvm/versions/node/v20.20.0/bin/node"
LOCK_FILE="/tmp/portfolio-homepage.lock"
LOG_FILE="/tmp/portfolio-homepage.log"

cd "$ROOT"

exec /usr/bin/flock -n "$LOCK_FILE" "$NODE_BIN" "$ROOT/server.js" >>"$LOG_FILE" 2>&1
