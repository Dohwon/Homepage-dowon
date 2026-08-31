#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALLER="$ROOT/deploy/windows/install-project-atlas-task.ps1"
PUBLISH_SCRIPT="$ROOT/scripts/project_atlas_scheduled_publish.sh"
DISTRO="${WSL_DISTRO_NAME:-Ubuntu-22.04}"
WSL_USER="${USER:-dowon}"
MODE="Install"

case "${1:-}" in
  "") ;;
  --check) MODE="Check" ;;
  --remove) MODE="Remove" ;;
  *) printf 'Usage: %s [--check|--remove]\n' "$0" >&2; exit 2 ;;
esac

if [ ! -f "$INSTALLER" ] || [ ! -f "$PUBLISH_SCRIPT" ]; then
  printf 'Project Atlas scheduling files are incomplete.\n' >&2
  exit 1
fi

if ! command -v powershell.exe >/dev/null || ! command -v wslpath >/dev/null; then
  printf 'Windows Task Scheduler installation requires WSL interop.\n' >&2
  exit 1
fi

windows_installer="$(wslpath -w "$INSTALLER")"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$windows_installer" \
  -Distro "$DISTRO" \
  -WslUser "$WSL_USER" \
  -ScriptPath "$PUBLISH_SCRIPT" \
  -Mode "$MODE"
