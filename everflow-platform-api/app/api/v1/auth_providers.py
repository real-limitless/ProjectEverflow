"""Public flags for which OAuth providers are configured."""

from fastapi import APIRouter, Depends

from app.config import Settings, get_settings

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/providers")
async def list_auth_providers(
    settings: Settings = Depends(get_settings),
) -> dict[str, bool]:
    return {
        "github": settings.github_oauth_enabled,
        "google": settings.google_oauth_enabled,
        "password": True,
    }
