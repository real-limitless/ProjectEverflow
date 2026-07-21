"""Preview tickets, endpoint minting, and host routing."""

from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings, get_settings
from app.services.preview_endpoints import parse_endpoint_id_from_host, public_preview_url
from app.services.preview_tickets import PreviewTicketError, mint_ticket, verify_ticket
from app.services.sandbox_agent_client import SandboxAgentError


def test_ticket_roundtrip() -> None:
    settings = Settings(secret_key="test-secret-key-for-jwt-signing-not-for-prod")
    uid, eid, pid = uuid4(), uuid4(), uuid4()
    token, exp = mint_ticket(
        user_id=uid,
        endpoint_id=eid,
        project_id=pid,
        port=5173,
        settings=settings,
    )
    claims = verify_ticket(token, settings=settings)
    assert claims.user_id == uid
    assert claims.endpoint_id == eid
    assert claims.project_id == pid
    assert claims.port == 5173
    assert claims.exp == exp


def test_ticket_bad_sig() -> None:
    settings = Settings(secret_key="test-secret-key-for-jwt-signing-not-for-prod")
    token, _ = mint_ticket(
        user_id=uuid4(),
        endpoint_id=uuid4(),
        project_id=uuid4(),
        port=80,
        settings=settings,
    )
    with pytest.raises(PreviewTicketError):
        verify_ticket(token + "x", settings=settings)


def test_parse_preview_host() -> None:
    settings = Settings(preview_base_domain="preview.localhost:8000")
    eid = uuid4()
    assert parse_endpoint_id_from_host(f"{eid}.preview.localhost", settings=settings) == eid
    assert parse_endpoint_id_from_host(f"{eid}.preview.localhost:8000", settings=settings) == eid
    assert parse_endpoint_id_from_host("api.localhost", settings=settings) is None
    assert public_preview_url(eid, settings=settings) == f"http://{eid}.preview.localhost:8000/"


def test_public_preview_url_injects_port_for_bare_localhost() -> None:
    """Bare preview.localhost must not resolve to browser port 80."""
    eid = uuid4()
    settings = Settings(
        preview_base_domain="preview.localhost",
        preview_public_scheme="http",
    )
    assert public_preview_url(eid, settings=settings) == f"http://{eid}.preview.localhost:8000/"

    with_port = Settings(preview_base_domain="preview.localhost", preview_public_port=5173)
    assert public_preview_url(eid, settings=with_port) == f"http://{eid}.preview.localhost:5173/"

    prod = Settings(
        preview_base_domain="preview.example.com",
        preview_public_scheme="https",
    )
    assert public_preview_url(eid, settings=prod) == f"https://{eid}.preview.example.com/"


class FakeAgentClient:
    def __init__(self) -> None:
        self.sandboxes: dict[str, dict[str, Any]] = {}

    async def create_sandbox(self, **kwargs: Any) -> dict[str, Any]:
        name = kwargs["name"]
        rec = {
            "name": name,
            "status": "running",
            "image": kwargs.get("image"),
            "labels": kwargs.get("labels", {}),
            "harnesses": kwargs.get("harnesses", []),
        }
        self.sandboxes[name] = rec
        return rec

    async def get_sandbox(self, name: str) -> dict[str, Any]:
        if name not in self.sandboxes:
            raise SandboxAgentError("not found", status_code=404)
        return self.sandboxes[name]

    async def remove_sandbox(self, name: str) -> None:
        self.sandboxes.pop(name, None)

    async def list_ports(self, name: str, *, probe: bool = False) -> dict[str, Any]:
        if name not in self.sandboxes:
            raise SandboxAgentError("not found", status_code=404)
        return {
            "sandbox_name": name,
            "ports": [
                {
                    "port": 5173,
                    "address": "0.0.0.0",
                    "protocol": "tcp",
                    "process": "node",
                    "http_likely": True,
                    "label": "node :5173",
                }
            ],
        }

    async def preview_proxy_stream(
        self,
        name: str,
        *,
        port: int,
        method: str,
        path: str,
        query: str | None = None,
        headers: dict[str, str] | None = None,
        content: bytes | None = None,
    ) -> tuple[httpx.Response, httpx.AsyncClient]:
        # Build a fake httpx response via a real local ASGI is heavy; use mock Response.
        from unittest.mock import AsyncMock, MagicMock

        if name not in self.sandboxes:
            raise SandboxAgentError("not found", status_code=404)

        body = f'{{"proxied":true,"port":{port},"path":"/{path}"}}'.encode()
        resp = MagicMock()
        resp.status_code = 200
        resp.headers = httpx.Headers({"content-type": "application/json"})
        resp.aread = AsyncMock(return_value=body)
        resp.aclose = AsyncMock()
        resp.aiter_raw = MagicMock(return_value=AsyncMock())
        client = MagicMock()
        client.aclose = AsyncMock()
        return resp, client  # type: ignore[return-value]


async def _create_org(client: AsyncClient, headers: dict[str, str], slug: str) -> str:
    response = await client.post(
        "/api/v1/orgs",
        headers=headers,
        json={"name": "Preview Org", "slug": slug},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


@pytest.mark.asyncio
async def test_mint_preview_endpoint_and_host_proxy(
    client: AsyncClient,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import sandbox as sandbox_service
    from app.services import sandbox_agent_client as sac
    from app.api.v1 import preview as preview_mod

    fake = FakeAgentClient()
    monkeypatch.setattr(sandbox_service, "SandboxAgentClient", lambda *a, **k: fake)
    monkeypatch.setattr(sac, "SandboxAgentClient", lambda *a, **k: fake)
    monkeypatch.setattr(preview_mod, "SandboxAgentClient", lambda *a, **k: fake)

    get_settings.cache_clear()
    monkeypatch.setenv("SANDBOX_ENABLED", "true")
    monkeypatch.setenv("PREVIEW_ENABLED", "true")
    monkeypatch.setenv("PREVIEW_BASE_DOMAIN", "preview.localhost")
    get_settings.cache_clear()

    # Re-init settings on app by clearing cache used in handlers
    org_id = await _create_org(client, auth_headers, slug="prev-org")
    create = await client.post(
        f"/api/v1/orgs/{org_id}/projects",
        headers=auth_headers,
        json={"name": "Prev", "slug": "prev"},
    )
    assert create.status_code == 201, create.text
    project_id = create.json()["id"]

    # Mark sandbox running with a name so mint works
    from app.db.session import get_session_factory
    from app.models.project import Project
    from sqlalchemy import select

    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(select(Project).where(Project.id == UUID(project_id)))
        project = result.scalar_one()
        project.sandbox_name = "ef-prev-test"
        project.sandbox_status = "running"
        await session.commit()
        fake.sandboxes["ef-prev-test"] = {
            "name": "ef-prev-test",
            "status": "running",
            "image": "mock",
            "labels": {},
            "harnesses": [],
        }

    ports = await client.get(
        f"/api/v1/projects/{project_id}/sandbox/ports",
        headers=auth_headers,
    )
    assert ports.status_code == 200, ports.text
    assert ports.json()["ports"][0]["port"] == 5173

    mint = await client.post(
        f"/api/v1/projects/{project_id}/preview/endpoints",
        headers=auth_headers,
        json={"port": 5173},
    )
    assert mint.status_code == 200, mint.text
    body = mint.json()
    assert body["port"] == 5173
    assert body["ticket"]
    assert body["endpoint_id"] in body["url"]
    assert "preview.localhost" in body["url"]

    # Host-based proxy with ticket
    eid = body["endpoint_id"]
    proxied = await client.get(
        "/hello",
        headers={"Host": f"{eid}.preview.localhost", "Cookie": f"ef_preview_auth={body['ticket']}"},
    )
    # ticket via query also
    proxied_q = await client.get(
        f"/hello?ticket={body['ticket']}",
        headers={"Host": f"{eid}.preview.localhost"},
    )
    assert proxied.status_code == 200 or proxied_q.status_code == 200, (
        proxied.text,
        proxied_q.text,
    )
    ok = proxied if proxied.status_code == 200 else proxied_q
    assert ok.json()["proxied"] is True
    assert ok.json()["port"] == 5173

    # No ticket still allowed (capability Host) — iframe subresources cannot send cookies
    client.cookies.clear()
    no_ticket = await client.get(
        "/",
        headers={"Host": f"{eid}.preview.localhost"},
    )
    assert no_ticket.status_code == 200, no_ticket.text

    # Wrong ticket must still fail closed
    bad = await client.get(
        "/?ticket=not-a-valid-ticket",
        headers={"Host": f"{eid}.preview.localhost"},
    )
    assert bad.status_code in (401, 403), bad.text

    # Unknown host → 404
    missing = await client.get(
        "/",
        headers={"Host": f"{uuid4()}.preview.localhost"},
    )
    assert missing.status_code == 404, missing.text

    get_settings.cache_clear()
