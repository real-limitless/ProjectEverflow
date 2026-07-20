#!/bin/sh
set -e
mkdir -p /data
# Apply migrations before serving
alembic upgrade head

RELOAD_ARGS=""
if [ "${UVICORN_RELOAD:-false}" = "true" ]; then
  RELOAD_ARGS="--reload"
fi

if [ "$#" -gt 0 ]; then
  exec "$@"
fi

exec uvicorn app.main:app --host 0.0.0.0 --port 8000 $RELOAD_ARGS
