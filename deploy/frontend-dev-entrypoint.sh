#!/bin/sh
# Keep the named node_modules volume in sync with package-lock.json.
# The volume persists across rebuilds; without this, new deps (e.g. xterm) never appear.
set -e
cd /ui

if [ ! -d node_modules/@xterm/xterm ] || [ package-lock.json -nt node_modules/.package-lock.json ] 2>/dev/null; then
  echo "[frontend] Installing npm dependencies…"
  npm ci
  # Stamp for crude freshness checks
  touch node_modules/.package-lock.json 2>/dev/null || true
fi

exec npm run dev -- --host 0.0.0.0 --port 5173
