#!/bin/bash
# Build script for workspace container images
# Creates pre-configured development environments for AI-assisted code editing

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DATE=$(date +%Y%m%d)

echo "========================================="
echo "Building Workspace Container Images"
echo "========================================="
echo

# Build Fedora 43 workspace
echo "Building Fedora 43 workspace image..."
podman build \
  -f "${SCRIPT_DIR}/Containerfile.fedora" \
  -t localhost/fedora-devtools:43 \
  -t localhost/fedora-devtools:43-${BUILD_DATE} \
  -t localhost/fedora-devtools:latest \
  "${SCRIPT_DIR}"

echo "✓ Fedora 43 workspace built successfully"
echo "  - localhost/fedora-devtools:43"
echo "  - localhost/fedora-devtools:43-${BUILD_DATE}"
echo "  - localhost/fedora-devtools:latest"
echo

# Build UBI 9 workspace
echo "Building UBI 9 workspace image..."
podman build \
  -f "${SCRIPT_DIR}/Containerfile.ubi9" \
  -t localhost/ubi9-devtools:latest \
  -t localhost/ubi9-devtools:${BUILD_DATE} \
  "${SCRIPT_DIR}"

echo "✓ UBI 9 workspace built successfully"
echo "  - localhost/ubi9-devtools:latest"
echo "  - localhost/ubi9-devtools:${BUILD_DATE}"
echo

echo "========================================="
echo "Build Summary"
echo "========================================="
podman images | grep -E "fedora-devtools|ubi9-devtools"
echo

echo "========================================="
echo "All workspace images built successfully!"
echo "========================================="
echo
echo "To use these images, configure projects with:"
echo "  - Fedora 43: workspace_image='fedora:43'"
echo "  - UBI 9: workspace_image='registry.access.redhat.com/ubi9/ubi'"
echo
echo "The orchestrator will automatically use the pre-built images:"
echo "  - localhost/fedora-devtools:43"
echo "  - localhost/ubi9-devtools:latest"
