"""Mint and inspect project-scoped sandbox access tokens (MCP auth)."""

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.users import current_active_user
from app.config import Settings, get_settings
from app.core.deps import get_project_for_member
from app.core.principal import Principal, get_principal, get_project_for_principal
from app.db.session import get_async_session
from app.models.project import Project
from app.models.sandbox_token import SandboxAccessToken
from app.models.user import User
from app.schemas.sandbox_token import (
    McpContextRead,
    SandboxTokenCreate,
    SandboxTokenCreated,
    SandboxTokenRead,
)
from app.services.sandbox_tokens import mint_sandbox_token

router = APIRouter(tags=["sandbox-tokens"])


@router.post(
    "/projects/{project_id}/sandbox-tokens",
    response_model=SandboxTokenCreated,
    status_code=status.HTTP_201_CREATED,
)
async def create_sandbox_token(
    body: SandboxTokenCreate,
    project: Project = Depends(get_project_for_member),
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_settings),
) -> SandboxTokenCreated:
    """Mint a project-bound token for the current user (OpenCode MCP / automation)."""
    row, raw = await mint_sandbox_token(
        session,
        project_id=project.id,
        user_id=user.id,
        scopes=body.scopes,
        label=body.label,
        ttl_seconds=body.ttl_seconds,
        settings=settings,
        revoke_existing=body.revoke_existing,
    )
    return SandboxTokenCreated(
        id=row.id,
        project_id=row.project_id,
        user_id=row.user_id,
        prefix=row.prefix,
        scopes=[str(s) for s in (row.scopes or [])],
        label=row.label,
        expires_at=row.expires_at,
        token=raw,
    )


@router.get(
    "/projects/{project_id}/sandbox-tokens",
    response_model=list[SandboxTokenRead],
)
async def list_sandbox_tokens(
    project: Project = Depends(get_project_for_member),
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> list[SandboxAccessToken]:
    """List the current user's tokens for this project (no raw secrets)."""
    result = await session.execute(
        select(SandboxAccessToken)
        .where(
            SandboxAccessToken.project_id == project.id,
            SandboxAccessToken.user_id == user.id,
        )
        .order_by(SandboxAccessToken.created_at.desc())
    )
    return list(result.scalars().all())


@router.get(
    "/projects/{project_id}/mcp/context",
    response_model=McpContextRead,
)
async def mcp_context(
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
) -> McpContextRead:
    """Bound identity for Everflow MCP ``everflow_whoami``."""
    principal.require_scope("project:read")
    return McpContextRead(
        via=principal.via,
        user_id=principal.user.id,
        user_email=getattr(principal.user, "email", None),
        project_id=project.id,
        project_name=project.name,
        project_slug=project.slug,
        organization_id=project.organization_id,
        sandbox_status=project.sandbox_status,
        scopes=list(principal.scopes) if principal.via == "sandbox_token" else ["*"],
    )
