"""Git PAT vault — user, org, and project scope."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.users import current_active_user
from app.config import Settings, get_settings
from app.core.deps import get_org_membership, get_project_for_member, require_org_admin
from app.db.session import get_async_session
from app.models.organization import OrganizationMember
from app.models.project import Project
from app.models.user import User
from app.schemas.git_credential import (
    GitCredentialCreate,
    GitCredentialRead,
    GitCredentialUpdate,
)
from app.services import git_credentials as git_svc

router = APIRouter(tags=["git-credentials"])


# ── Account (current user) ───────────────────────────────────────────────────


@router.get("/me/git-credentials", response_model=list[GitCredentialRead])
async def list_my_git_credentials(
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> list[GitCredentialRead]:
    rows = await git_svc.list_credentials(session, owner_type="user", owner_id=user.id)
    return [git_svc.to_read(r) for r in rows]


@router.post(
    "/me/git-credentials",
    response_model=GitCredentialRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_my_git_credential(
    body: GitCredentialCreate,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_settings),
) -> GitCredentialRead:
    row = await git_svc.create_credential(
        session,
        owner_type="user",
        owner_id=user.id,
        body=body,
        settings=settings,
    )
    return git_svc.to_read(row)


@router.patch("/me/git-credentials/{cred_id}", response_model=GitCredentialRead)
async def update_my_git_credential(
    cred_id: UUID,
    body: GitCredentialUpdate,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_settings),
) -> GitCredentialRead:
    row = await git_svc.get_credential(
        session, cred_id=cred_id, owner_type="user", owner_id=user.id
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Credential not found")
    row = await git_svc.update_credential(session, row, body, settings)
    return git_svc.to_read(row)


@router.delete("/me/git-credentials/{cred_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_my_git_credential(
    cred_id: UUID,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> None:
    row = await git_svc.get_credential(
        session, cred_id=cred_id, owner_type="user", owner_id=user.id
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Credential not found")
    await git_svc.delete_credential(session, row)


# ── Organization ─────────────────────────────────────────────────────────────


@router.get(
    "/orgs/{org_id}/git-credentials",
    response_model=list[GitCredentialRead],
)
async def list_org_git_credentials(
    membership: OrganizationMember = Depends(get_org_membership),
    session: AsyncSession = Depends(get_async_session),
) -> list[GitCredentialRead]:
    rows = await git_svc.list_credentials(
        session, owner_type="org", owner_id=membership.organization_id
    )
    return [git_svc.to_read(r) for r in rows]


@router.post(
    "/orgs/{org_id}/git-credentials",
    response_model=GitCredentialRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_org_git_credential(
    body: GitCredentialCreate,
    membership: OrganizationMember = Depends(require_org_admin),
    session: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_settings),
) -> GitCredentialRead:
    row = await git_svc.create_credential(
        session,
        owner_type="org",
        owner_id=membership.organization_id,
        body=body,
        settings=settings,
    )
    return git_svc.to_read(row)


@router.delete(
    "/orgs/{org_id}/git-credentials/{cred_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_org_git_credential(
    cred_id: UUID,
    membership: OrganizationMember = Depends(require_org_admin),
    session: AsyncSession = Depends(get_async_session),
) -> None:
    row = await git_svc.get_credential(
        session,
        cred_id=cred_id,
        owner_type="org",
        owner_id=membership.organization_id,
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Credential not found")
    await git_svc.delete_credential(session, row)


# ── Project ──────────────────────────────────────────────────────────────────


@router.get(
    "/projects/{project_id}/git-credentials",
    response_model=list[GitCredentialRead],
)
async def list_project_git_credentials(
    project: Project = Depends(get_project_for_member),
    session: AsyncSession = Depends(get_async_session),
) -> list[GitCredentialRead]:
    rows = await git_svc.list_credentials(
        session, owner_type="project", owner_id=project.id
    )
    return [git_svc.to_read(r) for r in rows]


@router.post(
    "/projects/{project_id}/git-credentials",
    response_model=GitCredentialRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_project_git_credential(
    body: GitCredentialCreate,
    project: Project = Depends(get_project_for_member),
    session: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_settings),
) -> GitCredentialRead:
    row = await git_svc.create_credential(
        session,
        owner_type="project",
        owner_id=project.id,
        body=body,
        settings=settings,
    )
    return git_svc.to_read(row)


@router.delete(
    "/projects/{project_id}/git-credentials/{cred_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_project_git_credential(
    cred_id: UUID,
    project: Project = Depends(get_project_for_member),
    session: AsyncSession = Depends(get_async_session),
) -> None:
    row = await git_svc.get_credential(
        session, cred_id=cred_id, owner_type="project", owner_id=project.id
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Credential not found")
    await git_svc.delete_credential(session, row)
