"""Health and readiness probes."""

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db.session import get_async_session
from app.services.sandbox_agent_client import SandboxAgentClient, SandboxAgentError

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
async def ready(
    session: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    await session.execute(text("SELECT 1"))

    sandbox: dict[str, Any] = {"enabled": settings.sandbox_enabled}
    if settings.sandbox_enabled:
        try:
            agent = await SandboxAgentClient(settings).health()
            sandbox["agent"] = agent
            sandbox["reachable"] = True
        except (SandboxAgentError, Exception) as exc:  # noqa: BLE001
            sandbox["reachable"] = False
            sandbox["error"] = str(exc)
    else:
        sandbox["reachable"] = None

    return {"status": "ready", "sandbox": sandbox}
