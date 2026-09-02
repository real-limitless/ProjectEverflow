"""Everflow Platform API application entrypoint."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.preview import PreviewHostMiddleware
from app.api.v1.router import api_router
from app.config import get_settings
from app.db.session import dispose_db, get_engine, init_db


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    # Ensure SQLite data directory exists
    if settings.is_sqlite and ":memory:" not in settings.database_url:
        # sqlite+aiosqlite:///./data/everflow.db → ./data
        raw = settings.database_url.split("///", 1)[-1]
        db_path = Path(raw)
        if db_path.parent and str(db_path.parent) not in (".", ""):
            db_path.parent.mkdir(parents=True, exist_ok=True)

    from app.services.production_checks import (
        assert_production_secrets,
        is_non_dev_environment,
    )

    if is_non_dev_environment(settings.environment):
        assert_production_secrets(settings)

    init_db(settings)
    # Warm engine
    get_engine()
    # Workflow schedule arming (no-op when disabled / test)
    from app.services.workflows.scheduler import start_scheduler, stop_scheduler

    start_scheduler(
        enabled=settings.workflows_scheduler_enabled and settings.environment != "test",
        interval_s=settings.workflows_scheduler_interval_seconds,
    )
    yield
    await stop_scheduler()
    await dispose_db()


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description=(
            "Everflow platform API. Dual-database (SQLite default, PostgreSQL via "
            "DATABASE_URL). JWT + optional GitHub/Google OAuth."
        ),
        lifespan=lifespan,
        debug=settings.debug,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(api_router)

    @application.get("/", include_in_schema=False)
    async def root() -> dict[str, str]:
        return {
            "service": settings.app_name,
            "docs": "/docs",
            "health": "/api/v1/health",
        }

    # Wildcard preview hosts: {endpoint_id}.{preview_base_domain}
    application.add_middleware(PreviewHostMiddleware)

    return application


app = create_app()
