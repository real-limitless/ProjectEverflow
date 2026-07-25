"""Unit tests for msb HTTP/insecure registry configuration."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.msb_registry import (
    ensure_msb_insecure_registries,
    image_needs_insecure_pull,
    parse_image_registry_host,
    parse_insecure_hosts_env,
    registry_pull_error_hint,
    resolve_insecure_registry_hosts,
)


@pytest.mark.parametrize(
    "image,expected",
    [
        ("registry:5000/everflow/everflow-sandbox-guest:latest", "registry:5000"),
        ("localhost:5000/everflow/guest:dev", "localhost:5000"),
        ("ghcr.io/limitless-rh/everflow-sandbox-guest:latest", "ghcr.io"),
        ("python", None),
        ("ubuntu:24.04", None),
        ("", None),
        (None, None),
    ],
)
def test_parse_image_registry_host(image: str | None, expected: str | None) -> None:
    assert parse_image_registry_host(image) == expected


def test_resolve_insecure_hosts_includes_builtins_and_image() -> None:
    hosts = resolve_insecure_registry_hosts(
        default_image="registry:5000/everflow/guest:latest",
        extra_hosts="myreg.local:5000, other:5001",
    )
    assert "registry:5000" in hosts
    assert "localhost:5000" in hosts
    assert "127.0.0.1:5000" in hosts
    assert "myreg.local:5000" in hosts
    assert "other:5001" in hosts


def test_parse_insecure_hosts_env() -> None:
    assert parse_insecure_hosts_env("a:1, b:2  c:3") == ["a:1", "b:2", "c:3"]
    assert parse_insecure_hosts_env(None) == []
    assert parse_insecure_hosts_env("  ") == []


@pytest.mark.parametrize(
    "image,expected",
    [
        ("registry:5000/everflow/guest:latest", True),
        ("localhost:5000/x:latest", True),
        ("ghcr.io/org/img:latest", False),
        ("python", False),
        ("docker.io/library/python:3", False),
    ],
)
def test_image_needs_insecure_pull(image: str, expected: bool) -> None:
    assert image_needs_insecure_pull(image) is expected


def test_ensure_msb_insecure_registries_creates_config(tmp_path: Path) -> None:
    path = ensure_msb_insecure_registries(tmp_path, ["registry:5000", "localhost:5000"])
    assert path == tmp_path / "config.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    hosts = data["registries"]["hosts"]
    assert hosts["registry:5000"]["insecure"] is True
    assert hosts["localhost:5000"]["insecure"] is True


def test_ensure_msb_merges_without_clobbering_auth(tmp_path: Path) -> None:
    config = tmp_path / "config.json"
    config.write_text(
        json.dumps(
            {
                "log_level": "info",
                "registries": {
                    "hosts": {
                        "ghcr.io": {
                            "auth": {"username": "u", "password_env": "T"},
                        },
                        "registry:5000": {
                            "auth": {"username": "dev", "password_env": "X"},
                        },
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    ensure_msb_insecure_registries(tmp_path, ["registry:5000", "localhost:5000"])
    data = json.loads(config.read_text(encoding="utf-8"))
    assert data["log_level"] == "info"
    assert data["registries"]["hosts"]["ghcr.io"]["auth"]["username"] == "u"
    # existing auth preserved + insecure set
    reg = data["registries"]["hosts"]["registry:5000"]
    assert reg["insecure"] is True
    assert reg["auth"]["username"] == "dev"
    assert data["registries"]["hosts"]["localhost:5000"]["insecure"] is True


def test_ensure_msb_idempotent(tmp_path: Path) -> None:
    ensure_msb_insecure_registries(tmp_path, ["registry:5000"])
    first = (tmp_path / "config.json").read_text(encoding="utf-8")
    ensure_msb_insecure_registries(tmp_path, ["registry:5000"])
    second = (tmp_path / "config.json").read_text(encoding="utf-8")
    assert first == second


def test_registry_pull_error_hint_appends_once() -> None:
    detail = "named-volume: image error: registry error: https://registry:5000/v2/x"
    hinted = registry_pull_error_hint(detail)
    assert "plain HTTP" in hinted
    assert "local-registry.sh" in hinted
    # second apply does not double
    assert registry_pull_error_hint(hinted) == hinted


def test_registry_pull_error_hint_ignores_unrelated() -> None:
    detail = "named-volume: /dev/kvm is not available"
    assert registry_pull_error_hint(detail) == detail
