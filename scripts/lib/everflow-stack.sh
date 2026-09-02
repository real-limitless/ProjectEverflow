# shellcheck shell=bash
# Stack lifecycle: install, start, stop, upgrade, uninstall, logs, status.
#
# Install is always phased:
#   1) ask (TUI wizard or env)
#   2) install registry (up + seed)
#   3) full stack install

print_phase() {
  local n="$1"
  local title="$2"
  echo ""
  echo "  ════════════════════════════════════════"
  echo "  Phase ${n}: ${title}"
  echo "  ════════════════════════════════════════"
  echo ""
}

# Ensure embedded registry is up before pull/build (always-on service).
ensure_local_registry() {
  if [[ ! -x "${ROOT}/deploy/local-registry.sh" ]]; then
    warn "deploy/local-registry.sh missing — skipping registry bootstrap"
    return 0
  fi
  step "Starting embedded OCI registry"
  if [[ "${VERBOSE}" == "1" || "${VERBOSE}" == "true" ]]; then
    CONTAINER_ENGINE="${ENGINE}" COMPOSE_FILE="${COMPOSE_FILE}" \
      "${ROOT}/deploy/local-registry.sh" up || return 1
  else
    (
      echo ""
      echo "===== $(date -Iseconds 2>/dev/null || date) :: local-registry up ====="
      CONTAINER_ENGINE="${ENGINE}" COMPOSE_FILE="${COMPOSE_FILE}" \
        "${ROOT}/deploy/local-registry.sh" up
    ) >>"${INSTALL_LOG}" 2>&1 || return 1
    ok "registry up"
  fi
}

# True if local registry catalog already has core Everflow images.
local_registry_has_core_images() {
  local port="${REGISTRY_HOST_PORT:-5000}"
  local catalog=""
  if command -v curl >/dev/null 2>&1; then
    catalog="$(curl -sf "http://127.0.0.1:${port}/v2/_catalog" 2>/dev/null || true)"
  fi
  [[ -n "${catalog}" ]] || return 1
  # Need at least guest + one control-plane image (or searxng for minimal)
  echo "${catalog}" | grep -q 'everflow-sandbox-guest' || return 1
  echo "${catalog}" | grep -qE 'everflow-backend|everflow-sandbox-agent' || return 1
  return 0
}

# Online seed: mirror upstream + build/push Everflow images into local registry.
# mode: build | ghcr
seed_local_registry() {
  local mode="${1:-build}"
  ensure_local_registry || return 1
  step "Seeding local registry (${mode})"
  if [[ "${mode}" == "ghcr" ]]; then
    if [[ "${VERBOSE}" == "1" || "${VERBOSE}" == "true" ]]; then
      CONTAINER_ENGINE="${ENGINE}" COMPOSE_FILE="${COMPOSE_FILE}" \
        SEED_FROM_GHCR=1 "${ROOT}/deploy/local-registry.sh" seed || return 1
    else
      (
        echo ""
        echo "===== $(date -Iseconds 2>/dev/null || date) :: local-registry seed (ghcr) ====="
        CONTAINER_ENGINE="${ENGINE}" COMPOSE_FILE="${COMPOSE_FILE}" \
          SEED_FROM_GHCR=1 "${ROOT}/deploy/local-registry.sh" seed
      ) >>"${INSTALL_LOG}" 2>&1 &
      local pid=$!
      if ! spin_while "${pid}" "Seeding local registry from GHCR" 1800; then
        return 1
      fi
    fi
  else
    if [[ "${VERBOSE}" == "1" || "${VERBOSE}" == "true" ]]; then
      CONTAINER_ENGINE="${ENGINE}" COMPOSE_FILE="${COMPOSE_FILE}" \
        "${ROOT}/deploy/local-registry.sh" seed || return 1
    else
      (
        echo ""
        echo "===== $(date -Iseconds 2>/dev/null || date) :: local-registry seed ====="
        CONTAINER_ENGINE="${ENGINE}" COMPOSE_FILE="${COMPOSE_FILE}" \
          "${ROOT}/deploy/local-registry.sh" seed
      ) >>"${INSTALL_LOG}" 2>&1 &
      local pid=$!
      if ! spin_while "${pid}" "Seeding local registry (build + mirror)" 3600; then
        return 1
      fi
    fi
  fi
  apply_local_registry_env_defaults
  return 0
}

# Phase 2 of install: start registry + seed images.
# REGISTRY_SEED_MODE: build | ghcr | skip | auto (default auto)
install_phase_registry() {
  print_phase "1/2" "Install local image registry"
  echo "  The stack uses an embedded OCI registry so microVMs and services"
  echo "  pull images locally (no GHCR required after seed)."
  echo ""

  ensure_local_registry || return 1

  local seed_mode="${REGISTRY_SEED_MODE:-}"
  if [[ -z "${seed_mode}" || "${seed_mode}" == "auto" ]]; then
    seed_mode=auto
    case "${INSTALL_MODE}" in
      build) seed_mode=build ;;
      ghcr) seed_mode=ghcr ;;
      *)
        if [[ "${SKIP_REGISTRY_SEED:-0}" == "1" || "${SKIP_REGISTRY_SEED:-}" == "true" ]]; then
          seed_mode=skip
        elif local_registry_has_core_images; then
          seed_mode=skip
        elif [[ "${INSTALL_FROM_GHCR:-0}" == "1" || "${INSTALL_FROM_GHCR:-}" == "true" ]]; then
          seed_mode=ghcr
        else
          # Empty registry, non-interactive: seed from source (airgap-ready)
          seed_mode=build
        fi
        ;;
    esac
  fi

  case "${seed_mode}" in
    skip)
      if local_registry_has_core_images; then
        ok "registry already has core images — skipping seed"
      else
        warn "registry catalog looks empty (SKIP seed). Stack start may fail."
        warn "Re-run with BUILD_FROM_SOURCE=1 or INSTALL_MODE=ghcr to seed."
      fi
      ;;
    ghcr)
      step "Seeding registry from GHCR (mirror)"
      if ! seed_local_registry ghcr; then
        die_ghcr_missing "registry seed from ${EVERFLOW_PUBLIC_REGISTRY} failed"
      fi
      ok "registry seeded from GHCR"
      ;;
    build | *)
      step "Seeding registry from source (build + push + upstream mirror)"
      seed_local_registry build || return 1
      ok "registry seeded from source"
      ;;
  esac

  # Avoid double-seed in start_stack_build
  SKIP_REGISTRY_SEED=1
  export SKIP_REGISTRY_SEED

  if [[ -x "${ROOT}/deploy/local-registry.sh" ]]; then
    step "Registry status"
    CONTAINER_ENGINE="${ENGINE}" COMPOSE_FILE="${COMPOSE_FILE}" \
      "${ROOT}/deploy/local-registry.sh" status 2>&1 || true
  fi
  return 0
}

# Phase 3 of install: start control plane from registry (or build compose services).
install_phase_stack() {
  print_phase "2/2" "Full stack install"
  echo "  Starting frontend, backend, sandbox-agent, searxng from the local registry."
  echo ""

  # Prefer pull from local registry. INSTALL_MODE=ghcr never falls back to a
  # source compile (that would look like a successful GHCR install).
  if [[ "${INSTALL_MODE}" == "build" ]]; then
    SKIP_REGISTRY_SEED=1
    if ! start_stack_pull; then
      warn "pull after seed failed — compose up --build"
      start_stack_build || return 1
    fi
  elif [[ "${INSTALL_MODE}" == "ghcr" ]]; then
    start_stack_pull || return 1
  else
    start_stack_pull || return 1
  fi
  return 0
}

# CLI / menu: registry-only operations.
cmd_registry() {
  local sub="${1:-status}"
  shift || true
  cd "${ROOT}"
  case "${sub}" in
    up | start)
      ensure_local_registry
      ;;
    seed)
      local mode="${1:-build}"
      seed_local_registry "${mode}"
      ;;
    status)
      ensure_local_registry || true
      CONTAINER_ENGINE="${ENGINE}" COMPOSE_FILE="${COMPOSE_FILE}" \
        "${ROOT}/deploy/local-registry.sh" status
      ;;
    export | import)
      CONTAINER_ENGINE="${ENGINE}" COMPOSE_FILE="${COMPOSE_FILE}" \
        "${ROOT}/deploy/local-registry.sh" "${sub}" "$@"
      ;;
    *)
      echo "  usage: everflow registry {up|seed|status|export|import}" >&2
      echo "    seed [build|ghcr]   populate local registry" >&2
      return 1
      ;;
  esac
}

start_stack_pull() {
  # Prefer images already in the embedded registry; pull only what compose needs.
  ensure_local_registry || return 1
  if [[ "${VERBOSE}" == "1" || "${VERBOSE}" == "true" ]]; then
    step "Pulling images (local registry / overrides)"
    if ! compose -f "${COMPOSE_FILE}" pull; then
      if [[ "${INSTALL_MODE}" == "ghcr" ]]; then
        die_ghcr_missing "compose pull failed after GHCR seed"
      fi
      warn "compose pull had errors — continuing"
    fi
    step "Starting stack"
    if ! compose -f "${COMPOSE_FILE}" up -d --no-build; then
      diagnose_stack_failure "compose up -d --no-build failed"
      return 1
    fi
    if ! assert_stack_started; then
      return 1
    fi
    ok "stack started (registry images)"
    return 0
  fi
  (
    echo ""
    echo "===== $(date -Iseconds 2>/dev/null || date) :: compose pull ====="
    if ! compose -f "${COMPOSE_FILE}" pull; then
      if [[ "${INSTALL_MODE}" == "ghcr" ]]; then
        echo "compose pull failed (INSTALL_MODE=ghcr — not ignoring)" >&2
        exit 1
      fi
    fi
    echo "===== compose up -d --no-build ====="
    compose -f "${COMPOSE_FILE}" up -d --no-build
  ) >>"${INSTALL_LOG}" 2>&1 &
  local pid=$!
  if ! spin_while "${pid}" "Pulling images & starting stack" "${COMPOSE_UP_TIMEOUT_SEC}"; then
    local rc=$?
    diagnose_stack_failure "compose pull/up failed or timed out (rc=${rc})"
    return 1
  fi
  if ! assert_stack_started; then
    return 1
  fi
  return 0
}

start_stack_build() {
  ensure_local_registry || return 1

  # Seed Everflow + upstream into local registry so msb can pull guest without GHCR.
  if [[ "${SKIP_REGISTRY_SEED:-0}" != "1" && "${SKIP_REGISTRY_SEED:-}" != "true" ]]; then
    if [[ "${VERBOSE}" == "1" || "${VERBOSE}" == "true" ]]; then
      step "Mirroring upstream + building images into local registry"
      CONTAINER_ENGINE="${ENGINE}" COMPOSE_FILE="${COMPOSE_FILE}" \
        "${ROOT}/deploy/local-registry.sh" mirror-upstream \
        || warn "upstream mirror failed — agent build may need network"
      if [[ "${SKIP_BUILD_GUEST}" != "true" ]]; then
        ONLY="${ONLY:-}" CONTAINER_ENGINE="${ENGINE}" COMPOSE_FILE="${COMPOSE_FILE}" \
          "${ROOT}/deploy/local-registry.sh" build-push \
          || warn "local-registry build-push failed — compose --build may still work for control plane"
      fi
    else
      (
        echo ""
        echo "===== $(date -Iseconds 2>/dev/null || date) :: mirror-upstream ====="
        CONTAINER_ENGINE="${ENGINE}" COMPOSE_FILE="${COMPOSE_FILE}" \
          "${ROOT}/deploy/local-registry.sh" mirror-upstream || true
        echo "===== build-push ====="
        if [[ "${SKIP_BUILD_GUEST}" != "true" ]]; then
          CONTAINER_ENGINE="${ENGINE}" COMPOSE_FILE="${COMPOSE_FILE}" \
            "${ROOT}/deploy/local-registry.sh" build-push || true
        fi
      ) >>"${INSTALL_LOG}" 2>&1 &
      local seed_pid=$!
      if ! spin_while "${seed_pid}" "Building & pushing images to local registry" 3600; then
        warn "registry seed had errors — continuing with compose --build"
      fi
    fi
  elif [[ "${SKIP_BUILD_GUEST}" != "true" ]] && [[ -x "${ROOT}/deploy/build-sandbox-guest.sh" ]]; then
    if [[ "${VERBOSE}" == "1" || "${VERBOSE}" == "true" ]]; then
      step "Building sandbox guest image"
      CONTAINER_ENGINE="${ENGINE}" "${ROOT}/deploy/build-sandbox-guest.sh" \
        || warn "guest image build failed — will use registry default if pullable"
    else
      (
        echo ""
        echo "===== $(date -Iseconds 2>/dev/null || date) :: guest image ====="
        CONTAINER_ENGINE="${ENGINE}" "${ROOT}/deploy/build-sandbox-guest.sh"
      ) >>"${INSTALL_LOG}" 2>&1 &
      local guest_pid=$!
      if ! spin_while "${guest_pid}" "Building sandbox guest image" 1800; then
        warn "guest image build failed — will use registry default if pullable"
      fi
    fi
  fi

  if [[ "${VERBOSE}" == "1" || "${VERBOSE}" == "true" ]]; then
    step "Building & starting stack (${COMPOSE_FILE})"
    if ! compose -f "${COMPOSE_FILE}" up --build -d; then
      diagnose_stack_failure "compose up --build -d failed"
      return 1
    fi
    if ! assert_stack_started; then
      return 1
    fi
    ok "stack started (built from source)"
    return 0
  fi
  (
    echo ""
    echo "===== $(date -Iseconds 2>/dev/null || date) :: compose up --build ====="
    compose -f "${COMPOSE_FILE}" up --build -d
  ) >>"${INSTALL_LOG}" 2>&1 &
  local stack_pid=$!
  if ! spin_while "${stack_pid}" "Building & starting containers" "${COMPOSE_UP_TIMEOUT_SEC}"; then
    local rc=$?
    diagnose_stack_failure "compose up --build failed or timed out (rc=${rc})"
    return 1
  fi
  if ! assert_stack_started; then
    return 1
  fi
  return 0
}

print_running_banner() {
  echo ""
  echo "  ────────────────────────────────────────"
  echo "  Everflow is running"
  echo "    UI     ${UI_URL}"
  echo "    API    ${API_URL}/docs"
  echo "    Ready  ${API_URL}/api/v1/ready"
  echo "  ────────────────────────────────────────"
  echo ""
}

cmd_install() {
  local offer_admin="${1:-auto}" # auto | yes | no
  cd "${ROOT}"
  : >"${INSTALL_LOG}"
  log_append "install begin mode=${INSTALL_MODE} registry_seed=${REGISTRY_SEED_MODE:-auto}"

  print_banner
  echo "  Install plan"
  echo "  ────────────────────────────────────────"
  echo "  engine     ${ENGINE}"
  echo "  root       ${ROOT}"
  echo "  mode       ${INSTALL_MODE}"
  echo "  registry   seed=${REGISTRY_SEED_MODE:-auto}  (build | ghcr | skip | auto)"
  echo "  log        ${INSTALL_LOG}"
  echo ""
  echo "  Steps:  ask (done) → install registry → full stack"
  [[ "${VERBOSE}" == "1" || "${VERBOSE}" == "true" ]] && echo "  verbose on"
  echo ""

  ensure_env_file
  apply_install_toggles
  apply_local_registry_env_defaults
  assert_operator_secrets_or_die || die "insecure production/staging secrets (see above)"

  if ! warn_kvm_status; then
    local env_val mock_val
    env_val="${ENVIRONMENT:-$(env_get ENVIRONMENT || true)}"
    env_val="${env_val:-development}"
    mock_val="${SANDBOX_MOCK:-$(env_get SANDBOX_MOCK || true)}"
    mock_val="$(printf '%s' "${mock_val}" | tr '[:upper:]' '[:lower:]')"
    case "${env_val}" in
      production | staging)
        die "ENVIRONMENT=${env_val} requires /dev/kvm. SANDBOX_MOCK=true is dev/CI only."
        ;;
    esac
    if [[ "${mock_val}" == "true" || "${mock_val}" == "1" ]]; then
      warn "Continuing with SANDBOX_MOCK=true (development/CI only)."
    else
      warn "Without /dev/kvm the sandbox-agent will refuse to start unless SANDBOX_MOCK=true."
      warn "Set SANDBOX_MOCK=true only for development or CI, then re-run install."
    fi
  fi

  # ── Phase 1/2: registry ──────────────────────────────────────────────────
  if ! install_phase_registry; then
    if [[ "${INSTALL_MODE}" == "ghcr" ]]; then
      die_ghcr_missing "registry install/seed failed"
    fi
    die "registry install/seed failed (see ${INSTALL_LOG}). Re-run with VERBOSE=1."
  fi

  # ── Phase 2/2: full stack ────────────────────────────────────────────────
  if ! install_phase_stack; then
    if [[ "${INSTALL_MODE}" == "ghcr" ]]; then
      die_ghcr_missing "stack start failed after GHCR seed (not falling back to a local compile)"
    fi
    # Last resort for pull/build: full compose build if pull failed after seed
    warn "stack start failed — retrying with compose --build"
    SKIP_REGISTRY_SEED=1
    if ! start_stack_build; then
      die "full stack install failed (see ${INSTALL_LOG}). Re-run with VERBOSE=1."
    fi
  fi

  if ! wait_for_api_health 60; then
    die "API did not become healthy in time"
  fi

  print_running_banner

  local setup_needed="unknown"
  if setup_needs_bootstrap; then
    setup_needed="yes"
  else
    if [[ "${SETUP_STATUS_OK:-0}" == "1" ]]; then
      setup_needed="no"
    fi
  fi

  if [[ "${setup_needed}" == "no" ]]; then
    echo "  Setup already completed — open the UI and sign in."
    echo ""
  elif [[ "${SKIP_BOOTSTRAP}" == "1" || "${SKIP_BOOTSTRAP}" == "true" || "${offer_admin}" == "no" ]]; then
    echo "  Next: create the platform admin"
    echo "        ./scripts/everflow setup-admin"
    echo "        or open the UI wizard at ${UI_URL}"
    echo ""
  elif [[ -n "${EVERFLOW_ADMIN_EMAIL:-}" && -n "${EVERFLOW_ADMIN_PASSWORD:-}" ]]; then
    step "Bootstrapping first admin from environment"
    if cmd_setup_admin_noninteractive; then
      ok "admin created"
    else
      warn "bootstrap failed — complete setup in the UI or re-run: everflow setup-admin"
    fi
    echo ""
  elif [[ "${offer_admin}" == "yes" ]] || { [[ "${offer_admin}" == "auto" ]] && is_tty; }; then
    if confirm_yes "Create platform admin now?" "y"; then
      cmd_setup_admin_interactive || warn "bootstrap skipped/failed — use UI or: everflow setup-admin"
    else
      echo "  Next: open the UI and complete first-run setup"
      echo "        (platform admin + organization), or run:"
      echo "        ./scripts/everflow setup-admin"
      echo ""
    fi
  else
    echo "  Next: open the UI and complete first-run setup"
    echo "        (platform admin + organization), or run:"
    echo "        ./scripts/everflow setup-admin"
    echo ""
  fi

  echo "  Tips:  ./scripts/everflow registry status"
  echo "         ./scripts/everflow registry seed build|ghcr"
  echo "         VERBOSE=1 ./scripts/everflow install"
  echo "         log file: ${INSTALL_LOG}"
  echo ""
}

cmd_start() {
  cd "${ROOT}"
  step "Starting stack"
  if [[ "${INSTALL_MODE}" == "build" ]]; then
    compose -f "${COMPOSE_FILE}" up -d --build || compose -f "${COMPOSE_FILE}" up -d
  else
    compose -f "${COMPOSE_FILE}" up -d --no-build 2>/dev/null \
      || compose -f "${COMPOSE_FILE}" up -d
  fi
  wait_for_api_health 45 || warn "stack started but API not healthy yet"
  print_running_banner
}

cmd_stop() {
  cd "${ROOT}"
  step "Stopping stack"
  compose -f "${COMPOSE_FILE}" stop
  ok "stack stopped"
}

cmd_restart() {
  cd "${ROOT}"
  step "Restarting stack"
  compose -f "${COMPOSE_FILE}" restart || {
    compose -f "${COMPOSE_FILE}" stop || true
    cmd_start
    return
  }
  wait_for_api_health 45 || warn "restarted but API not healthy yet"
  ok "stack restarted"
  print_running_banner
}

# Recreate Compose services from current image refs (no registry reseed).
# mode: pull | build | auto
#   pull  — compose pull + up -d --no-build (use after registry reseed)
#   build — compose up --build -d
#   auto  — build if INSTALL_MODE/BUILD_FROM_SOURCE say so, else pull
upgrade_recreate_stack() {
  local mode="${1:-auto}"
  if [[ "${mode}" == "auto" ]]; then
    if [[ "${INSTALL_MODE}" == "build" || "${BUILD_FROM_SOURCE}" == "1" || "${BUILD_FROM_SOURCE}" == "true" ]]; then
      mode="build"
    else
      mode="pull"
    fi
  fi
  ensure_local_registry || true
  # Always force-recreate: podman/docker compose often keep old containers when the
  # image *tag* is unchanged (e.g. :latest) even after registry reseed rewrote the digest.
  # Without --force-recreate, upgrades can report success while serving stale UI/API.
  if [[ "${mode}" == "build" ]]; then
    step "Rebuilding & recreating stack"
    compose -f "${COMPOSE_FILE}" up --build -d --force-recreate || return 1
  else
    step "Pulling images & recreating stack"
    compose -f "${COMPOSE_FILE}" pull || warn "pull had errors; continuing with local images"
    compose -f "${COMPOSE_FILE}" up -d --no-build --force-recreate 2>/dev/null \
      || compose -f "${COMPOSE_FILE}" up -d --force-recreate || return 1
  fi
  return 0
}

# Pick registry seed strategy for full upgrade (never skip — refresh is the point).
# Priority: explicit arg → REGISTRY_SEED_MODE → INSTALL_MODE / BUILD_FROM_SOURCE → ghcr.
resolve_upgrade_seed_mode() {
  local explicit="${1:-}"
  case "${explicit}" in
    build | ghcr) echo "${explicit}"; return 0 ;;
  esac
  case "${REGISTRY_SEED_MODE:-}" in
    build | ghcr) echo "${REGISTRY_SEED_MODE}"; return 0 ;;
  esac
  if [[ "${BUILD_FROM_SOURCE}" == "1" || "${BUILD_FROM_SOURCE}" == "true" || "${INSTALL_MODE}" == "build" ]]; then
    echo "build"
    return 0
  fi
  if [[ "${INSTALL_MODE}" == "ghcr" ]]; then
    echo "ghcr"
    return 0
  fi
  # Default for pull/unknown installs: re-mirror from GHCR (fast when published).
  echo "ghcr"
}

# Upgrade control plane.
#   full  (default) — reseed local registry, then pull + recreate stack
#   stack           — recreate stack only (keep current registry images)
#
# Optional seed mode for full: build | ghcr
# CLI examples:
#   everflow upgrade
#   everflow upgrade full build
#   everflow upgrade --stack-only
#   everflow upgrade --seed=ghcr
cmd_upgrade() {
  cd "${ROOT}"
  local scope="full"
  local seed_arg=""

  while [[ $# -gt 0 ]]; do
    case "$1" in
      full) scope="full" ;;
      stack | stack-only | --stack-only) scope="stack" ;;
      build | ghcr) seed_arg="$1" ;;
      --seed)
        seed_arg="${2:-}"
        if [[ -z "${seed_arg}" ]]; then
          echo "  error: --seed requires build|ghcr" >&2
          return 1
        fi
        shift
        ;;
      --seed=*)
        seed_arg="${1#--seed=}"
        ;;
      -h | --help)
        cat <<'EOF'
  everflow upgrade [full|stack] [build|ghcr]
  everflow upgrade --stack-only
  everflow upgrade --seed=build|ghcr

  full   (default)  Reseed local registry, then pull & recreate stack
  stack             Recreate stack from current registry images only

  Seed mode (full only): build | ghcr
  Defaults from REGISTRY_SEED_MODE / INSTALL_MODE / BUILD_FROM_SOURCE, else ghcr.
EOF
        return 0
        ;;
      *)
        echo "  unknown upgrade option: $1" >&2
        echo "  usage: everflow upgrade [full|stack] [build|ghcr] | --stack-only | --seed=…" >&2
        return 1
        ;;
    esac
    shift
  done

  case "${seed_arg}" in
    "" | build | ghcr) ;;
    *)
      echo "  error: seed mode must be build|ghcr (got: ${seed_arg})" >&2
      return 1
      ;;
  esac

  log_append "upgrade scope=${scope} seed=${seed_arg:-auto}"

  if [[ "${scope}" == "stack" ]]; then
    step "Upgrading stack only (no registry reseed)"
    if ! upgrade_recreate_stack auto; then
      warn "stack recreate failed"
      return 1
    fi
  else
    local seed_mode
    seed_mode="$(resolve_upgrade_seed_mode "${seed_arg}")"
    print_phase "1/2" "Refresh local registry (${seed_mode})"
    echo "  Pushing newer control-plane / guest images into the embedded registry."
    echo "  (Stack-only upgrades skip this — use: everflow upgrade --stack-only)"
    echo ""
    if ! seed_local_registry "${seed_mode}"; then
      warn "registry reseed failed — aborting upgrade (stack unchanged)"
      return 1
    fi
    apply_local_registry_env_defaults
    ok "registry refreshed (${seed_mode})"

    print_phase "2/2" "Recreate stack from registry"
    # Images just seeded — pull from registry; do not compose --build again.
    if ! upgrade_recreate_stack pull; then
      warn "stack recreate failed after registry reseed"
      return 1
    fi
  fi

  if ! wait_for_api_health 60; then
    warn "upgrade finished but API not healthy — check: everflow logs backend"
    return 1
  fi
  print_running_banner
  ok "upgrade complete"
}

cmd_logs() {
  local service="${1:-}"
  local follow="${2:-1}"
  cd "${ROOT}"
  if [[ "${follow}" == "1" ]]; then
    if [[ -n "${service}" && "${service}" != "all" ]]; then
      compose -f "${COMPOSE_FILE}" logs --tail=100 -f "${service}"
    else
      compose -f "${COMPOSE_FILE}" logs --tail=100 -f
    fi
  else
    if [[ -n "${service}" && "${service}" != "all" ]]; then
      compose -f "${COMPOSE_FILE}" logs --tail=100 "${service}"
    else
      compose -f "${COMPOSE_FILE}" logs --tail=100
    fi
  fi
}

cmd_status() {
  cd "${ROOT}"
  echo ""
  echo "  Everflow status"
  echo "  ────────────────────────────────────────"
  echo "  root     ${ROOT}"
  echo "  engine   ${ENGINE}"
  echo "  compose  ${COMPOSE_FILE}"
  echo "  UI       ${UI_URL}"
  echo "  API      ${API_URL}"
  echo ""

  if [[ -f "${ROOT}/.env" ]]; then
    ok ".env present"
  else
    warn ".env missing — run: everflow install"
  fi

  warn_kvm_status || true

  echo ""
  step "Containers"
  compose -f "${COMPOSE_FILE}" ps 2>&1 || warn "compose ps failed (stack may not be installed)"

  echo ""
  step "Local registry"
  if [[ -x "${ROOT}/deploy/local-registry.sh" ]]; then
    CONTAINER_ENGINE="${ENGINE}" COMPOSE_FILE="${COMPOSE_FILE}" \
      "${ROOT}/deploy/local-registry.sh" status 2>&1 || warn "registry status failed"
  else
    warn "deploy/local-registry.sh missing"
  fi

  echo ""
  step "API health"
  if api_health_ok; then
    ok "API healthy"
  else
    warn "API not reachable (is the stack running?)"
  fi

  step "First-run setup"
  local body
  if body="$(api_http GET /api/v1/setup/status 2>/dev/null)"; then
    SETUP_STATUS_OK=1
    if echo "${body}" | grep -q '"needs_setup"[[:space:]]*:[[:space:]]*true'; then
      warn "setup needed — run: everflow setup-admin  (or open UI wizard)"
    else
      ok "setup completed (platform admin exists)"
    fi
    if echo "${body}" | grep -q '"mock"[[:space:]]*:[[:space:]]*true'; then
      warn "sandbox is in mock mode"
    fi
  else
    warn "could not read setup status (HTTP ${API_HTTP_CODE:-?})"
  fi
  echo ""
}

# Uninstall levels:
#   containers — compose down
#   volumes    — compose down -v
#   env        — also remove .env (combine with either)
cmd_uninstall() {
  local remove_volumes="${1:-0}"
  local remove_env="${2:-0}"
  local assume_yes="${3:-0}"

  cd "${ROOT}"
  echo ""
  echo "  Uninstall Everflow"
  echo "  ────────────────────────────────────────"
  echo "  This will stop and remove Compose services for this project."
  if [[ "${remove_volumes}" == "1" ]]; then
    echo "  + DATA VOLUMES will be deleted (database, sandboxes, workspaces)."
  else
    echo "  Volumes are kept (database & workspace data preserved)."
  fi
  if [[ "${remove_env}" == "1" ]]; then
    echo "  + .env will be deleted (secrets lost)."
  fi
  echo ""

  if [[ "${assume_yes}" != "1" ]]; then
    if [[ "${remove_volumes}" == "1" || "${remove_env}" == "1" ]]; then
      local phrase
      read -r -p "  Type 'everflow' to confirm: " phrase || true
      if [[ "${phrase}" != "everflow" ]]; then
        warn "aborted"
        return 1
      fi
    else
      confirm_yes "Remove containers?" "n" || {
        warn "aborted"
        return 1
      }
    fi
  fi

  step "Removing stack"
  if [[ "${remove_volumes}" == "1" ]]; then
    compose -f "${COMPOSE_FILE}" down -v --remove-orphans || true
  else
    compose -f "${COMPOSE_FILE}" down --remove-orphans || true
  fi
  ok "containers removed"

  if [[ "${remove_env}" == "1" ]]; then
    if [[ -f "${ROOT}/.env" ]]; then
      rm -f "${ROOT}/.env"
      ok "removed .env"
    fi
  fi

  echo ""
  echo "  Uninstall complete."
  if [[ "${remove_volumes}" != "1" ]]; then
    echo "  Data volumes still exist; reinstall will reuse them."
    echo "  For a clean slate: everflow uninstall --volumes"
  fi
  echo ""
}

cmd_reinstall() {
  local remove_volumes="${1:-0}"
  local remove_env="${2:-0}"
  local assume_yes="${3:-0}"

  echo ""
  echo "  Reinstall will uninstall then install again."
  if [[ "${remove_volumes}" != "1" ]]; then
    warn "Without --volumes, the existing database (and admin) is kept."
  fi
  echo ""

  cmd_uninstall "${remove_volumes}" "${remove_env}" "${assume_yes}" || return 1
  cmd_install auto
}
