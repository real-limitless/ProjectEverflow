"""Application settings loaded from environment / .env."""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import BeforeValidator, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

try:
    # pydantic-settings v2.7+: skip JSON decode of complex env values so comma lists work
    from pydantic_settings import NoDecode
except ImportError:  # pragma: no cover
    NoDecode = None  # type: ignore[misc, assignment]


def _parse_str_list(value: object) -> list[str]:
    """Accept JSON arrays or comma-separated env strings."""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return []
        if raw.startswith("["):
            parsed = json.loads(raw)
            if not isinstance(parsed, list):
                raise ValueError("expected a JSON array of strings")
            return [str(v).strip() for v in parsed if str(v).strip()]
        return [part.strip() for part in raw.split(",") if part.strip()]
    return [str(value).strip()]


if NoDecode is not None:
    StrList = Annotated[list[str], NoDecode, BeforeValidator(_parse_str_list)]
else:
    StrList = Annotated[list[str], BeforeValidator(_parse_str_list)]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Everflow Platform API"
    environment: Literal["development", "staging", "production", "test"] = "development"
    debug: bool = True
    secret_key: str = "change-me-in-production-use-a-long-random-string"
    database_url: str = "sqlite+aiosqlite:///./data/everflow.db"
    cors_origins: StrList = Field(default_factory=lambda: ["http://localhost:5173"])
    access_token_expire_minutes: int = 60
    frontend_url: str = "http://localhost:5173"

    github_client_id: str = ""
    github_client_secret: str = ""
    google_client_id: str = ""
    google_client_secret: str = ""
    oauth_redirect_base_url: str = "http://localhost:8000"

    # Internal sandbox-agent (never exposed to browsers)
    sandbox_enabled: bool = True
    sandbox_agent_url: str = "http://localhost:8090"
    sandbox_agent_token: str = "change-me"
    # Prebaked guest image (./deploy/build-sandbox-guest.sh); override via SANDBOX_DEFAULT_IMAGE
    sandbox_default_image: str = "ghcr.io/real-limitless/everflow-sandbox-guest:dev"
    sandbox_default_memory_mib: int = 2048
    sandbox_default_cpus: int = 2
    sandbox_default_harnesses: StrList = Field(
        default_factory=lambda: ["agent-claude-code", "agent-opencode"],
    )
    sandbox_agent_timeout_seconds: float = 120.0

    # Live Preview edge: {endpoint_id}.{preview_base_domain}
    # Local default includes :8000 so browsers never hit implicit :80/:443.
    # Production: PREVIEW_BASE_DOMAIN=preview.example.com + PREVIEW_PUBLIC_SCHEME=https
    preview_enabled: bool = True
    preview_base_domain: str = "preview.localhost:8000"
    preview_public_scheme: str = "http"
    # If base domain has no :port, append this (local/dev). None/0 = leave as-is
    # (except *.localhost hardening in public_preview_url).
    preview_public_port: int | None = None
    preview_ticket_ttl_seconds: int = 1200
    preview_cookie_name: str = "ef_preview_auth"

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def github_oauth_enabled(self) -> bool:
        return bool(self.github_client_id and self.github_client_secret)

    @property
    def google_oauth_enabled(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret)


@lru_cache
def get_settings() -> Settings:
    return Settings()
