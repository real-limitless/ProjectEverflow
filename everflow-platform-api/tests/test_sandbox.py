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
        self.create_calls: list[dict[str, Any]] = []

    async def health(self) -> dict[str, Any]:
        return {"status": "ok", "kvm": False, "sdk": "mock", "mock": True}

    async def create_sandbox(self, **kwargs: Any) -> dict[str, Any]:
        self.create_calls.append(kwargs)
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

    async def inject_provider_secrets(
        self,
        name: str,
        *,
        env: dict[str, str] | None = None,
        providers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        if name not in self.sandboxes:
            raise SandboxAgentError("not found", status_code=404)
        return {
            "sandbox_name": name,
            "written": True,
            "env_keys": sorted((env or {}).keys()),
            "opencode_providers": sorted((providers or {}).keys()),
            "path": ".everflow/secrets/providers.env",
        }

    async def opencode_set_auth(self, name: str, provider_id: str, api_key: str) -> Any:
        if name not in self.sandboxes:
            raise SandboxAgentError("not found", status_code=404)
        return True

    async def opencode_ensure(self, name: str, **kwargs: Any) -> dict[str, Any]:
        if name not in self.sandboxes:
            raise SandboxAgentError("not found", status_code=404)
        return {
            "sandbox_name": name,
            "healthy": True,
            "port": 14100,
            "base_url": "http://127.0.0.1:14100",
            "version": "fake-0.0.1",
            "mode": "host",
        }


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
        # Platform still requests default harnesses; agent installs them off the critical path
        assert fake.create_calls, "create_sandbox should have been called"
        assert "agent-claude-code" in fake.create_calls[0].get("harnesses", [])

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

    monkeypatch.setattr("app.api.v1.opencode.SandboxAgentClient", lambda settings=None: fake)
    oc = await client.post(
        f"/api/v1/projects/{project_id}/opencode/ensure",
        headers=auth_headers,
        json={},
    )
    assert oc.status_code == 200, oc.text
    assert oc.json()["healthy"] is True


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

        refreshed, _ = await sandbox_service.refresh_sandbox_status(
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


def test_normalize_agent_status() -> None:
    assert sandbox_service.normalize_agent_status("running") == "running"
    assert sandbox_service.normalize_agent_status("stopped") == "stopped"
    assert sandbox_service.normalize_agent_status("crashed") == "error"
    assert sandbox_service.normalize_agent_status("exited") == "error"
    assert sandbox_service.normalize_agent_status("failed") == "error"
    assert sandbox_service.normalize_agent_status("weird-state") == "error"
    assert sandbox_service.normalize_agent_status(None, fallback="running") == "running"
    # draining is transitional — keep fallback, do not map to error
    assert sandbox_service.normalize_agent_status("draining", fallback="running") == "running"


@pytest.mark.asyncio
async def test_refresh_keeps_running_on_draining(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    """Transitional draining must not mark the project error."""
    fake = FakeAgentClient()
    org_id = await _create_org(client, auth_headers, slug="sbx-drain")
    create = await client.post(
        f"/api/v1/orgs/{org_id}/projects",
        headers=auth_headers,
        json={"name": "Drainy", "slug": "drainy"},
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
        assert name is not None
        fake.sandboxes[name]["status"] = "draining"
        sandbox_service.clear_sandbox_refresh_cache()

        refreshed, info = await sandbox_service.refresh_sandbox_status(
            session,
            await sandbox_service._load_project(session, project_id),
            settings=settings,
            client=fake,  # type: ignore[arg-type]
            force=True,
        )
        assert refreshed.sandbox_status == "running"
        assert refreshed.sandbox_error is None
        assert info is not None
        assert str(info.get("status")).lower() == "draining"


@pytest.mark.asyncio
async def test_refresh_maps_crashed_to_error(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    fake = FakeAgentClient()
    org_id = await _create_org(client, auth_headers, slug="sbx-crash")
    create = await client.post(
        f"/api/v1/orgs/{org_id}/projects",
        headers=auth_headers,
        json={"name": "Crashy", "slug": "crashy"},
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
        assert name is not None
        # Simulate agent restart leaving a dead microVM record
        fake.sandboxes[name]["status"] = "crashed"

        refreshed, _ = await sandbox_service.refresh_sandbox_status(
            session,
            await sandbox_service._load_project(session, project_id),
            settings=settings,
            client=fake,  # type: ignore[arg-type]
        )
        assert refreshed.sandbox_status == "error"
        assert "not running" in (refreshed.sandbox_error or "").lower() or "crashed" in (
            refreshed.sandbox_error or ""
        ).lower()


@pytest.mark.asyncio
async def test_refresh_heals_stale_error_when_agent_running(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    """Stale DB error must not stick when the agent still reports running (chat gate)."""
    fake = FakeAgentClient()
    org_id = await _create_org(client, auth_headers, slug="sbx-heal-err")
    create = await client.post(
        f"/api/v1/orgs/{org_id}/projects",
        headers=auth_headers,
        json={"name": "HealErr", "slug": "heal-err"},
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
        name = sandbox_service.make_sandbox_name(proj.organization.slug, proj.slug)
        proj.sandbox_name = name
        proj.sandbox_status = "error"
        proj.sandbox_error = "Sandbox is not running (status=error)"
        await session.commit()
        fake.sandboxes[name] = {
            "name": name,
            "status": "running",
            "image": "img",
            "labels": {},
            "harnesses": [],
        }

        healed, _ = await sandbox_service.refresh_sandbox_status(
            session,
            await sandbox_service._load_project(session, project_id),
            settings=settings,
            client=fake,  # type: ignore[arg-type]
        )
        assert healed.sandbox_status == "running"
        assert healed.sandbox_error is None


@pytest.mark.asyncio
async def test_refresh_creating_adopts_running_keeps_404(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    fake = FakeAgentClient()
    org_id = await _create_org(client, auth_headers, slug="sbx-create-sync")
    create = await client.post(
        f"/api/v1/orgs/{org_id}/projects",
        headers=auth_headers,
        json={"name": "Creating", "slug": "creating-box"},
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
        name = sandbox_service.make_sandbox_name(proj.organization.slug, proj.slug)
        proj.sandbox_name = name
        proj.sandbox_status = "creating"
        await session.commit()

        # 404 while creating → stay creating (not mark missing)
        missing, _ = await sandbox_service.refresh_sandbox_status(
            session,
            await sandbox_service._load_project(session, project_id),
            settings=settings,
            client=fake,  # type: ignore[arg-type]
        )
        assert missing.sandbox_status == "creating"

        # Agent already running → promote so UI unblocks if provision commit lags
        fake.sandboxes[name] = {
            "name": name,
            "status": "running",
            "image": "img",
            "labels": {},
            "harnesses": [],
        }
        promoted, _ = await sandbox_service.refresh_sandbox_status(
            session,
            await sandbox_service._load_project(session, project_id),
            settings=settings,
            client=fake,  # type: ignore[arg-type]
        )
        assert promoted.sandbox_status == "running"


@pytest.mark.asyncio
async def test_fs_path_not_found_is_404_not_sandbox_missing(
    client: AsyncClient,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing guest files must not mark the sandbox dead (chat worktree index)."""
    org_id = await _create_org(client, auth_headers, slug="fs-path-org")
    create = await client.post(
        f"/api/v1/orgs/{org_id}/projects",
        headers=auth_headers,
        json={"name": "FS Path", "slug": "fs-path"},
    )
    assert create.status_code == 201, create.text
    project_id = create.json()["id"]

    fake = FakeAgentClient()
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
        proj = await sandbox_service._load_project(session, UUID(project_id), with_org=True)
        if not proj.sandbox_name:
            proj.sandbox_name = sandbox_service.make_sandbox_name(
                proj.organization.slug,
                proj.slug,
            )
            await session.commit()
        await sandbox_service.provision_project_sandbox(
            session,
            UUID(project_id),
            settings=settings,
            client=fake,  # type: ignore[arg-type]
        )

    async def path_missing(_name: str, path: str) -> str:
        raise SandboxAgentError(f"Path not found: {path}", status_code=404)

    fake.read_fs = path_missing  # type: ignore[method-assign]
    monkeypatch.setattr("app.api.v1.sandbox.SandboxAgentClient", lambda settings=None: fake)
    monkeypatch.setattr("app.services.sandbox.SandboxAgentClient", lambda settings=None: fake)

    missing_file = await client.get(
        f"/api/v1/projects/{project_id}/sandbox/fs/content",
        headers=auth_headers,
        params={"path": ".everflow/worktrees/index.json"},
    )
    assert missing_file.status_code == 404, missing_file.text

    status = await client.get(f"/api/v1/projects/{project_id}/sandbox", headers=auth_headers)
    assert status.status_code == 200
    assert status.json()["status"] == "running"

    async def sandbox_gone(_name: str, _path: str) -> str:
        raise SandboxAgentError("Sandbox not found", status_code=404)

    fake.read_fs = sandbox_gone  # type: ignore[method-assign]
    gone = await client.get(
        f"/api/v1/projects/{project_id}/sandbox/fs/content",
        headers=auth_headers,
        params={"path": "README.md"},
    )
    assert gone.status_code == 409, gone.text
    assert "not found on agent" in gone.json()["detail"].lower()
