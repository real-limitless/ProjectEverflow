#!/usr/bin/env bash
# Idempotent Cloud Agent bootstrap. Does not start servers.
# Safe to run repeatedly after checkout.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT}"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required (expected on the Cloud Agent snapshot)" >&2
  exit 1
fi

# Nested Cloud Agent VMs often need sudo until the login session picks up the docker group.
if ! docker info >/dev/null 2>&1; then
  if ! sudo docker info >/dev/null 2>&1; then
    echo "docker daemon is not reachable" >&2
    exit 1
  fi
fi

if [[ ! -f .env ]]; then
  if [[ ! -f .env.example ]]; then
    echo ".env.example missing" >&2
    exit 1
  fi
  cp .env.example .env
  SECRET="$(openssl rand -hex 32)"
  AGENT_TOKEN="$(openssl rand -hex 32)"
  CREDS_KEY="$(openssl rand -hex 32)"
  python3 - "${SECRET}" "${AGENT_TOKEN}" "${CREDS_KEY}" <<'PY'
import pathlib, re, sys
secret, agent, creds = sys.argv[1], sys.argv[2], sys.argv[3]
p = pathlib.Path(".env")
text = p.read_text()
repl = {
    "SECRET_KEY": secret,
    "SANDBOX_AGENT_TOKEN": agent,
    "CREDENTIALS_ENCRYPTION_KEY": creds,
    "ENVIRONMENT": "development",
    "SANDBOX_MOCK": "true",
    "FRONTEND_URL": "http://localhost:5173",
    "CORS_ORIGINS": "http://localhost:3000,http://localhost:5173",
    "VITE_API_URL": "http://localhost:8000",
    "PUBLIC_API_URL": "http://localhost:8000",
    "SEARXNG_IMAGE": "docker.io/searxng/searxng:latest",
    "EVERFLOW_REGISTRY_IMAGE": "docker.io/library/registry:2",
}
for k, v in repl.items():
    text, n = re.subn(rf"^{k}=.*$", f"{k}={v}", text, flags=re.M)
    if n == 0:
        text += f"\n{k}={v}\n"
p.write_text(text)
PY
  echo "created .env for Cloud Agent (SANDBOX_MOCK=true, compose.dev URLs)"
else
  echo "using existing .env"
fi

echo "cloud-agent install ok"
