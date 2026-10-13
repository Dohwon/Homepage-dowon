#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FULL="$ROOT/.local-graphify/full/source/graphify-out/graph.json"
PRIORITY="$ROOT/.local-graphify/priority/source/graphify-out/graph.json"

if [[ -f "$FULL" ]]; then
  GRAPH="$FULL"
elif [[ -f "$PRIORITY" ]]; then
  GRAPH="$PRIORITY"
else
  echo "Graphify graph missing; build a local graph first" >&2
  exit 1
fi

cd "$ROOT"
HOST=127.0.0.1 PORT="${PORT:-4190}" ATLAS_LOCAL_GRAPHIFY_PATH="$GRAPH" exec node server.js
