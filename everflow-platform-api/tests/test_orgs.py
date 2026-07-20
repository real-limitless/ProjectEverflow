"""Organization CRUD tests."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_list_get_org(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    create = await client.post(
        "/api/v1/orgs",
        headers=auth_headers,
        json={"name": "Acme Corp", "slug": "acme"},
    )
    assert create.status_code == 201, create.text
    org = create.json()
    assert org["name"] == "Acme Corp"
    assert org["slug"] == "acme"
    assert org["role"] == "owner"
    org_id = org["id"]

    listed = await client.get("/api/v1/orgs", headers=auth_headers)
    assert listed.status_code == 200
    assert any(item["id"] == org_id for item in listed.json())

    got = await client.get(f"/api/v1/orgs/{org_id}", headers=auth_headers)
    assert got.status_code == 200
    assert got.json()["slug"] == "acme"


@pytest.mark.asyncio
async def test_duplicate_slug(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    await client.post(
        "/api/v1/orgs",
        headers=auth_headers,
        json={"name": "One", "slug": "dup-slug"},
    )
    second = await client.post(
        "/api/v1/orgs",
        headers=auth_headers,
        json={"name": "Two", "slug": "dup-slug"},
    )
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_update_and_delete_org(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    create = await client.post(
        "/api/v1/orgs",
        headers=auth_headers,
        json={"name": "Temp", "slug": "temp-org"},
    )
    org_id = create.json()["id"]

    patch = await client.patch(
        f"/api/v1/orgs/{org_id}",
        headers=auth_headers,
        json={"name": "Temp Renamed"},
    )
    assert patch.status_code == 200
    assert patch.json()["name"] == "Temp Renamed"

    delete = await client.delete(f"/api/v1/orgs/{org_id}", headers=auth_headers)
    assert delete.status_code == 204

    missing = await client.get(f"/api/v1/orgs/{org_id}", headers=auth_headers)
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_org_requires_auth(client: AsyncClient) -> None:
    response = await client.get("/api/v1/orgs")
    assert response.status_code == 401
