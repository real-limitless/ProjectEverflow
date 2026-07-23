"""Sandbox-agent settings."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Everflow Sandbox Agent"
    sandbox_agent_token: str = "change-me"
    # Explicit true → mock. False/None → real microsandbox (fail if KVM/SDK missing).
    sandbox_mock: bool | None = False
    # Guest microVM image (prebaked harnesses on GHCR)
    default_image: str = "ghcr.io/real-limitless/everflow-sandbox-guest:dev"
    default_cpus: int = 2
    default_memory_mib: int = 2048
    # Mount strategy for microVM workspace: named-volume | bind | no-volumes | auto
    # auto tries strategies in order and caches the last success for this process.
    volume_strategy: str = "auto"
    workspace_root: str = "/workspaces"
    host: str = "0.0.0.0"
    port: int = 8090
    # Platform API URL as reachable FROM the agent (compose: http://backend:8000).
    # Guest everflow-mcp uses a reverse tunnel to 127.0.0.1; agent dials this URL.
    platform_api_url: str = "http://backend:8000"
    # Guest-local port for the reverse tunnel listener
    everflow_mcp_tunnel_port: int = 18765

    def resolve_mock(self) -> bool:
        """Only mock when explicitly enabled."""
        return bool(self.sandbox_mock)

    @property
    def workspace_path(self) -> Path:
        return Path(self.workspace_root)


@lru_cache
def get_settings() -> Settings:
    return Settings()
