"""Sandbox access token + MCP dual-auth tests."""

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient

from app.config import Settings
from app.models.sandbox_token import SandboxAccessToken
from app.services.sandbox_tokens import _absolute_expiry_cap, _slide_expiry


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


@pytest.mark.asyncio
async def test_sandbox_token_slides_expiry_on_use(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    """Active MCP use extends expires_at so long sessions do not 401 after idle TTL."""
    project_id = await _project(client, auth_headers)
    minted = await client.post(
        f"/api/v1/projects/{project_id}/sandbox-tokens",
        headers=auth_headers,
        json={"label": "slide-test", "ttl_seconds": 3600},
    )
    assert minted.status_code == 201, minted.text
    raw = minted.json()["token"]
    token_id = minted.json()["id"]

    # Simulate near-expiry: remaining < slide_if_remaining → next verify extends.
    from app.db.session import _session_factory

    assert _session_factory is not None
    tid = UUID(token_id)
    async with _session_factory() as session:
        row = await session.get(SandboxAccessToken, tid)
        assert row is not None
        now = datetime.now(timezone.utc)
        row.expires_at = now + timedelta(minutes=30)  # below default 12h slide threshold
        await session.commit()
        near_exp = row.expires_at

    ok = await client.get(
        f"/api/v1/projects/{project_id}/mcp/context",
        headers={"Authorization": f"Bearer {raw}"},
    )
    assert ok.status_code == 200, ok.text

    async with _session_factory() as session:
        row = await session.get(SandboxAccessToken, tid)
        assert row is not None
        assert _as_utc(row.expires_at) > _as_utc(near_exp)


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


@pytest.mark.asyncio
async def test_sandbox_token_expired_returns_401(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    project_id = await _project(client, auth_headers)
    minted = await client.post(
        f"/api/v1/projects/{project_id}/sandbox-tokens",
        headers=auth_headers,
        json={"label": "expired-test", "ttl_seconds": 60},
    )
    assert minted.status_code == 201, minted.text
    raw = minted.json()["token"]
    token_id = minted.json()["id"]

    from app.db.session import _session_factory

    assert _session_factory is not None
    async with _session_factory() as session:
        row = await session.get(SandboxAccessToken, UUID(token_id))
        assert row is not None
        row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=5)
        await session.commit()

    bad = await client.get(
        f"/api/v1/projects/{project_id}/mcp/context",
        headers={"Authorization": f"Bearer {raw}"},
    )
    assert bad.status_code == 401
    assert "expired" in bad.json()["detail"].lower() or "invalid" in bad.json()["detail"].lower()


def test_slide_respects_max_lifetime() -> None:
    """Hard cap: continuous use cannot extend past max lifetime from mint."""
    settings = Settings(
        environment="test",
        secret_key="x" * 32,
        database_url="sqlite+aiosqlite:///:memory:",
        sandbox_token_ttl_seconds=3600,
        sandbox_token_max_lifetime_seconds=7200,
        sandbox_token_slide_if_remaining_seconds=3500,
    )
    now = datetime.now(timezone.utc)
    row = SandboxAccessToken(
        project_id=uuid4(),
        user_id=uuid4(),
        token_hash="a" * 64,
        prefix="ef_sbox_testxxxx",
        scopes=["project:read"],
        label="t",
        expires_at=now + timedelta(minutes=10),
        created_at=now - timedelta(seconds=7000),  # near 7200 cap
    )
    changed = _slide_expiry(row, now=now, settings=settings)
    if changed:
        assert row.expires_at <= row.created_at + timedelta(seconds=7200)
    row.created_at = now - timedelta(seconds=8000)
    row.expires_at = now + timedelta(hours=1)
    cap = _absolute_expiry_cap(created_at=row.created_at, now=now, settings=settings)
    assert cap is not None and now >= cap
