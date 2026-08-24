#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT_DIR/.env.sandbox}"
FRONTEND_DIR="$ROOT_DIR/projects/frontend"

if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

: "${VITE_DEV_PORT:=5173}"
: "${HRATS_DEV_PROXY_TARGET:=http://127.0.0.1:8100}"
export VITE_DEV_PORT HRATS_DEV_PROXY_TARGET

cd "$FRONTEND_DIR"
if [ ! -d node_modules ]; then
  npm ci
fi

exec npm run dev -- --host 0.0.0.0 --port "$VITE_DEV_PORT" --strictPort --clearScreen false --cors
