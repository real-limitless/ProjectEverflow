#!/bin/bash
# Start an X11 + XFCE + noVNC stack for the sandbox guest (HTTP on :6080).
# Safe to re-run. Requires BOTH VNC (:5900) and noVNC (:6080) accepting
# connections — websockify alone is not enough (noVNC shows "Failed to connect").
#
# Under microsandbox, /init.krun is PID 1 and the OCI ENTRYPOINT is not kept
# alive — the sandbox-agent installs/runs this script via guest exec.
set -euo pipefail

DISPLAY_NUM="${EF_DISPLAY:-99}"
export DISPLAY=":${DISPLAY_NUM}"
GEOMETRY="${EF_DESKTOP_GEOMETRY:-1280x800x24}"
VNC_PORT="${EF_VNC_PORT:-5900}"
NOVNC_PORT="${EF_NOVNC_PORT:-6080}"
NOVNC_WEB="${NOVNC_WEB:-/usr/share/novnc}"
LOG_DIR="${EF_DESKTOP_LOG_DIR:-/tmp/everflow-desktop}"
XSOCK="/tmp/.X11-unix/X${DISPLAY_NUM}"
# XFCE / apps need a writable HOME (microsandbox guests are often root).
export HOME="${HOME:-/root}"
mkdir -p "$LOG_DIR" "$HOME"

_port_open() {
  local port="$1"
  python3 -c "
import socket
s = socket.socket()
s.settimeout(0.5)
r = s.connect_ex(('127.0.0.1', int('${port}')))
s.close()
raise SystemExit(0 if r == 0 else 1)
" 2>/dev/null
}

_alive() {
  # True if a non-zombie process with this comm exists (pgrep matches zombies).
  local comm="$1" pid state
  for pid in $(pgrep -x "$comm" 2>/dev/null || true); do
    state="$(awk '/^State:/{print $2}' "/proc/${pid}/status" 2>/dev/null || true)"
    if [[ "$state" != "Z" && -n "$state" ]]; then
      return 0
    fi
  done
  return 1
}

_wm_alive() {
  _alive xfce4-session || _alive xfwm4 || _alive openbox || _alive fluxbox
}

_stack_healthy() {
  [[ -S "$XSOCK" ]] && _port_open "$VNC_PORT" && _port_open "$NOVNC_PORT"
}

_stop_session() {
  pkill -x xfce4-session 2>/dev/null || true
  pkill -x xfce4-panel 2>/dev/null || true
  pkill -x xfdesktop 2>/dev/null || true
  pkill -x xfwm4 2>/dev/null || true
  pkill -x Thunar 2>/dev/null || true
  pkill -x openbox 2>/dev/null || true
  pkill -x fluxbox 2>/dev/null || true
}

_stop_stack() {
  # Best-effort tear-down of live processes (zombies are ignored).
  pkill -x websockify 2>/dev/null || true
  pkill -x x11vnc 2>/dev/null || true
  _stop_session
  pkill -x Xvfb 2>/dev/null || true
  # Free ports if something else is bound
  if command -v fuser >/dev/null 2>&1; then
    fuser -k "${VNC_PORT}/tcp" 2>/dev/null || true
    fuser -k "${NOVNC_PORT}/tcp" 2>/dev/null || true
  fi
  sleep 0.3
}

_start_session() {
  # Prefer a real XFCE desktop; fall back to a minimal WM if packages are missing
  # (e.g. stale guest image that only received this script via agent install).
  if command -v startxfce4 >/dev/null 2>&1; then
    if command -v dbus-launch >/dev/null 2>&1; then
      nohup dbus-launch --exit-with-session startxfce4 \
        >"$LOG_DIR/wm.log" 2>&1 &
    else
      nohup startxfce4 >"$LOG_DIR/wm.log" 2>&1 &
    fi
    disown || true
    return
  fi
  if command -v openbox >/dev/null 2>&1; then
    nohup openbox >"$LOG_DIR/wm.log" 2>&1 &
    disown || true
    return
  fi
  if command -v fluxbox >/dev/null 2>&1; then
    nohup fluxbox >"$LOG_DIR/wm.log" 2>&1 &
    disown || true
  fi
}

_launch_terminal() {
  # Give the session a visible app so the first connect is not an empty desk.
  (
    sleep 1.5
    if command -v xfce4-terminal >/dev/null 2>&1; then
      xfce4-terminal --working-directory=/workspace >/dev/null 2>&1 || true
    elif command -v xterm >/dev/null 2>&1; then
      xterm -e bash -lc 'cd /workspace; exec bash' >/dev/null 2>&1 || true
    fi
  ) &
  disown || true
}

if [[ "${1:-}" == "--restart" ]]; then
  _stop_stack
elif _stack_healthy && _wm_alive; then
  echo "everflow-desktop: already up on :${NOVNC_PORT} (vnc :${VNC_PORT})"
  exit 0
elif _port_open "$NOVNC_PORT" || _port_open "$VNC_PORT" || [[ -S "$XSOCK" ]]; then
  # Partial / zombie-confused stack — repair
  echo "everflow-desktop: repairing partial stack" >&2
  _stop_stack
fi

if [[ ! -d "$NOVNC_WEB" ]]; then
  echo "everflow-desktop: noVNC web root missing at $NOVNC_WEB" >&2
  exit 1
fi

if [[ ! -S "$XSOCK" ]] || ! _alive Xvfb; then
  nohup Xvfb "$DISPLAY" -screen 0 "$GEOMETRY" -ac -nolisten tcp -noreset \
    >"$LOG_DIR/xvfb.log" 2>&1 &
  disown || true
  for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do
    [[ -S "$XSOCK" ]] && break
    sleep 0.1
  done
  if [[ ! -S "$XSOCK" ]]; then
    echo "everflow-desktop: Xvfb failed to create $XSOCK" >&2
    tail -n 40 "$LOG_DIR/xvfb.log" >&2 || true
    exit 1
  fi
fi

if ! _wm_alive; then
  _start_session
  for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
    _wm_alive && break
    sleep 0.2
  done
  if ! _wm_alive; then
    echo "everflow-desktop: window manager failed to start (check $LOG_DIR/wm.log)" >&2
    tail -n 40 "$LOG_DIR/wm.log" >&2 || true
    # Continue — VNC may still be useful for debugging a blank display
  else
    _launch_terminal
  fi
fi

if ! _port_open "$VNC_PORT"; then
  # Clear a dead x11vnc that still holds the name / port
  pkill -x x11vnc 2>/dev/null || true
  nohup x11vnc -display "$DISPLAY" -rfbport "$VNC_PORT" -forever -shared -nopw -xkb -noxdamage \
    -listen localhost -o "$LOG_DIR/x11vnc.log" >/dev/null 2>&1 &
  disown || true
  for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
    _port_open "$VNC_PORT" && break
    sleep 0.2
  done
  if ! _port_open "$VNC_PORT"; then
    echo "everflow-desktop: x11vnc failed to listen on :${VNC_PORT}" >&2
    tail -n 40 "$LOG_DIR/x11vnc.log" >&2 || true
    exit 1
  fi
fi

if ! _port_open "$NOVNC_PORT"; then
  pkill -x websockify 2>/dev/null || true
  if command -v websockify >/dev/null 2>&1; then
    nohup websockify --web="$NOVNC_WEB" "$NOVNC_PORT" "localhost:${VNC_PORT}" \
      >"$LOG_DIR/websockify.log" 2>&1 &
    disown || true
  else
    nohup python3 -m websockify --web="$NOVNC_WEB" "$NOVNC_PORT" "localhost:${VNC_PORT}" \
      >"$LOG_DIR/websockify.log" 2>&1 &
    disown || true
  fi
fi

for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
  if _stack_healthy; then
    echo "everflow-desktop: noVNC listening on :${NOVNC_PORT} (vnc :${VNC_PORT}, DISPLAY=${DISPLAY})"
    exit 0
  fi
  sleep 0.2
done

echo "everflow-desktop: stack unhealthy after start (check $LOG_DIR)" >&2
tail -n 20 "$LOG_DIR/xvfb.log" "$LOG_DIR/x11vnc.log" "$LOG_DIR/websockify.log" "$LOG_DIR/wm.log" >&2 || true
exit 1
