"""Startup / readiness fail-closed checks for insecure non-dev config."""

from __future__ import annotations

from app.config import Settings

# development and test may use documented placeholders. production and staging
# must set unique secrets and a dedicated credential encryption key.
NON_DEV_ENVIRONMENTS = frozenset({"production", "staging"})

_DEFAULT_SECRET = "change-me-in-production-use-a-long-random-string"
_DEFAULT_SANDBOX_TOKENS = frozenset(
    {
        "change-me",
        "dev-sandbox-token-change-me",
    }
)


def is_non_dev_environment(environment: str | None) -> bool:
    return (environment or "").strip().lower() in NON_DEV_ENVIRONMENTS


def secret_is_default(value: str | None) -> bool:
    raw = (value or "").strip()
    if not raw:
        return True
    if raw == _DEFAULT_SECRET:
        return True
    if "change-me" in raw.lower():
        return True
    return False


def sandbox_token_is_default(value: str | None) -> bool:
    raw = (value or "").strip()
    if not raw:
        return True
    if raw in _DEFAULT_SANDBOX_TOKENS:
        return True
    if "change-me" in raw.lower():
        return True
    return False


def production_config_warnings(settings: Settings) -> list[str]:
    """Return operator-facing warnings for the current settings.

    Empty when ``environment`` is development or test. Used by ``/ready`` and
    startup. Fatal items are also raised by :func:`assert_production_secrets`.
    """
    warnings: list[str] = []
    if not is_non_dev_environment(settings.environment):
        return warnings
    if secret_is_default(settings.secret_key):
        warnings.append("SECRET_KEY is still a default/insecure value")
    if sandbox_token_is_default(settings.sandbox_agent_token):
        warnings.append("SANDBOX_AGENT_TOKEN is still a default/insecure value")
    if not (settings.credentials_encryption_key or "").strip():
        warnings.append("CREDENTIALS_ENCRYPTION_KEY is unset (required outside development/test)")
    elif secret_is_default(settings.credentials_encryption_key):
        warnings.append("CREDENTIALS_ENCRYPTION_KEY is still a default/insecure value")
    if getattr(settings, "sandbox_mock", False):
        warnings.append("SANDBOX_MOCK=true is not allowed outside development/test")
    if settings.is_sqlite:
        warnings.append("DATABASE_URL is SQLite — PostgreSQL is recommended for production")
    return warnings


def assert_production_secrets(settings: Settings) -> None:
    """Raise RuntimeError when production/staging has unsafe defaults.

    Fail-closed for SECRET_KEY, SANDBOX_AGENT_TOKEN, CREDENTIALS_ENCRYPTION_KEY,
    and SANDBOX_MOCK. SQLite remains a warning only.
    """
    if not is_non_dev_environment(settings.environment):
        return
    warnings = production_config_warnings(settings)
    fatal = [
        w
        for w in warnings
        if any(
            key in w
            for key in (
                "SECRET_KEY",
                "SANDBOX_AGENT_TOKEN",
                "CREDENTIALS_ENCRYPTION_KEY",
                "SANDBOX_MOCK",
            )
        )
    ]
    if fatal:
        raise RuntimeError(
            "Refusing to start outside development/test with insecure config: "
            + "; ".join(fatal)
        )
