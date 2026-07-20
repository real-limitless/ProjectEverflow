"""Project CRUD under organizations."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.users import current_active_user
from app.core.deps import get_org_membership, get_project_for_member
from app.db.session import get_async_session
from app.models.organization import OrganizationMember
from app.models.project import Project
from app.models.user import User
from app.schemas.project import ProjectCreate, ProjectRead, ProjectUpdate

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
    _: OrganizationMember = Depends(get_org_membership),
    session: AsyncSession = Depends(get_async_session),
) -> Project:
    project = Project(
        organization_id=org_id,
        name=body.name,
        slug=body.slug,
        description=body.description,
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
    return project


@router.get("/projects/{project_id}", response_model=ProjectRead)
async def get_project(
    project: Project = Depends(get_project_for_member),
) -> Project:
    return project


@router.patch("/projects/{project_id}", response_model=ProjectRead)
async def update_project(
    body: ProjectUpdate,
    project: Project = Depends(get_project_for_member),
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> Project:
    # Name/slug changes require admin; description alone is fine for any member.
    if body.name is not None or body.slug is not None:
        await _require_project_admin(project, user, session)

    if body.name is not None:
        project.name = body.name
    if body.slug is not None:
        project.slug = body.slug
    if body.description is not None:
        project.description = body.description

    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project slug already exists in this organization",
        ) from None
    await session.refresh(project)
    return project


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project: Project = Depends(get_project_for_member),
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> None:
    await _require_project_admin(project, user, session)
    await session.delete(project)
    await session.commit()
