"""Tests for the OAuth credential vault."""

from __future__ import annotations

import time

import pytest

from app.services.workflows.oauth_vault import (
    N8N_OAUTH_TYPE_TO_PROVIDER,
    OAuthProvider,
    OAuthTokenSet,
    PROVIDERS,
    provider_for_n8n_type,
    resolve_engine_credentials,
)


def test_n8n_type_maps_to_provider() -> None:
    assert N8N_OAUTH_TYPE_TO_PROVIDER["googleSheetsOAuth2Api"] == "google"
    assert N8N_OAUTH_TYPE_TO_PROVIDER["slackOAuth2Api"] == "slack"
    assert N8N_OAUTH_TYPE_TO_PROVIDER["notionOAuth2Api"] == "notion"
    assert N8N_OAUTH_TYPE_TO_PROVIDER["githubOAuth2Api"] == "github"
    assert N8N_OAUTH_TYPE_TO_PROVIDER["gmailOAuth2"] == "google"


def test_provider_for_n8n_type_resolves() -> None:
    p = provider_for_n8n_type("googleSheetsOAuth2Api")
    assert isinstance(p, OAuthProvider)
    assert p.id == "google"
    assert "googleapis.com" in p.token_url


def test_provider_for_n8n_type_returns_none_for_unknown() -> None:
    assert provider_for_n8n_type("notARealType") is None


def test_oauth_token_set_expired() -> None:
    tok = OAuthTokenSet(access_token="x", expires_at=time.time() - 10)
    assert tok.is_expired() is True
    tok2 = OAuthTokenSet(access_token="x", expires_at=time.time() + 99999)
    assert tok2.is_expired() is False
    tok3 = OAuthTokenSet(access_token="x", expires_at=0.0)
    assert tok3.is_expired() is False


def test_oauth_token_set_engine_dict_shape() -> None:
    tok = OAuthTokenSet(access_token="abc", refresh_token="def", expires_at=1.0, scope="s", token_type="Bearer")
    d = tok.to_engine_dict()
    assert d["accessToken"] == "abc"
    assert d["refreshToken"] == "def"
    assert d["expiresAt"] == 1.0
    assert d["scope"] == "s"
    assert d["tokenType"] == "Bearer"


def test_providers_minimum_set() -> None:
    expected = {"google", "slack", "notion", "github", "linear", "hubspot", "microsoft", "airtable", "shopify"}
    assert expected.issubset(set(PROVIDERS.keys()))


@pytest.mark.asyncio
async def test_resolve_engine_credentials_passthrough_for_api_keys() -> None:
    stored = {
        "openai-1": {
            "credential_type": "openAiApi",
            "payload": {"apiKey": "sk-test"},
        },
    }
    out = await resolve_engine_credentials(stored=stored)
    assert out["openai-1"]["payload"] == {"apiKey": "sk-test"}


@pytest.mark.asyncio
async def test_resolve_engine_credentials_expands_oauth_payload() -> None:
    stored = {
        "gsheets-1": {
            "credential_type": "googleSheetsOAuth2Api",
            "payload": {"accessToken": "ya29.x", "refreshToken": "1//x", "expiresAt": 0.0},
        },
    }
    out = await resolve_engine_credentials(stored=stored)
    payload = out["gsheets-1"]["payload"]
    assert payload["accessToken"] == "ya29.x"
    assert payload["refreshToken"] == "1//x"
    assert payload["tokenType"] == "Bearer"


@pytest.mark.asyncio
async def test_resolve_engine_credentials_handles_string_payload() -> None:
    stored = {
        "gsheets-1": {
            "credential_type": "googleSheetsOAuth2Api",
            "payload": '{"accessToken":"ya29.y"}',
        },
    }
    out = await resolve_engine_credentials(stored=stored)
    assert out["gsheets-1"]["payload"]["accessToken"] == "ya29.y"


@pytest.mark.asyncio
async def test_resolve_engine_credentials_skips_refresh_without_secrets() -> None:
    stored = {
        "gsheets-1": {
            "credential_type": "googleSheetsOAuth2Api",
            "payload": {
                "accessToken": "old",
                "refreshToken": "rt",
                "expiresAt": time.time() - 100,
            },
        },
    }
    out = await resolve_engine_credentials(stored=stored)
    # Refresh secrets missing → keep the old access token, don't crash
    assert out["gsheets-1"]["payload"]["accessToken"] == "old"


@pytest.mark.asyncio
async def test_resolve_engine_credentials_handles_missing_payload() -> None:
    stored = {"gsheets-1": {"credential_type": "googleSheetsOAuth2Api"}}
    out = await resolve_engine_credentials(stored=stored)
    assert "gsheets-1" in out
