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
    # Prefer microsandbox-friendly defaults (docs use "python" / "debian")
    default_image: str = "python"
    default_cpus: int = 2
    default_memory_mib: int = 2048
    workspace_root: str = "/workspaces"
    host: str = "0.0.0.0"
    port: int = 8090

    def resolve_mock(self) -> bool:
        """Only mock when explicitly enabled."""
        return bool(self.sandbox_mock)

    @property
    def workspace_path(self) -> Path:
        return Path(self.workspace_root)


@lru_cache
def get_settings() -> Settings:
    return Settings()
