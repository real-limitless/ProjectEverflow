"""Aggregate v1 API routes."""

from fastapi import APIRouter

from app.api.v1 import (
    agents,
    deploy,
    deploy_runs,
    harness,
    health,
    http_tools,
    jobs,
    knowledge,
    opencode,
    orgs,
    preview,
    project_database,
    projects,
    providers,
    sandbox,
    sandbox_shell,
    sandbox_tokens,
    tests,
    workflows,
)
from app.auth.oauth import build_github_client, build_google_client
from app.auth.users import auth_backend, fastapi_users
from app.config import get_settings
from app.schemas.user import UserCreate, UserRead, UserUpdate

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(health.router)
api_router.include_router(orgs.router)
api_router.include_router(projects.router)
api_router.include_router(knowledge.router)
api_router.include_router(agents.router)
api_router.include_router(tests.router)
api_router.include_router(http_tools.router)
api_router.include_router(deploy.router)
api_router.include_router(workflows.router)
api_router.include_router(sandbox_tokens.router)
api_router.include_router(providers.router)
api_router.include_router(sandbox.router)
api_router.include_router(sandbox_shell.router)
api_router.include_router(jobs.router)
api_router.include_router(deploy_runs.router)
api_router.include_router(project_database.router)
api_router.include_router(opencode.router)
api_router.include_router(harness.router)
api_router.include_router(preview.router)

# Auth: register, JWT login/logout, users/me
api_router.include_router(
    fastapi_users.get_auth_router(auth_backend),
    prefix="/auth/jwt",
    tags=["auth"],
)
api_router.include_router(
    fastapi_users.get_register_router(UserRead, UserCreate),
    prefix="/auth",
    tags=["auth"],
)
api_router.include_router(
    fastapi_users.get_users_router(UserRead, UserUpdate),
    prefix="/users",
    tags=["users"],
)

# OAuth providers — only mount when credentials are configured
_settings = get_settings()
_github = build_github_client(_settings)
if _github is not None:
    api_router.include_router(
        fastapi_users.get_oauth_router(
            _github,
            auth_backend,
            _settings.secret_key,
            redirect_url=f"{_settings.oauth_redirect_base_url}/api/v1/auth/github/callback",
            associate_by_email=True,
        ),
        prefix="/auth/github",
        tags=["auth"],
    )

_google = build_google_client(_settings)
if _google is not None:
    api_router.include_router(
        fastapi_users.get_oauth_router(
            _google,
            auth_backend,
            _settings.secret_key,
            redirect_url=f"{_settings.oauth_redirect_base_url}/api/v1/auth/google/callback",
            associate_by_email=True,
        ),
        prefix="/auth/google",
        tags=["auth"],
    )
