"""Inject Everflow MCP config into sandbox workspaces (host path or guest FS)."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Any

from app.opencode_harness import OPENCODE_JSON, _guest_read_text, _guest_write_text

logger = logging.getLogger(__name__)

# Prefer python -m so OpenCode's minimal PATH does not need /usr/local/bin.
# Bare "everflow-mcp" fails with: Executable not found in $PATH: "everflow-mcp"
DEFAULT_MCP_COMMAND: list[str] = ["python3", "-m", "everflow_mcp"]
MCP_ENV_REL = ".everflow/mcp.env"
# Written after a successful install from the agent bundle; compared on ensure.
MCP_PACKAGE_STAMP_REL = ".everflow/mcp.package.sha"
# Local listener inside guest for API reverse tunnel
DEFAULT_GUEST_API_PORT = 18765
# Agent image ships the package here (deploy/sandbox-agent.Dockerfile).
# Dev compose should bind-mount ./everflow-mcp → this path so upgrades land without rebuild.
AGENT_MCP_ROOT = Path(os.environ.get("EVERFLOW_MCP_SRC", "/opt/everflow-mcp"))
# Copied into guest when the microVM image was built without everflow-mcp or is stale.
GUEST_MCP_VENDOR_REL = ".everflow/vendor/everflow-mcp"
# Files required for a pip-installable tree (tests/docs optional).
_VENDOR_FILES = (
    "pyproject.toml",
    "README.md",
    "src/everflow_mcp/__init__.py",
    "src/everflow_mcp/__main__.py",
    "src/everflow_mcp/client.py",
    "src/everflow_mcp/server.py",
)


def _normalize_command(command: str | list[str] | None) -> list[str]:
    if command is None:
        return list(DEFAULT_MCP_COMMAND)
    if isinstance(command, list):
        parts = [str(c) for c in command if str(c).strip()]
        return parts or list(DEFAULT_MCP_COMMAND)
    text = str(command).strip()
    if not text:
        return list(DEFAULT_MCP_COMMAND)
    # Legacy single binary name → module invocation (PATH-safe)
    if text == "everflow-mcp" or text.endswith("/everflow-mcp"):
        return list(DEFAULT_MCP_COMMAND)
    return [text]


def build_everflow_mcp_config(
    *,
    api_url: str,
    token: str,
    project_id: str,
    command: str | list[str] | None = None,
) -> dict[str, Any]:
    return {
        "type": "local",
        "command": _normalize_command(command),
        "enabled": True,
        "environment": {
            "EVERFLOW_API_URL": api_url,
            "EVERFLOW_TOKEN": token,
            "EVERFLOW_PROJECT_ID": project_id,
        },
    }


def agent_mcp_fingerprint(root: Path | None = None) -> str | None:
    """Stable content hash of the agent-bundled everflow-mcp sources.

    Returns None if the package tree is missing or incomplete.
    """
    base = Path(root) if root is not None else AGENT_MCP_ROOT
    if not base.is_dir():
        return None
    missing = [rel for rel in _VENDOR_FILES if not (base / rel).is_file()]
    if missing:
        return None
    digest = hashlib.sha256()
    for rel in _VENDOR_FILES:
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update((base / rel).read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


async def ensure_everflow_mcp_package(backend: Any, sandbox_name: str) -> dict[str, Any]:
    """Ensure guest ``everflow_mcp`` matches the agent-bundled package.

    Prebaked guest images and previous ensures may leave a *stale* install.
    We only skip reinstall when:

    1. ``import everflow_mcp`` works, **and**
    2. workspace stamp (``.everflow/mcp.package.sha``) equals the agent source fingerprint.

    Otherwise copy agent sources into the workspace and ``pip install --force-reinstall``
    so OpenCode picks up new MCP tools after ensure restarts it.
    """
    fingerprint = agent_mcp_fingerprint()
    stamp = (await _guest_read_text(backend, sandbox_name, MCP_PACKAGE_STAMP_REL) or "").strip()

    try:
        code, _stdout, _stderr = await backend.exec(
            sandbox_name,
            "python3",
            ["-c", "import everflow_mcp; print(getattr(everflow_mcp, '__version__', 'unknown'))"],
            cwd="/workspace",
            timeout_seconds=20,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("everflow_mcp probe failed name=%s: %s", sandbox_name, exc)
        return {"installed": False, "error": f"probe failed: {exc}"}

    importable = code == 0
    if importable and fingerprint and stamp == fingerprint:
        return {
            "installed": True,
            "source": "existing",
            "fingerprint": fingerprint,
            "upgraded": False,
        }

    # No agent bundle: keep whatever is already importable (cannot upgrade).
    if fingerprint is None:
        if importable:
            return {
                "installed": True,
                "source": "existing",
                "upgraded": False,
                "warning": f"agent package missing at {AGENT_MCP_ROOT}; cannot upgrade",
            }
        return {
            "installed": False,
            "error": f"agent package missing at {AGENT_MCP_ROOT}",
            "source": "vendor",
        }

    if not AGENT_MCP_ROOT.is_dir():
        return {
            "installed": False,
            "error": f"agent package missing at {AGENT_MCP_ROOT}",
            "source": "vendor",
        }

    try:
        for rel in _VENDOR_FILES:
            body = (AGENT_MCP_ROOT / rel).read_text(encoding="utf-8")
            await _guest_write_text(
                backend,
                sandbox_name,
                f"{GUEST_MCP_VENDOR_REL}/{rel}",
                body,
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("everflow_mcp vendor copy failed name=%s: %s", sandbox_name, exc)
        return {"installed": False, "error": f"vendor copy failed: {exc}", "source": "vendor"}

    # force-reinstall so site-packages picks up tool changes even when version is unchanged
    install_sh = (
        "set -eu; "
        "export PIP_BREAK_SYSTEM_PACKAGES=1 PIP_DISABLE_PIP_VERSION_CHECK=1; "
        f"pip3 install --no-cache-dir --force-reinstall /workspace/{GUEST_MCP_VENDOR_REL}; "
        "python3 -c 'import everflow_mcp; print(everflow_mcp.__file__); "
        "print(getattr(everflow_mcp, \"__version__\", \"unknown\"))'"
    )
    try:
        code, stdout, stderr = await backend.exec(
            sandbox_name,
            "sh",
            ["-c", install_sh],
            cwd="/workspace",
            timeout_seconds=180,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("everflow_mcp pip install failed name=%s: %s", sandbox_name, exc)
        return {"installed": False, "error": f"pip install failed: {exc}", "source": "vendor"}

    if code != 0:
        detail = (stderr or stdout or "pip install failed").strip()[:500]
        logger.warning(
            "everflow_mcp install exit=%s name=%s detail=%s",
            code,
            sandbox_name,
            detail,
        )
        return {"installed": False, "error": detail, "source": "vendor"}

    try:
        await _guest_write_text(backend, sandbox_name, MCP_PACKAGE_STAMP_REL, fingerprint + "\n")
    except Exception as exc:  # noqa: BLE001
        logger.warning("everflow_mcp stamp write failed name=%s: %s", sandbox_name, exc)

    out_lines = [ln.strip() for ln in (stdout or "").strip().splitlines() if ln.strip()]
    installed_path = out_lines[-2] if len(out_lines) >= 2 else (out_lines[-1] if out_lines else None)
    installed_version = out_lines[-1] if out_lines else None
    source = "upgraded" if importable else "vendor"
    logger.info(
        "everflow_mcp %s into guest name=%s path=%s version=%s fingerprint=%s",
        source,
        sandbox_name,
        installed_path,
        installed_version,
        fingerprint[:12],
    )
    return {
        "installed": True,
        "source": source,
        "path": installed_path,
        "version": installed_version,
        "fingerprint": fingerprint,
        "upgraded": source == "upgraded" or (not importable),
    }


# Injected into workspace AGENTS.md so OpenCode agents prefer knowledge_search.
KNOWLEDGE_POLICY_MARKER = "<!-- everflow-knowledge-policy -->"
KNOWLEDGE_POLICY_MD = """<!-- everflow-knowledge-policy -->
## Everflow project knowledge

Project documentation, passwords, API keys, and secrets are stored in **Everflow Knowledge canvases**
and indexed into the platform vector store (chunk embeddings).

- Use the **everflow** MCP tools — especially `knowledge_search` — before answering
  questions about project docs, config, passwords, keys, tokens, or a "knowledge key".
- Knowledge is **not** listed under MCP resources. An empty resources list does **not**
  mean knowledge is empty.
- If `knowledge_search` returns hits, quote the chunk text and name the canvas.
- Fallback: `list_canvases` → `get_canvas` when search returns nothing but canvases exist.
"""


def merge_opencode_mcp(existing: dict[str, Any], mcp_entry: dict[str, Any]) -> dict[str, Any]:
    """Merge everflow MCP entry into opencode.json without clobbering other keys."""
    data = dict(existing) if existing else {}
    data.setdefault("$schema", "https://opencode.ai/config.json")
    mcp_block = data.get("mcp") if isinstance(data.get("mcp"), dict) else {}
    mcp_block = dict(mcp_block)
    mcp_block["everflow"] = mcp_entry
    data["mcp"] = mcp_block
    return data


def merge_knowledge_policy_markdown(existing: str | None) -> str:
    """Upsert the Everflow knowledge policy block into AGENTS.md body."""
    body = (existing or "").strip()
    if KNOWLEDGE_POLICY_MARKER in body:
        # Replace existing block (marker through next HTML comment or EOF)
        import re

        pattern = re.compile(
            re.escape(KNOWLEDGE_POLICY_MARKER) + r".*?(?=\n<!--|\Z)",
            re.DOTALL,
        )
        body = pattern.sub(KNOWLEDGE_POLICY_MD.strip(), body).strip()
        return body + "\n"
    if body:
        return body + "\n\n" + KNOWLEDGE_POLICY_MD.strip() + "\n"
    return KNOWLEDGE_POLICY_MD.strip() + "\n"


def write_everflow_mcp_host(
    workspace: Path,
    *,
    api_url: str,
    token: str,
    project_id: str,
    command: str | list[str] | None = None,
) -> dict[str, Any]:
    """Write MCP env + opencode.json on a host-accessible workspace path."""
    ws = Path(workspace)
    ef = ws / ".everflow"
    ef.mkdir(parents=True, exist_ok=True)
    env_path = ef / "mcp.env"
    try:
        env_path.write_text(
            f'EVERFLOW_API_URL="{api_url}"\n'
            f'EVERFLOW_TOKEN="{token}"\n'
            f'EVERFLOW_PROJECT_ID="{project_id}"\n',
            encoding="utf-8",
        )
        try:
            env_path.chmod(0o600)
        except OSError:
            pass
    except OSError as exc:
        return {"configured": False, "error": f"write mcp.env failed: {exc}", "mode": "host"}

    mcp_cfg = build_everflow_mcp_config(
        api_url=api_url, token=token, project_id=project_id, command=command
    )
    cfg_path = ws / OPENCODE_JSON
    existing: dict[str, Any] = {}
    if cfg_path.exists():
        try:
            raw = json.loads(cfg_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                existing = raw
        except (OSError, json.JSONDecodeError):
            existing = {}
    merged = merge_opencode_mcp(existing, mcp_cfg)
    try:
        cfg_path.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        return {"configured": False, "error": f"write opencode.json failed: {exc}", "mode": "host"}

    # Project-level agent instructions so OpenCode prefers knowledge_search.
    agents_md = ws / "AGENTS.md"
    try:
        prev = agents_md.read_text(encoding="utf-8") if agents_md.is_file() else ""
        agents_md.write_text(merge_knowledge_policy_markdown(prev), encoding="utf-8")
    except OSError as exc:
        logger.debug("host AGENTS.md knowledge policy write failed: %s", exc)

    cmd = _normalize_command(command)
    return {
        "configured": True,
        "mode": "host",
        "command": cmd,
        "env_path": str(env_path),
        "project_id": project_id,
        "api_url": api_url,
    }


async def write_everflow_mcp_guest(
    backend: Any,
    sandbox_name: str,
    *,
    api_url: str,
    token: str,
    project_id: str,
    command: str | list[str] | None = None,
) -> dict[str, Any]:
    """Write MCP env + opencode.json into the guest workspace via write_fs."""
    mcp_cfg = build_everflow_mcp_config(
        api_url=api_url, token=token, project_id=project_id, command=command
    )
    env_body = (
        f'EVERFLOW_API_URL="{api_url}"\n'
        f'EVERFLOW_TOKEN="{token}"\n'
        f'EVERFLOW_PROJECT_ID="{project_id}"\n'
    )
    try:
        await _guest_write_text(backend, sandbox_name, MCP_ENV_REL, env_body)
    except Exception as exc:  # noqa: BLE001
        logger.warning("guest mcp.env write failed name=%s: %s", sandbox_name, exc)
        return {"configured": False, "error": f"write mcp.env failed: {exc}", "mode": "guest"}

    oc_raw = await _guest_read_text(backend, sandbox_name, OPENCODE_JSON)
    existing: dict[str, Any] = {}
    if oc_raw:
        try:
            parsed = json.loads(oc_raw)
            if isinstance(parsed, dict):
                existing = parsed
        except json.JSONDecodeError:
            existing = {}
    merged = merge_opencode_mcp(existing, mcp_cfg)
    try:
        await _guest_write_text(
            backend,
            sandbox_name,
            OPENCODE_JSON,
            json.dumps(merged, indent=2) + "\n",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("guest opencode.json write failed name=%s: %s", sandbox_name, exc)
        return {
            "configured": False,
            "error": f"write opencode.json failed: {exc}",
            "mode": "guest",
        }

    try:
        prev_agents = await _guest_read_text(backend, sandbox_name, "AGENTS.md")
        await _guest_write_text(
            backend,
            sandbox_name,
            "AGENTS.md",
            merge_knowledge_policy_markdown(prev_agents),
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("guest AGENTS.md knowledge policy write failed name=%s: %s", sandbox_name, exc)

    cmd = _normalize_command(command)
    return {
        "configured": True,
        "mode": "guest",
        "command": cmd,
        "env_path": f"/workspace/{MCP_ENV_REL}",
        "project_id": project_id,
        "api_url": api_url,
    }
