#!/usr/bin/env bash
# Generate a new Alembic revision from model changes (autogenerate).
# Usage: ./scripts/makemigration.sh "add_agents_table"
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH="${PYTHONPATH:-}:."

if [[ $# -lt 1 || -z "${1:-}" ]]; then
  echo "usage: $0 <message>" >&2
  echo "example: $0 \"add_agents_table\"" >&2
  exit 1
fi

MESSAGE="$1"

if [[ -x .venv/bin/alembic ]]; then
  ALEMBIC=.venv/bin/alembic
elif command -v alembic >/dev/null 2>&1; then
  ALEMBIC=alembic
else
  echo "error: alembic not found. Activate the venv or: uv pip install -e '.[dev]'" >&2
  exit 1
fi

echo "Generating revision: ${MESSAGE}"
"${ALEMBIC}" revision --autogenerate -m "${MESSAGE}"
echo
echo "Review the new file under alembic/versions/, then apply with:"
echo "  ./scripts/migrate.sh"
echo "  # or: alembic upgrade head"
