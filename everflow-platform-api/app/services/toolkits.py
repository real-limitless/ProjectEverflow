"""App toolkit catalog: resolve clone URLs and seed local starter trees."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from app.config import Settings
from app.services.repo_clone import is_cloneable_url
from app.services.sandbox_agent_client import SandboxAgentClient, SandboxAgentError

logger = logging.getLogger(__name__)

# template_id → toolkit_id + default preview device frame
TEMPLATE_CATALOG: dict[str, dict[str, str]] = {
    "blank": {"toolkit_id": "", "preview_device": "full"},
    "web-npm": {"toolkit_id": "web-npm", "preview_device": "desktop"},
    "web-php": {"toolkit_id": "web-php", "preview_device": "desktop"},
    "mobile-ios": {"toolkit_id": "mobile-expo", "preview_device": "iphone-12"},
    "mobile-android": {"toolkit_id": "mobile-expo", "preview_device": "pixel-7"},
    "desktop-gui": {"toolkit_id": "desktop-gui", "preview_device": "desktop"},
    "python-api": {"toolkit_id": "python-api", "preview_device": "desktop"},
    "fullstack": {"toolkit_id": "fullstack", "preview_device": "desktop"},
}

SKIP_DIR_NAMES = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    ".expo",
    "dist",
    "web-build",
    "vendor",
}


def resolve_template_meta(template_id: str | None) -> dict[str, str]:
    if not template_id:
        return {"toolkit_id": "", "preview_device": "full"}
    return TEMPLATE_CATALOG.get(
        template_id,
        {"toolkit_id": "", "preview_device": "full"},
    )


def toolkit_repo_url(settings: Settings, toolkit_id: str) -> str | None:
    if not toolkit_id:
        return None
    base = (settings.toolkit_repo_base or "").strip()
    if not base:
        return None
    url = base.replace("{id}", toolkit_id).strip()
    return url or None


def toolkit_local_dir(settings: Settings, toolkit_id: str) -> Path | None:
    if not toolkit_id:
        return None
    root = Path(settings.toolkit_local_root).expanduser()
    path = (root / toolkit_id).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError:
        return None
    if path.is_dir():
        return path
    return None


def inject_toolkit_repo(
    repos: list[dict[str, Any]],
    *,
    template_id: str | None,
    settings: Settings,
    project_slug: str,
) -> list[dict[str, Any]]:
    """
    If the template has a toolkit and no cloneable remote is present, inject
    the configured toolkit git URL into the first repo (or create one).
    """
    meta = resolve_template_meta(template_id)
    toolkit_id = meta.get("toolkit_id") or ""
    url = toolkit_repo_url(settings, toolkit_id)
    if not url or not is_cloneable_url(url):
        return repos

    if any(is_cloneable_url(str(r.get("url") or "")) for r in repos):
        return repos

    if repos:
        updated = [dict(r) for r in repos]
        updated[0]["url"] = url
        updated[0]["branch"] = updated[0].get("branch") or "main"
        updated[0]["provider"] = updated[0].get("provider") or "github"
        updated[0]["clone_status"] = "pending"
        return updated

    return [
        {
            "id": toolkit_id or "app",
            "label": f"{project_slug}/{toolkit_id or 'app'}",
            "url": url,
            "branch": "main",
            "provider": "github",
            "active": True,
            "clone_status": "pending",
        }
    ]


def _iter_toolkit_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel_parts = path.relative_to(root).parts
        if any(part in SKIP_DIR_NAMES for part in rel_parts):
            continue
        # Skip huge / binary-ish files by extension
        if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".woff", ".woff2"}:
            continue
        if path.stat().st_size > 512_000:
            continue
        files.append(path)
    return sorted(files)


async def seed_toolkit_into_sandbox(
    client: SandboxAgentClient,
    sandbox_name: str,
    *,
    template_id: str | None,
    settings: Settings,
    dest_subdir: str | None = None,
) -> dict[str, Any]:
    """
    Copy local toolkit files into the sandbox workspace when no git URL is configured.
    Returns a status dict for logging / repo clone_status.
    """
    meta = resolve_template_meta(template_id)
    toolkit_id = meta.get("toolkit_id") or ""
    if not toolkit_id:
        return {"seeded": False, "reason": "no_toolkit"}

    if toolkit_repo_url(settings, toolkit_id):
        return {"seeded": False, "reason": "remote_configured"}

    local = toolkit_local_dir(settings, toolkit_id)
    if local is None:
        logger.warning("toolkit local dir missing toolkit_id=%s root=%s", toolkit_id, settings.toolkit_local_root)
        return {"seeded": False, "reason": "local_missing", "toolkit_id": toolkit_id}

    files = _iter_toolkit_files(local)
    if not files:
        return {"seeded": False, "reason": "empty", "toolkit_id": toolkit_id}

    dest_root = (dest_subdir or toolkit_id).strip().strip("/") or toolkit_id
    written = 0
    errors: list[str] = []

    # Ensure destination directory exists
    try:
        await client.exec(
            sandbox_name,
            f"mkdir -p {_shell_quote(dest_root)}",
            timeout_seconds=30,
        )
    except SandboxAgentError as exc:
        return {"seeded": False, "reason": "mkdir_failed", "error": str(exc)[:500]}

    for path in files:
        rel = path.relative_to(local).as_posix()
        guest_path = f"{dest_root}/{rel}"
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        parent = str(Path(guest_path).parent)
        if parent and parent not in (".", dest_root):
            try:
                await client.exec(
                    sandbox_name,
                    f"mkdir -p {_shell_quote(parent)}",
                    timeout_seconds=15,
                )
            except SandboxAgentError as exc:
                errors.append(f"{parent}: {exc}"[:200])
                continue
        try:
            await client.write_fs(sandbox_name, guest_path, content)
            written += 1
        except SandboxAgentError as exc:
            errors.append(f"{guest_path}: {exc}"[:200])

    logger.info(
        "seeded toolkit=%s sandbox=%s files=%s errors=%s",
        toolkit_id,
        sandbox_name,
        written,
        len(errors),
    )
    return {
        "seeded": written > 0,
        "toolkit_id": toolkit_id,
        "files": written,
        "errors": errors[:5],
        "local_path": dest_root,
    }


def _shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"
