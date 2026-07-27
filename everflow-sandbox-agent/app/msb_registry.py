"""Configure microsandbox for plain-HTTP (insecure) OCI registries.

The embedded Everflow registry speaks HTTP only. msb defaults to HTTPS, which
fails with:

  registry error: error sending request for url
  (https://registry:5000/v2/.../manifests/latest)

Official fix: $MSB_HOME/config.json → registries.hosts.<host>.insecure = true
  https://docs.microsandbox.dev/configuration.md

Also: msb pull --insecure <ref>. Newer SDKs may accept Sandbox.create(...,
insecure=True); older builds rely on config.json only (see sandbox_create()).
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Hosts we always treat as plain HTTP when using the product compose stack.
_BUILTIN_INSECURE_HOSTS: tuple[str, ...] = (
    "registry:5000",
    "localhost:5000",
    "127.0.0.1:5000",
)

# Hostnames (no port) that imply a private/local registry over HTTP.
_LOCAL_HOSTNAMES = frozenset(
    {
        "registry",
        "localhost",
        "127.0.0.1",
        "host.containers.internal",
        "host.docker.internal",
    }
)


def parse_image_registry_host(image: str | None) -> str | None:
    """Return registry host:port from an OCI ref, or None for Docker Hub short names.

    Examples:
      registry:5000/everflow/guest:latest → registry:5000
      ghcr.io/org/img:tag → ghcr.io
      python → None
      ubuntu:24.04 → None  (tag, not registry)
    """
    if not image or not str(image).strip():
        return None
    ref = str(image).strip()
    # Explicit scheme (rare for OCI refs, but allow)
    if "://" in ref:
        parsed = urlparse(ref)
        if parsed.hostname:
            return f"{parsed.hostname}:{parsed.port}" if parsed.port else parsed.hostname
        return None

    # Drop digest / tag for path inspection
    path = ref.split("@", 1)[0]
    # If there is a slash, first component may be registry
    if "/" not in path:
        return None
    first, _rest = path.split("/", 1)
    # registry.example.com:5000 or localhost:5000 or 127.0.0.1:5000
    if ":" in first or "." in first or first in _LOCAL_HOSTNAMES:
        # "ubuntu:24.04/..." is invalid OCI; treat colon as host:port
        return first
    return None


def looks_like_http_registry_host(host: str | None) -> bool:
    """True for local/private compose-style registry hosts (not public HTTPS registries)."""
    if not host:
        return False
    h = host.strip().lower()
    if not h:
        return False
    if h in {x.lower() for x in _BUILTIN_INSECURE_HOSTS}:
        return True
    hostname = h.rsplit(":", 1)[0] if re.match(r"^.+:\d+$", h) else h
    if hostname in _LOCAL_HOSTNAMES:
        return True
    # RFC1918 / link-local style hostnames used for private registries
    if hostname.startswith("10.") or hostname.startswith("192.168."):
        return True
    if re.match(r"^172\.(1[6-9]|2\d|3[0-1])\.", hostname):
        return True
    return False


def parse_insecure_hosts_env(raw: str | None) -> list[str]:
    """Parse comma/space-separated MSB_INSECURE_REGISTRIES."""
    if not raw or not str(raw).strip():
        return []
    out: list[str] = []
    for part in re.split(r"[\s,]+", str(raw).strip()):
        p = part.strip()
        if p and p not in out:
            out.append(p)
    return out


def resolve_insecure_registry_hosts(
    *,
    default_image: str | None = None,
    extra_hosts: str | list[str] | None = None,
) -> list[str]:
    """Build the list of registry hosts that should use plain HTTP."""
    hosts: list[str] = []

    def _add(h: str | None) -> None:
        if not h:
            return
        h = h.strip()
        if h and h not in hosts:
            hosts.append(h)

    for h in _BUILTIN_INSECURE_HOSTS:
        _add(h)

    if isinstance(extra_hosts, str):
        for h in parse_insecure_hosts_env(extra_hosts):
            _add(h)
    elif extra_hosts:
        for h in extra_hosts:
            _add(h)

    img_host = parse_image_registry_host(default_image)
    if looks_like_http_registry_host(img_host):
        _add(img_host)

    return hosts


def image_needs_insecure_pull(image: str | None, insecure_hosts: list[str] | None = None) -> bool:
    """Whether Sandbox.create should pass insecure=True for this image ref."""
    host = parse_image_registry_host(image)
    if not host:
        return False
    known = {h.lower() for h in (insecure_hosts or resolve_insecure_registry_hosts())}
    if host.lower() in known:
        return True
    return looks_like_http_registry_host(host)


def ensure_msb_insecure_registries(
    msb_home: Path | str,
    hosts: list[str] | None = None,
) -> Path:
    """Merge insecure=true for each host into $MSB_HOME/config.json. Returns config path."""
    home = Path(msb_home)
    home.mkdir(parents=True, exist_ok=True)
    config_path = home / "config.json"
    host_list = hosts if hosts is not None else resolve_insecure_registry_hosts()

    data: dict[str, Any] = {}
    if config_path.is_file():
        try:
            raw = config_path.read_text(encoding="utf-8")
            loaded = json.loads(raw) if raw.strip() else {}
            if isinstance(loaded, dict):
                data = loaded
            else:
                logger.warning("msb config.json is not an object; replacing with registries block")
                data = {}
        except json.JSONDecodeError as exc:
            logger.warning("msb config.json invalid JSON (%s); rewriting registries hosts", exc)
            data = {}

    registries = data.get("registries")
    if not isinstance(registries, dict):
        registries = {}
        data["registries"] = registries
    host_map = registries.get("hosts")
    if not isinstance(host_map, dict):
        host_map = {}
        registries["hosts"] = host_map

    changed = False
    for host in host_list:
        entry = host_map.get(host)
        if not isinstance(entry, dict):
            host_map[host] = {"insecure": True}
            changed = True
            continue
        if entry.get("insecure") is not True:
            entry = dict(entry)
            entry["insecure"] = True
            host_map[host] = entry
            changed = True

    if changed or not config_path.is_file():
        config_path.write_text(
            json.dumps(data, indent=2, sort_keys=False) + "\n",
            encoding="utf-8",
        )
        logger.info(
            "msb insecure registry config written path=%s hosts=%s",
            config_path,
            ", ".join(host_list),
        )
    else:
        logger.debug(
            "msb insecure registry config already ok path=%s hosts=%s",
            config_path,
            ", ".join(host_list),
        )
    return config_path


def msb_home_from_env(default: str | Path = "/root/.microsandbox") -> Path:
    return Path(os.environ.get("MSB_HOME") or default)


def prepull_default_image(
    image: str,
    *,
    insecure: bool = True,
    timeout_sec: float = 300.0,
) -> bool:
    """Best-effort `msb pull [--insecure] <image>`. Returns True on success."""
    if not image or not str(image).strip():
        return False
    msb = shutil.which("msb")
    if not msb:
        logger.debug("msb binary not on PATH; skip pre-pull")
        return False
    cmd = [msb, "pull"]
    if insecure:
        cmd.append("--insecure")
    cmd.append(str(image).strip())
    try:
        logger.info("pre-pulling guest image: %s", " ".join(cmd))
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
        if proc.returncode == 0:
            logger.info("pre-pull ok image=%s", image)
            return True
        err = (proc.stderr or proc.stdout or "").strip()[:500]
        logger.warning("pre-pull failed image=%s rc=%s: %s", image, proc.returncode, err)
        return False
    except subprocess.TimeoutExpired:
        logger.warning("pre-pull timed out image=%s after %ss", image, timeout_sec)
        return False
    except OSError as exc:
        logger.warning("pre-pull could not run msb: %s", exc)
        return False


# Tri-state: None = untested, True/False after first Sandbox.create with insecure=.
_INSECURE_CREATE_KWARG_SUPPORTED: bool | None = None


def sandbox_create_insecure_kwarg_supported() -> bool | None:
    """Whether microsandbox.Sandbox.create accepts insecure= (cached after first probe)."""
    return _INSECURE_CREATE_KWARG_SUPPORTED


def mark_sandbox_create_insecure_kwarg_unsupported() -> None:
    global _INSECURE_CREATE_KWARG_SUPPORTED
    _INSECURE_CREATE_KWARG_SUPPORTED = False


async def sandbox_create(name: str, *, use_insecure: bool, **kwargs: Any) -> Any:
    """Call microsandbox Sandbox.create.

    Plain-HTTP registries are configured via $MSB_HOME/config.json (see
    ensure_msb_insecure_registries). Some microsandbox builds also accept
    insecure= on create; older builds (e.g. 0.6.x) do not — we probe once and
    fall back to config.json-only.
    """
    from microsandbox import Sandbox

    global _INSECURE_CREATE_KWARG_SUPPORTED

    if use_insecure and _INSECURE_CREATE_KWARG_SUPPORTED is not False:
        try:
            sb = await Sandbox.create(name, insecure=True, **kwargs)
            _INSECURE_CREATE_KWARG_SUPPORTED = True
            return sb
        except TypeError as exc:
            if "insecure" not in str(exc):
                raise
            mark_sandbox_create_insecure_kwarg_unsupported()
            logger.info(
                "Sandbox.create does not accept insecure=; relying on MSB_HOME config.json"
            )
    return await Sandbox.create(name, **kwargs)


def registry_pull_error_hint(detail: str) -> str:
    """Append operator-facing hint when msb fails on HTTP registry / missing image."""
    lower = detail.lower()
    if "registry error" not in lower and "https://registry" not in lower and "image error" not in lower:
        return detail
    hint = (
        " Guest image pull failed. The embedded registry is plain HTTP — msb must use "
        "insecure registry config for registry:5000 (agent seeds $MSB_HOME/config.json). "
        "Ensure the guest is seeded (./deploy/local-registry.sh seed or "
        "ONLY=guest ./deploy/local-registry.sh build-push) and the agent can reach "
        "http://registry:5000/v2/."
    )
    if hint.strip() in detail:
        return detail
    return detail.rstrip() + hint
