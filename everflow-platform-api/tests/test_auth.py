"""Auth register / login / me tests."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_login_me(client: AsyncClient) -> None:
    email = "alice@example.com"
    password = "alicepassword123"

    reg = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
    )
    assert reg.status_code == 201
    body = reg.json()
    assert body["email"] == email
    assert body["is_active"] is True
    assert "id" in body

    login = await client.post(
        "/api/v1/auth/jwt/login",
        data={"username": email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]
    assert token

    me = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me.status_code == 200
    assert me.json()["email"] == email


@pytest.mark.asyncio
async def test_me_unauthorized(client: AsyncClient) -> None:
    response = await client.get("/api/v1/users/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_bad_password(client: AsyncClient) -> None:
    await client.post(
        "/api/v1/auth/register",
        json={"email": "bob@example.com", "password": "bobpassword123"},
    )
    login = await client.post(
        "/api/v1/auth/jwt/login",
        data={"username": "bob@example.com", "password": "wrong"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert login.status_code == 400
