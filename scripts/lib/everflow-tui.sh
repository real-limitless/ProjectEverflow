# shellcheck shell=bash
# Interactive menu / install wizard.
#
# Install wizard always follows:
#   ask → install registry (up + seed) → full stack install

tui_has_whiptail() {
  command -v whiptail >/dev/null 2>&1
}

tui_press_enter() {
  if is_tty; then
    read -r -p "  Press Enter to continue… " _ || true
  fi
}

tui_status_line() {
  local stack="unknown" setup="?" health="?" reg="?"
  if compose -f "${COMPOSE_FILE}" ps 2>/dev/null | grep -qiE 'running|Up'; then
    stack="running"
  else
    stack="stopped"
  fi
  if api_health_ok 2>/dev/null; then
    health="healthy"
  else
    health="down"
  fi
  if setup_needs_bootstrap 2>/dev/null; then
    setup="needed"
  elif [[ "${SETUP_STATUS_OK:-0}" == "1" ]]; then
    setup="done"
  else
    setup="?"
  fi
  local port="${REGISTRY_HOST_PORT:-5000}"
  if command -v curl >/dev/null 2>&1 && curl -sf "http://127.0.0.1:${port}/v2/" >/dev/null 2>&1; then
    reg="up"
  else
    reg="down"
  fi
  echo "  Stack: ${stack} · API ${health} · registry ${reg} · setup ${setup}"
}

tui_install_wizard() {
  echo ""
  echo "  Install wizard"
  echo "  ────────────────────────────────────────"
  echo "  Supported runtime: Docker Compose or Podman Compose only."
  echo "  All services start together (frontend, backend, sandbox-agent,"
  echo "  registry, searxng). Host process installs are not supported."
  echo ""
  echo "  Flow: ask → install local registry → full Compose stack"
  echo ""

  # ── Ask: how to populate the local registry ─────────────────────────────
  local mode_choice
  echo "  How should images get into the local registry?"
  echo "    1) Build from source (recommended — works offline after seed)"
  echo "    2) Mirror from GHCR (fast if images are published)"
  echo "    3) Skip seed (registry already populated / import done)"
  read -r -p "  Choice [1]: " mode_choice
  mode_choice="${mode_choice:-1}"
  case "${mode_choice}" in
    2)
      INSTALL_MODE=ghcr
      BUILD_FROM_SOURCE=0
      REGISTRY_SEED_MODE=ghcr
      COMPOSE_UP_TIMEOUT_SEC="${COMPOSE_UP_TIMEOUT_SEC:-1800}"
      ;;
    3)
      INSTALL_MODE=pull
      BUILD_FROM_SOURCE=0
      REGISTRY_SEED_MODE=skip
      COMPOSE_UP_TIMEOUT_SEC="${COMPOSE_UP_TIMEOUT_SEC:-600}"
      ;;
    *)
      INSTALL_MODE=build
      BUILD_FROM_SOURCE=1
      REGISTRY_SEED_MODE=build
      COMPOSE_UP_TIMEOUT_SEC="${COMPOSE_UP_TIMEOUT_SEC:-3600}"
      ;;
  esac
  export INSTALL_MODE BUILD_FROM_SOURCE REGISTRY_SEED_MODE COMPOSE_UP_TIMEOUT_SEC

  echo ""
  echo "  Plan:"
  echo "    Phase 1 — start registry + seed (${REGISTRY_SEED_MODE})"
  echo "    Phase 2 — start full Everflow stack (all services via Compose)"
  echo ""

  # ── Ask: sandbox / environment ──────────────────────────────────────────
  if [[ ! -e /dev/kvm ]]; then
    warn "/dev/kvm is missing — real sandboxes need KVM"
    warn "SANDBOX_MOCK=true is for development and CI only — not production."
    if confirm_yes "Enable SANDBOX_MOCK=true (dev/CI only)?" "y"; then
      SANDBOX_MOCK=true
    else
      SANDBOX_MOCK=false
    fi
  else
    if confirm_yes "Use real microVMs (SANDBOX_MOCK=false)?" "y"; then
      SANDBOX_MOCK=false
    else
      SANDBOX_MOCK=true
      warn "mock mode is not for product use"
    fi
  fi
  export SANDBOX_MOCK

  local env_choice
  echo "  Environment:"
  echo "    1) development"
  echo "    2) production"
  read -r -p "  Choice [1]: " env_choice
  env_choice="${env_choice:-1}"
  if [[ "${env_choice}" == "2" ]]; then
    ENVIRONMENT=production
    warn "production refuses default secrets, missing CREDENTIALS_ENCRYPTION_KEY, and SANDBOX_MOCK"
    if [[ ! -e /dev/kvm ]]; then
      die "production requires /dev/kvm. SANDBOX_MOCK=true is not allowed."
    fi
    if [[ "${SANDBOX_MOCK}" == "true" ]]; then
      die "SANDBOX_MOCK=true cannot be used with ENVIRONMENT=production"
    fi
  else
    ENVIRONMENT=development
  fi
  export ENVIRONMENT

  if ! confirm_yes "Proceed with install?" "y"; then
    warn "install cancelled"
    return 0
  fi

  cmd_install auto
}

tui_registry_menu() {
  echo ""
  echo "  Local image registry"
  echo "  ────────────────────────────────────────"
  echo "  1) Status"
  echo "  2) Start registry only"
  echo "  3) Seed from source (build + push)"
  echo "  4) Seed from GHCR (mirror)"
  echo "  0) Back"
  local c
  read -r -p "  Choice [1]: " c
  c="${c:-1}"
  case "${c}" in
    1) cmd_registry status ;;
    2) cmd_registry up ;;
    3) cmd_registry seed build ;;
    4) cmd_registry seed ghcr ;;
    *) return 0 ;;
  esac
}

tui_uninstall_menu() {
  echo ""
  echo "  Uninstall"
  echo "  ────────────────────────────────────────"
  echo "  1) Remove containers only (keep data volumes + .env)"
  echo "  2) Remove containers + data volumes (wipes DB & sandboxes + registry data)"
  echo "  3) Full wipe (volumes + .env)"
  echo "  0) Cancel"
  local c
  read -r -p "  Choice [0]: " c
  c="${c:-0}"
  case "${c}" in
    1) cmd_uninstall 0 0 0 ;;
    2) cmd_uninstall 1 0 0 ;;
    3) cmd_uninstall 1 1 0 ;;
    *) warn "cancelled" ;;
  esac
}

tui_reinstall_menu() {
  echo ""
  echo "  Reinstall"
  echo "  ────────────────────────────────────────"
  echo "  1) Recreate containers (keep data — admin account kept)"
  echo "  2) Clean reinstall (delete volumes — new first admin)"
  echo "  3) Clean + delete .env (full reset)"
  echo "  0) Cancel"
  local c
  read -r -p "  Choice [0]: " c
  c="${c:-0}"
  case "${c}" in
    1) cmd_reinstall 0 0 0 ;;
    2) cmd_reinstall 1 0 0 ;;
    3) cmd_reinstall 1 1 0 ;;
    *) warn "cancelled" ;;
  esac
}

tui_logs_menu() {
  echo ""
  echo "  Logs (Ctrl-C to stop following)"
  echo "  ────────────────────────────────────────"
  echo "  1) all"
  echo "  2) backend"
  echo "  3) frontend"
  echo "  4) sandbox-agent"
  echo "  5) searxng"
  echo "  6) registry"
  local c
  read -r -p "  Choice [1]: " c
  c="${c:-1}"
  case "${c}" in
    1) cmd_logs all ;;
    2) cmd_logs backend ;;
    3) cmd_logs frontend ;;
    4) cmd_logs sandbox-agent ;;
    5) cmd_logs searxng ;;
    6) cmd_logs registry ;;
    *) cmd_logs all ;;
  esac
}

tui_upgrade_menu() {
  echo ""
  echo "  Upgrade"
  echo "  ────────────────────────────────────────"
  echo "  1) Full upgrade (refresh registry seed + recreate stack)  [recommended]"
  echo "  2) Stack only (recreate from current registry images — fast)"
  echo "  0) Cancel"
  local c
  read -r -p "  Choice [1]: " c
  c="${c:-1}"
  case "${c}" in
    1)
      local default_seed seed_choice seed_mode
      default_seed="$(resolve_upgrade_seed_mode)"
      echo ""
      echo "  How should the local registry be refreshed?"
      if [[ "${default_seed}" == "build" ]]; then
        echo "    1) Build from source (recommended — works offline after seed)"
        echo "    2) Mirror from GHCR (fast if images are published)"
        read -r -p "  Choice [1]: " seed_choice
        seed_choice="${seed_choice:-1}"
        case "${seed_choice}" in
          2) seed_mode=ghcr ;;
          *) seed_mode=build ;;
        esac
      else
        echo "    1) Mirror from GHCR (recommended — fast if images are published)"
        echo "    2) Build from source (works offline after seed)"
        read -r -p "  Choice [1]: " seed_choice
        seed_choice="${seed_choice:-1}"
        case "${seed_choice}" in
          2) seed_mode=build ;;
          *) seed_mode=ghcr ;;
        esac
      fi
      echo ""
      echo "  Plan:"
      echo "    Phase 1 — reseed local registry (${seed_mode})"
      echo "    Phase 2 — pull images & recreate stack"
      echo "  Data volumes and admin accounts are kept."
      echo ""
      if ! confirm_yes "Proceed with full upgrade?" "y"; then
        warn "upgrade cancelled"
        return 0
      fi
      cmd_upgrade full "${seed_mode}"
      ;;
    2)
      echo ""
      echo "  Plan: recreate Compose services from images already in the registry."
      echo "  Does not refresh guest / control-plane images in the registry."
      echo ""
      if ! confirm_yes "Proceed with stack-only upgrade?" "y"; then
        warn "upgrade cancelled"
        return 0
      fi
      cmd_upgrade stack
      ;;
    *)
      warn "cancelled"
      ;;
  esac
}

tui_main_menu() {
  while true; do
    clear 2>/dev/null || true
    print_banner
    tui_status_line 2>/dev/null || echo "  Stack: (status unavailable)"
    if [[ -n "${ENGINE:-}" ]]; then
      echo "  Engine: ${ENGINE} compose  ·  multi-service stack (Compose only)"
    else
      echo "  Runtime: Docker Compose or Podman Compose only"
    fi
    echo ""
    echo "  1) Install / start stack   (ask → registry → full Compose install)"
    echo "  2) Status & health"
    echo "  3) Local registry…         (up / seed / status)"
    echo "  4) Create first admin (email + password + org)"
    echo "  5) Reset user password"
    echo "  6) View logs"
    echo "  7) Stop stack"
    echo "  8) Restart stack"
    echo "  9) Upgrade…                (registry seed + recreate, or stack only)"
    echo "  u) Uninstall…"
    echo "  r) Reinstall…"
    echo "  0) Quit"
    echo ""
    local choice
    read -r -p "  Select: " choice || choice=0
    echo ""
    case "${choice}" in
      1) tui_install_wizard; tui_press_enter ;;
      2) cmd_status; tui_press_enter ;;
      3) tui_registry_menu; tui_press_enter ;;
      4) cmd_setup_admin; tui_press_enter ;;
      5) cmd_reset_password; tui_press_enter ;;
      6) tui_logs_menu ;;
      7) cmd_stop; tui_press_enter ;;
      8) cmd_restart; tui_press_enter ;;
      9) tui_upgrade_menu; tui_press_enter ;;
      u|U|10) tui_uninstall_menu; tui_press_enter ;;
      r|R) tui_reinstall_menu; tui_press_enter ;;
      0|q|Q) echo "  Bye."; return 0 ;;
      *) warn "unknown choice"; sleep 1 ;;
    esac
  done
}
