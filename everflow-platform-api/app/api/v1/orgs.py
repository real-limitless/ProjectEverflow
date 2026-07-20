"""Organization CRUD."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.users import current_active_user
from app.core.deps import get_org_membership, require_org_admin, require_org_owner
from app.db.session import get_async_session
from app.models.organization import Organization, OrganizationMember
from app.models.user import User
from app.schemas.organization import OrganizationCreate, OrganizationRead, OrganizationUpdate

router = APIRouter(prefix="/orgs", tags=["organizations"])


@router.get("", response_model=list[OrganizationRead])
async def list_orgs(
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> list[OrganizationRead]:
    result = await session.execute(
        select(Organization, OrganizationMember.role)
        .join(OrganizationMember, OrganizationMember.organization_id == Organization.id)
        .where(OrganizationMember.user_id == user.id)
        .order_by(Organization.name)
    )
    items: list[OrganizationRead] = []
    for org, role in result.all():
        data = OrganizationRead.model_validate(org)
        data.role = role
        items.append(data)
    return items


@router.post("", response_model=OrganizationRead, status_code=status.HTTP_201_CREATED)
async def create_org(
    body: OrganizationCreate,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> OrganizationRead:
    org = Organization(name=body.name, slug=body.slug)
    session.add(org)
    try:
        await session.flush()
        membership = OrganizationMember(
            organization_id=org.id,
            user_id=user.id,
            role="owner",
        )
        session.add(membership)
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Organization slug already exists",
        ) from None
    await session.refresh(org)
    read = OrganizationRead.model_validate(org)
    read.role = "owner"
    return read


@router.get("/{org_id}", response_model=OrganizationRead)
async def get_org(
    org_id: UUID,
    membership: OrganizationMember = Depends(get_org_membership),
    session: AsyncSession = Depends(get_async_session),
) -> OrganizationRead:
    org = await session.get(Organization, org_id)
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    read = OrganizationRead.model_validate(org)
    read.role = membership.role
    return read


@router.patch("/{org_id}", response_model=OrganizationRead)
async def update_org(
    org_id: UUID,
    body: OrganizationUpdate,
    membership: OrganizationMember = Depends(require_org_admin),
    session: AsyncSession = Depends(get_async_session),
) -> OrganizationRead:
    org = await session.get(Organization, org_id)
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    if body.name is not None:
        org.name = body.name
    if body.slug is not None:
        org.slug = body.slug
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Organization slug already exists",
        ) from None
    await session.refresh(org)
    read = OrganizationRead.model_validate(org)
    read.role = membership.role
    return read


@router.delete("/{org_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_org(
    org_id: UUID,
    _: OrganizationMember = Depends(require_org_owner),
    session: AsyncSession = Depends(get_async_session),
) -> None:
    org = await session.get(Organization, org_id)
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    await session.delete(org)
    await session.commit()
