#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_DIR="$ROOT_DIR/.sandbox-runtime"
mkdir -p "$RUNTIME_DIR/logs"

if [ -f "$RUNTIME_DIR/backend.pid" ] || [ -f "$RUNTIME_DIR/frontend.pid" ]; then
  echo "已有沙箱进程记录，请先执行 bash scripts/stop-all.sh"
  exit 1
fi

nohup bash "$ROOT_DIR/scripts/start-backend.sh" >"$RUNTIME_DIR/logs/backend.log" 2>&1 &
echo $! >"$RUNTIME_DIR/backend.pid"

nohup bash "$ROOT_DIR/scripts/start-frontend.sh" >"$RUNTIME_DIR/logs/frontend.log" 2>&1 &
echo $! >"$RUNTIME_DIR/frontend.pid"

echo "backend: http://127.0.0.1:8100"
echo "frontend: http://127.0.0.1:5173"
echo "logs: $RUNTIME_DIR/logs"
