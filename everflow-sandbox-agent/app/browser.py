"""Playwright browser harness helpers for OpenCode sandboxes.

Opt-in: marketplace / harness installs mcp.playwright. Mode is headless by
default; headed uses the guest Desktop (X11/noVNC). Actual browse tools come
from official @playwright/mcp via everflow-playwright-mcp wrapper.
"""

from __future__ import annotations

import base64
import json
import logging
from pathlib import Path
from typing import Any

from app.desktop import desktop_listening, ensure_guest_desktop
from app.opencode_harness import OPENCODE_JSON, _guest_read_text, _guest_write_text, load_json_file

logger = logging.getLogger(__name__)

BROWSER_MODE_REL = ".everflow/browser.mode"
BROWSER_ENABLED_REL = ".everflow/browser.enabled"
PLAYWRIGHT_MCP_KEY = "playwright"
BROWSERS_PATH = "/opt/everflow-browsers"
WRAPPER_BIN = "/usr/local/bin/everflow-playwright-mcp"
_HOST_WRAPPER = Path(__file__).with_name("everflow_playwright_mcp.sh")

DEFAULT_PLAYWRIGHT_MCP: dict[str, Any] = {
    "type": "local",
    "command": ["everflow-playwright-mcp"],
    "enabled": True,
    "environment": {
        "PLAYWRIGHT_BROWSERS_PATH": BROWSERS_PATH,
        "DISPLAY": ":99",
    },
}


def normalize_mode(raw: str | None) -> str:
    text = (raw or "headless").strip().lower()
    if text in ("headed", "headful", "visible"):
        return "headed"
    return "headless"


def playwright_mcp_config() -> dict[str, Any]:
    return {
        "type": "local",
        "command": list(DEFAULT_PLAYWRIGHT_MCP["command"]),
        "enabled": True,
        "environment": dict(DEFAULT_PLAYWRIGHT_MCP["environment"]),
    }


def is_playwright_mcp_entry(cfg: Any) -> bool:
    if not isinstance(cfg, dict):
        return False
    if cfg.get("enabled") is False:
        return False
    cmd = cfg.get("command")
    if isinstance(cmd, list):
        joined = " ".join(str(c) for c in cmd).lower()
    else:
        joined = str(cmd or "").lower()
    return (
        "playwright" in joined
        or "everflow-playwright-mcp" in joined
        or "@playwright/mcp" in joined
    )


def apply_browser_stamps_host(workspace: Path, *, enabled: bool, mode: str | None = None) -> None:
    """Write or clear browser stamp files on a host-mounted workspace."""
    root = workspace.resolve()
    everflow = root / ".everflow"
    everflow.mkdir(parents=True, exist_ok=True)
    mode_path = root / BROWSER_MODE_REL
    enabled_path = root / BROWSER_ENABLED_REL
    if enabled:
        if mode is not None:
            mode_path.write_text(normalize_mode(mode) + "\n", encoding="utf-8")
        elif not mode_path.is_file():
            mode_path.write_text("headless\n", encoding="utf-8")
        enabled_path.write_text("1\n", encoding="utf-8")
    else:
        for path in (mode_path, enabled_path):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass


def sync_browser_stamps_from_pack(workspace: Path, pack: dict[str, Any]) -> dict[str, Any]:
    """After harness apply: enable/disable stamps when playwright MCP changes."""
    mcp_in = pack.get("mcp")
    if not isinstance(mcp_in, dict):
        return {"touched": False}
    if PLAYWRIGHT_MCP_KEY not in mcp_in:
        return {"touched": False}
    cfg = mcp_in.get(PLAYWRIGHT_MCP_KEY)
    if cfg is None:
        apply_browser_stamps_host(workspace, enabled=False)
        return {"touched": True, "enabled": False}
    if is_playwright_mcp_entry(cfg) or (isinstance(cfg, dict) and cfg.get("enabled") is not False):
        apply_browser_stamps_host(workspace, enabled=True)
        return {"touched": True, "enabled": True}
    apply_browser_stamps_host(workspace, enabled=False)
    return {"touched": True, "enabled": False}


async def sync_browser_stamps_guest(
    backend: Any,
    sandbox_name: str,
    pack: dict[str, Any],
) -> dict[str, Any]:
    mcp_in = pack.get("mcp")
    if not isinstance(mcp_in, dict) or PLAYWRIGHT_MCP_KEY not in mcp_in:
        return {"touched": False}
    cfg = mcp_in.get(PLAYWRIGHT_MCP_KEY)
    if cfg is None:
        await _guest_write_text(backend, sandbox_name, BROWSER_ENABLED_REL, "")
        # Best-effort clear
        try:
            await backend.exec(
                sandbox_name,
                "rm",
                ["-f", BROWSER_MODE_REL, BROWSER_ENABLED_REL],
                cwd="/workspace",
                timeout_seconds=10,
            )
        except Exception:  # noqa: BLE001
            pass
        return {"touched": True, "enabled": False}
    await _guest_write_text(backend, sandbox_name, BROWSER_ENABLED_REL, "1\n")
    existing = await _guest_read_text(backend, sandbox_name, BROWSER_MODE_REL)
    if not (existing or "").strip():
        await _guest_write_text(backend, sandbox_name, BROWSER_MODE_REL, "headless\n")
    return {"touched": True, "enabled": True}


async def _install_wrapper(exec_fn: Any, name: str) -> bool:
    """Heal stale guest images with the agent-bundled wrapper script."""
    try:
        body = _HOST_WRAPPER.read_bytes()
    except OSError as exc:
        logger.warning("playwright wrapper missing (%s): %s", _HOST_WRAPPER, exc)
        return False
    b64 = base64.b64encode(body).decode("ascii")
    install = (
        "import base64, pathlib\n"
        f"p=pathlib.Path({WRAPPER_BIN!r})\n"
        f"p.write_bytes(base64.b64decode({b64!r}))\n"
        "p.chmod(0o755)\n"
        "print('installed', p)\n"
    )
    try:
        code, _, stderr = await exec_fn(
            name,
            "python3",
            ["-c", install],
            cwd="/workspace",
            env=None,
            timeout_seconds=20,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("playwright wrapper install failed name=%s: %s", name, exc)
        return False
    if code != 0:
        logger.warning("playwright wrapper install exit name=%s err=%s", name, stderr)
        return False
    return True


async def _probe_cmd(backend: Any, name: str, script: str, *, timeout: float = 15) -> tuple[int, str, str]:
    return await backend.exec(
        name,
        "python3",
        ["-c", script],
        cwd="/workspace",
        timeout_seconds=timeout,
    )


async def browser_status(backend: Any, name: str) -> dict[str, Any]:
    """Collect browser harness status from the guest workspace."""
    mode_raw = (await _guest_read_text(backend, name, BROWSER_MODE_REL) or "").strip()
    enabled_stamp = (await _guest_read_text(backend, name, BROWSER_ENABLED_REL) or "").strip()
    oc_text = await _guest_read_text(backend, name, OPENCODE_JSON)
    oc: dict[str, Any] = {}
    if oc_text:
        try:
            parsed = json.loads(oc_text)
            if isinstance(parsed, dict):
                oc = parsed
        except json.JSONDecodeError:
            pass
    mcp = oc.get("mcp") if isinstance(oc.get("mcp"), dict) else {}
    pw_cfg = mcp.get(PLAYWRIGHT_MCP_KEY)
    mcp_enabled = is_playwright_mcp_entry(pw_cfg)

    wrapper_ok = False
    browsers_ok = False
    try:
        code, stdout, _ = await _probe_cmd(
            backend,
            name,
            (
                "import os, pathlib\n"
                f"w=pathlib.Path({WRAPPER_BIN!r})\n"
                f"b=pathlib.Path({BROWSERS_PATH!r})\n"
                "print('wrapper', w.is_file() or bool(__import__('shutil').which('everflow-playwright-mcp')))\n"
                "print('browsers', b.is_dir() and any(b.iterdir()) if b.is_dir() else False)\n"
            ),
        )
        if code == 0:
            for line in stdout.splitlines():
                if line.startswith("wrapper "):
                    wrapper_ok = line.split(None, 1)[-1].lower() in ("true", "1", "yes")
                if line.startswith("browsers "):
                    browsers_ok = line.split(None, 1)[-1].lower() in ("true", "1", "yes")
    except Exception as exc:  # noqa: BLE001
        logger.debug("browser probe failed name=%s: %s", name, exc)

    desktop_up = False
    try:
        desktop_up = await desktop_listening(backend.exec, name)
    except Exception:  # noqa: BLE001
        desktop_up = False

    mode = normalize_mode(mode_raw or "headless")
    enabled = bool(enabled_stamp == "1" or mcp_enabled)

    hints: list[str] = []
    if enabled and not wrapper_ok and not browsers_ok:
        hints.append(
            "Playwright runtime missing in guest — rebuild everflow-sandbox-guest "
            "or install @playwright/mcp + chromium browsers"
        )
    elif enabled and not browsers_ok:
        hints.append(f"Browsers path empty ({BROWSERS_PATH}); rebuild guest image recommended")
    if mode == "headed" and not desktop_up:
        hints.append("Headed mode needs Desktop (noVNC); call browser_set_mode headed or open Desktop panel")

    return {
        "sandbox_name": name,
        "enabled": enabled,
        "mode": mode,
        "mcp_configured": mcp_enabled,
        "wrapper_present": wrapper_ok,
        "browsers_present": browsers_ok,
        "desktop_listening": desktop_up,
        "display": ":99",
        "browsers_path": BROWSERS_PATH,
        "hints": hints,
        "playwright_mcp": pw_cfg if isinstance(pw_cfg, dict) else None,
    }


async def _recycle_playwright_mcp(exec_fn: Any, name: str) -> dict[str, Any]:
    """Stop Playwright MCP children so OpenCode respawns them with the new mode.

    Must NOT kill ``opencode serve``: ``browser_set_mode`` is often invoked via
    Everflow MCP inside that process, and a full restart aborts the in-flight
    tool call (chat hangs forever).
    """
    script = (
        "pkill -f 'everflow-playwright-mcp|@playwright/mcp|playwright-mcp' "
        "2>/dev/null || true; echo recycled"
    )
    try:
        code, stdout, stderr = await exec_fn(
            name,
            "sh",
            ["-c", script],
            cwd="/workspace",
            env=None,
            timeout_seconds=15,
        )
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc), "playwright_mcp_recycled": False}
    # pkill exits 1 when nothing matched — still success for our purposes.
    return {
        "ok": True,
        "playwright_mcp_recycled": True,
        "full_opencode_restart": False,
        "exit_code": code,
        "stdout": (stdout or "")[:120],
        "stderr": (stderr or "")[:120],
    }


async def set_browser_mode(
    backend: Any,
    name: str,
    *,
    mode: str,
    restart_opencode: bool = True,
) -> dict[str, Any]:
    """Set headless/headed mode, ensure desktop when headed, reload Playwright MCP.

    ``restart_opencode`` historically force-restarted ``opencode serve``. That
    deadlocks when the call arrives through Everflow MCP (child of OpenCode).
    It now only recycles Playwright MCP so ``browser.mode`` is re-read.
    """
    resolved = normalize_mode(mode)
    await _install_wrapper(backend.exec, name)
    await _guest_write_text(backend, name, BROWSER_MODE_REL, resolved + "\n")
    await _guest_write_text(backend, name, BROWSER_ENABLED_REL, "1\n")

    # Normalize MCP entry if present
    oc_text = await _guest_read_text(backend, name, OPENCODE_JSON)
    oc: dict[str, Any] = {}
    if oc_text:
        try:
            parsed = json.loads(oc_text)
            if isinstance(parsed, dict):
                oc = parsed
        except json.JSONDecodeError:
            oc = {}
    mcp = oc.get("mcp") if isinstance(oc.get("mcp"), dict) else {}
    if PLAYWRIGHT_MCP_KEY in mcp and mcp.get(PLAYWRIGHT_MCP_KEY) is not None:
        mcp[PLAYWRIGHT_MCP_KEY] = playwright_mcp_config()
        oc["mcp"] = mcp
        if "$schema" not in oc:
            oc["$schema"] = "https://opencode.ai/config.json"
        await _guest_write_text(
            backend,
            name,
            OPENCODE_JSON,
            json.dumps(oc, indent=2, ensure_ascii=False) + "\n",
        )

    desktop: dict[str, Any] | None = None
    if resolved == "headed":
        try:
            await ensure_guest_desktop(backend.exec, name)
            desktop = {"ok": True, "listening": await desktop_listening(backend.exec, name)}
        except Exception as exc:  # noqa: BLE001
            logger.warning("ensure desktop for headed browser failed name=%s: %s", name, exc)
            desktop = {"ok": False, "error": str(exc)}

    opencode_restart: dict[str, Any] | None = None
    if restart_opencode:
        try:
            opencode_restart = await _recycle_playwright_mcp(backend.exec, name)
        except Exception as exc:  # noqa: BLE001
            # OpenCode / Playwright may not be running yet — mode still applied.
            logger.info("playwright MCP recycle after browser mode skipped name=%s: %s", name, exc)
            opencode_restart = {"ok": False, "skipped": True, "error": str(exc)}

    status = await browser_status(backend, name)
    status["mode"] = resolved
    status["desktop_action"] = desktop
    status["opencode_restart"] = opencode_restart
    status["ok"] = True
    return status


async def normalize_playwright_mcp_if_enabled(backend: Any, name: str) -> dict[str, Any]:
    """On OpenCode ensure: rewrite legacy npx playwright MCP to Everflow wrapper."""
    oc_text = await _guest_read_text(backend, name, OPENCODE_JSON)
    if not oc_text:
        return {"normalized": False, "reason": "no opencode.json"}
    try:
        oc = json.loads(oc_text)
    except json.JSONDecodeError:
        return {"normalized": False, "reason": "invalid opencode.json"}
    if not isinstance(oc, dict):
        return {"normalized": False}
    mcp = oc.get("mcp") if isinstance(oc.get("mcp"), dict) else {}
    cfg = mcp.get(PLAYWRIGHT_MCP_KEY)
    if cfg is None:
        enabled = (await _guest_read_text(backend, name, BROWSER_ENABLED_REL) or "").strip()
        if enabled != "1":
            return {"normalized": False, "reason": "not enabled"}
        # Stamp says enabled but MCP missing — re-inject config
        mcp[PLAYWRIGHT_MCP_KEY] = playwright_mcp_config()
        oc["mcp"] = mcp
        await _guest_write_text(
            backend,
            name,
            OPENCODE_JSON,
            json.dumps(oc, indent=2, ensure_ascii=False) + "\n",
        )
        await _install_wrapper(backend.exec, name)
        return {"normalized": True, "reinjected": True}

    if not is_playwright_mcp_entry(cfg) and not isinstance(cfg, dict):
        return {"normalized": False}

    desired = playwright_mcp_config()
    needs = True
    if isinstance(cfg, dict):
        cmd = cfg.get("command")
        env = cfg.get("environment") if isinstance(cfg.get("environment"), dict) else {}
        if cmd == desired["command"] and env.get("PLAYWRIGHT_BROWSERS_PATH") == BROWSERS_PATH:
            needs = False
    if needs:
        mcp[PLAYWRIGHT_MCP_KEY] = desired
        oc["mcp"] = mcp
        await _guest_write_text(
            backend,
            name,
            OPENCODE_JSON,
            json.dumps(oc, indent=2, ensure_ascii=False) + "\n",
        )
    await _install_wrapper(backend.exec, name)
    await _guest_write_text(backend, name, BROWSER_ENABLED_REL, "1\n")
    mode_raw = (await _guest_read_text(backend, name, BROWSER_MODE_REL) or "").strip()
    if not mode_raw:
        await _guest_write_text(backend, name, BROWSER_MODE_REL, "headless\n")
        mode_raw = "headless"
    if normalize_mode(mode_raw) == "headed":
        try:
            await ensure_guest_desktop(backend.exec, name)
        except Exception as exc:  # noqa: BLE001
            logger.warning("headed browser desktop ensure failed name=%s: %s", name, exc)
    return {"normalized": True, "rewrote": needs, "mode": normalize_mode(mode_raw)}


def apply_playwright_mcp_host(workspace: Path) -> None:
    """Host-path ensure: normalize playwright MCP entry + stamps."""
    root = workspace.resolve()
    oc_path = root / OPENCODE_JSON
    oc = load_json_file(oc_path)
    mcp = oc.get("mcp") if isinstance(oc.get("mcp"), dict) else {}
    cfg = mcp.get(PLAYWRIGHT_MCP_KEY)
    enabled_path = root / BROWSER_ENABLED_REL
    stamp = enabled_path.is_file() and enabled_path.read_text(encoding="utf-8").strip() == "1"
    if cfg is None and not stamp:
        return
    mcp[PLAYWRIGHT_MCP_KEY] = playwright_mcp_config()
    oc["mcp"] = mcp
    if "$schema" not in oc:
        oc["$schema"] = "https://opencode.ai/config.json"
    oc_path.write_text(json.dumps(oc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    apply_browser_stamps_host(root, enabled=True)
