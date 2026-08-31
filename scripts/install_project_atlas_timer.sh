#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_DIR="$ROOT/deploy/systemd-user"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
SERVICE="project-atlas.service"
TIMER="project-atlas.timer"

if ! systemctl --user show-environment >/dev/null 2>&1; then
  printf 'A user systemd manager is unavailable; using Windows Task Scheduler.\n'
  exec "$ROOT/scripts/install_project_atlas_schedule.sh" "$@"
fi

check_templates() {
  grep -Fq 'scripts/project_atlas.py publish --workspace /home/dowon/securedir/git/codex --changed-only --push' "$SOURCE_DIR/$SERVICE"
  grep -Fq 'OnBootSec=5m' "$SOURCE_DIR/$TIMER"
  grep -Fq 'OnUnitActiveSec=15m' "$SOURCE_DIR/$TIMER"
  grep -Fq 'RandomizedDelaySec=60' "$SOURCE_DIR/$TIMER"
  grep -Fq 'Persistent=true' "$SOURCE_DIR/$TIMER"
  printf 'Project Atlas user-unit templates are valid.\n'
}

case "${1:-}" in
  --check)
    check_templates
    ;;
  --remove)
    systemctl --user disable --now "$TIMER" 2>/dev/null || true
    rm -f -- "$UNIT_DIR/$SERVICE" "$UNIT_DIR/$TIMER"
    systemctl --user daemon-reload
    ;;
  "")
    check_templates
    install -d -m 700 "$UNIT_DIR"
    install -m 644 "$SOURCE_DIR/$SERVICE" "$UNIT_DIR/$SERVICE"
    install -m 644 "$SOURCE_DIR/$TIMER" "$UNIT_DIR/$TIMER"
    systemctl --user daemon-reload
    systemctl --user enable --now "$TIMER"
    ;;
  *)
    printf 'Usage: %s [--check|--remove]\n' "$0" >&2
    exit 2
    ;;
esac
