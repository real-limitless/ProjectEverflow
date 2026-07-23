"""Knowledge canvas and project agent CRUD tests."""

import pytest
from httpx import AsyncClient


async def _create_org_and_project(
    client: AsyncClient,
    headers: dict[str, str],
    *,
    org_slug: str = "studio-org",
    project_slug: str = "studio-app",
) -> str:
    org = await client.post(
        "/api/v1/orgs",
        headers=headers,
        json={"name": "Studio Org", "slug": org_slug},
    )
    assert org.status_code == 201, org.text
    org_id = org.json()["id"]
    proj = await client.post(
        f"/api/v1/orgs/{org_id}/projects",
        headers=headers,
        json={"name": "Studio App", "slug": project_slug, "description": "MCP-ready"},
    )
    assert proj.status_code == 201, proj.text
    return proj.json()["id"]


async def _second_user_headers(client: AsyncClient) -> dict[str, str]:
    email = "outsider@example.com"
    password = "securepassword123"
    reg = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
    )
    assert reg.status_code == 201, reg.text
    login = await client.post(
        "/api/v1/auth/jwt/login",
        data={"username": email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


@pytest.mark.asyncio
async def test_canvas_lifecycle(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    project_id = await _create_org_and_project(client, auth_headers)

    empty = await client.get(
        f"/api/v1/projects/{project_id}/knowledge/canvases",
        headers=auth_headers,
    )
    assert empty.status_code == 200
    assert empty.json() == []

    create = await client.post(
        f"/api/v1/projects/{project_id}/knowledge/canvases",
        headers=auth_headers,
        json={
            "name": "Architecture",
            "description": "System sketch",
            "content_md": "# Overview\n\nMicroVMs + API.",
            "origin": "created",
        },
    )
    assert create.status_code == 201, create.text
    canvas = create.json()
    assert canvas["name"] == "Architecture"
    assert canvas["content_md"].startswith("# Overview")
    assert canvas["status"] == "ready"
    assert canvas["project_id"] == project_id
    canvas_id = canvas["id"]

    listed = await client.get(
        f"/api/v1/projects/{project_id}/knowledge/canvases",
        headers=auth_headers,
    )
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert "content_md" not in listed.json()[0]

    got = await client.get(
        f"/api/v1/projects/{project_id}/knowledge/canvases/{canvas_id}",
        headers=auth_headers,
    )
    assert got.status_code == 200
    assert got.json()["content_md"].startswith("# Overview")

    # Simulate indexed, then content edit → stale
    marked = await client.patch(
        f"/api/v1/projects/{project_id}/knowledge/canvases/{canvas_id}",
        headers=auth_headers,
        json={"status": "indexed", "chunks": 3},
    )
    assert marked.status_code == 200
    assert marked.json()["status"] == "indexed"

    patched = await client.patch(
        f"/api/v1/projects/{project_id}/knowledge/canvases/{canvas_id}",
        headers=auth_headers,
        json={"content_md": "# Overview\n\nUpdated."},
    )
    assert patched.status_code == 200
    assert patched.json()["status"] == "stale"
    assert "Updated" in patched.json()["content_md"]

    deleted = await client.delete(
        f"/api/v1/projects/{project_id}/knowledge/canvases/{canvas_id}",
        headers=auth_headers,
    )
    assert deleted.status_code == 204

    missing = await client.get(
        f"/api/v1/projects/{project_id}/knowledge/canvases/{canvas_id}",
        headers=auth_headers,
    )
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_agent_lifecycle(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    project_id = await _create_org_and_project(
        client, auth_headers, org_slug="agent-org", project_slug="agent-app"
    )

    create = await client.post(
        f"/api/v1/projects/{project_id}/agents",
        headers=auth_headers,
        json={
            "name": "Security Reviewer",
            "role": "review",
            "description": "Reviews PRs for security",
            "system_prompt": "You review code for security issues.",
            "tools": ["file_read", "git_status"],
            "active": True,
        },
    )
    assert create.status_code == 201, create.text
    agent = create.json()
    assert agent["name"] == "Security Reviewer"
    assert agent["tools"] == ["file_read", "git_status"]
    agent_id = agent["id"]

    listed = await client.get(f"/api/v1/projects/{project_id}/agents", headers=auth_headers)
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    patched = await client.patch(
        f"/api/v1/projects/{project_id}/agents/{agent_id}",
        headers=auth_headers,
        json={"active": False, "tools": ["file_read"]},
    )
    assert patched.status_code == 200
    assert patched.json()["active"] is False
    assert patched.json()["tools"] == ["file_read"]

    deleted = await client.delete(
        f"/api/v1/projects/{project_id}/agents/{agent_id}",
        headers=auth_headers,
    )
    assert deleted.status_code == 204


@pytest.mark.asyncio
async def test_non_member_cannot_access_studio(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    project_id = await _create_org_and_project(
        client, auth_headers, org_slug="private-org", project_slug="private-app"
    )
    outsider = await _second_user_headers(client)

    canvases = await client.get(
        f"/api/v1/projects/{project_id}/knowledge/canvases",
        headers=outsider,
    )
    assert canvases.status_code == 403

    agents = await client.get(
        f"/api/v1/projects/{project_id}/agents",
        headers=outsider,
    )
    assert agents.status_code == 403

    create = await client.post(
        f"/api/v1/projects/{project_id}/knowledge/canvases",
        headers=outsider,
        json={"name": "Nope"},
    )
    assert create.status_code == 403
