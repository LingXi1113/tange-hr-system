#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT_DIR/.env.sandbox}"
BACKEND_DIR="$ROOT_DIR/projects/backend"

if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

: "${HRATS_ENV:=development}"
: "${HRATS_PORT:=8100}"
: "${HRATS_ENABLE_MOCK_AUTH:=1}"
: "${HRATS_SEED_DEMO_DATA:=1}"
: "${MONGODB_URI:=mongodb://127.0.0.1:27017}"
: "${MONGODB_DATABASE:=hr_ats_sandbox}"
export HRATS_ENV HRATS_PORT HRATS_ENABLE_MOCK_AUTH HRATS_SEED_DEMO_DATA
export MONGODB_URI MONGODB_DATABASE

cd "$BACKEND_DIR"

if command -v uv >/dev/null 2>&1; then
  if [ ! -x .venv/bin/python ]; then
    uv venv .venv --python 3.12
  fi
  uv pip install -r requirements.txt --python .venv/bin/python
  exec .venv/bin/python run.py
fi

if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
fi
.venv/bin/python -m pip install -r requirements.txt
exec .venv/bin/python run.py
