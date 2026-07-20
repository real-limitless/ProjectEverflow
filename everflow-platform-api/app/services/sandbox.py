"""Project-oriented sandbox provisioning via sandbox-agent."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
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

MISSING_ON_AGENT = "Sandbox not found on agent; recreate to restore"


def make_sandbox_name(org_slug: str, project_slug: str) -> str:
    """Deterministic microsandbox name ≤128 bytes."""
    raw = f"ef-{org_slug}-{project_slug}".lower()
    cleaned = re.sub(r"[^a-z0-9-]+", "-", raw)
    cleaned = re.sub(r"-+", "-", cleaned).strip("-")
    if len(cleaned) > 128:
        cleaned = cleaned[:128].rstrip("-")
    return cleaned or "ef-project"


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
            harnesses=list(settings.sandbox_default_harnesses),
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
    await session.commit()


async def mark_sandbox_missing(
    session: AsyncSession,
    project: Project,
    *,
    message: str = MISSING_ON_AGENT,
) -> Project:
    project.sandbox_status = "error"
    project.sandbox_error = message[:2000]
    await session.commit()
    await session.refresh(project)
    return project


async def refresh_sandbox_status(
    session: AsyncSession,
    project: Project,
    *,
    settings: Settings | None = None,
    client: SandboxAgentClient | None = None,
) -> Project:
    settings = settings or get_settings()
    if not settings.sandbox_enabled or not project.sandbox_name:
        return project
    if project.sandbox_status in ("pending", "creating", "destroyed"):
        return project

    client = client or SandboxAgentClient(settings)
    try:
        info = await client.get_sandbox(project.sandbox_name)
        live = str(info.get("status") or project.sandbox_status)
        if live in SANDBOX_STATUSES:
            project.sandbox_status = live
        elif live not in ("unknown",):
            project.sandbox_status = live if live else project.sandbox_status
        if project.sandbox_status == "running":
            project.sandbox_error = None
        await session.commit()
        await session.refresh(project)
    except SandboxAgentError as exc:
        if exc.status_code == 404:
            # DB out of sync with agent (restart, wipe, manual delete)
            await mark_sandbox_missing(session, project)
        # Agent unreachable: keep DB status (avoid false recreate loops)
    return project


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
