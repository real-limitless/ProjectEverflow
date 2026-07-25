#!/usr/bin/env bash
# Build (and optionally push) the Everflow project sandbox guest image.
# Thin wrapper around ./deploy/build-images.sh (ONLY=guest).
#
# Usage:
#   ./deploy/build-sandbox-guest.sh
#   SANDBOX_GUEST_IMAGE=localhost:5000/everflow/everflow-sandbox-guest:v1 PUSH=true ./deploy/build-sandbox-guest.sh
# Prefer: ONLY=guest ./deploy/local-registry.sh build-push
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Map legacy SANDBOX_GUEST_IMAGE → registry/tag when possible
if [[ -n "${SANDBOX_GUEST_IMAGE:-}" ]]; then
  export SANDBOX_GUEST_IMAGE
  # If user passed a full ref like registry/name:tag, also set TAG from it when
  # it matches our guest image name; otherwise build-images tags the override.
  if [[ "${SANDBOX_GUEST_IMAGE}" == *:* ]]; then
    export EVERFLOW_IMAGE_TAG="${EVERFLOW_IMAGE_TAG:-${SANDBOX_GUEST_IMAGE##*:}}"
  fi
fi

export ONLY=guest
exec "${ROOT}/deploy/build-images.sh"
