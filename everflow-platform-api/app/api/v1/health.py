"""Health and readiness probes."""

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db.session import get_async_session
from app.models.user import User
from app.services.production_checks import production_config_warnings
from app.services.sandbox_agent_client import SandboxAgentClient, SandboxAgentError

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/system/health")
async def system_health() -> dict[str, str]:
    """Alias used by install scripts and first-run wizard."""
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
            if isinstance(agent, dict) and "mock" in agent:
                sandbox["mock"] = bool(agent.get("mock"))
        except (SandboxAgentError, Exception) as exc:  # noqa: BLE001
            sandbox["reachable"] = False
            sandbox["error"] = str(exc)
    else:
        sandbox["reachable"] = None

    count = await session.execute(select(func.count()).select_from(User))
    needs_setup = int(count.scalar_one()) == 0

    return {
        "status": "ready",
        "sandbox": sandbox,
        "needs_setup": needs_setup,
        "warnings": production_config_warnings(settings),
        "oauth": {
            "github": settings.github_oauth_enabled,
            "google": settings.google_oauth_enabled,
        },
    }
