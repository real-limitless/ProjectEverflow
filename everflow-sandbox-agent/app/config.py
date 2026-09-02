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
    # development|staging|production|test — production/staging refuse default tokens and mock.
    environment: str = "development"
    sandbox_agent_token: str = "change-me"
    # Explicit true → mock. False/None → real guest (microVM or container fallback).
    sandbox_mock: bool | None = False
    # auto | microsandbox | container — auto uses microVMs when KVM_CREATE_VCPU works,
    # otherwise boots the same guest image as a Docker container (nested Cloud Agent).
    sandbox_runtime: str = "auto"
    docker_bin: str = "docker"
    docker_host: str | None = None
    # Host-docker image rewrite (compose DNS → dockerd). Comma-separated src=dst.
    container_image_rewrite: str = "registry:5000=127.0.0.1:5000"
    container_network: str | None = None
    workspace_docker_volume: str | None = None
    # Guest microVM image (msb pulls via compose DNS into local registry)
    default_image: str = "registry:5000/everflow/everflow-sandbox-guest:latest"
    default_cpus: int = 2
    # 2GiB is tight for OpenCode (~500MiB) + Playwright + XFCE/noVNC together.
    default_memory_mib: int = 3072
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
    # microsandbox home (image cache + config.json). Compose sets MSB_HOME.
    msb_home: str = "/root/.microsandbox"
    # Extra plain-HTTP registry hosts (comma-separated), merged with builtins.
    # Env: MSB_INSECURE_REGISTRIES=registry:5000,localhost:5000
    msb_insecure_registries: str | None = None
    # Best-effort `msb pull --insecure` of default_image on agent start.
    msb_prepull_default_image: bool = True

    def resolve_mock(self) -> bool:
        """Only mock when explicitly enabled."""
        return bool(self.sandbox_mock)

    @property
    def workspace_path(self) -> Path:
        return Path(self.workspace_root)


@lru_cache
def get_settings() -> Settings:
    return Settings()
