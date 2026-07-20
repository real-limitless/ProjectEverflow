"""Shared FastAPI dependencies for org membership checks."""

from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.users import current_active_user
from app.db.session import get_async_session
from app.models.organization import Organization, OrganizationMember
from app.models.project import Project
from app.models.user import User


async def get_org_membership(
    org_id: UUID,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> OrganizationMember:
    result = await session.execute(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == org_id,
            OrganizationMember.user_id == user.id,
        )
    )
    membership = result.scalar_one_or_none()
    if membership is None:
        # Hide existence of orgs the user cannot see
        exists = await session.get(Organization, org_id)
        if exists is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a member of this organization")
    return membership


async def require_org_admin(
    membership: OrganizationMember = Depends(get_org_membership),
) -> OrganizationMember:
    if membership.role not in ("owner", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin or owner role required",
        )
    return membership


async def require_org_owner(
    membership: OrganizationMember = Depends(get_org_membership),
) -> OrganizationMember:
    if membership.role != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Owner role required",
        )
    return membership


async def get_project_for_member(
    project_id: UUID,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> Project:
    result = await session.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    mem = await session.execute(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == project.organization_id,
            OrganizationMember.user_id == user.id,
        )
    )
    if mem.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a member of this organization")
    return project
