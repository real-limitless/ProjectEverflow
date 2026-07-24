#!/bin/bash
# Guest entrypoint: start noVNC desktop stack, then run the container command.
#
# Under microsandbox, PID 1 is /init.krun and this ENTRYPOINT is not kept as a
# long-lived process — the sandbox-agent starts everflow-desktop.sh via exec.
# Keep this for plain container runs and as a best-effort boot hook.
set -euo pipefail

if [[ "${EF_DESKTOP_ENABLE:-1}" != "0" ]]; then
  if ! /usr/local/bin/everflow-desktop.sh; then
    echo "everflow-guest: desktop stack failed to start (continuing)" >&2
  fi
fi

if [[ "$#" -gt 0 ]]; then
  exec "$@"
fi

exec sleep infinity
