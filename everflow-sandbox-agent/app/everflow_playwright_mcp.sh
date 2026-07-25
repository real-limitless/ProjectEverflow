#!/bin/bash
# Launch official @playwright/mcp for OpenCode inside the Everflow guest.
#
# Mode is read from /workspace/.everflow/browser.mode:
#   headless (default) — --headless
#   headed             — visible Chromium on the guest X display (Desktop panel)
#
# Always uses Playwright Chromium + --no-sandbox (required in microVMs).
set -euo pipefail

WORKSPACE="${EVERFLOW_WORKSPACE:-/workspace}"
MODE_FILE="${WORKSPACE}/.everflow/browser.mode"
DISPLAY_NUM="${EF_DISPLAY:-99}"
export DISPLAY="${DISPLAY:-:${DISPLAY_NUM}}"
export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-/opt/everflow-browsers}"

mode="headless"
if [[ -f "$MODE_FILE" ]]; then
  raw="$(tr -d '[:space:]' <"$MODE_FILE" | tr '[:upper:]' '[:lower:]')"
  case "$raw" in
    headed|headful|visible) mode="headed" ;;
    headless|*) mode="headless" ;;
  esac
fi

# Prefer global install; fall back to npx for stale guests.
MCP_BIN=""
if command -v playwright-mcp >/dev/null 2>&1; then
  MCP_BIN="playwright-mcp"
elif [[ -x /usr/local/lib/node_modules/@playwright/mcp/cli.js ]]; then
  MCP_BIN="node"
  set -- /usr/local/lib/node_modules/@playwright/mcp/cli.js "$@"
elif command -v npx >/dev/null 2>&1; then
  MCP_BIN="npx"
  set -- -y @playwright/mcp "$@"
else
  echo "everflow-playwright-mcp: @playwright/mcp not found; rebuild everflow-sandbox-guest" >&2
  exit 127
fi

args=(--browser chromium --no-sandbox)
# Reduce flakiness in small /dev/shm microVMs (Playwright launchOptions via env where supported).
export PLAYWRIGHT_CHROMIUM_ARGS="${PLAYWRIGHT_CHROMIUM_ARGS:---disable-dev-shm-usage}"

if [[ "$mode" == "headless" ]]; then
  args+=(--headless)
else
  # Headed needs X11 (everflow-desktop / Xvfb on :99).
  if [[ ! -S "/tmp/.X11-unix/X${DISPLAY_NUM}" ]]; then
    if command -v everflow-desktop.sh >/dev/null 2>&1; then
      everflow-desktop.sh start >/tmp/everflow-desktop-playwright.log 2>&1 || true
    elif [[ -x /usr/local/bin/everflow-desktop.sh ]]; then
      /usr/local/bin/everflow-desktop.sh start >/tmp/everflow-desktop-playwright.log 2>&1 || true
    fi
  fi
fi

if [[ "$MCP_BIN" == "playwright-mcp" ]]; then
  exec playwright-mcp "${args[@]}" "$@"
elif [[ "$MCP_BIN" == "node" ]]; then
  exec node "$@" "${args[@]}"
else
  exec npx "$@" "${args[@]}"
fi
