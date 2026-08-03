#!/usr/bin/env bash
# =============================================================================
# Everflow remote bootstrap — single script for website / one-liner install
# =============================================================================
#
# Host this file at a stable URL, then users run:
#
#   curl -fsSL https://YOUR_DOMAIN/install | bash
#
# Or inspect first (recommended):
#
#   curl -fsSL https://YOUR_DOMAIN/install -o get-everflow.sh
#   less get-everflow.sh
#   bash get-everflow.sh
#
# Direct from GitHub (no custom website required).
# Product code lives on Development-Everflow (CORE is concept/docs only).
#
#   curl -fsSL https://raw.githubusercontent.com/real-limitless/ProjectEverflow/Development-Everflow/scripts/get-everflow.sh | bash
#
# What this script does:
#   1. Checks Docker or Podman + Compose
#   2. Downloads ProjectEverflow (git clone or GitHub archive)
#   3. Runs ./scripts/everflow install  (or interactive menu on TTY)
#
# Optional environment variables:
#   EVERFLOW_DIR          Install directory (default: $HOME/everflow)
#   EVERFLOW_REPO         Git remote (default: https://github.com/real-limitless/ProjectEverflow.git)
#   EVERFLOW_VERSION      Branch or tag (default: Development-Everflow)
#   EVERFLOW_REF          Alias for EVERFLOW_VERSION
#   EVERFLOW_ACTION       install | menu | setup-admin  (default: install on non-TTY, menu on TTY)
#   CONTAINER_ENGINE      docker | podman
#   BUILD_FROM_SOURCE=1   Build images instead of pull path
#   INSTALL_MODE=ghcr|pull|build   Passed through to everflow install
#   SKIP_CLONE=1          Reuse existing EVERFLOW_DIR without re-downloading
#   EVERFLOW_NONINTERACTIVE=1  Force non-interactive install (no menu)
#
# Host needs: bash, curl or wget, git (preferred) or tar+gzip, Docker or Podman.
# No host Python/Node required for the control plane.
# =============================================================================
set -euo pipefail

EVERFLOW_DIR="${EVERFLOW_DIR:-${HOME}/everflow}"
EVERFLOW_REPO="${EVERFLOW_REPO:-https://github.com/real-limitless/ProjectEverflow.git}"
EVERFLOW_VERSION="${EVERFLOW_REF:-${EVERFLOW_VERSION:-Development-Everflow}}"
EVERFLOW_ACTION="${EVERFLOW_ACTION:-}"
SKIP_CLONE="${SKIP_CLONE:-0}"
EVERFLOW_NONINTERACTIVE="${EVERFLOW_NONINTERACTIVE:-0}"

# Derive GitHub tarball URL from repo if using github.com
github_archive_url() {
  local repo="$1"
  local ref="$2"
  # https://github.com/org/repo.git → org/repo
  if [[ "${repo}" =~ github\.com[:/]([^/]+)/([^/.]+)(\.git)?$ ]]; then
    echo "https://github.com/${BASH_REMATCH[1]}/${BASH_REMATCH[2]}/archive/refs/heads/${ref}.tar.gz"
    return 0
  fi
  return 1
}

# Tag archive: try tags/ if heads fails — handled by caller
github_tag_archive_url() {
  local repo="$1"
  local ref="$2"
  if [[ "${repo}" =~ github\.com[:/]([^/]+)/([^/.]+)(\.git)?$ ]]; then
    echo "https://github.com/${BASH_REMATCH[1]}/${BASH_REMATCH[2]}/archive/refs/tags/${ref}.tar.gz"
    return 0
  fi
  return 1
}

log() { printf '  ▸ %s\n' "$*"; }
ok() { printf '    ✓ %s\n' "$*"; }
warn() { printf '    ! %s\n' "$*" >&2; }
die() { printf '\n  ✗ %s\n\n' "$*" >&2; exit 1; }

print_banner() {
  cat <<'EOF'

  Everflow — remote install
  Self-hosted AI app platform (Docker / Podman)

EOF
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "missing required command: $1"
}

download() {
  local url="$1"
  local dest="$2"
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL --retry 3 --retry-delay 2 -o "${dest}" "${url}"
  elif command -v wget >/dev/null 2>&1; then
    wget -q -O "${dest}" "${url}"
  else
    die "need curl or wget to download ${url}"
  fi
}

check_engine() {
  if [[ -n "${CONTAINER_ENGINE:-}" ]]; then
    need_cmd "${CONTAINER_ENGINE}"
    ok "using CONTAINER_ENGINE=${CONTAINER_ENGINE}"
    return
  fi
  if command -v docker >/dev/null 2>&1; then
    ok "docker found"
    return
  fi
  if command -v podman >/dev/null 2>&1; then
    ok "podman found"
    return
  fi
  die "need Docker or Podman on the host.

  Install Docker Engine: https://docs.docker.com/engine/install/
  or Podman:           https://podman.io/getting-started/installation
  then re-run this script."
}

check_compose() {
  local engine="${CONTAINER_ENGINE:-}"
  if [[ -z "${engine}" ]]; then
    if command -v docker >/dev/null 2>&1; then
      engine=docker
    else
      engine=podman
    fi
  fi
  if "${engine}" compose version >/dev/null 2>&1; then
    ok "${engine} compose available"
    return
  fi
  if [[ "${engine}" == "podman" ]] && command -v podman-compose >/dev/null 2>&1; then
    ok "podman-compose available"
    return
  fi
  if command -v docker-compose >/dev/null 2>&1; then
    ok "docker-compose available"
    return
  fi
  die "${engine} Compose plugin not found. Install Compose V2 (docker compose / podman compose)."
}

clone_or_update() {
  local dir="$1"
  local repo="$2"
  local ref="$3"

  if [[ -d "${dir}/.git" ]]; then
    log "Updating existing clone at ${dir}"
    git -C "${dir}" fetch --depth 1 origin "${ref}" 2>/dev/null \
      || git -C "${dir}" fetch origin "${ref}"
    git -C "${dir}" checkout "${ref}" 2>/dev/null \
      || git -C "${dir}" checkout -B "${ref}" "FETCH_HEAD"
    git -C "${dir}" pull --ff-only origin "${ref}" 2>/dev/null || true
    ok "repo updated (${ref})"
    return
  fi

  if [[ -d "${dir}" ]] && [[ -f "${dir}/scripts/everflow" ]]; then
    ok "existing install tree at ${dir} (no .git) — reusing"
    return
  fi

  if [[ -e "${dir}" ]] && [[ ! -d "${dir}/.git" ]]; then
    die "EVERFLOW_DIR exists but is not an Everflow checkout: ${dir}
  Set EVERFLOW_DIR to a new path, or remove it, then re-run."
  fi

  mkdir -p "$(dirname "${dir}")"

  if command -v git >/dev/null 2>&1; then
    log "Cloning ${repo} (${ref}) → ${dir}"
    if git clone --depth 1 --branch "${ref}" "${repo}" "${dir}" 2>/dev/null; then
      ok "cloned"
      return
    fi
    # branch might be a tag that needs full clone depth quirks
    if git clone --depth 1 "${repo}" "${dir}" 2>/dev/null; then
      git -C "${dir}" fetch --depth 1 origin "refs/tags/${ref}:refs/tags/${ref}" 2>/dev/null || true
      git -C "${dir}" checkout "${ref}" 2>/dev/null || die "could not checkout ${ref}"
      ok "cloned (tag/ref ${ref})"
      return
    fi
    warn "git clone failed — trying GitHub archive download"
    rm -rf "${dir}"
  else
    warn "git not found — downloading archive"
  fi

  download_archive "${dir}" "${repo}" "${ref}"
}

download_archive() {
  local dir="$1"
  local repo="$2"
  local ref="$3"
  local tmp archive url
  need_cmd tar
  tmp="$(mktemp -d)"
  archive="${tmp}/everflow.tgz"

  url="$(github_archive_url "${repo}" "${ref}" || true)"
  if [[ -z "${url}" ]]; then
    die "cannot build archive URL for ${repo} (need git, or a github.com repo)"
  fi

  log "Downloading ${url}"
  if ! download "${url}" "${archive}" 2>/dev/null; then
    url="$(github_tag_archive_url "${repo}" "${ref}" || true)"
    [[ -n "${url}" ]] || die "download failed for branch ${ref}"
    log "Retrying as tag: ${url}"
    download "${url}" "${archive}" || die "archive download failed"
  fi

  mkdir -p "${tmp}/extract"
  tar -xzf "${archive}" -C "${tmp}/extract"
  # GitHub archives unpack to repo-ref/
  local extracted
  extracted="$(find "${tmp}/extract" -mindepth 1 -maxdepth 1 -type d | head -n1)"
  [[ -n "${extracted}" ]] || die "empty archive"
  rm -rf "${dir}"
  mv "${extracted}" "${dir}"
  rm -rf "${tmp}"
  ok "extracted to ${dir}"
}

run_everflow() {
  local dir="$1"
  local action="$2"
  local ef="${dir}/scripts/everflow"

  [[ -x "${ef}" ]] || chmod +x "${ef}" 2>/dev/null || true
  [[ -f "${ef}" ]] || die "scripts/everflow missing in ${dir} — bad download?"

  # Ensure helper scripts are executable
  chmod +x "${dir}/scripts/everflow" "${dir}/scripts/everflow-install.sh" 2>/dev/null || true
  chmod +x "${dir}/deploy/"*.sh 2>/dev/null || true

  cd "${dir}"
  export EVERFLOW_ROOT="${dir}"

  case "${action}" in
    menu)
      log "Launching interactive control menu"
      exec bash "${ef}" menu
      ;;
    setup-admin)
      log "Running setup-admin"
      exec bash "${ef}" setup-admin
      ;;
    install | *)
      log "Running everflow install"
      # shellcheck disable=SC2086
      exec bash "${ef}" install ${EVERFLOW_INSTALL_ARGS:-}
      ;;
  esac
}

main() {
  print_banner

  log "Install directory: ${EVERFLOW_DIR}"
  log "Version / ref:     ${EVERFLOW_VERSION}"
  log "Repository:        ${EVERFLOW_REPO}"
  echo ""

  check_engine
  check_compose

  if [[ ! -e /dev/kvm ]]; then
    warn "/dev/kvm missing — real microVMs need KVM; install may use SANDBOX_MOCK=true for dev only"
  else
    ok "/dev/kvm present"
  fi
  echo ""

  if [[ "${SKIP_CLONE}" == "1" || "${SKIP_CLONE}" == "true" ]]; then
    [[ -f "${EVERFLOW_DIR}/scripts/everflow" ]] || die "SKIP_CLONE set but ${EVERFLOW_DIR} is not a valid Everflow tree"
    ok "skipping download (SKIP_CLONE=1)"
  else
    clone_or_update "${EVERFLOW_DIR}" "${EVERFLOW_REPO}" "${EVERFLOW_VERSION}"
  fi

  # Default action: menu on TTY, install otherwise
  local action="${EVERFLOW_ACTION}"
  if [[ -z "${action}" ]]; then
    if [[ "${EVERFLOW_NONINTERACTIVE}" == "1" || "${EVERFLOW_NONINTERACTIVE}" == "true" ]]; then
      action=install
    elif [[ -t 0 && -t 1 ]]; then
      action=menu
    else
      action=install
    fi
  fi

  echo ""
  ok "Everflow files ready at ${EVERFLOW_DIR}"
  echo "  Later:  cd ${EVERFLOW_DIR} && ./scripts/everflow"
  echo ""

  run_everflow "${EVERFLOW_DIR}" "${action}"
}

main "$@"
