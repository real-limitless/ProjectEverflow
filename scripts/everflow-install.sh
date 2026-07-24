#!/usr/bin/env bash
# Everflow control-plane installer (Docker Compose).
# Generates .env secrets, optionally builds the guest image, starts the stack.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
SKIP_BUILD_GUEST="${SKIP_BUILD_GUEST:-false}"
ENVIRONMENT="${ENVIRONMENT:-development}"

rand_hex() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 32
  else
    head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n'
  fi
}

echo "==> Everflow install (self-hosted)"
echo "    root: $ROOT"

if [[ ! -f .env ]]; then
  echo "==> Creating .env from .env.example"
  cp .env.example .env
  SECRET="$(rand_hex)"
  AGENT_TOKEN="$(rand_hex)"
  CREDS_KEY="$(rand_hex)"
  # Portable in-place edit
  if [[ "$(uname -s)" == "Darwin" ]]; then
    sed -i '' \
      -e "s|^SECRET_KEY=.*|SECRET_KEY=${SECRET}|" \
      -e "s|^SANDBOX_AGENT_TOKEN=.*|SANDBOX_AGENT_TOKEN=${AGENT_TOKEN}|" \
      .env
  else
    sed -i \
      -e "s|^SECRET_KEY=.*|SECRET_KEY=${SECRET}|" \
      -e "s|^SANDBOX_AGENT_TOKEN=.*|SANDBOX_AGENT_TOKEN=${AGENT_TOKEN}|" \
      .env
  fi
  if ! grep -q '^CREDENTIALS_ENCRYPTION_KEY=' .env; then
    echo "CREDENTIALS_ENCRYPTION_KEY=${CREDS_KEY}" >> .env
  else
    if [[ "$(uname -s)" == "Darwin" ]]; then
      sed -i '' -e "s|^CREDENTIALS_ENCRYPTION_KEY=.*|CREDENTIALS_ENCRYPTION_KEY=${CREDS_KEY}|" .env
    else
      sed -i -e "s|^CREDENTIALS_ENCRYPTION_KEY=.*|CREDENTIALS_ENCRYPTION_KEY=${CREDS_KEY}|" .env
    fi
  fi
  if ! grep -q '^ENVIRONMENT=' .env; then
    echo "ENVIRONMENT=${ENVIRONMENT}" >> .env
  fi
  echo "    Generated SECRET_KEY, SANDBOX_AGENT_TOKEN, CREDENTIALS_ENCRYPTION_KEY"
else
  echo "==> Using existing .env"
fi

if [[ ! -e /dev/kvm ]]; then
  echo "WARN: /dev/kvm not found — real microVMs will not work."
  echo "      Set SANDBOX_MOCK=true in .env for CI/dev only."
else
  echo "==> /dev/kvm present"
fi

if [[ "$SKIP_BUILD_GUEST" != "true" ]]; then
  if [[ -x ./deploy/build-sandbox-guest.sh ]]; then
    echo "==> Building sandbox guest image (skip with SKIP_BUILD_GUEST=true)"
    ./deploy/build-sandbox-guest.sh || echo "WARN: guest image build failed — continuing"
  fi
fi

echo "==> Starting stack ($COMPOSE_FILE)"
docker compose -f "$COMPOSE_FILE" up --build -d

echo "==> Waiting for API health…"
API_URL="${PUBLIC_API_URL:-http://localhost:8000}"
for i in $(seq 1 60); do
  if curl -fsS "${API_URL}/api/v1/system/health" >/dev/null 2>&1 \
    || curl -fsS "${API_URL}/api/v1/health" >/dev/null 2>&1; then
    echo "    API is up"
    break
  fi
  if [[ "$i" -eq 60 ]]; then
    echo "ERROR: API did not become healthy in time"
    docker compose -f "$COMPOSE_FILE" ps
    exit 1
  fi
  sleep 2
done

UI_URL="${FRONTEND_URL:-http://localhost:3000}"
echo ""
echo "Everflow is running."
echo "  UI:   ${UI_URL}"
echo "  API:  ${API_URL}/docs"
echo "  Ready:${API_URL}/api/v1/ready"
echo ""
echo "Open the UI to complete first-run setup (create platform admin + organization)."
echo "Production checklist: set ENVIRONMENT=production, use PostgreSQL, rotate secrets,"
echo "set CREDENTIALS_ENCRYPTION_KEY, and configure OAuth in .env if needed."
