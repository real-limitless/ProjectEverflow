#!/bin/sh
# Install Everflow agent harnesses inside a project sandbox.
# Idempotent; safe to re-run.
set -eu

MARKER_DIR="${WORKSPACE:-/workspace}/.everflow"
BIN_DIR="${MARKER_DIR}/bin"
mkdir -p "$BIN_DIR"
export PATH="$BIN_DIR:$PATH"

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
  if command -v claude >/dev/null 2>&1; then
    echo "claude already present: $(command -v claude)"
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
  if command -v opencode >/dev/null 2>&1; then
    echo "opencode already present: $(command -v opencode)"
    return 0
  fi
  install_node_if_needed
  if command -v npm >/dev/null 2>&1; then
    npm install -g opencode-ai 2>/dev/null \
      || npm install -g @opencode-ai/cli 2>/dev/null \
      || true
  fi
  if ! command -v opencode >/dev/null 2>&1; then
    cat >"$BIN_DIR/opencode" <<'EOF'
#!/bin/sh
echo "opencode: CLI not fully installed in this image. Re-run bootstrap or install manually."
exit 1
EOF
    chmod +x "$BIN_DIR/opencode"
  fi
  echo "agent-opencode" >>"$MARKER_DIR/bootstrapped"
}

if [ "$#" -eq 0 ]; then
  set -- agent-claude-code agent-opencode
fi

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
