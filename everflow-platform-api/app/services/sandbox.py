"""Project-oriented sandbox provisioning via sandbox-agent."""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import Settings, get_settings
from app.models.project import Project
from app.services.sandbox_agent_client import SandboxAgentClient, SandboxAgentError

logger = logging.getLogger(__name__)


SANDBOX_STATUSES = (
    "pending",
    "creating",
    "running",
    "stopped",
    "error",
    "destroyed",
)

# Microsandbox / runtime statuses that mean the VM is unusable and needs recreate.
DEAD_AGENT_STATUSES = frozenset(
    {
        "crashed",
        "error",
        "destroyed",
        "unknown",
        "exited",
        "failed",
        "dead",
    }
)

# Graceful shutdown in progress — do not mark dead; wait for stopped/crashed/running.
TRANSITIONAL_AGENT_STATUSES = frozenset({"draining"})

MISSING_ON_AGENT = "Sandbox not found on agent; recreate to restore"
DEAD_ON_AGENT = "Sandbox is not running on agent; recreate to restore"

# Short TTL so OpenCode/tab-bar storms reuse the last successful running refresh.
_REFRESH_TTL_S = 2.5
# project_id -> (monotonic_ts, db_status, agent_info)
_refresh_cache: dict[UUID, tuple[float, str, dict[str, Any] | None]] = {}


def sandbox_not_running_detail(project: Project) -> str:
    """409 detail for chat/API gates — include stored reason, not just status=error."""
    status = (project.sandbox_status or "unknown").strip() or "unknown"
    base = f"Sandbox is not running (status={status})"
    err = (project.sandbox_error or "").strip()
    if not err or err.lower() == base.lower():
        return base
    if base.lower() in err.lower():
        return err[:2000]
    return f"{base}: {err}"[:2000]


def normalize_harness_ids(raw: list[Any] | None) -> list[str]:
    """Accept string ids or {id, enabled?} dicts; return unique enabled ids."""
    if not raw:
        return []
    out: list[str] = []
    for item in raw:
        if isinstance(item, str):
            s = item.strip()
            if s:
                out.append(s)
            continue
        if isinstance(item, dict):
            if item.get("enabled", True) is False:
                continue
            hid = item.get("id")
            if isinstance(hid, str) and hid.strip():
                out.append(hid.strip())
    return list(dict.fromkeys(out))


def harness_ids_for_project(project: Project, settings: Settings) -> list[str]:
    """Project harness selection, falling back to platform defaults."""
    ids = normalize_harness_ids(project.harnesses)
    if ids:
        return ids
    return list(settings.sandbox_default_harnesses)


def make_sandbox_name(org_slug: str, project_slug: str) -> str:
    """Deterministic microsandbox name ≤128 bytes."""
    raw = f"ef-{org_slug}-{project_slug}".lower()
    cleaned = re.sub(r"[^a-z0-9-]+", "-", raw)
    cleaned = re.sub(r"-+", "-", cleaned).strip("-")
    if len(cleaned) > 128:
        cleaned = cleaned[:128].rstrip("-")
    return cleaned or "ef-project"


def normalize_agent_status(live: str | None, *, fallback: str | None = None) -> str:
    """Map agent/runtime status strings into platform sandbox statuses."""
    raw = (live or "").strip().lower()
    if not raw:
        return (fallback or "unknown").strip().lower() or "unknown"
    if raw in TRANSITIONAL_AGENT_STATUSES:
        # Keep prior platform status (caller should not demote on draining).
        return (fallback or "running").strip().lower() or "running"
    if raw in DEAD_AGENT_STATUSES:
        return "error"
    if raw in SANDBOX_STATUSES:
        return raw
    # Any other non-canonical value is treated as unhealthy so UI can recreate.
    return "error"


def clear_sandbox_refresh_cache(project_id: UUID | None = None) -> None:
    """Drop refresh TTL cache (tests / after recreate)."""
    if project_id is None:
        _refresh_cache.clear()
    else:
        _refresh_cache.pop(project_id, None)


async def provision_project_sandbox(
    session: AsyncSession,
    project_id: UUID,
    *,
    settings: Settings | None = None,
    client: SandboxAgentClient | None = None,
    force: bool = False,
) -> Project:
    """Create (or force-recreate) the project's sandbox on the agent."""
    settings = settings or get_settings()
    if not settings.sandbox_enabled:
        project = await _load_project(session, project_id)
        project.sandbox_status = "destroyed"
        project.sandbox_error = "Sandbox provisioning disabled"
        await session.commit()
        await session.refresh(project)
        return project

    client = client or SandboxAgentClient(settings)
    project = await _load_project(session, project_id, with_org=True)
    org = project.organization
    name = project.sandbox_name or make_sandbox_name(org.slug, project.slug)

    project.sandbox_name = name
    project.sandbox_status = "creating"
    project.sandbox_error = None
    project.sandbox_image = settings.sandbox_default_image
    clear_sandbox_refresh_cache(project_id)
    await session.commit()

    if force and name:
        try:
            await client.stop_sandbox(name)
        except SandboxAgentError:
            pass
        try:
            await client.remove_sandbox(name)
        except SandboxAgentError:
            pass
        try:
            from app.services.preview_endpoints import revoke_endpoints_for_sandbox

            await revoke_endpoints_for_sandbox(
                session, project_id=project.id, sandbox_name=name
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("preview endpoint revoke on force: %s", exc)

    try:
        await client.create_sandbox(
            name=name,
            image=settings.sandbox_default_image,
            cpus=settings.sandbox_default_cpus,
            memory_mib=settings.sandbox_default_memory_mib,
            labels={
                "everflow.project_id": str(project.id),
                "everflow.org_id": str(project.organization_id),
                "everflow.project_slug": project.slug,
            },
            harnesses=harness_ids_for_project(project, settings),
            workspace_host_path=f"/workspaces/{name}",
            replace=True,
        )
        project.sandbox_status = "running"
        project.sandbox_created_at = datetime.now(timezone.utc)
        project.sandbox_error = None
    except SandboxAgentError as exc:
        logger.exception("sandbox provision failed project=%s", project_id)
        project.sandbox_status = "error"
        project.sandbox_error = str(exc)[:2000]
    except Exception as exc:  # noqa: BLE001
        logger.exception("sandbox provision unexpected error project=%s", project_id)
        project.sandbox_status = "error"
        project.sandbox_error = str(exc)[:2000]

    await session.commit()
    await session.refresh(project)
    return project


async def recreate_project_sandbox(
    session: AsyncSession,
    project_id: UUID,
    *,
    settings: Settings | None = None,
    client: SandboxAgentClient | None = None,
) -> Project:
    """Force remove (if any) then provision again. Workspace path is preserved."""
    return await provision_project_sandbox(
        session,
        project_id,
        settings=settings,
        client=client,
        force=True,
    )


async def reconfigure_project_sandbox(
    session: AsyncSession,
    project: Project,
    *,
    settings: Settings | None = None,
    client: SandboxAgentClient | None = None,
    force_recreate: bool = False,
    previous_harness_ids: list[str] | None = None,
) -> tuple[Project, str]:
    """Apply current project harnesses to the sandbox.

    Returns (project, mode) where mode is ``bootstrap`` or ``recreate``.

    - Running sandbox + only additions → in-place bootstrap
    - Removals, force_recreate, or non-running → full recreate (async caller)
    """
    settings = settings or get_settings()
    if not settings.sandbox_enabled:
        raise SandboxAgentError("Sandbox disabled", status_code=503)

    desired = harness_ids_for_project(project, settings)
    prev = list(previous_harness_ids or [])
    removed = bool(set(prev) - set(desired)) if prev else False
    needs_recreate = (
        force_recreate
        or removed
        or project.sandbox_status != "running"
        or not project.sandbox_name
    )

    if needs_recreate:
        return project, "recreate"

    client = client or SandboxAgentClient(settings)
    name = project.sandbox_name
    assert name  # guarded by needs_recreate
    try:
        await client.bootstrap(name, desired)
    except SandboxAgentError as exc:
        if exc.status_code == 404:
            await mark_sandbox_missing(session, project)
            return project, "recreate"
        raise
    project.sandbox_error = None
    await session.commit()
    await session.refresh(project)
    return project, "bootstrap"


async def destroy_project_sandbox(
    session: AsyncSession,
    project: Project,
    *,
    settings: Settings | None = None,
    client: SandboxAgentClient | None = None,
) -> None:
    settings = settings or get_settings()
    if not settings.sandbox_enabled or not project.sandbox_name:
        project.sandbox_status = "destroyed"
        await session.commit()
        return

    client = client or SandboxAgentClient(settings)
    try:
        try:
            await client.stop_sandbox(project.sandbox_name)
        except SandboxAgentError:
            pass
        await client.remove_sandbox(project.sandbox_name)
        project.sandbox_status = "destroyed"
        project.sandbox_error = None
    except SandboxAgentError as exc:
        logger.warning("sandbox destroy failed name=%s: %s", project.sandbox_name, exc)
        project.sandbox_status = "error"
        project.sandbox_error = f"destroy failed: {exc}"[:2000]
    try:
        from app.services.sandbox_tokens import revoke_tokens_for_project

        await revoke_tokens_for_project(session, project.id)
    except Exception as exc:  # noqa: BLE001
        logger.debug("sandbox token revoke on destroy: %s", exc)
    await session.commit()


async def mark_sandbox_missing(
    session: AsyncSession,
    project: Project,
    *,
    message: str = MISSING_ON_AGENT,
) -> Project:
    project.sandbox_status = "error"
    project.sandbox_error = message[:2000]
    try:
        from app.services.preview_endpoints import revoke_endpoints_for_sandbox

        await revoke_endpoints_for_sandbox(
            session,
            project_id=project.id,
            sandbox_name=project.sandbox_name,
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("preview endpoint revoke on missing: %s", exc)
    await session.commit()
    await session.refresh(project)
    return project


async def mark_sandbox_dead(
    session: AsyncSession,
    project: Project,
    *,
    live_status: str,
    message: str | None = None,
) -> Project:
    """Mark a sandbox unusable so clients recreate instead of polling forever."""
    project.sandbox_status = "error"
    project.sandbox_error = (message or f"{DEAD_ON_AGENT} (status={live_status})")[:2000]
    try:
        from app.services.preview_endpoints import revoke_endpoints_for_sandbox

        await revoke_endpoints_for_sandbox(
            session,
            project_id=project.id,
            sandbox_name=project.sandbox_name,
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("preview endpoint revoke on dead: %s", exc)
    await session.commit()
    await session.refresh(project)
    return project


async def refresh_sandbox_status(
    session: AsyncSession,
    project: Project,
    *,
    settings: Settings | None = None,
    client: SandboxAgentClient | None = None,
    force: bool = False,
) -> tuple[Project, dict[str, Any] | None]:
    """Sync project.sandbox_status from the agent.

    Returns ``(project, agent_info)`` so callers need not fetch status twice.

    - ``destroyed`` is left alone (intentional).
    - ``pending`` / ``creating``: adopt ``running`` if the agent already has the VM
      (unblocks UI when provision commit lags); do not demote on 404/crash mid-create.
    - ``draining`` is transitional: keep prior DB status (do not mark dead).
    - Otherwise map dead agent states (``crashed``, etc.) to ``error`` so the UI
      auto-recreates instead of polling forever.
    - When DB status is ``running`` and a recent refresh succeeded, skip the agent
      round-trip unless ``force=True``.
    """
    settings = settings or get_settings()
    if not settings.sandbox_enabled or not project.sandbox_name:
        return project, None
    if project.sandbox_status == "destroyed":
        return project, None

    if (
        not force
        and project.sandbox_status == "running"
        and project.id in _refresh_cache
    ):
        ts, cached_status, cached_info = _refresh_cache[project.id]
        if cached_status == "running" and (time.monotonic() - ts) < _REFRESH_TTL_S:
            return project, cached_info

    client = client or SandboxAgentClient(settings)
    creating = project.sandbox_status in ("pending", "creating")
    info: dict[str, Any] | None = None
    try:
        info = await client.get_sandbox(project.sandbox_name)
        live_raw = str(info.get("status") or "").strip()
        live_raw_l = live_raw.lower()

        if live_raw_l in TRANSITIONAL_AGENT_STATUSES:
            # Mid-drain: do not poison DB; UI/OpenCode keep using prior status.
            logger.info(
                "sandbox transitional status project=%s name=%s live=%s keeping=%s",
                project.id,
                project.sandbox_name,
                live_raw,
                project.sandbox_status,
            )
            return project, info

        live = normalize_agent_status(live_raw, fallback=project.sandbox_status)

        if creating:
            # Only promote to running while create is in flight; never demote mid-create.
            if live == "running":
                project.sandbox_status = "running"
                project.sandbox_error = None
                await session.commit()
                await session.refresh(project)
                _refresh_cache[project.id] = (time.monotonic(), "running", info)
            return project, info

        if live == "running":
            project.sandbox_status = "running"
            project.sandbox_error = None
        elif live == "stopped":
            project.sandbox_status = "stopped"
            project.sandbox_error = None
            _refresh_cache.pop(project.id, None)
        elif live == "error" or live_raw_l in DEAD_AGENT_STATUSES:
            _refresh_cache.pop(project.id, None)
            project = await mark_sandbox_dead(
                session,
                project,
                live_status=live_raw or live,
            )
            return project, info
        elif live in SANDBOX_STATUSES:
            project.sandbox_status = live
        else:
            _refresh_cache.pop(project.id, None)
            project = await mark_sandbox_dead(
                session,
                project,
                live_status=live_raw or live,
            )
            return project, info

        await session.commit()
        await session.refresh(project)
        if project.sandbox_status == "running":
            _refresh_cache[project.id] = (time.monotonic(), "running", info)
    except SandboxAgentError as exc:
        if exc.status_code == 404:
            if creating:
                # Create still in progress — name may not be registered yet.
                return project, None
            # DB out of sync with agent (restart, wipe, manual delete)
            _refresh_cache.pop(project.id, None)
            project = await mark_sandbox_missing(session, project)
            return project, None
        # Agent unreachable: keep DB status (avoid false recreate loops)
    return project, info


async def _load_project(
    session: AsyncSession,
    project_id: UUID,
    *,
    with_org: bool = False,
) -> Project:
    stmt = select(Project).where(Project.id == project_id)
    if with_org:
        stmt = stmt.options(selectinload(Project.organization))
    result = await session.execute(stmt)
    project = result.scalar_one()
    return project
