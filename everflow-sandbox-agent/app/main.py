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
    from app.startup_checks import assert_agent_startup

    assert_agent_startup(settings)
    Path(settings.workspace_root).mkdir(parents=True, exist_ok=True)

    # Embedded registry is plain HTTP; msb defaults to HTTPS for pulls.
    # Seed $MSB_HOME/config.json registries.hosts.*.insecure before any create.
    if not settings.resolve_mock():
        try:
            from app.msb_registry import (
                ensure_msb_insecure_registries,
                prepull_default_image,
                resolve_insecure_registry_hosts,
            )

            hosts = resolve_insecure_registry_hosts(
                default_image=settings.default_image,
                extra_hosts=settings.msb_insecure_registries,
            )
            ensure_msb_insecure_registries(settings.msb_home, hosts)
            log.info("msb insecure registries ready: %s", ", ".join(hosts))
            if settings.msb_prepull_default_image and settings.default_image:
                from app.msb_registry import image_needs_insecure_pull

                ok = prepull_default_image(
                    settings.default_image,
                    insecure=image_needs_insecure_pull(settings.default_image, hosts),
                )
                if not ok:
                    log.warning(
                        "msb pre-pull of default guest image failed image=%s "
                        "(first project create will retry; seed with ./deploy/local-registry.sh)",
                        settings.default_image,
                    )
        except Exception as exc:  # noqa: BLE001
            log.warning("msb registry bootstrap failed (provision may fail): %s", exc)

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
