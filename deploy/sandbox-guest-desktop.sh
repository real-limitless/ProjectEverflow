#!/bin/bash
# Start a lean X11 + noVNC stack for the sandbox guest (HTTP on :6080).
# Safe to re-run; skips components that are already up.
set -euo pipefail

DISPLAY_NUM="${EF_DISPLAY:-99}"
export DISPLAY=":${DISPLAY_NUM}"
GEOMETRY="${EF_DESKTOP_GEOMETRY:-1280x800x24}"
VNC_PORT="${EF_VNC_PORT:-5900}"
NOVNC_PORT="${EF_NOVNC_PORT:-6080}"
NOVNC_WEB="${NOVNC_WEB:-/usr/share/novnc}"
LOG_DIR="${EF_DESKTOP_LOG_DIR:-/tmp/everflow-desktop}"
mkdir -p "$LOG_DIR"

if pgrep -f "[w]ebsockify.*${NOVNC_PORT}" >/dev/null 2>&1; then
  echo "everflow-desktop: already up on :${NOVNC_PORT}"
  exit 0
fi

if ! pgrep -x Xvfb >/dev/null 2>&1; then
  Xvfb "$DISPLAY" -screen 0 "$GEOMETRY" -ac -nolisten tcp -noreset \
    >"$LOG_DIR/xvfb.log" 2>&1 &
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    [[ -S "/tmp/.X11-unix/X${DISPLAY_NUM}" ]] && break
    sleep 0.1
  done
fi

if ! pgrep -x openbox >/dev/null 2>&1 && ! pgrep -x fluxbox >/dev/null 2>&1; then
  if command -v openbox >/dev/null 2>&1; then
    openbox >"$LOG_DIR/wm.log" 2>&1 &
  elif command -v fluxbox >/dev/null 2>&1; then
    fluxbox >"$LOG_DIR/wm.log" 2>&1 &
  fi
fi

if ! pgrep -x x11vnc >/dev/null 2>&1; then
  x11vnc -display "$DISPLAY" -rfbport "$VNC_PORT" -forever -shared -nopw -xkb -noxdamage \
    -listen localhost -o "$LOG_DIR/x11vnc.log" >/dev/null 2>&1 &
fi

if [[ ! -d "$NOVNC_WEB" ]]; then
  echo "everflow-desktop: noVNC web root missing at $NOVNC_WEB" >&2
  exit 1
fi

if command -v websockify >/dev/null 2>&1; then
  websockify --web="$NOVNC_WEB" "$NOVNC_PORT" "localhost:${VNC_PORT}" \
    >"$LOG_DIR/websockify.log" 2>&1 &
else
  python3 -m websockify --web="$NOVNC_WEB" "$NOVNC_PORT" "localhost:${VNC_PORT}" \
    >"$LOG_DIR/websockify.log" 2>&1 &
fi

echo "everflow-desktop: noVNC listening on :${NOVNC_PORT} (DISPLAY=${DISPLAY})"
