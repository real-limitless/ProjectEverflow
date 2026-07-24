"""Organization members and invite flow."""

import pytest
from httpx import AsyncClient


async def _register_login(client: AsyncClient, email: str, password: str = "password123") -> str:
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
    )
    login = await client.post(
        "/api/v1/auth/jwt/login",
        data={"username": email, "password": password},
    )
    assert login.status_code == 200, login.text
    return login.json()["access_token"]


@pytest.mark.asyncio
async def test_invite_accept_and_list_members(client: AsyncClient) -> None:
    owner_token = await _register_login(client, "owner@example.com")
    owner_headers = {"Authorization": f"Bearer {owner_token}"}

    org = await client.post(
        "/api/v1/orgs",
        headers=owner_headers,
        json={"name": "Team", "slug": "team"},
    )
    assert org.status_code == 201
    org_id = org.json()["id"]

    invite = await client.post(
        f"/api/v1/orgs/{org_id}/invites",
        headers=owner_headers,
        json={"role": "member", "expires_hours": 24},
    )
    assert invite.status_code == 201, invite.text
    token = invite.json()["token"]
    assert token
    assert invite.json()["invite_url"]

    member_token = await _register_login(client, "member@example.com")
    member_headers = {"Authorization": f"Bearer {member_token}"}
    accept = await client.post(
        f"/api/v1/invites/{token}/accept",
        headers=member_headers,
    )
    assert accept.status_code == 200, accept.text
    assert accept.json()["organization_slug"] == "team"

    members = await client.get(
        f"/api/v1/orgs/{org_id}/members",
        headers=owner_headers,
    )
    assert members.status_code == 200
    emails = {m["email"] for m in members.json()}
    assert "owner@example.com" in emails
    assert "member@example.com" in emails

    member_user_id = next(
        m["user_id"] for m in members.json() if m["email"] == "member@example.com"
    )
    patch = await client.patch(
        f"/api/v1/orgs/{org_id}/members/{member_user_id}",
        headers=owner_headers,
        json={"role": "admin"},
    )
    assert patch.status_code == 200
    assert patch.json()["role"] == "admin"
