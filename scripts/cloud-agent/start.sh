#!/usr/bin/env bash
# Per-boot Cloud Agent start: dockerd + compose.dev stack.
# Must terminate after the stack is healthy.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT}"

if [[ -x "${ROOT}/scripts/cloud-agent/install.sh" ]]; then
  "${ROOT}/scripts/cloud-agent/install.sh"
fi

docker_ok() {
  docker info >/dev/null 2>&1 || sudo docker info >/dev/null 2>&1
}

if ! docker_ok; then
  if [[ ! -f /etc/docker/daemon.json ]]; then
    sudo mkdir -p /etc/docker
    sudo tee /etc/docker/daemon.json >/dev/null <<'JSON'
{
  "storage-driver": "fuse-overlayfs",
  "iptables": true,
  "live-restore": true,
  "log-driver": "json-file",
  "log-opts": { "max-size": "10m", "max-file": "3" }
}
JSON
  fi
  sudo mkdir -p /var/run/docker /var/lib/docker
  sudo dockerd --host=unix:///var/run/docker.sock >/tmp/dockerd.log 2>&1 &
  for _ in $(seq 1 40); do
    if docker_ok; then
      break
    fi
    sleep 1
  done
fi

if ! docker_ok; then
  echo "dockerd failed to start; see /tmp/dockerd.log" >&2
  exit 1
fi

# Let the Cloud Agent user talk to the socket without a new login.
if [[ -S /var/run/docker.sock ]]; then
  sudo chmod 666 /var/run/docker.sock || true
fi

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.dev.yml}"
if [[ ! -f "${COMPOSE_FILE}" ]]; then
  COMPOSE_FILE=docker-compose.yml
fi

# Prefer sudo docker so a fresh login shell without the docker group still works.
if docker info >/dev/null 2>&1 && [[ -w /var/run/docker.sock ]]; then
  DOCKER=(docker)
else
  DOCKER=(sudo docker)
fi

"${DOCKER[@]}" compose -f "${COMPOSE_FILE}" up -d --wait --wait-timeout 180

echo "Everflow UI  http://localhost:5173"
echo "Everflow API http://localhost:8000/docs"
echo "Health       http://localhost:8000/api/v1/health"
