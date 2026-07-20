"""Sandbox-agent application entrypoint."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from app.config import get_settings
from app.msb import build_backend
from app.routes import router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    Path(settings.workspace_root).mkdir(parents=True, exist_ok=True)
    app.state.backend = build_backend(settings)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="Internal Everflow sandbox-agent. Not for browser clients.",
        lifespan=lifespan,
    )
    application.include_router(router)

    @application.get("/", include_in_schema=False)
    async def root() -> dict[str, str]:
        return {
            "service": settings.app_name,
            "health": "/health",
            "note": "internal only — use everflow-platform-api",
        }

    return application


app = create_app()
