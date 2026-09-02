"""Fail-closed sandbox-agent startup — deny default tokens and mock in prod."""

from __future__ import annotations

import pytest

from app.config import Settings
from app.startup_checks import assert_agent_startup, is_non_dev_environment, token_is_default


def test_token_helpers() -> None:
    assert token_is_default("")
    assert token_is_default("change-me")
    assert token_is_default("dev-sandbox-token-change-me")
    assert not token_is_default("unique-production-agent-token")
    assert is_non_dev_environment("production")
    assert is_non_dev_environment("staging")
    assert not is_non_dev_environment("development")
    assert not is_non_dev_environment("test")


def test_development_allows_defaults_and_mock() -> None:
    settings = Settings(
        environment="development",
        sandbox_agent_token="change-me",
        sandbox_mock=True,
    )
    assert_agent_startup(settings)


def test_production_refuses_default_token() -> None:
    settings = Settings(
        environment="production",
        sandbox_agent_token="dev-sandbox-token-change-me",
        sandbox_mock=False,
    )
    with pytest.raises(RuntimeError, match="SANDBOX_AGENT_TOKEN"):
        assert_agent_startup(settings)


def test_production_refuses_mock() -> None:
    settings = Settings(
        environment="production",
        sandbox_agent_token="unique-production-agent-token",
        sandbox_mock=True,
    )
    with pytest.raises(RuntimeError, match="SANDBOX_MOCK"):
        assert_agent_startup(settings)


def test_staging_refuses_default_token() -> None:
    settings = Settings(
        environment="staging",
        sandbox_agent_token="change-me",
        sandbox_mock=False,
    )
    with pytest.raises(RuntimeError, match="SANDBOX_AGENT_TOKEN"):
        assert_agent_startup(settings)


def test_production_ok_with_unique_token() -> None:
    settings = Settings(
        environment="production",
        sandbox_agent_token="unique-production-agent-token",
        sandbox_mock=False,
    )
    assert_agent_startup(settings)
