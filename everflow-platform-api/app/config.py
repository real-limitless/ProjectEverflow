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
    # Fernet key material for provider API keys; falls back to secret_key if empty
    credentials_encryption_key: str = ""
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
    sandbox_default_image: str = "ghcr.io/limitless-rh/everflow-sandbox-guest:dev"
    # Keep in sync with sandbox-agent default; 2GiB OOMs under OpenCode+desktop+browser.
    sandbox_default_memory_mib: int = 3072
    sandbox_default_cpus: int = 2
    sandbox_default_harnesses: StrList = Field(
        default_factory=lambda: ["agent-claude-code", "agent-opencode"],
    )
    sandbox_agent_timeout_seconds: float = 120.0
    # Project-scoped tokens for in-sandbox Everflow MCP (seconds).
    # Idle TTL: unused tokens expire after this window. Active use slides expiry
    # (see sandbox_tokens.verify) so long-running OpenCode/MCP sessions stay valid.
    sandbox_token_ttl_seconds: int = 60 * 60 * 24  # 24h idle / slide window
    # Hard cap from mint time even with continuous use (0 = no absolute cap).
    sandbox_token_max_lifetime_seconds: int = 60 * 60 * 24 * 30  # 30d
    # When remaining life is below this, extend expires_at (reduces DB writes).
    # Default half of TTL so active sessions renew once per ~12h with 24h TTL.
    sandbox_token_slide_if_remaining_seconds: int = 60 * 60 * 12  # 12h
    # Browser / external base for the API
    public_api_url: str = "http://localhost:8000"
    # Platform API URL as seen by sandbox-agent (compose service DNS). Used for
    # reverse-tunnel dial from agent → API when injecting Everflow MCP in guests.
    agent_platform_api_url: str = "http://backend:8000"

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

    # In-process workflow schedule arming (disable in multi-replica unless leader-only)
    workflows_scheduler_enabled: bool = True
    workflows_scheduler_interval_seconds: float = 60.0

    # SearXNG (compose service DNS; local default for host-run API)
    searxng_url: str = "http://localhost:8080"

    # HTTP tools: outbound fetch SSRF policy
    # When true, allow RFC1918 / loopback (docker/sandbox-internal). Link-local +
    # cloud metadata (169.254.169.254) remain blocked either way.
    http_tools_allow_sandbox_internal: bool = False
    http_tools_request_timeout_seconds: float = 30.0

    # App toolkits (starter trees under /toolkits). Use {id} placeholder for toolkit id.
    # Example: https://github.com/org/everflow-toolkit-{id}.git
    # When empty, create seeds from toolkit_local_root into the sandbox.
    toolkit_repo_base: str = ""
    toolkit_local_root: str = "/toolkits"

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
