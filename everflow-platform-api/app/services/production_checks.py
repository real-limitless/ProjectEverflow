"""Startup / readiness warnings for insecure production config."""

from __future__ import annotations

from app.config import Settings

_DEFAULT_SECRET = "change-me-in-production-use-a-long-random-string"
_DEFAULT_SANDBOX_TOKENS = frozenset(
    {
        "change-me",
        "dev-sandbox-token-change-me",
    }
)


def production_config_warnings(settings: Settings) -> list[str]:
    warnings: list[str] = []
    if settings.environment != "production":
        return warnings
    if settings.secret_key.strip() in ("", _DEFAULT_SECRET) or "change-me" in settings.secret_key:
        warnings.append("SECRET_KEY is still a default/insecure value")
    if settings.sandbox_agent_token.strip() in _DEFAULT_SANDBOX_TOKENS:
        warnings.append("SANDBOX_AGENT_TOKEN is still a default/insecure value")
    if not (settings.credentials_encryption_key or "").strip():
        warnings.append("CREDENTIALS_ENCRYPTION_KEY is unset (falling back to SECRET_KEY)")
    if settings.is_sqlite:
        warnings.append("DATABASE_URL is SQLite — PostgreSQL is recommended for production")
    return warnings


def assert_production_secrets(settings: Settings) -> None:
    """Raise RuntimeError when production has unsafe defaults."""
    warnings = production_config_warnings(settings)
    fatal = [w for w in warnings if "SECRET_KEY" in w or "SANDBOX_AGENT_TOKEN" in w]
    if fatal:
        raise RuntimeError(
            "Refusing to start in production with insecure secrets: " + "; ".join(fatal)
        )
