#!/usr/bin/env bash
# Build (and optionally push) all Everflow OCI images for GHCR / local install.
#
# Images:
#   everflow-frontend
#   everflow-backend
#   everflow-sandbox-agent
#   everflow-sandbox-guest
#
# Usage (from repo root):
#   ./deploy/build-images.sh
#   PUSH=true ./deploy/build-images.sh
#   EVERFLOW_IMAGE_TAG=v0.1.0 PUSH=true ./deploy/build-images.sh
#   ONLY=backend,frontend ./deploy/build-images.sh
#   CONTAINER_ENGINE=podman ./deploy/build-images.sh
#
# Defaults match docker-compose.yml pull tags:
#   ghcr.io/limitless-rh/everflow-*:latest
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

REGISTRY="${EVERFLOW_REGISTRY:-ghcr.io/limitless-rh}"
TAG="${EVERFLOW_IMAGE_TAG:-latest}"
# Also tag guest as :dev for older docs / local defaults (set EXTRA_GUEST_TAG= to disable)
EXTRA_GUEST_TAG="${EXTRA_GUEST_TAG:-dev}"
PUSH="${PUSH:-false}"
ONLY="${ONLY:-}"
ENGINE="${CONTAINER_ENGINE:-}"

# Frontend: empty VITE_API_URL → same-origin /api (nginx proxy) for portable prebuilt images
VITE_API_URL="${VITE_API_URL:-}"

if [[ -z "${ENGINE}" ]]; then
  if command -v docker >/dev/null 2>&1; then
    ENGINE=docker
  elif command -v podman >/dev/null 2>&1; then
    ENGINE=podman
  else
    echo "error: need docker or podman" >&2
    exit 1
  fi
fi

want() {
  local name="$1"
  if [[ -z "${ONLY}" ]]; then
    return 0
  fi
  [[ ",${ONLY}," == *",${name},"* ]]
}

build_one() {
  local name="$1"
  local dockerfile="$2"
  shift 2
  local image="${REGISTRY}/${name}:${TAG}"
  local -a extra_tags=()
  local -a build_args=()

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --tag)
        extra_tags+=("$2")
        shift 2
        ;;
      --build-arg)
        build_args+=(--build-arg "$2")
        shift 2
        ;;
      *)
        echo "error: unknown arg to build_one: $1" >&2
        exit 1
        ;;
    esac
  done

  echo ""
  echo "==> Building ${image}"
  echo "    dockerfile=${dockerfile}  engine=${ENGINE}"

  local -a cmd=(
    "${ENGINE}" build
    -f "${dockerfile}"
    -t "${image}"
  )
  local t
  for t in "${extra_tags[@]+"${extra_tags[@]}"}"; do
    cmd+=(-t "${t}")
  done
  cmd+=("${build_args[@]+"${build_args[@]}"}")
  cmd+=("${ROOT}")

  "${cmd[@]}"
  echo "    Built ${image}"
  for t in "${extra_tags[@]+"${extra_tags[@]}"}"; do
    echo "    Tagged ${t}"
  done

  if [[ "${PUSH}" == "true" || "${PUSH}" == "1" ]]; then
    echo "    Pushing ${image} …"
    "${ENGINE}" push "${image}"
    for t in "${extra_tags[@]+"${extra_tags[@]}"}"; do
      echo "    Pushing ${t} …"
      "${ENGINE}" push "${t}"
    done
    echo "    Pushed"
  fi
}

echo "Everflow image build"
echo "  registry=${REGISTRY}"
echo "  tag=${TAG}"
echo "  engine=${ENGINE}"
echo "  push=${PUSH}"
[[ -n "${ONLY}" ]] && echo "  only=${ONLY}"

BUILT=()

if want frontend; then
  build_one everflow-frontend "${ROOT}/deploy/frontend.Dockerfile" \
    --build-arg "VITE_API_URL=${VITE_API_URL}"
  BUILT+=("${REGISTRY}/everflow-frontend:${TAG}")
fi

if want backend; then
  build_one everflow-backend "${ROOT}/deploy/backend.Dockerfile"
  BUILT+=("${REGISTRY}/everflow-backend:${TAG}")
fi

if want sandbox-agent; then
  build_one everflow-sandbox-agent "${ROOT}/deploy/sandbox-agent.Dockerfile"
  BUILT+=("${REGISTRY}/everflow-sandbox-agent:${TAG}")
fi

if want guest || want sandbox-guest; then
  guest_extras=()
  if [[ -n "${EXTRA_GUEST_TAG}" && "${EXTRA_GUEST_TAG}" != "${TAG}" ]]; then
    guest_extras+=(--tag "${REGISTRY}/everflow-sandbox-guest:${EXTRA_GUEST_TAG}")
  fi
  # Honor SANDBOX_GUEST_IMAGE override for primary tag (legacy)
  if [[ -n "${SANDBOX_GUEST_IMAGE:-}" ]]; then
    # Build with default name:tag then also tag the override
    build_one everflow-sandbox-guest "${ROOT}/deploy/sandbox-guest.Dockerfile" \
      --tag "${SANDBOX_GUEST_IMAGE}" \
      "${guest_extras[@]+"${guest_extras[@]}"}"
    BUILT+=("${REGISTRY}/everflow-sandbox-guest:${TAG}" "${SANDBOX_GUEST_IMAGE}")
  else
    build_one everflow-sandbox-guest "${ROOT}/deploy/sandbox-guest.Dockerfile" \
      "${guest_extras[@]+"${guest_extras[@]}"}"
    BUILT+=("${REGISTRY}/everflow-sandbox-guest:${TAG}")
  fi
fi

if [[ ${#BUILT[@]} -eq 0 ]]; then
  echo "error: nothing to build (ONLY=${ONLY})" >&2
  exit 1
fi

echo ""
echo "Done. Images:"
for img in "${BUILT[@]}"; do
  echo "  ${img}"
done

cat <<EOF

Install with prebuilt images:
  ./scripts/everflow-install.sh

Or point compose at a custom registry/tag:
  EVERFLOW_BACKEND_IMAGE=${REGISTRY}/everflow-backend:${TAG}
  EVERFLOW_FRONTEND_IMAGE=${REGISTRY}/everflow-frontend:${TAG}
  EVERFLOW_SANDBOX_AGENT_IMAGE=${REGISTRY}/everflow-sandbox-agent:${TAG}
  SANDBOX_DEFAULT_IMAGE=${REGISTRY}/everflow-sandbox-guest:${TAG}

Push to GHCR (requires registry login):
  ${ENGINE} login ghcr.io
  PUSH=true ./deploy/build-images.sh
EOF
