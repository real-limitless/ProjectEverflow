"""Git credential vault."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_user_git_credential_crud(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    create = await client.post(
        "/api/v1/me/git-credentials",
        headers=auth_headers,
        json={
            "provider": "github",
            "token": "ghp_testtoken1234567890",
            "label": "Personal",
            "is_default": True,
        },
    )
    assert create.status_code == 201, create.text
    body = create.json()
    assert body["key_hint"].endswith("7890")
    assert "token" not in body
    assert "secret" not in body
    cred_id = body["id"]

    listed = await client.get("/api/v1/me/git-credentials", headers=auth_headers)
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    deleted = await client.delete(
        f"/api/v1/me/git-credentials/{cred_id}",
        headers=auth_headers,
    )
    assert deleted.status_code == 204

    listed2 = await client.get("/api/v1/me/git-credentials", headers=auth_headers)
    assert listed2.json() == []


@pytest.mark.asyncio
async def test_org_git_credential(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    org = await client.post(
        "/api/v1/orgs",
        headers=auth_headers,
        json={"name": "Git Org", "slug": "git-org"},
    )
    org_id = org.json()["id"]
    create = await client.post(
        f"/api/v1/orgs/{org_id}/git-credentials",
        headers=auth_headers,
        json={"provider": "github", "token": "ghp_orgtoken9999", "label": "Org"},
    )
    assert create.status_code == 201, create.text
    listed = await client.get(
        f"/api/v1/orgs/{org_id}/git-credentials",
        headers=auth_headers,
    )
    assert len(listed.json()) == 1
