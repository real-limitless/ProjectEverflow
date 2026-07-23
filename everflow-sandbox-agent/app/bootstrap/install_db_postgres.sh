#!/bin/sh
# Install Postgres client tools and write a sample .everflow/database.json.
# Does NOT start a full Postgres server (too heavy for typical microVMs).
# User sets DATABASE_URL (env) or database_url in database.json, or starts
# Postgres via docker if available.
set -eu

MARKER_DIR="${WORKSPACE:-/workspace}/.everflow"
mkdir -p "$MARKER_DIR"

install_psql_if_needed() {
  if command -v psql >/dev/null 2>&1; then
    echo "psql already present: $(command -v psql)"
    return 0
  fi
  if command -v apt-get >/dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y -qq postgresql-client || apt-get install -y -qq postgresql-client-common || true
  elif command -v apk >/dev/null 2>&1; then
    apk add --no-cache postgresql-client || true
  elif command -v dnf >/dev/null 2>&1; then
    dnf install -y postgresql || true
  fi
  if command -v psql >/dev/null 2>&1; then
    echo "psql installed: $(command -v psql)"
  else
    echo "WARNING: psql not installed; Database panel needs postgresql-client" >&2
  fi
}

write_sample_database_json() {
  target="$MARKER_DIR/database.json"
  if [ -f "$target" ]; then
    echo "database.json already present: $target"
    return 0
  fi
  # Prefer an existing DATABASE_URL from the environment when writing the sample.
  url="${DATABASE_URL:-}"
  if [ -z "$url" ]; then
    url="postgresql://postgres:postgres@127.0.0.1:5432/postgres"
    status="not_provisioned"
    message="Set DATABASE_URL in the sandbox env, update database_url below, or start Postgres (e.g. docker run -d -p 5432:5432 -e POSTGRES_PASSWORD=postgres postgres:16) then re-check status."
  else
    status="configured"
    message="Using DATABASE_URL from environment. Ensure Postgres is reachable from this sandbox."
  fi
  # Escape JSON string values (minimal: backslash and quotes).
  esc_url=$(printf '%s' "$url" | sed 's/\\/\\\\/g; s/"/\\"/g')
  esc_msg=$(printf '%s' "$message" | sed 's/\\/\\\\/g; s/"/\\"/g')
  cat >"$target" <<EOF
{
  "engine": "postgres",
  "database_url": "$esc_url",
  "status": "$status",
  "message": "$esc_msg"
}
EOF
  echo "wrote sample database.json → $target"
}

install_psql_if_needed
write_sample_database_json
echo "db-postgres" >>"$MARKER_DIR/bootstrapped"
echo "db-postgres harness ready (psql client + database.json)"
