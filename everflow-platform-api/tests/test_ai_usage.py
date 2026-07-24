"""AI usage ingest + summary tests."""

from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient


async def _register_login(
    client: AsyncClient, email: str, password: str = "securepassword123"
) -> dict[str, str]:
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


async def _create_org_project(
    client: AsyncClient, headers: dict[str, str], slug: str
) -> tuple[str, str]:
    org = await client.post(
        "/api/v1/orgs",
        headers=headers,
        json={"name": f"Usage {slug}", "slug": slug},
    )
    assert org.status_code == 201, org.text
    org_id = org.json()["id"]
    project = await client.post(
        f"/api/v1/orgs/{org_id}/projects",
        headers=headers,
        json={"name": "Chat Proj", "slug": "chat"},
    )
    assert project.status_code == 201, project.text
    return org_id, project.json()["id"]


def _event(
    message_id: str,
    *,
    input_tokens: int = 100,
    output_tokens: int = 50,
    occurred_at: datetime | None = None,
    session_id: str = "sess-1",
    provider: str = "openai",
    model: str = "gpt-4o",
) -> dict:
    return {
        "session_id": session_id,
        "message_id": message_id,
        "provider": provider,
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "reasoning_tokens": 0,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
        "total_tokens": input_tokens + output_tokens,
        "duration_ms": 1200,
        "ttft_ms": 200,
        "occurred_at": (occurred_at or datetime.now(timezone.utc)).isoformat(),
        "completed": True,
    }


@pytest.mark.asyncio
async def test_usage_ingest_idempotent(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    _org_id, project_id = await _create_org_project(client, auth_headers, "usage-idem")

    first = await client.post(
        f"/api/v1/projects/{project_id}/usage/events",
        headers=auth_headers,
        json=_event("msg-1", input_tokens=10, output_tokens=5),
    )
    assert first.status_code == 201, first.text
    assert first.json()["total_tokens"] == 15
    event_id = first.json()["id"]

    second = await client.post(
        f"/api/v1/projects/{project_id}/usage/events",
        headers=auth_headers,
        json=_event("msg-1", input_tokens=100, output_tokens=50),
    )
    assert second.status_code == 201, second.text
    assert second.json()["id"] == event_id
    assert second.json()["total_tokens"] == 150

    # Same tokens again — still one row
    third = await client.post(
        f"/api/v1/projects/{project_id}/usage/events",
        headers=auth_headers,
        json=_event("msg-1", input_tokens=100, output_tokens=50),
    )
    assert third.status_code == 201
    assert third.json()["id"] == event_id


@pytest.mark.asyncio
async def test_usage_reject_empty_noise(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    _org_id, project_id = await _create_org_project(client, auth_headers, "usage-empty")
    empty = await client.post(
        f"/api/v1/projects/{project_id}/usage/events",
        headers=auth_headers,
        json={
            "session_id": "s",
            "message_id": "empty-1",
            "input_tokens": 0,
            "output_tokens": 0,
            "completed": False,
        },
    )
    assert empty.status_code == 422


@pytest.mark.asyncio
async def test_usage_batch_and_summary_me_vs_org(client: AsyncClient) -> None:
    owner = await _register_login(client, "usage-owner@example.com")
    member = await _register_login(client, "usage-member@example.com")
    org_id, project_id = await _create_org_project(client, owner, "usage-scope")

    invite = await client.post(
        f"/api/v1/orgs/{org_id}/invites",
        headers=owner,
        json={"role": "member", "expires_hours": 24},
    )
    assert invite.status_code == 201, invite.text
    acc = await client.post(
        f"/api/v1/invites/{invite.json()['token']}/accept",
        headers=member,
    )
    assert acc.status_code == 200, acc.text

    now = datetime.now(timezone.utc)
    batch = await client.post(
        f"/api/v1/projects/{project_id}/usage/events/batch",
        headers=owner,
        json={
            "events": [
                _event("owner-msg-1", input_tokens=200, output_tokens=100, occurred_at=now),
                _event(
                    "owner-msg-2",
                    input_tokens=50,
                    output_tokens=25,
                    occurred_at=now - timedelta(days=1),
                    session_id="sess-2",
                    model="gpt-4o-mini",
                ),
            ]
        },
    )
    assert batch.status_code == 200, batch.text
    assert batch.json()["accepted"] == 2

    mem_event = await client.post(
        f"/api/v1/projects/{project_id}/usage/events",
        headers=member,
        json=_event("member-msg-1", input_tokens=30, output_tokens=20, occurred_at=now),
    )
    assert mem_event.status_code == 201, mem_event.text

    me = await client.get(
        f"/api/v1/orgs/{org_id}/usage/summary",
        headers=owner,
        params={"scope": "me"},
    )
    assert me.status_code == 200, me.text
    me_body = me.json()
    assert me_body["scope"] == "me"
    assert me_body["totals"]["messages"] == 2
    assert me_body["totals"]["total_tokens"] == 375
    assert len(me_body["series_daily"]) >= 1
    assert len(me_body["by_model"]) >= 1
    assert me_body["by_user"] == []

    org = await client.get(
        f"/api/v1/orgs/{org_id}/usage/summary",
        headers=owner,
        params={"scope": "org"},
    )
    assert org.status_code == 200, org.text
    org_body = org.json()
    assert org_body["scope"] == "org"
    assert org_body["totals"]["messages"] == 3
    assert org_body["totals"]["total_tokens"] == 425
    assert len(org_body["by_user"]) == 2
    assert org_body["by_project"][0]["project_name"] == "Chat Proj"


@pytest.mark.asyncio
async def test_usage_summary_date_filter(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    org_id, project_id = await _create_org_project(client, auth_headers, "usage-dates")
    old = datetime.now(timezone.utc) - timedelta(days=40)
    recent = datetime.now(timezone.utc) - timedelta(days=2)

    await client.post(
        f"/api/v1/projects/{project_id}/usage/events",
        headers=auth_headers,
        json=_event("old-msg", input_tokens=1000, output_tokens=0, occurred_at=old),
    )
    await client.post(
        f"/api/v1/projects/{project_id}/usage/events",
        headers=auth_headers,
        json=_event("new-msg", input_tokens=10, output_tokens=5, occurred_at=recent),
    )

    summary = await client.get(
        f"/api/v1/orgs/{org_id}/usage/summary",
        headers=auth_headers,
        params={
            "scope": "me",
            "from": (datetime.now(timezone.utc) - timedelta(days=7)).isoformat(),
            "to": datetime.now(timezone.utc).isoformat(),
        },
    )
    assert summary.status_code == 200, summary.text
    body = summary.json()
    assert body["totals"]["messages"] == 1
    assert body["totals"]["total_tokens"] == 15
