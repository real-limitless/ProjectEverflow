#!/bin/sh
# Install Everflow agent harnesses inside a project sandbox.
# Idempotent; safe to re-run.
#
# Prefer prebaked guest images (deploy/sandbox-guest.Dockerfile) so this is a
# no-op: tools already on PATH, only workspace markers are written.
set -eu

MARKER_DIR="${WORKSPACE:-/workspace}/.everflow"
BIN_DIR="${MARKER_DIR}/bin"
mkdir -p "$BIN_DIR"
export PATH="$BIN_DIR:$PATH"

if [ "$#" -eq 0 ]; then
  set -- agent-claude-code agent-opencode
fi

harness_present() {
  case "$1" in
    agent-claude-code|claude-code|claude)
      command -v claude >/dev/null 2>&1 || command -v claude-code >/dev/null 2>&1
      ;;
    agent-opencode|opencode)
      command -v opencode >/dev/null 2>&1
      ;;
    db-postgres|postgres)
      command -v psql >/dev/null 2>&1 && [ -f "$MARKER_DIR/database.json" ]
      ;;
    *)
      # unknown harness: not "present"
      return 1
      ;;
  esac
}

# Fast path: prebaked image and/or all requested tools already installed.
all_present=1
for h in "$@"; do
  if ! harness_present "$h"; then
    all_present=0
    break
  fi
done

if [ "$all_present" -eq 1 ]; then
  : >"$MARKER_DIR/bootstrapped"
  for h in "$@"; do
    echo "$h" >>"$MARKER_DIR/bootstrapped"
  done
  if [ -f /etc/everflow/prebaked ]; then
    echo "bootstrap complete (prebaked guest image)"
    cat /etc/everflow/prebaked 2>/dev/null || true
  else
    echo "bootstrap complete (tools already on PATH)"
  fi
  exit 0
fi

if [ -f /etc/everflow/prebaked ]; then
  echo "prebaked marker present but some harnesses missing; installing remainder"
fi

install_node_tarball() {
  # Official Node linux binary — works on Fedora/RHEL and as a generic fallback.
  # Prefers major 22 to match the prebaked guest image.
  if ! command -v curl >/dev/null 2>&1; then
    return 1
  fi
  arch="$(uname -m 2>/dev/null || echo x86_64)"
  case "$arch" in
    x86_64) node_arch=x64 ;;
    aarch64|arm64) node_arch=arm64 ;;
    *) return 1 ;;
  esac
  ver="$(curl -fsSL https://nodejs.org/dist/index.json 2>/dev/null \
    | python3 -c "import json,sys
try:
  data=json.load(sys.stdin)
  v=next(x['version'] for x in data if x['version'].startswith('v22.'))
  print(v.lstrip('v'))
except Exception:
  raise SystemExit(1)
" 2>/dev/null || true)"
  if [ -z "$ver" ]; then
    return 1
  fi
  tmp="/tmp/node-v${ver}-linux-${node_arch}.tar.xz"
  curl -fsSL "https://nodejs.org/dist/v${ver}/node-v${ver}-linux-${node_arch}.tar.xz" -o "$tmp" \
    || return 1
  tar -xJf "$tmp" -C /usr/local --strip-components=1 \
    || tar -xJf "$tmp" -C "$BIN_DIR" --strip-components=1 \
    || return 1
  rm -f "$tmp"
  command -v node >/dev/null 2>&1
}

install_node_if_needed() {
  if command -v node >/dev/null 2>&1; then
    return 0
  fi
  if command -v apt-get >/dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y -qq curl ca-certificates gnupg
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
    apt-get install -y -qq nodejs
  elif command -v dnf >/dev/null 2>&1; then
    dnf install -y -q curl ca-certificates tar xz 2>/dev/null || true
    # Prefer official tarball (matches guest image); fall back to distro nodejs.
    install_node_tarball \
      || dnf install -y -q nodejs npm 2>/dev/null \
      || true
  elif command -v apk >/dev/null 2>&1; then
    apk add --no-cache nodejs npm curl 2>/dev/null || true
  else
    install_node_tarball || true
  fi
}

install_claude_code() {
  if command -v claude >/dev/null 2>&1 || command -v claude-code >/dev/null 2>&1; then
    echo "claude already present: $(command -v claude 2>/dev/null || command -v claude-code)"
    echo "agent-claude-code" >>"$MARKER_DIR/bootstrapped"
    return 0
  fi
  install_node_if_needed
  if command -v npm >/dev/null 2>&1; then
    npm install -g @anthropic-ai/claude-code 2>/dev/null \
      || npm install -g @anthropic-ai/claude-code@latest 2>/dev/null \
      || true
  fi
  if ! command -v claude >/dev/null 2>&1; then
    cat >"$BIN_DIR/claude" <<'EOF'
#!/bin/sh
echo "claude: CLI not fully installed in this image. Set ANTHROPIC_API_KEY and re-run bootstrap."
exit 1
EOF
    chmod +x "$BIN_DIR/claude"
  fi
  echo "agent-claude-code" >>"$MARKER_DIR/bootstrapped"
}

install_opencode() {
  if command -v opencode >/dev/null 2>&1 && opencode --version >/dev/null 2>&1; then
    echo "opencode already present: $(command -v opencode) ($(opencode --version 2>/dev/null || echo ok))"
    echo "agent-opencode" >>"$MARKER_DIR/bootstrapped"
    return 0
  fi
  install_node_if_needed
  if command -v npm >/dev/null 2>&1; then
    npm install -g opencode-ai 2>/dev/null \
      || npm install -g @opencode-ai/cli 2>/dev/null \
      || npm install -g opencode-ai@latest 2>/dev/null \
      || true
  fi
  if ! command -v opencode >/dev/null 2>&1 && command -v curl >/dev/null 2>&1; then
    curl -fsSL https://opencode.ai/install 2>/dev/null | bash 2>/dev/null || true
  fi
  if ! command -v opencode >/dev/null 2>&1 || ! opencode --version >/dev/null 2>&1; then
    cat >"$BIN_DIR/opencode" <<'EOF'
#!/bin/sh
echo "opencode: CLI not fully installed in this image. Re-run bootstrap or install manually."
exit 1
EOF
    chmod +x "$BIN_DIR/opencode"
    echo "WARNING: opencode install fell back to stub" >&2
  elif [ -x "$BIN_DIR/opencode" ] && grep -q "not fully installed" "$BIN_DIR/opencode" 2>/dev/null; then
    rm -f "$BIN_DIR/opencode"
  fi
  echo "agent-opencode" >>"$MARKER_DIR/bootstrapped"
}

install_db_postgres() {
  # Prefer companion script when present (copied alongside this file in guest).
  self_dir=$(CDPATH= cd -- "$(dirname -- "$0")" 2>/dev/null && pwd || echo "")
  companion=""
  for candidate in \
    "${self_dir}/install_db_postgres.sh" \
    "/tmp/install_db_postgres.sh" \
    "$MARKER_DIR/install_db_postgres.sh"
  do
    if [ -f "$candidate" ]; then
      companion="$candidate"
      break
    fi
  done
  if [ -n "$companion" ]; then
    sh "$companion"
    return 0
  fi
  # Inline fallback if companion script was not copied into the guest.
  if ! command -v psql >/dev/null 2>&1; then
    if command -v apt-get >/dev/null 2>&1; then
      export DEBIAN_FRONTEND=noninteractive
      apt-get update -qq
      apt-get install -y -qq postgresql-client || true
    elif command -v dnf >/dev/null 2>&1; then
      dnf install -y -q postgresql 2>/dev/null || true
    elif command -v apk >/dev/null 2>&1; then
      apk add --no-cache postgresql-client 2>/dev/null || true
    fi
  fi
  if [ ! -f "$MARKER_DIR/database.json" ]; then
    cat >"$MARKER_DIR/database.json" <<'EOF'
{
  "engine": "postgres",
  "database_url": "postgresql://postgres:postgres@127.0.0.1:5432/postgres",
  "status": "not_provisioned",
  "message": "Set DATABASE_URL in the sandbox env, update database_url below, or start Postgres (e.g. docker) then re-check status."
}
EOF
  fi
  echo "db-postgres" >>"$MARKER_DIR/bootstrapped"
}

for h in "$@"; do
  case "$h" in
    agent-claude-code|claude-code|claude)
      install_claude_code
      ;;
    agent-opencode|opencode)
      install_opencode
      ;;
    db-postgres|postgres)
      install_db_postgres
      ;;
    *)
      echo "unknown harness: $h" >&2
      ;;
  esac
done

echo "bootstrap complete"
