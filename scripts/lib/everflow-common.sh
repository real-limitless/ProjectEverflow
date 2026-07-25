# shellcheck shell=bash
# Shared helpers for the Everflow control tool (sourced, not executed).

# Resolve repo root when this file is sourced from scripts/ or scripts/lib/.
if [[ -z "${EVERFLOW_ROOT:-}" ]]; then
  _ef_lib_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  EVERFLOW_ROOT="$(cd "${_ef_lib_dir}/../.." && pwd)"
  unset _ef_lib_dir
fi
ROOT="${EVERFLOW_ROOT}"

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
INSTALL_MODE="${INSTALL_MODE:-}"
BUILD_FROM_SOURCE="${BUILD_FROM_SOURCE:-0}"
SKIP_BUILD_GUEST="${SKIP_BUILD_GUEST:-false}"
ENVIRONMENT="${ENVIRONMENT:-development}"
CONTAINER_ENGINE="${CONTAINER_ENGINE:-}"
VERBOSE="${VERBOSE:-0}"
INSTALL_LOG="${INSTALL_LOG:-${ROOT}/.everflow-install.log}"
COMPOSE_UP_TIMEOUT_SEC="${COMPOSE_UP_TIMEOUT_SEC:-}"
SKIP_BOOTSTRAP="${SKIP_BOOTSTRAP:-0}"

PUBLIC_API_URL="${PUBLIC_API_URL:-http://localhost:8000}"
FRONTEND_URL="${FRONTEND_URL:-http://localhost:3000}"
API_URL="${PUBLIC_API_URL}"
UI_URL="${FRONTEND_URL}"

# Optional explicit seed control for install phase 1 (build|ghcr|skip|auto).
# Leave empty for interactive install wizard; install_phase_registry treats empty as auto.
REGISTRY_SEED_MODE="${REGISTRY_SEED_MODE:-}"

if [[ -z "${INSTALL_MODE}" ]]; then
  if [[ "${BUILD_FROM_SOURCE}" == "1" || "${BUILD_FROM_SOURCE}" == "true" ]]; then
    INSTALL_MODE=build
    : "${REGISTRY_SEED_MODE:=build}"
  elif [[ "${INSTALL_FROM_GHCR:-0}" == "1" || "${INSTALL_FROM_GHCR:-}" == "true" ]]; then
    INSTALL_MODE=ghcr
    : "${REGISTRY_SEED_MODE:=ghcr}"
  else
    # pull = compose images from embedded local registry (auto-seed if empty)
    INSTALL_MODE=pull
    # Do not force REGISTRY_SEED_MODE here — empty triggers TTY wizard on `install`
  fi
fi

if [[ -z "${COMPOSE_UP_TIMEOUT_SEC}" ]]; then
  if [[ "${INSTALL_MODE}" == "build" ]]; then
    COMPOSE_UP_TIMEOUT_SEC=1200
  else
    COMPOSE_UP_TIMEOUT_SEC=600
  fi
fi

# ── UI helpers ───────────────────────────────────────────────────────────────

print_banner() {
  local c0="" c1="" c2=""
  if [[ -t 1 ]] && [[ "${NO_COLOR:-}" == "" ]]; then
    c0=$'\033[0m'
    c1=$'\033[38;5;39m'
    c2=$'\033[38;5;245m'
  fi
  printf '%s' "${c1}"
  cat <<'BANNER'

  ____            _           _   _____                __ _
 |  _ \ _ __ ___ (_) ___  ___| |_| ____|_   _____ _ __/ _| | _____      __
 | |_) | '__/ _ \| |/ _ \/ __| __|  _| \ \ / / _ \ '__| |_| |/ _ \ \ /\ / /
 |  __/| | | (_) | |  __/ (__| |_| |___ \ V /  __/ |  |  _| | (_) \ V  V /
 |_|   |_|  \___// |\___|\___|\__|_____| \_/ \___|_|  |_| |_|\___/ \_/\_/
               |__/
BANNER
  printf '%s%s%s\n\n' "${c0}${c2}" \
    '         Self-hosted AI app platform  ·  control plane' \
    "${c0}"
}

step() {
  echo "  ▸ $*"
}

ok() {
  echo "    ✓ $*"
}

warn() {
  echo "    ! $*" >&2
}

die() {
  echo "" >&2
  echo "  ✗ $*" >&2
  if [[ -f "${INSTALL_LOG}" ]]; then
    echo "    Last log lines (${INSTALL_LOG}):" >&2
    tail -n 40 "${INSTALL_LOG}" >&2 || true
  fi
  exit 1
}

log_append() {
  {
    echo ""
    echo "===== $(date -Iseconds 2>/dev/null || date) :: $* ====="
  } >>"${INSTALL_LOG}" 2>/dev/null || true
}

# Run a command quietly (log file) unless VERBOSE=1
run_quiet() {
  local label="$1"
  shift
  step "${label}"
  if [[ "${VERBOSE}" == "1" || "${VERBOSE}" == "true" ]]; then
    "$@"
    return
  fi
  {
    echo ""
    echo "===== $(date -Iseconds 2>/dev/null || date) :: ${label} ====="
    echo "+ $*"
  } >>"${INSTALL_LOG}"
  if "$@" >>"${INSTALL_LOG}" 2>&1; then
    ok "done"
  else
    local rc=$?
    die "${label} failed (exit ${rc}). Re-run with VERBOSE=1 for live logs."
  fi
}

# Spinner while a background PID runs. Optional 3rd arg: timeout seconds (0 = none).
spin_while() {
  local pid="$1"
  local msg="$2"
  local timeout_sec="${3:-0}"
  local frames=('⠋' '⠙' '⠹' '⠸' '⠼' '⠴' '⠦' '⠧' '⠇' '⠏')
  local i=0
  local start="${SECONDS}"
  if [[ ! -t 1 ]] || [[ "${VERBOSE}" == "1" || "${VERBOSE}" == "true" ]]; then
    if [[ "${timeout_sec}" -gt 0 ]]; then
      while kill -0 "${pid}" 2>/dev/null; do
        if [[ $((SECONDS - start)) -ge "${timeout_sec}" ]]; then
          kill "${pid}" 2>/dev/null || true
          wait "${pid}" 2>/dev/null || true
          echo "    ! timed out after ${timeout_sec}s: ${msg}" >>"${INSTALL_LOG}"
          return 124
        fi
        sleep 0.5
      done
    fi
    wait "${pid}"
    return $?
  fi
  while kill -0 "${pid}" 2>/dev/null; do
    if [[ "${timeout_sec}" -gt 0 ]] && [[ $((SECONDS - start)) -ge "${timeout_sec}" ]]; then
      kill "${pid}" 2>/dev/null || true
      wait "${pid}" 2>/dev/null || true
      printf '\r\033[K'
      echo "    ! timed out after ${timeout_sec}s: ${msg}" >>"${INSTALL_LOG}"
      return 124
    fi
    printf '\r    %s %s…' "${frames[$((i % ${#frames[@]}))]}" "${msg}"
    i=$((i + 1))
    sleep 0.12
  done
  wait "${pid}"
  local rc=$?
  printf '\r\033[K'
  if [[ ${rc} -eq 0 ]]; then
    ok "${msg}"
  fi
  return ${rc}
}

# ── Engine detection ─────────────────────────────────────────────────────────

detect_engine() {
  if [[ -n "${CONTAINER_ENGINE}" ]]; then
    echo "${CONTAINER_ENGINE}"
    return
  fi
  if command -v docker >/dev/null 2>&1; then
    echo docker
    return
  fi
  if command -v podman >/dev/null 2>&1; then
    echo podman
    return
  fi
  echo "error: need docker or podman on the host (no other install path)." >&2
  echo "       Install Docker Engine or Podman, then re-run this tool." >&2
  exit 1
}

# Call once after sourcing: sets ENGINE and ensures compose works.
everflow_init_engine() {
  ENGINE="$(detect_engine)"
  export ENGINE
  mkdir -p "$(dirname "${INSTALL_LOG}")" 2>/dev/null || true
  touch "${INSTALL_LOG}" 2>/dev/null || true
}

compose() {
  if [[ -z "${ENGINE:-}" ]]; then
    everflow_init_engine
  fi
  if "${ENGINE}" compose version >/dev/null 2>&1; then
    "${ENGINE}" compose "$@"
    return
  fi
  if [[ "${ENGINE}" == "podman" ]] && command -v podman-compose >/dev/null 2>&1; then
    podman-compose "$@"
    return
  fi
  if command -v docker-compose >/dev/null 2>&1; then
    docker-compose "$@"
    return
  fi
  echo "error: ${ENGINE} compose plugin not found." >&2
  echo "       Install the Compose V2 plugin (docker compose / podman compose)." >&2
  exit 1
}

compose_ps_all() {
  compose -f "${COMPOSE_FILE}" ps 2>&1 || true
  "${ENGINE}" ps -a --filter "name=projecteverflow_" --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}' 2>&1 \
    || "${ENGINE}" ps -a 2>&1 | grep -iE 'projecteverflow|everflow' || true
}

diagnose_stack_failure() {
  local reason="${1:-compose up failed}"
  {
    echo ""
    echo "===== diagnose: ${reason} ====="
    echo "===== compose / engine ps ====="
    compose_ps_all
    for svc in registry sandbox-agent searxng backend frontend; do
      echo "===== logs: ${svc} (tail) ====="
      compose -f "${COMPOSE_FILE}" logs --tail=50 "${svc}" 2>&1 || true
    done
  } >>"${INSTALL_LOG}" 2>&1

  if grep -qiE 'Permission denied.*settings\.yml|Permission denied.*/etc/searxng' "${INSTALL_LOG}" 2>/dev/null; then
    warn "searxng cannot read settings.yml (SELinux EACCES is common on Fedora/RHEL/Podman)."
    warn "Ensure compose mounts use :Z,ro (see docker-compose.yml searxng volumes)."
  fi
}

assert_stack_started() {
  local ps_out
  ps_out="$(compose_ps_all)"
  {
    echo ""
    echo "===== post-up compose ps ====="
    echo "${ps_out}"
  } >>"${INSTALL_LOG}"

  if echo "${ps_out}" | grep -iE 'searxng|sandbox-agent|backend' | grep -qiE 'Exit|Exited|dead'; then
    diagnose_stack_failure "one or more services exited after compose up"
    return 1
  fi
  if echo "${ps_out}" | grep -iE 'backend|frontend' | grep -qiE '\bCreated\b'; then
    diagnose_stack_failure "backend/frontend stuck in Created (dependency or compose hang)"
    return 1
  fi
  return 0
}

api_health_ok() {
  compose -f "${COMPOSE_FILE}" exec -T backend \
    python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/system/health')" \
    >/dev/null 2>&1 \
    || compose -f "${COMPOSE_FILE}" exec -T backend \
      python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health')" \
      >/dev/null 2>&1
}

wait_for_api_health() {
  local max="${1:-60}"
  local i
  step "Waiting for API health"
  for i in $(seq 1 "${max}"); do
    if api_health_ok; then
      ok "API is ready"
      return 0
    fi
    if [[ -t 1 ]] && [[ "${VERBOSE}" != "1" && "${VERBOSE}" != "true" ]]; then
      printf '\r    … health check %s/%s' "${i}" "${max}"
    fi
    if [[ "${i}" -eq "${max}" ]]; then
      printf '\r'
      return 1
    fi
    sleep 2
  done
  printf '\r'
  return 1
}

# Host curl if available; else compose exec into backend for localhost API.
# Usage: api_http GET /api/v1/setup/status
#        api_http POST /api/v1/setup/bootstrap '{"email":...}'
# Prints body on stdout; exit code is HTTP success (0) vs failure (1).
# Sets API_HTTP_CODE.
api_http() {
  local method="$1"
  local path="$2"
  local body="${3:-}"
  local url="${API_URL}${path}"
  API_HTTP_CODE="000"

  if command -v curl >/dev/null 2>&1; then
    local tmp
    tmp="$(mktemp)"
    if [[ -n "${body}" ]]; then
      API_HTTP_CODE="$(
        curl -sS -o "${tmp}" -w '%{http_code}' \
          -X "${method}" \
          -H 'Content-Type: application/json' \
          -d "${body}" \
          "${url}" 2>/dev/null || echo "000"
      )"
    else
      API_HTTP_CODE="$(
        curl -sS -o "${tmp}" -w '%{http_code}' \
          -X "${method}" \
          "${url}" 2>/dev/null || echo "000"
      )"
    fi
    cat "${tmp}" 2>/dev/null || true
    rm -f "${tmp}"
    [[ "${API_HTTP_CODE}" =~ ^2[0-9][0-9] ]]
    return
  fi

  # Fallback: call from inside backend container (path on loopback).
  # Pass method/path/body via env to avoid shell quoting of secrets in process list beyond compose.
  local out
  out="$(
    METHOD="${method}" PATH_Q="${path}" BODY_Q="${body}" \
      compose -f "${COMPOSE_FILE}" exec -T \
      -e METHOD -e PATH_Q -e BODY_Q \
      backend python -c '
import os, urllib.error, urllib.request
method = os.environ.get("METHOD", "GET")
path = os.environ.get("PATH_Q", "/")
body = os.environ.get("BODY_Q", "")
data = body.encode() if body else None
headers = {"Content-Type": "application/json"} if body else {}
req = urllib.request.Request("http://127.0.0.1:8000" + path, data=data, method=method, headers=headers)
try:
    with urllib.request.urlopen(req, timeout=30) as r:
        print(r.status)
        print(r.read().decode())
except urllib.error.HTTPError as e:
    print(e.code)
    print(e.read().decode(errors="replace"))
except Exception as e:
    print(0)
    print(str(e))
' 2>/dev/null || true
  )"
  API_HTTP_CODE="$(printf '%s\n' "${out}" | head -n1 | tr -d '[:space:]')"
  printf '%s\n' "${out}" | tail -n +2
  [[ "${API_HTTP_CODE}" =~ ^2[0-9][0-9] ]]
}

is_tty() {
  [[ -t 0 && -t 1 ]]
}

confirm_yes() {
  local prompt="${1:-Continue?}"
  local default="${2:-n}"
  local reply
  if [[ "${default}" == "y" ]]; then
    read -r -p "  ${prompt} [Y/n] " reply || true
    reply="${reply:-y}"
  else
    read -r -p "  ${prompt} [y/N] " reply || true
    reply="${reply:-n}"
  fi
  [[ "${reply}" =~ ^[Yy]([Ee][Ss])?$ ]]
}

read_secret() {
  local prompt="$1"
  local var
  read -r -s -p "  ${prompt}: " var
  echo "" >&2
  printf '%s' "${var}"
}
