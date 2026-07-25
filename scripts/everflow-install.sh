#!/usr/bin/env bash
# Compatibility wrapper — prefer: ./scripts/everflow install
# or interactive menu: ./scripts/everflow
#
# Default: start stack from embedded local OCI registry (seed first if empty).
# Seed:         ./deploy/local-registry.sh seed
# From source:  BUILD_FROM_SOURCE=1 ./scripts/everflow-install.sh
# From GHCR:    INSTALL_MODE=ghcr ./scripts/everflow-install.sh
# Verbose:      VERBOSE=1 ./scripts/everflow-install.sh
#
# Host prerequisites: docker or podman (+ compose plugin), Linux + /dev/kvm for
# real sandboxes. No host Python/Node required.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "${SCRIPT_DIR}/everflow" install --no-admin "$@"
