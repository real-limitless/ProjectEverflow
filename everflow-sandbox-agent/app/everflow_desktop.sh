#!/bin/bash
# Start an X11 + XFCE + noVNC stack for the sandbox guest (HTTP on :6080).
# Safe to re-run. Requires BOTH VNC (:5900) and noVNC (:6080) accepting
# connections — websockify alone is not enough (noVNC shows "Failed to connect").
#
# Under microsandbox, /init.krun is PID 1 and the OCI ENTRYPOINT is not kept
# alive — the sandbox-agent installs/runs this script via guest exec.
#
# Panel resize: everflow-desktop.sh --resize WIDTH HEIGHT
#   Xvfb is started at a large max framebuffer; xrandr --fb shrinks/grows the
#   active size; x11vnc -xrandr pushes NewFBSize to noVNC clients.
set -euo pipefail

DISPLAY_NUM="${EF_DISPLAY:-99}"
export DISPLAY=":${DISPLAY_NUM}"
# Preferred initial size (WxHxDepth). Xvfb starts at MAX so the panel can grow.
GEOMETRY="${EF_DESKTOP_GEOMETRY:-1280x800x24}"
MAX_GEOMETRY="${EF_DESKTOP_MAX_GEOMETRY:-3840x2160x24}"
VNC_PORT="${EF_VNC_PORT:-5900}"
NOVNC_PORT="${EF_NOVNC_PORT:-6080}"
NOVNC_WEB="${NOVNC_WEB:-/usr/share/novnc}"
LOG_DIR="${EF_DESKTOP_LOG_DIR:-/tmp/everflow-desktop}"
XSOCK="/tmp/.X11-unix/X${DISPLAY_NUM}"
# XFCE / apps need a writable HOME (microsandbox guests are often root).
export HOME="${HOME:-/root}"
mkdir -p "$LOG_DIR" "$HOME"

_parse_wh() {
  # "1280x800x24" or "1280x800" -> sets _W _H
  local g="$1"
  _W="${g%%x*}"
  local rest="${g#*x}"
  _H="${rest%%x*}"
}

_clamp_wh() {
  # even dimensions within [640..3840] x [480..2160]
  local w="$1" h="$2"
  w=$((w < 640 ? 640 : w))
  h=$((h < 480 ? 480 : h))
  w=$((w > 3840 ? 3840 : w))
  h=$((h > 2160 ? 2160 : h))
  w=$((w - w % 2))
  h=$((h - h % 2))
  _W=$w
  _H=$h
}

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

_set_fb_size() {
  # Resize the active X framebuffer (x11vnc -xrandr picks this up → NewFBSize).
  local w="$1" h="$2"
  _clamp_wh "$w" "$h"
  w=$_W
  h=$_H
  if ! command -v xrandr >/dev/null 2>&1; then
    echo "everflow-desktop: xrandr not available" >&2
    return 1
  fi
  if ! xrandr --fb "${w}x${h}" >/dev/null 2>&1; then
    # Some Xvfb builds need an explicit mode first
    if command -v gtf >/dev/null 2>&1; then
      local modeline name
      modeline="$(gtf "$w" "$h" 60 | awk -F'Modeline ' '/Modeline/{print $2}')"
      name="$(echo "$modeline" | awk '{print $1}' | tr -d '"')"
      if [[ -n "$modeline" && -n "$name" ]]; then
        # shellcheck disable=SC2086
        xrandr --newmode $modeline 2>/dev/null || true
        xrandr --addmode screen "$name" 2>/dev/null || true
        xrandr --output screen --mode "$name" 2>/dev/null || true
      fi
    fi
    xrandr --fb "${w}x${h}" >/dev/null 2>&1 || {
      echo "everflow-desktop: resize to ${w}x${h} failed" >&2
      xrandr 2>&1 | head -n 8 >&2 || true
      return 1
    }
  fi
  echo "everflow-desktop: framebuffer ${w}x${h}"
  return 0
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

_clean_x_files() {
  # Stale lock/socket after a dead Xvfb block restart ("Server is already active").
  rm -f "/tmp/.X${DISPLAY_NUM}-lock" "$XSOCK" 2>/dev/null || true
  mkdir -p /tmp/.X11-unix
  chmod 1777 /tmp/.X11-unix 2>/dev/null || true
}

_daemon() {
  # microsandbox guest exec captures stdout/stderr as pipes and waits until
  # every writer closes them. nohup/disown alone still leaves children in the
  # exec process group (they die as zombies) and can hold the pipes open
  # (hang until agent timeout). setsid -f double-forks into a new session and
  # we fully redirect stdio away from the exec pipes.
  local log="${1:-/dev/null}"
  shift
  if command -v setsid >/dev/null 2>&1; then
    # -f: fork so setsid returns immediately; child is session leader.
    if setsid -f "$@" </dev/null >"$log" 2>&1; then
      return 0
    fi
    # BusyBox/old setsid may lack -f
    setsid "$@" </dev/null >"$log" 2>&1 &
  else
    nohup "$@" </dev/null >"$log" 2>&1 &
  fi
  disown 2>/dev/null || true
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
  _clean_x_files
}

_start_session() {
  # Prefer a real XFCE desktop; fall back to a minimal WM if packages are missing
  # (e.g. stale guest image that only received this script via agent install).
  if command -v startxfce4 >/dev/null 2>&1; then
    if command -v dbus-launch >/dev/null 2>&1; then
      _daemon "$LOG_DIR/wm.log" dbus-launch --exit-with-session startxfce4
    else
      _daemon "$LOG_DIR/wm.log" startxfce4
    fi
    return
  fi
  if command -v openbox >/dev/null 2>&1; then
    _daemon "$LOG_DIR/wm.log" openbox
    return
  fi
  if command -v fluxbox >/dev/null 2>&1; then
    _daemon "$LOG_DIR/wm.log" fluxbox
  fi
}

_launch_terminal() {
  # Give the session a visible app so the first connect is not an empty desk.
  # Must not hold exec stdout/stderr (would hang guest exec until timeout).
  if command -v xfce4-terminal >/dev/null 2>&1; then
    _daemon /dev/null bash -c 'sleep 1.5; exec xfce4-terminal --working-directory=/workspace'
  elif command -v xterm >/dev/null 2>&1; then
    _daemon /dev/null bash -c 'sleep 1.5; exec xterm -e bash -lc "cd /workspace; exec bash"'
  fi
}

# --- one-shot resize (panel ResizeObserver) ---------------------------------
if [[ "${1:-}" == "--resize" ]]; then
  if [[ -z "${2:-}" || -z "${3:-}" ]]; then
    echo "usage: everflow-desktop.sh --resize WIDTH HEIGHT" >&2
    exit 2
  fi
  if [[ ! -S "$XSOCK" ]] || ! _alive Xvfb; then
    echo "everflow-desktop: X display not running; start desktop first" >&2
    exit 1
  fi
  _set_fb_size "$2" "$3"
  exit $?
fi

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
  # Drop stale lock/socket if Xvfb is dead but left files behind.
  if ! _alive Xvfb; then
    _clean_x_files
  fi
  # Large max framebuffer so --resize can grow up to 4K; RANDR enables xrandr --fb.
  _daemon "$LOG_DIR/xvfb.log" Xvfb "$DISPLAY" -screen 0 "$MAX_GEOMETRY" \
    -ac -nolisten tcp -noreset +extension RANDR
  for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do
    [[ -S "$XSOCK" ]] && _alive Xvfb && break
    sleep 0.1
  done
  if [[ ! -S "$XSOCK" ]] || ! _alive Xvfb; then
    echo "everflow-desktop: Xvfb failed to create $XSOCK" >&2
    tail -n 40 "$LOG_DIR/xvfb.log" >&2 || true
    exit 1
  fi
  # Shrink from max down to preferred initial geometry.
  _parse_wh "$GEOMETRY"
  _set_fb_size "$_W" "$_H" || true
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
  # -xrandr resize: when the panel resizes via xrandr --fb, push NewFBSize to clients
  _daemon /dev/null x11vnc -display "$DISPLAY" -rfbport "$VNC_PORT" -forever -shared -nopw \
    -xkb -noxdamage -listen localhost -xrandr resize -o "$LOG_DIR/x11vnc.log"
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
    _daemon "$LOG_DIR/websockify.log" websockify --web="$NOVNC_WEB" "$NOVNC_PORT" "localhost:${VNC_PORT}"
  else
    _daemon "$LOG_DIR/websockify.log" python3 -m websockify --web="$NOVNC_WEB" "$NOVNC_PORT" "localhost:${VNC_PORT}"
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
