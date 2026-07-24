"""Platform admin endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_admin_list_requires_superuser(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    # First registered user becomes superuser via on_after_register
    res = await client.get("/api/v1/admin/users", headers=auth_headers)
    assert res.status_code == 200
    users = res.json()
    assert len(users) >= 1
    assert users[0]["is_superuser"] is True

    orgs = await client.get("/api/v1/admin/orgs", headers=auth_headers)
    assert orgs.status_code == 200
