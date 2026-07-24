"""Organization CRUD, members, and invites."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.users import current_active_user
from app.config import Settings, get_settings
from app.core.deps import get_org_membership, require_org_admin, require_org_owner
from app.db.session import get_async_session
from app.models.organization import Organization, OrganizationInvite, OrganizationMember
from app.models.user import User
from app.schemas.organization import (
    OrganizationCreate,
    OrganizationInviteAcceptResult,
    OrganizationInviteCreate,
    OrganizationInviteRead,
    OrganizationMemberRead,
    OrganizationMemberUpdate,
    OrganizationRead,
    OrganizationUpdate,
)

router = APIRouter(prefix="/orgs", tags=["organizations"])
invites_router = APIRouter(tags=["organizations"])


def _hash_invite_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _invite_url(settings: Settings, token: str) -> str:
    base = settings.frontend_url.rstrip("/")
    return f"{base}/?invite={token}"


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


# ── Members ──────────────────────────────────────────────────────────────────


@router.get("/{org_id}/members", response_model=list[OrganizationMemberRead])
async def list_members(
    membership: OrganizationMember = Depends(get_org_membership),
    session: AsyncSession = Depends(get_async_session),
) -> list[OrganizationMemberRead]:
    result = await session.execute(
        select(OrganizationMember, User.email)
        .join(User, User.id == OrganizationMember.user_id)
        .where(OrganizationMember.organization_id == membership.organization_id)
        .order_by(OrganizationMember.created_at.asc())
    )
    out: list[OrganizationMemberRead] = []
    for member, email in result.all():
        read = OrganizationMemberRead.model_validate(member)
        read.email = email
        out.append(read)
    return out


@router.patch("/{org_id}/members/{user_id}", response_model=OrganizationMemberRead)
async def update_member_role(
    user_id: UUID,
    body: OrganizationMemberUpdate,
    actor: OrganizationMember = Depends(require_org_admin),
    session: AsyncSession = Depends(get_async_session),
) -> OrganizationMemberRead:
    if body.role == "owner" and actor.role != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only owners can grant owner role",
        )
    result = await session.execute(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == actor.organization_id,
            OrganizationMember.user_id == user_id,
        )
    )
    target = result.scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")

    if target.role == "owner" and body.role != "owner":
        owners = await session.execute(
            select(func.count())
            .select_from(OrganizationMember)
            .where(
                OrganizationMember.organization_id == actor.organization_id,
                OrganizationMember.role == "owner",
            )
        )
        if int(owners.scalar_one()) <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot demote the last owner",
            )

    target.role = body.role
    await session.commit()
    await session.refresh(target)
    user = await session.get(User, target.user_id)
    read = OrganizationMemberRead.model_validate(target)
    read.email = user.email if user else None
    return read


@router.delete("/{org_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    user_id: UUID,
    actor: OrganizationMember = Depends(require_org_admin),
    session: AsyncSession = Depends(get_async_session),
) -> None:
    result = await session.execute(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == actor.organization_id,
            OrganizationMember.user_id == user_id,
        )
    )
    target = result.scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")

    if target.role == "owner":
        owners = await session.execute(
            select(func.count())
            .select_from(OrganizationMember)
            .where(
                OrganizationMember.organization_id == actor.organization_id,
                OrganizationMember.role == "owner",
            )
        )
        if int(owners.scalar_one()) <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot remove the last owner",
            )
        if actor.role != "owner":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only owners can remove owners",
            )

    await session.delete(target)
    await session.commit()


# ── Invites ──────────────────────────────────────────────────────────────────


@router.post(
    "/{org_id}/invites",
    response_model=OrganizationInviteRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_invite(
    body: OrganizationInviteCreate,
    membership: OrganizationMember = Depends(require_org_admin),
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_settings),
) -> OrganizationInviteRead:
    token = secrets.token_urlsafe(32)
    invite = OrganizationInvite(
        organization_id=membership.organization_id,
        token_hash=_hash_invite_token(token),
        role=body.role,
        email=str(body.email).lower() if body.email else None,
        created_by=user.id,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=body.expires_hours),
    )
    session.add(invite)
    await session.commit()
    await session.refresh(invite)
    read = OrganizationInviteRead.model_validate(invite)
    read.token = token
    read.invite_url = _invite_url(settings, token)
    return read


@router.get("/{org_id}/invites", response_model=list[OrganizationInviteRead])
async def list_invites(
    membership: OrganizationMember = Depends(require_org_admin),
    session: AsyncSession = Depends(get_async_session),
) -> list[OrganizationInviteRead]:
    result = await session.execute(
        select(OrganizationInvite)
        .where(
            OrganizationInvite.organization_id == membership.organization_id,
            OrganizationInvite.accepted_at.is_(None),
        )
        .order_by(OrganizationInvite.created_at.desc())
    )
    return [OrganizationInviteRead.model_validate(i) for i in result.scalars().all()]


@invites_router.post(
    "/invites/{token}/accept",
    response_model=OrganizationInviteAcceptResult,
)
async def accept_invite(
    token: str,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> OrganizationInviteAcceptResult:
    token_hash = _hash_invite_token(token)
    result = await session.execute(
        select(OrganizationInvite).where(OrganizationInvite.token_hash == token_hash)
    )
    invite = result.scalar_one_or_none()
    if invite is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invite not found")
    if invite.accepted_at is not None:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Invite already used")
    expires = invite.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Invite expired")
    if invite.email and invite.email.lower() != user.email.lower():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invite is restricted to a different email",
        )

    existing = await session.execute(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == invite.organization_id,
            OrganizationMember.user_id == user.id,
        )
    )
    if existing.scalar_one_or_none() is None:
        session.add(
            OrganizationMember(
                organization_id=invite.organization_id,
                user_id=user.id,
                role=invite.role if invite.role in ("admin", "member") else "member",
            )
        )

    invite.accepted_at = datetime.now(timezone.utc)
    invite.accepted_by = user.id
    await session.commit()

    org = await session.get(Organization, invite.organization_id)
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    return OrganizationInviteAcceptResult(
        organization_id=org.id,
        organization_name=org.name,
        organization_slug=org.slug,
        role=invite.role,
    )
