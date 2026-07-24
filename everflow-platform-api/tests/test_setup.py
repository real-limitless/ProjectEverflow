"""First-run setup and auth provider flags."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_setup_status_needs_setup(client: AsyncClient) -> None:
    res = await client.get("/api/v1/setup/status")
    assert res.status_code == 200
    data = res.json()
    assert data["needs_setup"] is True
    assert "oauth" in data


@pytest.mark.asyncio
async def test_bootstrap_creates_superuser_and_org(client: AsyncClient) -> None:
    res = await client.post(
        "/api/v1/setup/bootstrap",
        json={
            "email": "admin@example.com",
            "password": "adminpass123",
            "org_name": "Acme",
            "org_slug": "acme",
        },
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["email"] == "admin@example.com"
    assert body["org_slug"] == "acme"
    assert body["access_token"]

    status = await client.get("/api/v1/setup/status")
    assert status.json()["needs_setup"] is False

    again = await client.post(
        "/api/v1/setup/bootstrap",
        json={
            "email": "other@example.com",
            "password": "otherpass123",
            "org_name": "Other",
            "org_slug": "other",
        },
    )
    assert again.status_code == 410

    me = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {body['access_token']}"},
    )
    assert me.status_code == 200
    assert me.json()["is_superuser"] is True


@pytest.mark.asyncio
async def test_auth_providers_flags(client: AsyncClient) -> None:
    res = await client.get("/api/v1/auth/providers")
    assert res.status_code == 200
    data = res.json()
    assert data["password"] is True
    assert "github" in data
    assert "google" in data


@pytest.mark.asyncio
async def test_system_health_alias(client: AsyncClient) -> None:
    res = await client.get("/api/v1/system/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"
