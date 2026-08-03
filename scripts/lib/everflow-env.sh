# shellcheck shell=bash
# .env helpers (requires everflow-common.sh).

rand_hex() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 32 2>/dev/null && return
  fi
  "${ENGINE}" run --rm --entrypoint /bin/sh docker.io/library/alpine:3.20 -c \
    'apk add --no-cache openssl >/dev/null 2>&1 && openssl rand -hex 32' 2>>"${INSTALL_LOG}"
}

# Set KEY=value in ROOT/.env (creates file line if missing).
# Prefer host sed when .env is writable to avoid engine dependency for simple updates.
env_set() {
  local key="$1"
  local value="$2"
  local env_file="${ROOT}/.env"

  if [[ -w "${env_file}" ]] || [[ ! -e "${env_file}" && -w "${ROOT}" ]]; then
    if [[ -f "${env_file}" ]] && grep -q "^${key}=" "${env_file}" 2>/dev/null; then
      # Escape sed replacement carefully: use | delimiter; escape \ & |
      local esc="${value//\\/\\\\}"
      esc="${esc//|/\\|}"
      esc="${esc//&/\\&}"
      sed -i "s|^${key}=.*|${key}=${esc}|" "${env_file}"
    else
      printf '%s=%s\n' "${key}" "${value}" >>"${env_file}"
    fi
    return 0
  fi

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

env_get() {
  local key="$1"
  local env_file="${ROOT}/.env"
  [[ -f "${env_file}" ]] || return 1
  # shellcheck disable=SC2002
  grep -E "^${key}=" "${env_file}" 2>/dev/null | head -n1 | cut -d= -f2- || true
}

ensure_env_file() {
  local force_env="${1:-}"
  cd "${ROOT}"

  if [[ ! -f .env ]]; then
    step "Creating .env and generating secrets"
    if [[ ! -f .env.example ]]; then
      die ".env.example missing in ${ROOT}"
    fi
    cp .env.example .env
    local secret agent_token creds_key
    secret="$(rand_hex)"
    agent_token="$(rand_hex)"
    creds_key="$(rand_hex)"
    env_set SECRET_KEY "${secret}"
    env_set SANDBOX_AGENT_TOKEN "${agent_token}"
    env_set CREDENTIALS_ENCRYPTION_KEY "${creds_key}"
    env_set ENVIRONMENT "${ENVIRONMENT}"
    ok "secrets written to .env"
  else
    ok "using existing .env"
    if [[ -n "${force_env}" ]]; then
      env_set ENVIRONMENT "${force_env}"
      ENVIRONMENT="${force_env}"
    fi
  fi

  # Refresh URL vars from .env when present
  local u a
  u="$(env_get FRONTEND_URL || true)"
  a="$(env_get PUBLIC_API_URL || true)"
  if [[ -n "${u}" ]]; then
    UI_URL="${u}"
    FRONTEND_URL="${u}"
  fi
  if [[ -n "${a}" ]]; then
    API_URL="${a}"
    PUBLIC_API_URL="${a}"
  fi
}

apply_install_toggles() {
  # Optional: SANDBOX_MOCK, ENVIRONMENT already may be set via env or wizard
  if [[ -n "${SANDBOX_MOCK:-}" ]]; then
    env_set SANDBOX_MOCK "${SANDBOX_MOCK}"
  fi
  if [[ -n "${ENVIRONMENT:-}" ]]; then
    env_set ENVIRONMENT "${ENVIRONMENT}"
  fi
}

# Point .env image refs at the embedded local registry when unset or still on legacy GHCR defaults.
apply_local_registry_env_defaults() {
  local port="${REGISTRY_HOST_PORT:-5000}"
  local host_reg="localhost:${port}/everflow"
  local int_reg="registry:${port}/everflow"
  local key cur

  _maybe_set_local_image() {
    key="$1"
    local host_val="$2"
    cur="$(env_get "${key}" || true)"
    # Empty, commented legacy, or old GHCR default → local registry
    if [[ -z "${cur}" ]] \
      || [[ "${cur}" == ghcr.io/real-limitless/* ]] \
      || [[ "${cur}" == ghcr.io/limitless-rh/* ]] \
      || [[ "${cur}" == docker.io/searxng/* ]]; then
      env_set "${key}" "${host_val}"
    fi
  }

  _maybe_set_local_image EVERFLOW_FRONTEND_IMAGE "${host_reg}/everflow-frontend:latest"
  _maybe_set_local_image EVERFLOW_BACKEND_IMAGE "${host_reg}/everflow-backend:latest"
  _maybe_set_local_image EVERFLOW_SANDBOX_AGENT_IMAGE "${host_reg}/everflow-sandbox-agent:latest"
  _maybe_set_local_image SEARXNG_IMAGE "${host_reg}/upstream-searxng:latest"

  # Guest must use compose DNS for msb (inside sandbox-agent)
  cur="$(env_get SANDBOX_DEFAULT_IMAGE || true)"
  if [[ -z "${cur}" ]] \
    || [[ "${cur}" == ghcr.io/real-limitless/* ]] \
    || [[ "${cur}" == ghcr.io/limitless-rh/* ]] \
    || [[ "${cur}" == localhost:*/everflow/* ]] \
    || [[ "${cur}" == everflow-sandbox-guest:* ]]; then
    env_set SANDBOX_DEFAULT_IMAGE "${int_reg}/everflow-sandbox-guest:latest"
  fi
}
