#!/usr/bin/env bash
# Build (and optionally push) the Everflow project sandbox guest image.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TAG="${SANDBOX_GUEST_IMAGE:-ghcr.io/limitless-rh/everflow-sandbox-guest:dev}"
DOCKERFILE="${ROOT}/deploy/sandbox-guest.Dockerfile"
PUSH="${PUSH:-false}"
ENGINE="${CONTAINER_ENGINE:-}"

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

echo "Building guest image: ${TAG}"
echo "  engine=${ENGINE}  dockerfile=${DOCKERFILE}"

"${ENGINE}" build \
  -f "${DOCKERFILE}" \
  -t "${TAG}" \
  "${ROOT}"

echo "Built ${TAG}"

if [[ "${PUSH}" == "true" || "${PUSH}" == "1" ]]; then
  echo "Pushing ${TAG} …"
  "${ENGINE}" push "${TAG}"
  echo "Pushed ${TAG}"
fi

cat <<EOF

Next:
  1. Ensure microsandbox can pull this image (local tag if msb shares the host store,
     otherwise push to a registry and use the full ref).
  2. Set in .env:
       SANDBOX_DEFAULT_IMAGE=${TAG}
  3. Recreate / re-provision projects so they boot from the new image.

Cold pull is once; later creates reuse the cached guest image (~seconds).
EOF
