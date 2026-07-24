"""First-run setup: bootstrap platform admin + first organization."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi_users.password import PasswordHelper
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.users import get_jwt_strategy
from app.config import Settings, get_settings
from app.db.session import get_async_session
from app.models.organization import Organization, OrganizationMember
from app.models.user import User
from app.schemas.setup import SetupBootstrapRequest, SetupBootstrapResponse, SetupStatus
from app.services.production_checks import production_config_warnings
from app.services.sandbox_agent_client import SandboxAgentClient, SandboxAgentError

router = APIRouter(prefix="/setup", tags=["setup"])
_password_helper = PasswordHelper()


async def _user_count(session: AsyncSession) -> int:
    result = await session.execute(select(func.count()).select_from(User))
    return int(result.scalar_one())


async def _sandbox_probe(settings: Settings) -> dict[str, Any]:
    info: dict[str, Any] = {"enabled": settings.sandbox_enabled}
    if not settings.sandbox_enabled:
        info["reachable"] = None
        return info
    try:
        agent = await SandboxAgentClient(settings).health()
        info["agent"] = agent
        info["reachable"] = True
        info["mock"] = bool(agent.get("mock")) if isinstance(agent, dict) else None
    except (SandboxAgentError, Exception) as exc:  # noqa: BLE001
        info["reachable"] = False
        info["error"] = str(exc)
    return info


@router.get("/status", response_model=SetupStatus)
async def setup_status(
    session: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_settings),
) -> SetupStatus:
    count = await _user_count(session)
    return SetupStatus(
        needs_setup=count == 0,
        environment=settings.environment,
        warnings=production_config_warnings(settings),
        sandbox=await _sandbox_probe(settings),
        oauth={
            "github": settings.github_oauth_enabled,
            "google": settings.google_oauth_enabled,
        },
    )


@router.post(
    "/bootstrap",
    response_model=SetupBootstrapResponse,
    status_code=status.HTTP_201_CREATED,
)
async def setup_bootstrap(
    body: SetupBootstrapRequest,
    session: AsyncSession = Depends(get_async_session),
) -> SetupBootstrapResponse:
    if await _user_count(session) > 0:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Setup already completed",
        )

    hashed = _password_helper.hash(body.password)
    user = User(
        id=uuid4(),
        email=str(body.email).lower(),
        hashed_password=hashed,
        is_active=True,
        is_superuser=True,
        is_verified=True,
    )
    org = Organization(name=body.org_name, slug=body.org_slug)
    session.add(user)
    session.add(org)
    try:
        await session.flush()
        session.add(
            OrganizationMember(
                organization_id=org.id,
                user_id=user.id,
                role="owner",
            )
        )
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email or organization slug already exists",
        ) from exc

    await session.refresh(user)
    await session.refresh(org)

    token = await get_jwt_strategy().write_token(user)
    return SetupBootstrapResponse(
        user_id=str(user.id),
        email=user.email,
        org_id=str(org.id),
        org_slug=org.slug,
        access_token=token,
    )
