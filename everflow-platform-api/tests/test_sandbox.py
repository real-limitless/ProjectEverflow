"""Sandbox provision and public API tests (mocked agent)."""

from typing import Any
from uuid import UUID

import pytest
from httpx import AsyncClient

from app.config import Settings
from app.db.session import get_session_factory
from app.services import sandbox as sandbox_service
from app.services.sandbox_agent_client import SandboxAgentError


class FakeAgentClient:
    def __init__(self) -> None:
        self.sandboxes: dict[str, dict[str, Any]] = {}
        self.removed: list[str] = []

    async def health(self) -> dict[str, Any]:
        return {"status": "ok", "kvm": False, "sdk": "mock", "mock": True}

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

    async def start_sandbox(self, name: str) -> dict[str, Any]:
        self.sandboxes[name]["status"] = "running"
        return self.sandboxes[name]

    async def stop_sandbox(self, name: str) -> dict[str, Any]:
        if name in self.sandboxes:
            self.sandboxes[name]["status"] = "stopped"
            return self.sandboxes[name]
        raise SandboxAgentError("not found", status_code=404)

    async def remove_sandbox(self, name: str) -> None:
        self.sandboxes.pop(name, None)
        self.removed.append(name)

    async def exec(self, name: str, **kwargs: Any) -> dict[str, Any]:
        if name not in self.sandboxes:
            raise SandboxAgentError("not found", status_code=404)
        cmd = kwargs.get("cmd", "")
        args = kwargs.get("args") or []
        return {"exit_code": 0, "stdout": f"{cmd} {' '.join(args)}\n", "stderr": ""}

    async def list_fs(self, name: str, path: str = ".") -> list[dict[str, Any]]:
        return [{"path": "README.md", "name": "README.md", "is_dir": False, "size": 12}]

    async def read_fs(self, name: str, path: str) -> str:
        return "# hello\n"

    async def write_fs(self, name: str, path: str, content: str) -> None:
        return None


async def _create_org(client: AsyncClient, headers: dict[str, str], slug: str = "sbx-org") -> str:
    response = await client.post(
        "/api/v1/orgs",
        headers=headers,
        json={"name": "Sandbox Org", "slug": slug},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


@pytest.mark.asyncio
async def test_create_project_includes_sandbox_fields(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    org_id = await _create_org(client, auth_headers, slug="sbx-fields")
    create = await client.post(
        f"/api/v1/orgs/{org_id}/projects",
        headers=auth_headers,
        json={"name": "Sbox", "slug": "sbox"},
    )
    assert create.status_code == 201, create.text
    project = create.json()
    assert project["sandbox_status"] == "destroyed"  # disabled in tests
    assert project["sandbox_name"] is None or project["sandbox_name"]  # may be unset when disabled


@pytest.mark.asyncio
async def test_provision_and_exec_with_fake_agent(
    client: AsyncClient,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeAgentClient()
    org_id = await _create_org(client, auth_headers, slug="sbx-prov")
    create = await client.post(
        f"/api/v1/orgs/{org_id}/projects",
        headers=auth_headers,
        json={"name": "Sbox", "slug": "sbox-run"},
    )
    assert create.status_code == 201, create.text
    project = create.json()
    project_id = UUID(project["id"])

    settings = Settings(
        environment="test",
        secret_key="test-secret-key-for-jwt-signing-not-for-prod",
        database_url="sqlite+aiosqlite:///:memory:",
        sandbox_enabled=True,
        sandbox_agent_url="http://fake",
        sandbox_agent_token="t",
    )

    factory = get_session_factory()
    async with factory() as session:
        # Ensure sandbox_name is set for provision
        proj = await sandbox_service._load_project(session, project_id, with_org=True)
        if not proj.sandbox_name:
            proj.sandbox_name = sandbox_service.make_sandbox_name(
                proj.organization.slug,
                proj.slug,
            )
            await session.commit()

        await sandbox_service.provision_project_sandbox(
            session,
            project_id,
            settings=settings,
            client=fake,  # type: ignore[arg-type]
        )
        refreshed = await sandbox_service._load_project(session, project_id)
        assert refreshed.sandbox_status == "running"
        assert refreshed.sandbox_name in fake.sandboxes

    monkeypatch.setattr("app.api.v1.sandbox.SandboxAgentClient", lambda settings=None: fake)
    monkeypatch.setattr("app.services.sandbox.SandboxAgentClient", lambda settings=None: fake)

    status = await client.get(f"/api/v1/projects/{project_id}/sandbox", headers=auth_headers)
    assert status.status_code == 200, status.text
    assert status.json()["status"] == "running"

    exe = await client.post(
        f"/api/v1/projects/{project_id}/sandbox/exec",
        headers=auth_headers,
        json={"cmd": "echo", "args": ["hi"]},
    )
    assert exe.status_code == 200, exe.text
    assert "echo" in exe.json()["stdout"]

    listing = await client.get(
        f"/api/v1/projects/{project_id}/sandbox/fs",
        headers=auth_headers,
    )
    assert listing.status_code == 200
    assert listing.json()[0]["name"] == "README.md"

    stop = await client.post(f"/api/v1/projects/{project_id}/sandbox/stop", headers=auth_headers)
    assert stop.status_code == 200
    assert stop.json()["status"] == "stopped"

    start = await client.post(f"/api/v1/projects/{project_id}/sandbox/start", headers=auth_headers)
    assert start.status_code == 200
    assert start.json()["status"] == "running"


@pytest.mark.asyncio
async def test_missing_on_agent_refresh_and_recreate(
    client: AsyncClient,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeAgentClient()
    org_id = await _create_org(client, auth_headers, slug="sbx-miss")
    create = await client.post(
        f"/api/v1/orgs/{org_id}/projects",
        headers=auth_headers,
        json={"name": "Gone", "slug": "gone-box"},
    )
    project_id = UUID(create.json()["id"])

    settings = Settings(
        environment="test",
        secret_key="test-secret-key-for-jwt-signing-not-for-prod",
        database_url="sqlite+aiosqlite:///:memory:",
        sandbox_enabled=True,
        sandbox_agent_url="http://fake",
        sandbox_agent_token="t",
    )

    factory = get_session_factory()
    async with factory() as session:
        proj = await sandbox_service._load_project(session, project_id, with_org=True)
        proj.sandbox_name = sandbox_service.make_sandbox_name(proj.organization.slug, proj.slug)
        await session.commit()
        await sandbox_service.provision_project_sandbox(
            session,
            project_id,
            settings=settings,
            client=fake,  # type: ignore[arg-type]
        )
        name = (await sandbox_service._load_project(session, project_id)).sandbox_name
        assert name in fake.sandboxes
        # Simulate agent restart / wipe
        fake.sandboxes.clear()

        refreshed = await sandbox_service.refresh_sandbox_status(
            session,
            await sandbox_service._load_project(session, project_id),
            settings=settings,
            client=fake,  # type: ignore[arg-type]
        )
        assert refreshed.sandbox_status == "error"
        assert "not found on agent" in (refreshed.sandbox_error or "").lower()

        # Recreate restores sandbox
        await sandbox_service.recreate_project_sandbox(
            session,
            project_id,
            settings=settings,
            client=fake,  # type: ignore[arg-type]
        )
        again = await sandbox_service._load_project(session, project_id)
        assert again.sandbox_status == "running"
        assert again.sandbox_name in fake.sandboxes
        assert again.sandbox_name in fake.removed  # force path called remove

    monkeypatch.setattr("app.api.v1.sandbox.SandboxAgentClient", lambda settings=None: fake)
    monkeypatch.setattr("app.services.sandbox.SandboxAgentClient", lambda settings=None: fake)

    # Exec when missing updates DB
    fake.sandboxes.clear()
    async with factory() as session:
        proj = await sandbox_service._load_project(session, project_id)
        proj.sandbox_status = "running"
        await session.commit()

    exec_missing = await client.post(
        f"/api/v1/projects/{project_id}/sandbox/exec",
        headers=auth_headers,
        json={"cmd": "echo", "args": ["x"]},
    )
    assert exec_missing.status_code == 409
    assert "recreate" in exec_missing.json()["detail"].lower()


@pytest.mark.asyncio
async def test_make_sandbox_name() -> None:
    assert sandbox_service.make_sandbox_name("Acme!", "my-app") == "ef-acme-my-app"
    long_slug = "x" * 200
    name = sandbox_service.make_sandbox_name("org", long_slug)
    assert len(name) <= 128
