# shellcheck shell=bash
# First-run admin bootstrap via platform API.

SETUP_STATUS_OK=0

# Returns 0 if needs_setup is true.
setup_needs_bootstrap() {
  SETUP_STATUS_OK=0
  local body
  if ! body="$(api_http GET /api/v1/setup/status 2>/dev/null)"; then
    return 1
  fi
  SETUP_STATUS_OK=1
  echo "${body}" | grep -q '"needs_setup"[[:space:]]*:[[:space:]]*true'
}

# JSON-escape a string for embedding in a JSON value.
json_escape() {
  local s="$1"
  s="${s//\\/\\\\}"
  s="${s//\"/\\\"}"
  s="${s//$'\n'/\\n}"
  s="${s//$'\r'/\\r}"
  s="${s//$'\t'/\\t}"
  printf '%s' "${s}"
}

slugify() {
  local s
  s="$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/-/g; s/^-+//; s/-+$//; s/-+/-/g')"
  if [[ -z "${s}" ]]; then
    s="my-organization"
  fi
  printf '%s' "${s}"
}

# Bootstrap using variables (does not log password).
# Required: BOOTSTRAP_EMAIL BOOTSTRAP_PASSWORD
# Optional: BOOTSTRAP_ORG_NAME BOOTSTRAP_ORG_SLUG
do_bootstrap() {
  local email="${BOOTSTRAP_EMAIL:-}"
  local password="${BOOTSTRAP_PASSWORD:-}"
  local org_name="${BOOTSTRAP_ORG_NAME:-My Organization}"
  local org_slug="${BOOTSTRAP_ORG_SLUG:-}"

  if [[ -z "${email}" || -z "${password}" ]]; then
    warn "email and password are required"
    return 1
  fi
  if [[ "${#password}" -lt 8 ]]; then
    warn "password must be at least 8 characters"
    return 1
  fi
  if [[ -z "${org_slug}" ]]; then
    org_slug="$(slugify "${org_name}")"
  fi

  if ! setup_needs_bootstrap; then
    if [[ "${SETUP_STATUS_OK}" == "1" ]]; then
      ok "setup already completed — nothing to do"
      return 0
    fi
    warn "cannot reach setup API (is the stack running? try: everflow status)"
    return 1
  fi

  local payload
  payload="$(printf '{"email":"%s","password":"%s","org_name":"%s","org_slug":"%s"}' \
    "$(json_escape "${email}")" \
    "$(json_escape "${password}")" \
    "$(json_escape "${org_name}")" \
    "$(json_escape "${org_slug}")")"

  step "Creating platform admin"
  local body
  # Do not append payload to INSTALL_LOG (contains password).
  if body="$(api_http POST /api/v1/setup/bootstrap "${payload}" 2>/dev/null)"; then
    ok "admin created: ${email}"
    ok "organization: ${org_name} (${org_slug})"
    echo ""
    echo "  Sign in at ${UI_URL}"
    echo "  Email: ${email}"
    echo ""
    return 0
  fi

  warn "bootstrap failed (HTTP ${API_HTTP_CODE:-?})"
  if [[ -n "${body}" ]]; then
    # Body may contain error detail only — safe-ish to show
    echo "    ${body}" | head -c 400 >&2
    echo "" >&2
  fi
  if [[ "${API_HTTP_CODE}" == "410" ]]; then
    warn "setup was already completed"
  fi
  return 1
}

cmd_setup_admin_noninteractive() {
  BOOTSTRAP_EMAIL="${EVERFLOW_ADMIN_EMAIL:-${BOOTSTRAP_EMAIL:-}}"
  BOOTSTRAP_PASSWORD="${EVERFLOW_ADMIN_PASSWORD:-${BOOTSTRAP_PASSWORD:-}}"
  BOOTSTRAP_ORG_NAME="${EVERFLOW_ORG_NAME:-${BOOTSTRAP_ORG_NAME:-My Organization}}"
  BOOTSTRAP_ORG_SLUG="${EVERFLOW_ORG_SLUG:-${BOOTSTRAP_ORG_SLUG:-}}"

  if [[ -n "${EVERFLOW_ADMIN_PASSWORD_ENV:-}" ]]; then
    local env_name="${EVERFLOW_ADMIN_PASSWORD_ENV}"
    BOOTSTRAP_PASSWORD="${!env_name:-}"
  fi

  if [[ -z "${BOOTSTRAP_EMAIL}" || -z "${BOOTSTRAP_PASSWORD}" ]]; then
    cat >&2 <<'EOF'
  setup-admin (non-interactive) requires:
    EVERFLOW_ADMIN_EMAIL
    EVERFLOW_ADMIN_PASSWORD   (or --password-env NAME)
  optional:
    EVERFLOW_ORG_NAME  EVERFLOW_ORG_SLUG
EOF
    return 1
  fi
  do_bootstrap
}

cmd_setup_admin_interactive() {
  if ! setup_needs_bootstrap; then
    if [[ "${SETUP_STATUS_OK}" == "1" ]]; then
      ok "setup already completed — open ${UI_URL} and sign in"
      return 0
    fi
    warn "API not ready — start the stack first: everflow install"
    return 1
  fi

  echo ""
  echo "  Create platform admin (first-run setup)"
  echo "  ────────────────────────────────────────"
  echo "  This creates the superuser and first organization."
  echo "  Login uses email + password (not a separate username)."
  echo ""

  local email password password2 org_name org_slug
  read -r -p "  Admin email: " email
  email="$(printf '%s' "${email}" | tr '[:upper:]' '[:lower:]')"
  email="${email#"${email%%[![:space:]]*}"}"
  email="${email%"${email##*[![:space:]]}"}"

  if [[ -z "${email}" || "${email}" != *@* ]]; then
    warn "valid email required"
    return 1
  fi

  if confirm_yes "Generate a strong password?" "n"; then
    if command -v openssl >/dev/null 2>&1; then
      password="$(openssl rand -base64 18 | tr -d '/+=' | head -c 20)"
    else
      password="$(rand_hex | head -c 20)"
    fi
    echo ""
    echo "  Generated password (copy now — will not be shown again):"
    echo "    ${password}"
    echo ""
  else
    password="$(read_secret "Password (min 8 chars)")"
    password2="$(read_secret "Confirm password")"
    if [[ "${password}" != "${password2}" ]]; then
      warn "passwords do not match"
      return 1
    fi
  fi

  read -r -p "  Organization name [My Organization]: " org_name
  org_name="${org_name:-My Organization}"
  local default_slug
  default_slug="$(slugify "${org_name}")"
  read -r -p "  Organization slug [${default_slug}]: " org_slug
  org_slug="${org_slug:-${default_slug}}"
  org_slug="$(slugify "${org_slug}")"

  BOOTSTRAP_EMAIL="${email}"
  BOOTSTRAP_PASSWORD="${password}"
  BOOTSTRAP_ORG_NAME="${org_name}"
  BOOTSTRAP_ORG_SLUG="${org_slug}"
  do_bootstrap
}

cmd_setup_admin() {
  # If env credentials present, non-interactive; else interactive when TTY
  if [[ -n "${EVERFLOW_ADMIN_EMAIL:-}" && ( -n "${EVERFLOW_ADMIN_PASSWORD:-}" || -n "${EVERFLOW_ADMIN_PASSWORD_ENV:-}" ) ]]; then
    cmd_setup_admin_noninteractive
    return
  fi
  if is_tty; then
    cmd_setup_admin_interactive
    return
  fi
  echo "  Non-interactive setup-admin requires EVERFLOW_ADMIN_EMAIL and EVERFLOW_ADMIN_PASSWORD." >&2
  return 1
}

# ── Password reset (host operator recovery; no email flow yet) ───────────────

# List users from the backend DB (email, superuser flag). Prints clean lines to stdout.
list_platform_users() {
  # SQLAlchemy engine logs go to stderr; keep stdout clean for parsing.
  compose -f "${COMPOSE_FILE}" exec -T backend python -c '
import asyncio
import logging
import sys
logging.disable(logging.CRITICAL)
from sqlalchemy import select
from app.db.session import get_session_factory
from app.models.user import User

async def main():
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            select(User.email, User.is_superuser, User.is_active).order_by(User.email)
        )
        rows = result.all()
        if not rows:
            print("(no users)")
            return
        for email, su, active in rows:
            flags = []
            if su:
                flags.append("superuser")
            if not active:
                flags.append("inactive")
            tag = (" (" + ", ".join(flags) + ")") if flags else ""
            print(str(email) + tag)

asyncio.run(main())
' 2>/dev/null
}

# Reset password for RESET_EMAIL / RESET_PASSWORD (not written to install log).
do_reset_password() {
  local email="${RESET_EMAIL:-}"
  local password="${RESET_PASSWORD:-}"

  if [[ -z "${email}" || -z "${password}" ]]; then
    warn "email and password are required"
    return 1
  fi
  if [[ "${#password}" -lt 8 ]]; then
    warn "password must be at least 8 characters"
    return 1
  fi

  if ! api_health_ok 2>/dev/null; then
    warn "API not healthy — is the stack running? try: everflow start"
    return 1
  fi

  step "Resetting password for ${email}"
  # Feed email + password on stdin (avoids compose exec -e quirks with podman-compose).
  # Format: line1=email, line2=password (password may contain anything except we use a length prefix for safety).
  local out rc
  set +e
  out="$(
    {
      # length-prefixed to allow any password characters
      printf '%s\n' "${email}"
      printf '%s\n' "${#password}"
      printf '%s' "${password}"
    } | compose -f "${COMPOSE_FILE}" exec -T backend python -c '
import asyncio
import logging
import sys
logging.disable(logging.CRITICAL)

email = sys.stdin.readline().strip().lower()
length_line = sys.stdin.readline().strip()
try:
    n = int(length_line)
except ValueError:
    print("bad password framing", file=sys.stderr)
    sys.exit(2)
password = sys.stdin.read(n)
if len(password) < 8:
    print("password too short", file=sys.stderr)
    sys.exit(2)

from fastapi_users.password import PasswordHelper
from sqlalchemy import select
from app.db.session import get_session_factory
from app.models.user import User

async def main():
    factory = get_session_factory()
    async with factory() as session:
        # .unique() required: User.oauth_accounts uses joined eager load
        result = await session.execute(select(User).where(User.email == email))
        user = result.unique().scalar_one_or_none()
        if user is None:
            print("user not found: " + email, file=sys.stderr)
            sys.exit(3)
        user.hashed_password = PasswordHelper().hash(password)
        user.is_active = True
        await session.commit()
        # Distinct marker (compose/podman may prefix ANSI codes on the same line)
        print("EVERFLOW_RESET_OK " + str(user.email))

asyncio.run(main())
' 2>&1
  )"
  rc=$?
  set -e

  if printf '%s\n' "${out}" | grep -q 'EVERFLOW_RESET_OK'; then
    ok "password updated for ${email}"
    echo ""
    echo "  Sign in at ${UI_URL}"
    echo "  Email: ${email}"
    echo "  (use the new password you just set)"
    echo ""
    return 0
  fi

  if printf '%s\n' "${out}" | grep -qi 'user not found'; then
    warn "no user with email: ${email}"
    echo "  Known users:" >&2
    list_platform_users 2>/dev/null | sed 's/^/    /' >&2 || true
    return 1
  fi
  warn "password reset failed (exit ${rc})"
  printf '%s\n' "${out}" | grep -viE 'password|hashed' | tail -n 8 | sed 's/^/    /' >&2 || true
  return 1
}

cmd_reset_password_noninteractive() {
  RESET_EMAIL="${EVERFLOW_RESET_EMAIL:-${RESET_EMAIL:-${EVERFLOW_ADMIN_EMAIL:-}}}"
  RESET_PASSWORD="${EVERFLOW_RESET_PASSWORD:-${RESET_PASSWORD:-${EVERFLOW_ADMIN_PASSWORD:-}}}"
  if [[ -n "${EVERFLOW_RESET_PASSWORD_ENV:-}" ]]; then
    local env_name="${EVERFLOW_RESET_PASSWORD_ENV}"
    RESET_PASSWORD="${!env_name:-}"
  elif [[ -n "${EVERFLOW_ADMIN_PASSWORD_ENV:-}" ]]; then
    local env_name="${EVERFLOW_ADMIN_PASSWORD_ENV}"
    RESET_PASSWORD="${!env_name:-}"
  fi
  if [[ -z "${RESET_EMAIL}" || -z "${RESET_PASSWORD}" ]]; then
    cat >&2 <<'EOF'
  reset-password (non-interactive) requires:
    EVERFLOW_RESET_EMAIL   (or --email)
    EVERFLOW_RESET_PASSWORD  (or --password-env NAME)
EOF
    return 1
  fi
  do_reset_password
}

cmd_reset_password_interactive() {
  if ! api_health_ok 2>/dev/null; then
    warn "API not healthy — start the stack first: everflow start"
    return 1
  fi

  echo ""
  echo "  Reset user password"
  echo "  ────────────────────────────────────────"
  echo "  Host-operator recovery (self-hosted). There is no email"
  echo "  forgot-password flow yet — this updates the DB hash directly."
  echo ""
  step "Users on this instance"
  local users_out
  users_out="$(list_platform_users 2>/dev/null || true)"
  if [[ -z "${users_out}" || "${users_out}" == "(no users)" ]]; then
    warn "no users found — run setup-admin first"
    return 1
  fi
  echo "${users_out}" | sed 's/^/    /'
  echo ""

  local default_email
  default_email="$(printf '%s\n' "${users_out}" | head -n1 | awk '{print $1}')"
  # Prefer first superuser line if present
  if printf '%s\n' "${users_out}" | grep -q 'superuser'; then
    default_email="$(printf '%s\n' "${users_out}" | grep 'superuser' | head -n1 | awk '{print $1}')"
  fi

  local email password password2
  read -r -p "  Email [${default_email}]: " email
  email="${email:-${default_email}}"
  email="$(printf '%s' "${email}" | tr '[:upper:]' '[:lower:]')"
  email="${email#"${email%%[![:space:]]*}"}"
  email="${email%"${email##*[![:space:]]}"}"

  if confirm_yes "Generate a strong password?" "n"; then
    if command -v openssl >/dev/null 2>&1; then
      password="$(openssl rand -base64 18 | tr -d '/+=' | head -c 20)"
    else
      password="$(rand_hex | head -c 20)"
    fi
    echo ""
    echo "  Generated password (copy now — will not be shown again):"
    echo "    ${password}"
    echo ""
  else
    password="$(read_secret "New password (min 8 chars)")"
    password2="$(read_secret "Confirm new password")"
    if [[ "${password}" != "${password2}" ]]; then
      warn "passwords do not match"
      return 1
    fi
  fi

  RESET_EMAIL="${email}"
  RESET_PASSWORD="${password}"
  do_reset_password
}

cmd_reset_password() {
  if [[ -n "${EVERFLOW_RESET_EMAIL:-}" || -n "${RESET_EMAIL:-}" || -n "${EVERFLOW_ADMIN_EMAIL:-}" ]] \
    && { [[ -n "${EVERFLOW_RESET_PASSWORD:-}" || -n "${RESET_PASSWORD:-}" || -n "${EVERFLOW_ADMIN_PASSWORD:-}" \
      || -n "${EVERFLOW_RESET_PASSWORD_ENV:-}" || -n "${EVERFLOW_ADMIN_PASSWORD_ENV:-}" ]]; }; then
    cmd_reset_password_noninteractive
    return
  fi
  if is_tty; then
    cmd_reset_password_interactive
    return
  fi
  echo "  Non-interactive reset-password requires EVERFLOW_RESET_EMAIL and EVERFLOW_RESET_PASSWORD." >&2
  return 1
}
