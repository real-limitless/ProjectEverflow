"""Fail-closed operator checks — deny default secrets / missing keys / mock."""

from __future__ import annotations

import pytest

from app.config import Settings
from app.services.credential_crypto import encrypt_secret, fernet_for_settings
from app.services.production_checks import (
    assert_production_secrets,
    is_non_dev_environment,
    production_config_warnings,
    sandbox_token_is_default,
    secret_is_default,
)


def _settings(**kwargs) -> Settings:
    base = dict(
        environment="production",
        secret_key="unique-production-secret-key-not-a-placeholder",
        sandbox_agent_token="unique-production-agent-token",
        credentials_encryption_key="unique-production-fernet-material",
        sandbox_mock=False,
        database_url="postgresql+asyncpg://everflow:everflow@db:5432/everflow",
    )
    base.update(kwargs)
    return Settings(**base)


def test_is_non_dev_environment() -> None:
    assert is_non_dev_environment("production")
    assert is_non_dev_environment("staging")
    assert is_non_dev_environment("Production")
    assert not is_non_dev_environment("development")
    assert not is_non_dev_environment("test")
    assert not is_non_dev_environment("")


def test_secret_helpers() -> None:
    assert secret_is_default("")
    assert secret_is_default("change-me-in-production-use-a-long-random-string")
    assert secret_is_default("please-change-me-now")
    assert not secret_is_default("unique-production-secret-key-not-a-placeholder")
    assert sandbox_token_is_default("change-me")
    assert sandbox_token_is_default("dev-sandbox-token-change-me")
    assert not sandbox_token_is_default("unique-production-agent-token")


def test_development_and_test_allow_defaults() -> None:
    for env in ("development", "test"):
        s = _settings(
            environment=env,
            secret_key="change-me-in-production-use-a-long-random-string",
            sandbox_agent_token="dev-sandbox-token-change-me",
            credentials_encryption_key="",
            sandbox_mock=True,
        )
        assert production_config_warnings(s) == []
        assert_production_secrets(s)  # does not raise


def test_production_refuses_default_secret_key() -> None:
    s = _settings(secret_key="change-me-in-production-use-a-long-random-string")
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        assert_production_secrets(s)


def test_production_refuses_default_agent_token() -> None:
    s = _settings(sandbox_agent_token="dev-sandbox-token-change-me")
    with pytest.raises(RuntimeError, match="SANDBOX_AGENT_TOKEN"):
        assert_production_secrets(s)


def test_production_refuses_missing_credentials_key() -> None:
    s = _settings(credentials_encryption_key="")
    with pytest.raises(RuntimeError, match="CREDENTIALS_ENCRYPTION_KEY"):
        assert_production_secrets(s)


def test_staging_refuses_missing_credentials_key() -> None:
    s = _settings(environment="staging", credentials_encryption_key="")
    with pytest.raises(RuntimeError, match="CREDENTIALS_ENCRYPTION_KEY"):
        assert_production_secrets(s)


def test_production_refuses_sandbox_mock() -> None:
    s = _settings(sandbox_mock=True)
    with pytest.raises(RuntimeError, match="SANDBOX_MOCK"):
        assert_production_secrets(s)


def test_production_ok_with_unique_secrets() -> None:
    s = _settings()
    warnings = production_config_warnings(s)
    assert warnings == []
    assert_production_secrets(s)


def test_sqlite_is_warning_only() -> None:
    s = _settings(database_url="sqlite+aiosqlite:////data/everflow.db")
    warnings = production_config_warnings(s)
    assert any("SQLite" in w for w in warnings)
    assert_production_secrets(s)  # not fatal


def test_fernet_refuses_missing_key_in_production() -> None:
    s = _settings(credentials_encryption_key="")
    with pytest.raises(RuntimeError, match="CREDENTIALS_ENCRYPTION_KEY"):
        fernet_for_settings(s)


def test_fernet_allows_secret_key_fallback_in_development() -> None:
    s = _settings(
        environment="development",
        credentials_encryption_key="",
        secret_key="dev-only-secret",
    )
    token, _ = encrypt_secret("hello", settings=s)
    assert token


def test_fernet_uses_dedicated_key_in_production() -> None:
    s = _settings()
    token, _ = encrypt_secret("hello", settings=s)
    assert token
