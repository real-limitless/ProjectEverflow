#!/usr/bin/env bash
# Everflow control-plane installer — Docker / Podman only.
#
# Default: pull prebuilt images from GHCR (no local container build).
# From source:  BUILD_FROM_SOURCE=1 ./scripts/everflow-install.sh
# Verbose:      VERBOSE=1 ./scripts/everflow-install.sh
#
# Host prerequisites: docker or podman (+ compose plugin), Linux + /dev/kvm for
# real sandboxes. No host Python/Node required.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
# pull (default) | build
INSTALL_MODE="${INSTALL_MODE:-}"
BUILD_FROM_SOURCE="${BUILD_FROM_SOURCE:-0}"
SKIP_BUILD_GUEST="${SKIP_BUILD_GUEST:-false}"
ENVIRONMENT="${ENVIRONMENT:-development}"
CONTAINER_ENGINE="${CONTAINER_ENGINE:-}"
VERBOSE="${VERBOSE:-0}"
INSTALL_LOG="${INSTALL_LOG:-${ROOT}/.everflow-install.log}"

if [[ -z "${INSTALL_MODE}" ]]; then
  if [[ "${BUILD_FROM_SOURCE}" == "1" || "${BUILD_FROM_SOURCE}" == "true" ]]; then
    INSTALL_MODE=build
  else
    INSTALL_MODE=pull
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
    '         Self-hosted AI app platform  ·  container install' \
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

# Spinner while a background PID runs
spin_while() {
  local pid="$1"
  local msg="$2"
  local frames=('⠋' '⠙' '⠹' '⠸' '⠼' '⠴' '⠦' '⠧' '⠇' '⠏')
  local i=0
  if [[ ! -t 1 ]] || [[ "${VERBOSE}" == "1" || "${VERBOSE}" == "true" ]]; then
    wait "${pid}"
    return $?
  fi
  while kill -0 "${pid}" 2>/dev/null; do
    printf '\r    %s %s…' "${frames[$((i % ${#frames[@]}))]}" "${msg}"
    i=$((i + 1))
    sleep 0.12
  done
  wait "${pid}"
  local rc=$?
  # Clear the spinner line
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
  echo "       Install Docker Engine or Podman, then re-run this script." >&2
  exit 1
}

ENGINE="$(detect_engine)"

compose() {
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

rand_hex() {
  "${ENGINE}" run --rm --entrypoint /bin/sh docker.io/library/alpine:3.20 -c \
    'apk add --no-cache openssl >/dev/null 2>&1 && openssl rand -hex 32' 2>>"${INSTALL_LOG}"
}

env_set() {
  local key="$1"
  local value="$2"
  "${ENGINE}" run --rm -v "${ROOT}:/work:Z" -w /work docker.io/library/alpine:3.20 \
    /bin/sh -c "
      set -e
      if grep -q '^${key}=' .env 2>/dev/null; then
        sed -i 's|^${key}=.*|${key}=${value}|' .env
      else
        printf '%s=%s\n' '${key}' '${value}' >> .env
      fi
    " >>"${INSTALL_LOG}" 2>&1
}

# ── Main ─────────────────────────────────────────────────────────────────────

: >"${INSTALL_LOG}"
print_banner

echo "  engine  ${ENGINE}"
echo "  root    ${ROOT}"
echo "  mode    ${INSTALL_MODE}  (pull = GHCR images · build = from source)"
echo "  log     ${INSTALL_LOG}"
[[ "${VERBOSE}" == "1" || "${VERBOSE}" == "true" ]] && echo "  verbose on"
echo ""

if [[ ! -f .env ]]; then
  step "Creating .env and generating secrets"
  cp .env.example .env
  SECRET="$(rand_hex)"
  AGENT_TOKEN="$(rand_hex)"
  CREDS_KEY="$(rand_hex)"
  env_set SECRET_KEY "${SECRET}"
  env_set SANDBOX_AGENT_TOKEN "${AGENT_TOKEN}"
  env_set CREDENTIALS_ENCRYPTION_KEY "${CREDS_KEY}"
  env_set ENVIRONMENT "${ENVIRONMENT}"
  ok "secrets written to .env"
else
  ok "using existing .env"
fi

if [[ ! -e /dev/kvm ]]; then
  warn "/dev/kvm missing — set SANDBOX_MOCK=true for CI/dev only"
else
  ok "/dev/kvm present"
fi

start_stack_pull() {
  # Prefer registry images; no --build.
  if [[ "${VERBOSE}" == "1" || "${VERBOSE}" == "true" ]]; then
    step "Pulling prebuilt images from GHCR"
    compose -f "${COMPOSE_FILE}" pull
    step "Starting stack"
    compose -f "${COMPOSE_FILE}" up -d --no-build
    ok "stack started (prebuilt images)"
    return 0
  fi
  (
    echo ""
    echo "===== $(date -Iseconds 2>/dev/null || date) :: compose pull ====="
    compose -f "${COMPOSE_FILE}" pull
    echo "===== compose up -d --no-build ====="
    compose -f "${COMPOSE_FILE}" up -d --no-build
  ) >>"${INSTALL_LOG}" 2>&1 &
  local pid=$!
  if ! spin_while "${pid}" "Pulling images & starting stack"; then
    return 1
  fi
  return 0
}

start_stack_build() {
  if [[ "${SKIP_BUILD_GUEST}" != "true" ]] && [[ -x ./deploy/build-sandbox-guest.sh ]]; then
    if [[ "${VERBOSE}" == "1" || "${VERBOSE}" == "true" ]]; then
      step "Building sandbox guest image"
      CONTAINER_ENGINE="${ENGINE}" ./deploy/build-sandbox-guest.sh \
        || warn "guest image build failed — will use registry default if pullable"
    else
      (
        echo ""
        echo "===== $(date -Iseconds 2>/dev/null || date) :: guest image ====="
        CONTAINER_ENGINE="${ENGINE}" ./deploy/build-sandbox-guest.sh
      ) >>"${INSTALL_LOG}" 2>&1 &
      local guest_pid=$!
      if ! spin_while "${guest_pid}" "Building sandbox guest image"; then
        warn "guest image build failed — will use registry default if pullable"
      fi
    fi
  fi

  if [[ "${VERBOSE}" == "1" || "${VERBOSE}" == "true" ]]; then
    step "Building & starting stack (${COMPOSE_FILE})"
    compose -f "${COMPOSE_FILE}" up --build -d
    ok "stack started (built from source)"
    return 0
  fi
  (
    echo ""
    echo "===== $(date -Iseconds 2>/dev/null || date) :: compose up --build ====="
    compose -f "${COMPOSE_FILE}" up --build -d
  ) >>"${INSTALL_LOG}" 2>&1 &
  local stack_pid=$!
  if ! spin_while "${stack_pid}" "Building & starting containers"; then
    return 1
  fi
  return 0
}

if [[ "${INSTALL_MODE}" == "build" ]]; then
  if ! start_stack_build; then
    die "compose build/up failed"
  fi
else
  step "Using prebuilt GHCR images (set BUILD_FROM_SOURCE=1 to compile locally)"
  if ! start_stack_pull; then
    warn "Pull failed — falling back to local build (images may not be published yet)"
    if ! start_stack_build; then
      die "pull and local build both failed"
    fi
  fi
fi

step "Waiting for API health"
API_URL="${PUBLIC_API_URL:-http://localhost:8000}"
healthy=false
for i in $(seq 1 60); do
  if compose -f "${COMPOSE_FILE}" exec -T backend \
    python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/system/health')" \
    >/dev/null 2>&1 \
    || compose -f "${COMPOSE_FILE}" exec -T backend \
      python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health')" \
      >/dev/null 2>&1; then
    ok "API is ready"
    healthy=true
    break
  fi
  if [[ -t 1 ]] && [[ "${VERBOSE}" != "1" && "${VERBOSE}" != "true" ]]; then
    printf '\r    … health check %s/60' "${i}"
  fi
  if [[ "${i}" -eq 60 ]]; then
    printf '\r'
    die "API did not become healthy in time"
  fi
  sleep 2
done
printf '\r'

if [[ "${healthy}" != "true" ]]; then
  die "health wait failed"
fi

UI_URL="${FRONTEND_URL:-http://localhost:3000}"
echo ""
echo "  ────────────────────────────────────────"
echo "  Everflow is running"
echo "    UI     ${UI_URL}"
echo "    API    ${API_URL}/docs"
echo "    Ready  ${API_URL}/api/v1/ready"
echo "  ────────────────────────────────────────"
echo ""
echo "  Next: open the UI and complete first-run setup"
echo "        (platform admin + organization)."
echo ""
echo "  Tips:  BUILD_FROM_SOURCE=1  build images locally instead of GHCR"
echo "         VERBOSE=1            stream container logs"
echo "         log file: ${INSTALL_LOG}"
echo ""
