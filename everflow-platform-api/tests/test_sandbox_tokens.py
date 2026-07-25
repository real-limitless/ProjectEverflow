"""Sandbox access token + MCP dual-auth tests."""

import pytest
from httpx import AsyncClient


async def _project(client: AsyncClient, headers: dict[str, str]) -> str:
    org = await client.post(
        "/api/v1/orgs",
        headers=headers,
        json={"name": "Tok Org", "slug": "tok-org"},
    )
    assert org.status_code == 201, org.text
    proj = await client.post(
        f"/api/v1/orgs/{org.json()['id']}/projects",
        headers=headers,
        json={"name": "Tok App", "slug": "tok-app"},
    )
    assert proj.status_code == 201, proj.text
    return proj.json()["id"]


@pytest.mark.asyncio
async def test_mint_and_use_sandbox_token(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    project_id = await _project(client, auth_headers)

    minted = await client.post(
        f"/api/v1/projects/{project_id}/sandbox-tokens",
        headers=auth_headers,
        json={"label": "test-mcp", "revoke_existing": True},
    )
    assert minted.status_code == 201, minted.text
    body = minted.json()
    assert body["token"].startswith("ef_sbox_")
    assert body["project_id"] == project_id
    token = body["token"]
    sbox = {"Authorization": f"Bearer {token}"}

    ctx = await client.get(
        f"/api/v1/projects/{project_id}/mcp/context",
        headers=sbox,
    )
    assert ctx.status_code == 200, ctx.text
    assert ctx.json()["via"] == "sandbox_token"
    assert ctx.json()["project_slug"] == "tok-app"
    assert "knowledge:rw" in ctx.json()["scopes"]
    assert "jobs:rw" in ctx.json()["scopes"]

    create = await client.post(
        f"/api/v1/projects/{project_id}/knowledge/canvases",
        headers=sbox,
        json={"name": "From MCP", "content_md": "hello"},
    )
    assert create.status_code == 201, create.text
    assert create.json()["name"] == "From MCP"

    listed = await client.get(
        f"/api/v1/projects/{project_id}/knowledge/canvases",
        headers=sbox,
    )
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    # MCP list_projects / get_project hit GET /projects/{id} with sandbox token.
    proj = await client.get(f"/api/v1/projects/{project_id}", headers=sbox)
    assert proj.status_code == 200, proj.text
    assert proj.json()["slug"] == "tok-app"

    # Jobs accept sandbox tokens (scope jobs:rw). Without a running sandbox → 409, not 401/403.
    jobs = await client.get(f"/api/v1/projects/{project_id}/jobs", headers=sbox)
    assert jobs.status_code == 409, jobs.text
    assert "sandbox" in jobs.json()["detail"].lower()


@pytest.mark.asyncio
async def test_sandbox_token_cannot_access_other_project(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    project_a = await _project(client, auth_headers)
    org_b = await client.post(
        "/api/v1/orgs",
        headers=auth_headers,
        json={"name": "Other", "slug": "other-org"},
    )
    proj_b = await client.post(
        f"/api/v1/orgs/{org_b.json()['id']}/projects",
        headers=auth_headers,
        json={"name": "B", "slug": "proj-b"},
    )
    project_b = proj_b.json()["id"]

    minted = await client.post(
        f"/api/v1/projects/{project_a}/sandbox-tokens",
        headers=auth_headers,
        json={},
    )
    assert minted.status_code == 201
    sbox = {"Authorization": f"Bearer {minted.json()['token']}"}

    denied = await client.get(
        f"/api/v1/projects/{project_b}/knowledge/canvases",
        headers=sbox,
    )
    assert denied.status_code == 403

    denied_proj = await client.get(f"/api/v1/projects/{project_b}", headers=sbox)
    assert denied_proj.status_code == 403


@pytest.mark.asyncio
async def test_invalid_sandbox_token(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    project_id = await _project(client, auth_headers)
    bad = await client.get(
        f"/api/v1/projects/{project_id}/mcp/context",
        headers={"Authorization": "Bearer ef_sbox_notarealtokenvalue000"},
    )
    assert bad.status_code == 401
