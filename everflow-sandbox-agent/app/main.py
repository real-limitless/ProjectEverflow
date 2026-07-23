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
    import logging

    log = logging.getLogger("everflow.sandbox_agent")
    settings = get_settings()
    Path(settings.workspace_root).mkdir(parents=True, exist_ok=True)
    backend = build_backend(settings)
    app.state.backend = backend
    try:
        from app.guest_tunnel import get_tunnel_manager

        get_tunnel_manager().bind_backend(backend)
    except Exception:
        pass
    try:
        from app.api_tunnel import get_api_tunnel_manager

        get_api_tunnel_manager().bind_backend(backend)
    except Exception:
        pass
    # Reconcile: after agent restart, microsandbox often leaves crashed records.
    # Log them so operators know platform clients will recreate on open.
    try:
        recs = await backend.list()
        stale = [r for r in recs if str(getattr(r, "status", "")).lower() not in ("running", "stopped")]
        if stale:
            log.warning(
                "sandbox reconcile: %d non-running sandbox(es) after startup: %s",
                len(stale),
                ", ".join(f"{r.name}={r.status}" for r in stale[:20]),
            )
        else:
            log.info("sandbox reconcile: %d sandbox(es) known to runtime", len(recs))
    except Exception as exc:  # noqa: BLE001
        log.debug("sandbox reconcile skipped: %s", exc)
    yield
    try:
        from app.guest_tunnel import get_tunnel_manager

        await get_tunnel_manager().close_all()
    except Exception:
        pass
    try:
        from app.api_tunnel import get_api_tunnel_manager

        await get_api_tunnel_manager().close_all()
    except Exception:
        pass


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
