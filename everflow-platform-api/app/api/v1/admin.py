"""Thin platform admin (superuser) endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.users import current_superuser
from app.db.session import get_async_session
from app.models.organization import Organization, OrganizationMember
from app.models.user import User
from app.schemas.admin import AdminOrgRead, AdminUserRead

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users", response_model=list[AdminUserRead])
async def list_users(
    _: User = Depends(current_superuser),
    session: AsyncSession = Depends(get_async_session),
) -> list[AdminUserRead]:
    result = await session.execute(select(User).order_by(User.email.asc()))
    # User.oauth_accounts uses joinedload — unique() required for collections
    return [AdminUserRead.model_validate(u) for u in result.scalars().unique().all()]


@router.patch("/users/{user_id}/deactivate", response_model=AdminUserRead)
async def deactivate_user(
    user_id: UUID,
    actor: User = Depends(current_superuser),
    session: AsyncSession = Depends(get_async_session),
) -> AdminUserRead:
    if user_id == actor.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot deactivate yourself",
        )
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    user.is_active = False
    await session.commit()
    await session.refresh(user)
    return AdminUserRead.model_validate(user)


@router.patch("/users/{user_id}/activate", response_model=AdminUserRead)
async def activate_user(
    user_id: UUID,
    _: User = Depends(current_superuser),
    session: AsyncSession = Depends(get_async_session),
) -> AdminUserRead:
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    user.is_active = True
    await session.commit()
    await session.refresh(user)
    return AdminUserRead.model_validate(user)


@router.get("/orgs", response_model=list[AdminOrgRead])
async def list_all_orgs(
    _: User = Depends(current_superuser),
    session: AsyncSession = Depends(get_async_session),
) -> list[AdminOrgRead]:
    result = await session.execute(
        select(Organization)
        .options(selectinload(Organization.members))
        .order_by(Organization.name.asc())
    )
    orgs = list(result.scalars().all())
    # Fallback count if members not loaded
    out: list[AdminOrgRead] = []
    for org in orgs:
        count = len(org.members) if org.members is not None else 0
        if count == 0:
            cresult = await session.execute(
                select(func.count())
                .select_from(OrganizationMember)
                .where(OrganizationMember.organization_id == org.id)
            )
            count = int(cresult.scalar_one())
        read = AdminOrgRead.model_validate(org)
        read.member_count = count
        out.append(read)
    return out
