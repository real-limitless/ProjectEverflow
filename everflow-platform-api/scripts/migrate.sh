#!/usr/bin/env bash
# Apply all pending Alembic migrations (upgrade to head).
# Usage: ./scripts/migrate.sh
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH="${PYTHONPATH:-}:."

if [[ -x .venv/bin/alembic ]]; then
  exec .venv/bin/alembic upgrade head
elif command -v alembic >/dev/null 2>&1; then
  exec alembic upgrade head
else
  echo "error: alembic not found. Activate the venv or: uv pip install -e '.[dev]'" >&2
  exit 1
fi
