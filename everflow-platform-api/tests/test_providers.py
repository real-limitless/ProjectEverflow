"""Provider credential vault tests."""

import pytest
from httpx import AsyncClient

from app.config import Settings
from app.services.credential_crypto import (
    clear_crypto_cache,
    decrypt_secret,
    encrypt_secret,
    mask_secret,
)


def test_encrypt_roundtrip() -> None:
    clear_crypto_cache()
    settings = Settings(secret_key="unit-test-secret-key-material", environment="test")
    ct, nonce = encrypt_secret("sk-test-abc123xyz", settings)
    assert ct
    assert "sk-test" not in ct
    plain = decrypt_secret(ct, nonce, settings)
    assert plain == "sk-test-abc123xyz"
    assert mask_secret(plain).endswith("xyz")
    clear_crypto_cache()


async def _create_org(client: AsyncClient, headers: dict[str, str], slug: str = "prov-org") -> str:
    response = await client.post(
        "/api/v1/orgs",
        headers=headers,
        json={"name": "Provider Org", "slug": slug},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _create_project(
    client: AsyncClient, headers: dict[str, str], org_id: str, slug: str = "prov-proj"
) -> str:
    response = await client.post(
        f"/api/v1/orgs/{org_id}/projects",
        headers=headers,
        json={"name": "Provider Project", "slug": slug},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


@pytest.mark.asyncio
async def test_me_provider_lifecycle(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    catalog = await client.get("/api/v1/providers/catalog", headers=auth_headers)
    assert catalog.status_code == 200
    assert any(p["id"] == "openrouter" for p in catalog.json())

    empty = await client.get("/api/v1/me/providers", headers=auth_headers)
    assert empty.status_code == 200
    assert empty.json() == []

    created = await client.post(
        "/api/v1/me/providers",
        headers=auth_headers,
        json={
            "provider": "openrouter",
            "api_key": "sk-or-v1-super-secret-key-1234",
            "label": "Work OpenRouter",
            "scopes": ["chat", "embed"],
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["provider"] == "openrouter"
    assert body["label"] == "Work OpenRouter"
    assert "api_key" not in body
    assert "secret" not in body
    assert body["key_hint"].endswith("1234")
    assert "super-secret" not in str(body)
    cred_id = body["id"]

    listed = await client.get("/api/v1/me/providers", headers=auth_headers)
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    # Re-post same provider upserts key
    again = await client.post(
        "/api/v1/me/providers",
        headers=auth_headers,
        json={"provider": "openrouter", "api_key": "sk-or-v1-rotated-key-9999"},
    )
    assert again.status_code == 201
    assert again.json()["id"] == cred_id
    assert again.json()["key_hint"].endswith("9999")

    patched = await client.patch(
        f"/api/v1/me/providers/{cred_id}",
        headers=auth_headers,
        json={"label": "Personal"},
    )
    assert patched.status_code == 200
    assert patched.json()["label"] == "Personal"

    deleted = await client.delete(f"/api/v1/me/providers/{cred_id}", headers=auth_headers)
    assert deleted.status_code == 204

    after = await client.get("/api/v1/me/providers", headers=auth_headers)
    assert after.json() == []


@pytest.mark.asyncio
async def test_project_providers(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    org_id = await _create_org(client, auth_headers)
    project_id = await _create_project(client, auth_headers, org_id)

    created = await client.post(
        f"/api/v1/projects/{project_id}/providers",
        headers=auth_headers,
        json={"provider": "openai", "api_key": "sk-proj-abcdef123456"},
    )
    assert created.status_code == 201, created.text
    assert created.json()["owner_type"] == "project"
    assert created.json()["key_hint"].endswith("3456")
    cred_id = created.json()["id"]

    listed = await client.get(
        f"/api/v1/projects/{project_id}/providers",
        headers=auth_headers,
    )
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    deleted = await client.delete(
        f"/api/v1/projects/{project_id}/providers/{cred_id}",
        headers=auth_headers,
    )
    assert deleted.status_code == 204


@pytest.mark.asyncio
async def test_inject_without_sandbox(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    org_id = await _create_org(client, auth_headers, slug="inj-org")
    project_id = await _create_project(client, auth_headers, org_id, slug="inj-proj")

    await client.post(
        "/api/v1/me/providers",
        headers=auth_headers,
        json={"provider": "openai", "api_key": "sk-inject-test-aaaa"},
    )

    # Sandbox disabled in tests → inject reports not injected (no crash)
    inj = await client.post(
        f"/api/v1/projects/{project_id}/providers/inject",
        headers=auth_headers,
    )
    assert inj.status_code == 200, inj.text
    body = inj.json()
    assert body["injected"] is False
    assert "env_keys" in body
    assert "sk-inject" not in str(body)
