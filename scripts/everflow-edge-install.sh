#!/usr/bin/env bash
# everflow-edge-install.sh — sketch installer for a deploy host.
#
# Installs Docker (if missing), copies Traefik compose + static config,
# prepares /etc/everflow/dynamic, starts Traefik + edge, and prints
# instructions for adding the Everflow deploy public key.
#
# Usage (as root or via sudo):
#   ./scripts/everflow-edge-install.sh
#   EVERFLOW_EDGE_SRC=/path/to/repo/everflow-edge ./scripts/everflow-edge-install.sh

set -euo pipefail

INSTALL_ROOT="${EVERFLOW_INSTALL_ROOT:-/opt/everflow-edge}"
DYNAMIC_DIR="${EVERFLOW_DYNAMIC_DIR:-/etc/everflow/dynamic}"
DEPLOY_USER="${EVERFLOW_DEPLOY_USER:-everflow}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
EDGE_SRC="${EVERFLOW_EDGE_SRC:-${REPO_ROOT}/everflow-edge}"

log() { printf '==> %s\n' "$*"; }
warn() { printf '!!  %s\n' "$*" >&2; }

require_root() {
  if [[ "${EUID}" -ne 0 ]]; then
    warn "Re-run as root (sudo $0)"
    exit 1
  fi
}

install_docker() {
  if command -v docker >/dev/null 2>&1; then
    log "Docker already installed: $(docker --version)"
    return
  fi
  log "Installing Docker Engine (get.docker.com)…"
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL https://get.docker.com | sh
  else
    warn "curl not found; install Docker manually then re-run."
    exit 1
  fi
  systemctl enable --now docker 2>/dev/null || true
}

ensure_compose() {
  if docker compose version >/dev/null 2>&1; then
    log "docker compose plugin OK"
    return
  fi
  warn "docker compose plugin missing — install docker-compose-plugin for your distro."
  exit 1
}

ensure_deploy_user() {
  if id -u "${DEPLOY_USER}" >/dev/null 2>&1; then
    log "Deploy user '${DEPLOY_USER}' exists"
  else
    log "Creating deploy user '${DEPLOY_USER}'"
    useradd --create-home --shell /bin/bash "${DEPLOY_USER}"
  fi
  # Docker group so compose works without root (best-effort)
  if getent group docker >/dev/null 2>&1; then
    usermod -aG docker "${DEPLOY_USER}" || true
  fi
  install -d -m 700 -o "${DEPLOY_USER}" -g "${DEPLOY_USER}" \
    "$(getent passwd "${DEPLOY_USER}" | cut -d: -f6)/.ssh"
}

copy_edge_files() {
  if [[ ! -d "${EDGE_SRC}/traefik" ]]; then
    warn "Edge source not found at ${EDGE_SRC}/traefik"
    warn "Set EVERFLOW_EDGE_SRC to the everflow-edge directory."
    exit 1
  fi
  log "Installing edge files → ${INSTALL_ROOT}"
  mkdir -p "${INSTALL_ROOT}"
  rsync -a --delete \
    --exclude '.venv' --exclude '__pycache__' --exclude '.git' \
    "${EDGE_SRC}/" "${INSTALL_ROOT}/"
  mkdir -p "${DYNAMIC_DIR}"
  if [[ ! -f "${DYNAMIC_DIR}/routes.yml" ]]; then
    cp "${INSTALL_ROOT}/traefik/dynamic/routes.yml.example" \
      "${DYNAMIC_DIR}/routes.yml"
    log "Seeded ${DYNAMIC_DIR}/routes.yml from example"
  fi
  chown -R "${DEPLOY_USER}:${DEPLOY_USER}" "${INSTALL_ROOT}" || true
}

start_traefik() {
  log "Starting Traefik + edge via docker compose"
  cd "${INSTALL_ROOT}/traefik"
  docker compose up -d
  log "Traefik dashboard (MVP): http://$(hostname -f 2>/dev/null || hostname):8080"
  log "Edge health:            http://$(hostname -f 2>/dev/null || hostname):9100/health"
}

print_pubkey_instructions() {
  cat <<EOF

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Add the Everflow deploy public key (required for remote deploy)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. In the Everflow platform UI → Deploy → host / keys
   (or your org's deploy key settings), copy the *public* key.

2. On this host, as ${DEPLOY_USER}:

     sudo -u ${DEPLOY_USER} mkdir -p ~/.ssh
     sudo -u ${DEPLOY_USER} chmod 700 ~/.ssh
     echo 'ssh-ed25519 AAAA... everflow-deploy' \\
       | sudo -u ${DEPLOY_USER} tee -a ~/.ssh/authorized_keys
     sudo -u ${DEPLOY_USER} chmod 600 ~/.ssh/authorized_keys

3. Ensure sshd allows pubkey auth for ${DEPLOY_USER}, and that
   ${DEPLOY_USER} can run:  docker compose  (docker group applied above;
   re-login may be required).

4. From the platform, create a deploy run targeting:

     host=$(hostname -f 2>/dev/null || hostname)
     user=${DEPLOY_USER}
     remote_dir=/opt/everflow/apps/<project>
     compose_path=docker-compose.yml

Dynamic Traefik routes live in:  ${DYNAMIC_DIR}/routes.yml
Compose stack lives in:          ${INSTALL_ROOT}/traefik

EOF
}

main() {
  require_root
  install_docker
  ensure_compose
  ensure_deploy_user
  copy_edge_files
  start_traefik
  print_pubkey_instructions
  log "Done."
}

main "$@"
