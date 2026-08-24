#!/usr/bin/env bash
set -euo pipefail

BACKEND_URL="${BACKEND_URL:-http://127.0.0.1:8100/health}"
FRONTEND_URL="${FRONTEND_URL:-http://127.0.0.1:5173}"

curl --fail --silent --show-error "$BACKEND_URL" >/dev/null
curl --fail --silent --show-error "$FRONTEND_URL" >/dev/null
echo "backend ok: $BACKEND_URL"
echo "frontend ok: $FRONTEND_URL"
