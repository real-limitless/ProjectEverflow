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

for h in "$@"; do
  case "$h" in
    agent-claude-code|claude-code|claude)
      install_claude_code
      ;;
    agent-opencode|opencode)
      install_opencode
      ;;
    *)
      echo "unknown harness: $h" >&2
      ;;
  esac
done

echo "bootstrap complete"
