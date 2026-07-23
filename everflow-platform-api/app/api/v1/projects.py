"""Project CRUD under organizations."""

import logging
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth.users import current_active_user
from app.config import Settings, get_settings
from app.core.deps import get_org_membership, get_project_for_member
from app.db.session import get_async_session, get_session_factory
from app.models.organization import Organization, OrganizationMember
from app.models.project import Project
from app.models.user import User
from app.schemas.project import ProjectCreate, ProjectRead, ProjectUpdate
from app.services.repo_clone import clone_project_repos, repos_to_storage
from app.services.sandbox import (
    destroy_project_sandbox,
    make_sandbox_name,
    normalize_harness_ids,
    provision_project_sandbox,
    reconfigure_project_sandbox,
)
from app.services.sandbox_agent_client import SandboxAgentClient, SandboxAgentError

logger = logging.getLogger(__name__)

router = APIRouter(tags=["projects"])


async def _require_project_admin(
    project: Project,
    user: User,
    session: AsyncSession,
) -> OrganizationMember:
    result = await session.execute(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == project.organization_id,
            OrganizationMember.user_id == user.id,
        )
    )
    membership = result.scalar_one_or_none()
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not a member of this organization",
        )
    if membership.role not in ("owner", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin or owner role required",
        )
    return membership


async def _clone_repos_for_project(session: AsyncSession, project: Project, settings: Settings) -> Project:
    """Clone stored remotes into the running sandbox and persist status on project.repos."""
    repos = list(project.repos or [])
    if not repos or not project.sandbox_name or project.sandbox_status != "running":
        return project
    # Clone when any remote is not yet ready/skipped (pending, error, cloning, or unset)
    needs = any(
        isinstance(r, dict) and r.get("url") and r.get("clone_status") not in ("ready", "skipped")
        for r in repos
    )
    if not needs:
        return project

    client = SandboxAgentClient(settings)
    try:
        updated = await clone_project_repos(client, project.sandbox_name, repos)
        project.repos = updated
        await session.commit()
        await session.refresh(project)
    except SandboxAgentError as exc:
        logger.warning("repo clone agent error project=%s: %s", project.id, exc)
        # Mark pending clones as error without failing sandbox
        marked: list[dict] = []
        for r in repos:
            if not isinstance(r, dict):
                continue
            item = dict(r)
            if item.get("url") and item.get("clone_status") not in ("ready", "skipped"):
                item["clone_status"] = "error"
                item["clone_error"] = str(exc)[:1500]
            marked.append(item)
        project.repos = marked
        await session.commit()
        await session.refresh(project)
    except Exception as exc:  # noqa: BLE001
        logger.exception("repo clone failed project=%s", project.id)
        marked = []
        for r in repos:
            if not isinstance(r, dict):
                continue
            item = dict(r)
            if item.get("url") and item.get("clone_status") not in ("ready", "skipped"):
                item["clone_status"] = "error"
                item["clone_error"] = str(exc)[:1500]
            marked.append(item)
        project.repos = marked
        await session.commit()
        await session.refresh(project)
    return project


async def _bg_provision(project_id: UUID) -> None:
    """Background task: provision sandbox, then clone project repos into workspace."""
    settings = get_settings()
    factory = get_session_factory()
    async with factory() as session:
        project = await provision_project_sandbox(session, project_id, settings=settings)
        if project.sandbox_status == "running":
            await _clone_repos_for_project(session, project, settings)


@router.get("/orgs/{org_id}/projects", response_model=list[ProjectRead])
async def list_projects(
    org_id: UUID,
    _: OrganizationMember = Depends(get_org_membership),
    session: AsyncSession = Depends(get_async_session),
) -> list[Project]:
    result = await session.execute(
        select(Project).where(Project.organization_id == org_id).order_by(Project.name)
    )
    return list(result.scalars().all())


@router.post(
    "/orgs/{org_id}/projects",
    response_model=ProjectRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_project(
    org_id: UUID,
    body: ProjectCreate,
    background_tasks: BackgroundTasks,
    _: OrganizationMember = Depends(get_org_membership),
    session: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_settings),
) -> Project:
    org_result = await session.execute(select(Organization).where(Organization.id == org_id))
    org = org_result.scalar_one()

    sandbox_name = make_sandbox_name(org.slug, body.slug) if settings.sandbox_enabled else None
    stored_repos = repos_to_storage(body.repos)
    harness_ids = normalize_harness_ids(body.harnesses)
    if not harness_ids:
        harness_ids = list(settings.sandbox_default_harnesses)
    project = Project(
        organization_id=org_id,
        name=body.name,
        slug=body.slug,
        description=body.description,
        repos=stored_repos,
        harnesses=harness_ids,
        sandbox_name=sandbox_name,
        sandbox_status="pending" if settings.sandbox_enabled else "destroyed",
        sandbox_image=settings.sandbox_default_image if settings.sandbox_enabled else None,
    )
    session.add(project)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project slug already exists in this organization",
        ) from None
    await session.refresh(project)

    if settings.sandbox_enabled:
        background_tasks.add_task(_bg_provision, project.id)

    return project


@router.get("/projects/{project_id}", response_model=ProjectRead)
async def get_project(
    project: Project = Depends(get_project_for_member),
) -> Project:
    return project


@router.patch("/projects/{project_id}", response_model=ProjectRead)
async def update_project(
    body: ProjectUpdate,
    background_tasks: BackgroundTasks,
    project: Project = Depends(get_project_for_member),
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_settings),
) -> Project:
    # Name/slug changes require admin; description alone is fine for any member.
    if body.name is not None or body.slug is not None:
        await _require_project_admin(project, user, session)

    prev_harnesses = normalize_harness_ids(project.harnesses)
    harnesses_changed = False

    if body.name is not None:
        project.name = body.name
    if body.slug is not None:
        project.slug = body.slug
    if body.description is not None:
        project.description = body.description
    if body.repos is not None:
        project.repos = repos_to_storage(body.repos)
    if body.harnesses is not None:
        new_ids = normalize_harness_ids(body.harnesses)
        project.harnesses = new_ids
        harnesses_changed = new_ids != prev_harnesses

    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project slug already exists in this organization",
        ) from None
    await session.refresh(project)

    # Default: reconfigure when harnesses change unless the client opts out.
    should_reconfigure = harnesses_changed and body.reconfigure_sandbox is not False
    if should_reconfigure and settings.sandbox_enabled:
        from app.api.v1.sandbox import _bg_recreate

        try:
            project, mode = await reconfigure_project_sandbox(
                session,
                project,
                settings=settings,
                previous_harness_ids=prev_harnesses,
            )
        except SandboxAgentError as exc:
            logger.warning(
                "sandbox reconfigure after harness update failed project=%s: %s",
                project.id,
                exc,
            )
        else:
            if mode == "recreate":
                project.sandbox_status = "pending"
                project.sandbox_error = None
                if project.repos:
                    reset = []
                    for r in project.repos:
                        if not isinstance(r, dict):
                            continue
                        item = dict(r)
                        if item.get("url"):
                            item["clone_status"] = "pending"
                            item["clone_error"] = None
                        reset.append(item)
                    project.repos = reset
                await session.commit()
                await session.refresh(project)
                background_tasks.add_task(_bg_recreate, project.id)

    return project


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project: Project = Depends(get_project_for_member),
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_settings),
) -> None:
    await _require_project_admin(project, user, session)

    # Load with org if needed — destroy uses sandbox_name only
    await destroy_project_sandbox(session, project, settings=settings)

    # Re-fetch after destroy commit (session may have committed)
    result = await session.execute(select(Project).where(Project.id == project.id))
    project = result.scalar_one_or_none()
    if project is not None:
        await session.delete(project)
        await session.commit()
