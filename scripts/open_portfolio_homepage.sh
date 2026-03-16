#!/bin/bash
set -euo pipefail

URL="http://127.0.0.1:4173"
BOOTSTRAP_URL="$URL/api/bootstrap"
START_SCRIPT="/home/dowon/securedir/git/codex/portfolio-homepage/scripts/start_portfolio_homepage.sh"
LAUNCH_LOG="/tmp/portfolio-homepage-launch.log"

if ! curl -fsS "$BOOTSTRAP_URL" >/dev/null 2>&1; then
  nohup "$START_SCRIPT" >>"$LAUNCH_LOG" 2>&1 &
  for _ in $(seq 1 20); do
    if curl -fsS "$BOOTSTRAP_URL" >/dev/null 2>&1; then
      break
    fi
    sleep 0.5
  done
fi

exec xdg-open "$URL"
