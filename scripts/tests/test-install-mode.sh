#!/usr/bin/env bash
# Unit-style checks for INSTALL_MODE / secret / GHCR helpers (no Docker required).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=../lib/everflow-common.sh
source "${ROOT}/scripts/lib/everflow-common.sh"
# shellcheck source=../lib/everflow-env.sh
source "${ROOT}/scripts/lib/everflow-env.sh"

fail() { echo "FAIL: $*" >&2; exit 1; }
pass() { echo "  ok $*"; }

# ── INSTALL_MODE derivation ──────────────────────────────────────────
(
  unset INSTALL_MODE REGISTRY_SEED_MODE BUILD_FROM_SOURCE INSTALL_FROM_GHCR
  INSTALL_MODE=""
  BUILD_FROM_SOURCE=1
  REGISTRY_SEED_MODE=""
  sync_install_mode
  [[ "${INSTALL_MODE}" == "build" ]] || fail "BUILD_FROM_SOURCE should set INSTALL_MODE=build"
  [[ "${REGISTRY_SEED_MODE}" == "build" ]] || fail "BUILD_FROM_SOURCE should set REGISTRY_SEED_MODE=build"
  pass "BUILD_FROM_SOURCE=1 → build"
)

(
  unset INSTALL_MODE REGISTRY_SEED_MODE BUILD_FROM_SOURCE
  INSTALL_MODE=ghcr
  BUILD_FROM_SOURCE=0
  REGISTRY_SEED_MODE=""
  sync_install_mode
  [[ "${INSTALL_MODE}" == "ghcr" ]] || fail "INSTALL_MODE=ghcr should stick"
  [[ "${REGISTRY_SEED_MODE}" == "ghcr" ]] || fail "INSTALL_MODE=ghcr should set REGISTRY_SEED_MODE=ghcr"
  pass "INSTALL_MODE=ghcr → seed=ghcr"
)

(
  unset INSTALL_MODE REGISTRY_SEED_MODE BUILD_FROM_SOURCE
  INSTALL_MODE=ghcr
  BUILD_FROM_SOURCE=1
  REGISTRY_SEED_MODE=""
  sync_install_mode
  [[ "${INSTALL_MODE}" == "ghcr" ]] || fail "explicit INSTALL_MODE=ghcr must not be remapped by BUILD_FROM_SOURCE"
  pass "INSTALL_MODE=ghcr wins over BUILD_FROM_SOURCE"
)

# ── GHCR image list ──────────────────────────────────────────────────
list="$(print_required_ghcr_images)"
echo "${list}" | grep -q 'ghcr.io/real-limitless/everflow-frontend:latest' || fail "missing frontend image in catalog"
echo "${list}" | grep -q 'everflow-backend' || fail "missing backend"
echo "${list}" | grep -q 'everflow-sandbox-agent' || fail "missing agent"
echo "${list}" | grep -q 'everflow-sandbox-guest' || fail "missing guest"
pass "required GHCR image catalog"

# ── Secret helpers ───────────────────────────────────────────────────
_is_default_secret "change-me-in-production-use-a-long-random-string" || fail "default SECRET_KEY not detected"
_is_default_secret "" || fail "empty SECRET_KEY not detected"
_is_default_secret "unique-long-random-value" && fail "unique SECRET_KEY flagged as default"
_is_default_agent_token "dev-sandbox-token-change-me" || fail "default agent token not detected"
_is_default_agent_token "unique-agent-token" && fail "unique agent token flagged as default"
pass "secret default detectors"

# ── Operator secret gate (temp .env) ─────────────────────────────────
tmp="$(mktemp -d)"
trap 'rm -rf "${tmp}"' EXIT
ROOT="${tmp}"
export ROOT
cat >"${tmp}/.env" <<'EOF'
ENVIRONMENT=production
SECRET_KEY=change-me-in-production-use-a-long-random-string
SANDBOX_AGENT_TOKEN=dev-sandbox-token-change-me
CREDENTIALS_ENCRYPTION_KEY=
SANDBOX_MOCK=false
EOF
ENVIRONMENT=production
if assert_operator_secrets_or_die >/tmp/everflow-secret-test.out 2>&1; then
  fail "production defaults should have been refused"
else
  pass "production defaults refused"
fi

cat >"${tmp}/.env" <<'EOF'
ENVIRONMENT=production
SECRET_KEY=unique-production-secret-key-not-a-placeholder
SANDBOX_AGENT_TOKEN=unique-production-agent-token
CREDENTIALS_ENCRYPTION_KEY=unique-production-fernet-material
SANDBOX_MOCK=false
EOF
ENVIRONMENT=production
assert_operator_secrets_or_die
pass "production unique secrets accepted"

cat >"${tmp}/.env" <<'EOF'
ENVIRONMENT=production
SECRET_KEY=unique-production-secret-key-not-a-placeholder
SANDBOX_AGENT_TOKEN=unique-production-agent-token
CREDENTIALS_ENCRYPTION_KEY=unique-production-fernet-material
SANDBOX_MOCK=true
EOF
ENVIRONMENT=production
if assert_operator_secrets_or_die >/tmp/everflow-secret-test.out 2>&1; then
  fail "production + SANDBOX_MOCK should have been refused"
else
  pass "production mock refused"
fi

ENVIRONMENT=development
cat >"${tmp}/.env" <<'EOF'
ENVIRONMENT=development
SECRET_KEY=change-me-in-production-use-a-long-random-string
SANDBOX_AGENT_TOKEN=dev-sandbox-token-change-me
CREDENTIALS_ENCRYPTION_KEY=
SANDBOX_MOCK=true
EOF
assert_operator_secrets_or_die
pass "development defaults allowed"

echo ""
echo "All install-mode helper checks passed."
