"""Request principal: JWT user or sandbox access token."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.users import fastapi_users
from app.db.session import get_async_session
from app.models.organization import OrganizationMember
from app.models.project import Project
from app.models.sandbox_token import TOKEN_PREFIX
from app.models.user import User
from app.services.sandbox_tokens import has_scope, verify_sandbox_token

# Optional JWT — sandbox tokens are handled first when the bearer matches TOKEN_PREFIX.
_optional_jwt_user = fastapi_users.current_user(active=True, optional=True)


@dataclass
class Principal:
    user: User
    bound_project_id: UUID | None = None
    scopes: list[str] = field(default_factory=list)
    via: str = "jwt"  # jwt | sandbox_token

    def require_scope(self, scope: str) -> None:
        if self.via == "jwt":
            return
        if not has_scope(self.scopes, scope):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing scope: {scope}",
            )


def _extract_bearer(request: Request) -> str | None:
    auth = request.headers.get("Authorization") or ""
    if not auth.lower().startswith("bearer "):
        return None
    return auth[7:].strip() or None


async def get_principal(
    request: Request,
    session: AsyncSession = Depends(get_async_session),
    jwt_user: User | None = Depends(_optional_jwt_user),
) -> Principal:
    """Resolve caller from sandbox access token or JWT."""
    raw = _extract_bearer(request)
    if raw and raw.startswith(TOKEN_PREFIX):
        row = await verify_sandbox_token(session, raw)
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired sandbox token",
            )
        db_user = await session.get(User, row.user_id)
        if db_user is None or not db_user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token user inactive",
            )
        return Principal(
            user=db_user,
            bound_project_id=row.project_id,
            scopes=[str(s) for s in (row.scopes or [])],
            via="sandbox_token",
        )

    if jwt_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return Principal(user=jwt_user, via="jwt")


async def get_project_for_principal(
    project_id: UUID,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> Project:
    """Load project; enforce membership (JWT) or bound project (sandbox token)."""
    result = await session.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    if principal.bound_project_id is not None:
        if principal.bound_project_id != project.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Token is not bound to this project",
            )
        return project

    mem = await session.execute(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == project.organization_id,
            OrganizationMember.user_id == principal.user.id,
        )
    )
    if mem.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not a member of this organization",
        )
    return project
