"""Project CRUD tests."""

import pytest
from httpx import AsyncClient


async def _create_org(client: AsyncClient, headers: dict[str, str], slug: str = "proj-org") -> str:
    response = await client.post(
        "/api/v1/orgs",
        headers=headers,
        json={"name": "Project Org", "slug": slug},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


@pytest.mark.asyncio
async def test_project_lifecycle(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    org_id = await _create_org(client, auth_headers)

    create = await client.post(
        f"/api/v1/orgs/{org_id}/projects",
        headers=auth_headers,
        json={"name": "Aura Host", "slug": "aura", "description": "Demo project"},
    )
    assert create.status_code == 201, create.text
    project = create.json()
    assert project["name"] == "Aura Host"
    assert project["organization_id"] == org_id
    project_id = project["id"]

    listed = await client.get(f"/api/v1/orgs/{org_id}/projects", headers=auth_headers)
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    got = await client.get(f"/api/v1/projects/{project_id}", headers=auth_headers)
    assert got.status_code == 200
    assert got.json()["slug"] == "aura"

    patch = await client.patch(
        f"/api/v1/projects/{project_id}",
        headers=auth_headers,
        json={"description": "Updated description"},
    )
    assert patch.status_code == 200
    assert patch.json()["description"] == "Updated description"

    rename = await client.patch(
        f"/api/v1/projects/{project_id}",
        headers=auth_headers,
        json={"name": "Aura Host v2", "slug": "aura-v2"},
    )
    assert rename.status_code == 200
    assert rename.json()["slug"] == "aura-v2"

    delete = await client.delete(f"/api/v1/projects/{project_id}", headers=auth_headers)
    assert delete.status_code == 204

    missing = await client.get(f"/api/v1/projects/{project_id}", headers=auth_headers)
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_duplicate_project_slug(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    org_id = await _create_org(client, auth_headers, slug="dup-proj-org")
    await client.post(
        f"/api/v1/orgs/{org_id}/projects",
        headers=auth_headers,
        json={"name": "One", "slug": "same"},
    )
    second = await client.post(
        f"/api/v1/orgs/{org_id}/projects",
        headers=auth_headers,
        json={"name": "Two", "slug": "same"},
    )
    assert second.status_code == 409
