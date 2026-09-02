"""Container sandbox backend helpers and runtime selection."""

from __future__ import annotations

import pytest

from app.config import Settings
from app.container_backend import parse_image_rewrites, rewrite_image_for_host_docker
from app.msb import MockSandboxBackend, build_backend


def test_parse_image_rewrites() -> None:
    assert parse_image_rewrites("") == []
    assert parse_image_rewrites("registry:5000=127.0.0.1:5000") == [
        ("registry:5000", "127.0.0.1:5000")
    ]
    assert parse_image_rewrites("a=b, c=d") == [("a", "b"), ("c", "d")]


def test_rewrite_image_default_registry() -> None:
    src = "registry:5000/everflow/everflow-sandbox-guest:latest"
    assert rewrite_image_for_host_docker(src) == (
        "127.0.0.1:5000/everflow/everflow-sandbox-guest:latest"
    )
    assert rewrite_image_for_host_docker("ghcr.io/org/img:tag") == "ghcr.io/org/img:tag"
    assert rewrite_image_for_host_docker("127.0.0.1:5000/everflow/guest:latest") == (
        "127.0.0.1:5000/everflow/guest:latest"
    )


def test_rewrite_image_custom_rules() -> None:
    rules = [("registry:5000", "localhost:5000")]
    assert rewrite_image_for_host_docker(
        "registry:5000/everflow/guest:latest", rules
    ) == "localhost:5000/everflow/guest:latest"


def test_build_backend_mock_still_wins() -> None:
    settings = Settings(sandbox_mock=True, sandbox_runtime="container")
    backend = build_backend(settings)
    assert isinstance(backend, MockSandboxBackend)


def test_build_backend_auto_uses_container_when_kvm_broken(monkeypatch) -> None:
    monkeypatch.setattr("app.kvm_probe.kvm_vcpu_usable", lambda **_k: False)
    monkeypatch.setattr("app.msb.kvm_available", lambda: True)
    monkeypatch.setattr("app.container_backend.docker_cli_available", lambda _b="docker": True)
    monkeypatch.setattr("app.container_backend.docker_socket_available", lambda _h=None: True)

    settings = Settings(sandbox_mock=False, sandbox_runtime="auto")
    backend = build_backend(settings)
    from app.container_backend import ContainerSandboxBackend

    assert isinstance(backend, ContainerSandboxBackend)


def test_build_backend_auto_uses_msb_when_kvm_works(monkeypatch) -> None:
    monkeypatch.setattr("app.kvm_probe.kvm_vcpu_usable", lambda **_k: True)
    monkeypatch.setattr("app.msb.kvm_available", lambda: True)

    import sys
    import types

    fake = types.ModuleType("microsandbox")
    monkeypatch.setitem(sys.modules, "microsandbox", fake)

    settings = Settings(sandbox_mock=False, sandbox_runtime="auto")
    backend = build_backend(settings)
    from app.msb import MicrosandboxBackend

    assert isinstance(backend, MicrosandboxBackend)


def test_container_backend_uses_guest_opencode() -> None:
    from app.container_backend import ContainerSandboxBackend
    from app.msb import MicrosandboxBackend, MockSandboxBackend

    assert ContainerSandboxBackend.guest_opencode is True
    assert MicrosandboxBackend.guest_opencode is True
    assert MockSandboxBackend.guest_opencode is False


def test_build_backend_container_forced_without_docker_raises(monkeypatch) -> None:
    monkeypatch.setattr("app.container_backend.docker_cli_available", lambda _b="docker": False)
    settings = Settings(sandbox_mock=False, sandbox_runtime="container")
    with pytest.raises(RuntimeError, match="docker CLI"):
        build_backend(settings)
