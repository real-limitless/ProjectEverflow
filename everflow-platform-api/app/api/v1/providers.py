"""AI provider credential vault — account and project scope."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.users import current_active_user
from app.config import Settings, get_settings
from app.core.deps import get_project_for_member
from app.db.session import get_async_session
from app.models.project import Project
from app.models.user import User
from app.schemas.provider import (
    ProviderCatalogItem,
    ProviderCredentialCreate,
    ProviderCredentialRead,
    ProviderCredentialUpdate,
)
from app.services import providers as provider_svc
from app.services.provider_inject import inject_project_provider_secrets

router = APIRouter(tags=["providers"])


@router.get("/providers/catalog", response_model=list[ProviderCatalogItem])
async def list_provider_catalog(
    _user: User = Depends(current_active_user),
) -> list[ProviderCatalogItem]:
    return [ProviderCatalogItem(**item) for item in provider_svc.PROVIDER_CATALOG]


# ── Account (current user) ───────────────────────────────────────────────────


@router.get("/me/providers", response_model=list[ProviderCredentialRead])
async def list_my_providers(
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> list[ProviderCredentialRead]:
    rows = await provider_svc.list_credentials(
        session, owner_type="user", owner_id=user.id
    )
    return [provider_svc.to_read(r) for r in rows]


@router.post(
    "/me/providers",
    response_model=ProviderCredentialRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_my_provider(
    body: ProviderCredentialCreate,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_settings),
) -> ProviderCredentialRead:
    row = await provider_svc.create_credential(
        session,
        owner_type="user",
        owner_id=user.id,
        body=body,
        settings=settings,
    )
    return provider_svc.to_read(row)


@router.patch("/me/providers/{cred_id}", response_model=ProviderCredentialRead)
async def update_my_provider(
    cred_id: UUID,
    body: ProviderCredentialUpdate,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_settings),
) -> ProviderCredentialRead:
    row = await provider_svc.get_credential(
        session, cred_id=cred_id, owner_type="user", owner_id=user.id
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")
    row = await provider_svc.update_credential(session, row, body, settings)
    return provider_svc.to_read(row)


@router.delete("/me/providers/{cred_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_my_provider(
    cred_id: UUID,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> None:
    row = await provider_svc.get_credential(
        session, cred_id=cred_id, owner_type="user", owner_id=user.id
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")
    await provider_svc.delete_credential(session, row)


# ── Project ──────────────────────────────────────────────────────────────────


@router.get(
    "/projects/{project_id}/providers",
    response_model=list[ProviderCredentialRead],
)
async def list_project_providers(
    project: Project = Depends(get_project_for_member),
    session: AsyncSession = Depends(get_async_session),
) -> list[ProviderCredentialRead]:
    rows = await provider_svc.list_credentials(
        session, owner_type="project", owner_id=project.id
    )
    return [provider_svc.to_read(r) for r in rows]


@router.post(
    "/projects/{project_id}/providers",
    response_model=ProviderCredentialRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_project_provider(
    body: ProviderCredentialCreate,
    project: Project = Depends(get_project_for_member),
    session: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_settings),
) -> ProviderCredentialRead:
    # Any org member may attach keys used by this project's sandbox (chat/RAG).
    row = await provider_svc.create_credential(
        session,
        owner_type="project",
        owner_id=project.id,
        body=body,
        settings=settings,
    )
    return provider_svc.to_read(row)


@router.patch(
    "/projects/{project_id}/providers/{cred_id}",
    response_model=ProviderCredentialRead,
)
async def update_project_provider(
    cred_id: UUID,
    body: ProviderCredentialUpdate,
    project: Project = Depends(get_project_for_member),
    session: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_settings),
) -> ProviderCredentialRead:
    row = await provider_svc.get_credential(
        session, cred_id=cred_id, owner_type="project", owner_id=project.id
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")
    row = await provider_svc.update_credential(session, row, body, settings)
    return provider_svc.to_read(row)


@router.delete(
    "/projects/{project_id}/providers/{cred_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_project_provider(
    cred_id: UUID,
    project: Project = Depends(get_project_for_member),
    session: AsyncSession = Depends(get_async_session),
) -> None:
    row = await provider_svc.get_credential(
        session, cred_id=cred_id, owner_type="project", owner_id=project.id
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")
    await provider_svc.delete_credential(session, row)


@router.post("/projects/{project_id}/providers/inject")
async def inject_project_providers(
    project: Project = Depends(get_project_for_member),
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Resolve account+project vault keys and inject into the running sandbox."""
    if not settings.sandbox_enabled:
        return {
            "injected": False,
            "reason": "sandbox_disabled",
            "env_keys": [],
            "opencode_providers": [],
        }
    return await inject_project_provider_secrets(
        session,
        project,
        user_id=user.id,
        settings=settings,
        apply_opencode_auth=True,
    )
