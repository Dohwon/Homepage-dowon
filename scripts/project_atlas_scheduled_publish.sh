#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKSPACE="$(cd "$ROOT/.." && pwd)"
STATE_DIR="$WORKSPACE/.knowledge-worker"
LOG_FILE="$STATE_DIR/project-atlas-schedule.log"
LOCK_FILE="$STATE_DIR/project-atlas-schedule.lock"

install -d -m 700 "$STATE_DIR"
if [ -f "$LOG_FILE" ] && [ "$(stat -c %s "$LOG_FILE")" -gt 5242880 ]; then
  mv -f -- "$LOG_FILE" "$LOG_FILE.previous"
fi
exec >>"$LOG_FILE" 2>&1

printf '[%s] Project Atlas scheduled publish started\n' "$(date --iso-8601=seconds)"
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  printf '[%s] skipped: another scheduled publish is running\n' "$(date --iso-8601=seconds)"
  exit 0
fi

available_kib="$(awk '/^MemAvailable:/ { print $2 }' /proc/meminfo)"
if [ -z "$available_kib" ] || [ "$available_kib" -lt 2097152 ]; then
  printf '[%s] skipped: less than 2 GiB memory is available\n' "$(date --iso-8601=seconds)"
  exit 0
fi

python="$ROOT/.venv/bin/python"
if [ ! -x "$python" ]; then
  python="$(command -v python3)"
fi

cd "$ROOT"
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 nice -n 10 \
  prlimit --as=2147483648 --cpu=1800 -- \
  "$python" scripts/project_atlas.py publish \
  --workspace "$WORKSPACE" --changed-only --push
printf '[%s] Project Atlas scheduled publish finished\n' "$(date --iso-8601=seconds)"
