"""Clone project repositories into a running sandbox workspace."""

from __future__ import annotations

import logging
import re
import shlex
from typing import Any
from urllib.parse import urlparse

from app.services.sandbox_agent_client import SandboxAgentClient, SandboxAgentError

logger = logging.getLogger(__name__)

CLONE_TIMEOUT_SECONDS = 300.0
MAX_REPOS = 10

# Markers written by Everflow bootstrap that do not count as real workspace content
_EVERFLOW_ONLY = frozenset({".everflow", ".gitkeep", "README.md"})


def path_hint_from_url(url: str | None) -> str:
    """Basename of a git remote URL (org/app.git → app)."""
    if not url:
        return ""
    s = url.strip()
    if not s:
        return ""
    s = re.sub(r"\.git$", "", s, flags=re.IGNORECASE)
    # git@host:org/repo
    if s.startswith("git@"):
        s = s.split(":", 1)[-1]
    elif "://" in s:
        try:
            path = urlparse(s).path
            s = path.lstrip("/")
        except Exception:  # noqa: BLE001
            pass
    parts = [p for p in re.split(r"[/\\]", s) if p]
    if not parts:
        return ""
    name = parts[-1]
    # Sanitize to a single safe path segment
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip(".-")
    return name[:80] if name else ""


def path_hint_from_label(label: str | None) -> str:
    if not label:
        return ""
    s = label.strip().replace("\\", "/")
    if not s:
        return ""
    s = re.sub(r"\.git$", "", s, flags=re.IGNORECASE)
    parts = [p for p in s.split("/") if p]
    name = parts[-1] if parts else s
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip(".-")
    return name[:80] if name else ""


def sanitize_local_path(raw: str | None) -> str:
    if raw is None or raw.strip() in ("", ".", "./"):
        return "."
    p = raw.strip().replace("\\", "/")
    if p.startswith("/"):
        return "."
    while p.startswith("./"):
        p = p[2:]
    parts = [seg for seg in p.split("/") if seg and seg != "."]
    if not parts or any(seg == ".." for seg in parts):
        return "."
    return "/".join(parts)


def is_cloneable_url(url: str | None) -> bool:
    if not url:
        return False
    s = url.strip()
    if not s:
        return False
    if s.startswith("https://") or s.startswith("http://"):
        return True
    if s.startswith("git@"):
        return True
    if s.startswith("ssh://"):
        return True
    return False


def resolve_named_dest(
    *,
    url: str | None,
    label: str | None = None,
    repo_id: str | None = None,
    local_path: str | None = None,
) -> str:
    """
    Workspace-relative directory for a remote. Always a single path segment
    (never '.'): every repo lives under /workspace/<name>/.
    """
    preferred = sanitize_local_path(local_path)
    if preferred and preferred != ".":
        # Only allow a single relative segment for clone roots
        if "/" not in preferred and "\\" not in preferred:
            return preferred
    return (
        path_hint_from_url(url)
        or path_hint_from_label(label)
        or path_hint_from_label(repo_id)
        or "repo"
    )


def resolve_clone_destinations(repos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Attach resolved `dest` workspace-relative paths for each repo that has a URL.

    Every cloneable remote gets its own directory under /workspace (basename from
    URL/label). Never uses workspace root ('.') so multi-repo layouts stay clear.
    """
    used: set[str] = set()
    out: list[dict[str, Any]] = []

    for r in repos:
        item = dict(r)
        url = (item.get("url") or "").strip() or None
        if not is_cloneable_url(url):
            item["dest"] = sanitize_local_path(item.get("local_path"))
            out.append(item)
            continue

        dest = resolve_named_dest(
            url=url,
            label=item.get("label"),
            repo_id=item.get("id"),
            local_path=item.get("local_path"),
        )
        base = dest
        n = 2
        while dest in used:
            dest = f"{base}-{n}"
            n += 1
        used.add(dest)
        item["dest"] = dest
        # Persist canonical path so UI / rediscovery agree
        item["local_path"] = dest
        out.append(item)
    return out


def _shell_quote(s: str) -> str:
    return shlex.quote(s)


def _exit_code(res: dict[str, Any] | None) -> int:
    """Read agent exec exit_code. IMPORTANT: 0 is success — never use `or 1` (0 is falsy)."""
    if not res:
        return 1
    code = res.get("exit_code")
    if code is None:
        return 1
    try:
        return int(code)
    except (TypeError, ValueError):
        return 1


async def _exec(
    client: SandboxAgentClient,
    name: str,
    script: str,
    *,
    timeout: float = 60.0,
) -> dict[str, Any]:
    return await client.exec(
        name,
        cmd="sh",
        args=["-c", script],
        cwd="/workspace",
        timeout_seconds=timeout,
    )


async def _workspace_is_effectively_empty(client: SandboxAgentClient, name: str) -> bool:
    """True if /workspace has no meaningful content (safe to clone into .)."""
    try:
        res = await _exec(
            client,
            name,
            "ls -A /workspace 2>/dev/null | head -50",
            timeout=20.0,
        )
    except SandboxAgentError:
        return True
    lines = [ln.strip() for ln in (res.get("stdout") or "").splitlines() if ln.strip()]
    if not lines:
        return True
    # Ignore everflow markers only
    remaining = [ln for ln in lines if ln not in _EVERFLOW_ONLY and not ln.startswith(".everflow")]
    return len(remaining) == 0


async def _is_git_root(client: SandboxAgentClient, name: str, dest: str) -> bool:
    path = "/workspace" if dest in (".", "") else f"/workspace/{dest}"
    script = (
        f"cd {_shell_quote(path)} 2>/dev/null || exit 1; "
        "git rev-parse --is-inside-work-tree 2>/dev/null | grep -qx true || exit 2; "
        'pfx=$(git rev-parse --show-prefix 2>/dev/null); '
        '[ -z "$pfx" ] || exit 3'
    )
    try:
        res = await _exec(client, name, script, timeout=20.0)
        return _exit_code(res) == 0
    except SandboxAgentError:
        return False


async def clone_one(
    client: SandboxAgentClient,
    sandbox_name: str,
    repo: dict[str, Any],
    *,
    allow_root: bool = False,
) -> dict[str, Any]:
    """
    Clone a single repo into /workspace/<dest>/.

    Every remote gets its own directory (never workspace root) so multi-repo
    workspaces stay readable. Returns updated repo dict with clone_status /
    clone_error / local_path.
    """
    _ = allow_root  # legacy kwarg; root clones are no longer used
    updated = dict(repo)
    url = (updated.get("url") or "").strip()
    if not is_cloneable_url(url):
        updated["clone_status"] = "skipped"
        updated["clone_error"] = None
        return updated

    dest = sanitize_local_path(updated.get("dest") or updated.get("local_path") or "")
    if not dest or dest == ".":
        dest = resolve_named_dest(
            url=url,
            label=updated.get("label"),
            repo_id=updated.get("id"),
            local_path=None,
        )
    branch = (updated.get("branch") or "main").strip() or "main"

    if await _is_git_root(client, sandbox_name, dest):
        updated["local_path"] = dest
        updated["clone_status"] = "ready"
        updated["clone_error"] = None
        try:
            path = f"/workspace/{dest}"
            res = await _exec(
                client,
                sandbox_name,
                f"git -C {_shell_quote(path)} rev-parse --abbrev-ref HEAD",
                timeout=15.0,
            )
            if _exit_code(res) == 0:
                b = (res.get("stdout") or "").strip()
                if b and b != "HEAD":
                    updated["branch"] = b
        except SandboxAgentError:
            pass
        return updated

    updated["clone_status"] = "cloning"
    updated["clone_error"] = None

    # Always clone into a named subdirectory under /workspace
    script = (
        "set -e; "
        "cd /workspace; "
        f"(git clone --depth 1 -b {_shell_quote(branch)} -- {_shell_quote(url)} {_shell_quote(dest)} "
        f"|| git clone --depth 1 -- {_shell_quote(url)} {_shell_quote(dest)}); "
        f"test -d {_shell_quote(dest)}/.git"
    )

    try:
        res = await _exec(client, sandbox_name, script, timeout=CLONE_TIMEOUT_SECONDS)
        code = _exit_code(res)
        if code != 0:
            err = (res.get("stderr") or res.get("stdout") or "git clone failed").strip()
            err = err[-1500:]
            low = err.lower()
            if "authentication" in low or "403" in low or "could not read username" in low:
                err = (
                    f"{err}\n\nPrivate repositories need a GitHub token "
                    "(not configured yet). Use a public HTTPS URL for now."
                )
            updated["clone_status"] = "error"
            updated["clone_error"] = err
            updated["local_path"] = dest
            return updated

        updated["local_path"] = dest
        updated["clone_status"] = "ready"
        updated["clone_error"] = None
        if await _is_git_root(client, sandbox_name, dest):
            try:
                path = f"/workspace/{dest}"
                bres = await _exec(
                    client,
                    sandbox_name,
                    f"git -C {_shell_quote(path)} rev-parse --abbrev-ref HEAD",
                    timeout=15.0,
                )
                if _exit_code(bres) == 0:
                    b = (bres.get("stdout") or "").strip()
                    if b and b != "HEAD":
                        updated["branch"] = b
            except SandboxAgentError:
                pass
        return updated
    except SandboxAgentError as exc:
        updated["clone_status"] = "error"
        updated["clone_error"] = str(exc)[:1500]
        updated["local_path"] = dest
        return updated
    except Exception as exc:  # noqa: BLE001
        logger.exception("clone unexpected error url=%s", url)
        updated["clone_status"] = "error"
        updated["clone_error"] = str(exc)[:1500]
        updated["local_path"] = dest
        return updated


async def clone_project_repos(
    client: SandboxAgentClient,
    sandbox_name: str,
    repos: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """
    Clone all cloneable repos into the sandbox. Returns updated repos list
    (preserves non-URL entries; sets clone_status on each).
    """
    if not repos:
        return []

    limited = list(repos)[:MAX_REPOS]
    planned = resolve_clone_destinations(limited)

    result: list[dict[str, Any]] = []
    for r in planned:
        # Strip internal dest key from stored form after clone_one uses it
        updated = await clone_one(client, sandbox_name, r, allow_root=False)
        updated.pop("dest", None)
        result.append(updated)
        logger.info(
            "clone sandbox=%s repo=%s status=%s path=%s",
            sandbox_name,
            updated.get("id") or updated.get("label"),
            updated.get("clone_status"),
            updated.get("local_path"),
        )
    return result


def repos_to_storage(repos_in: list[Any] | None) -> list[dict[str, Any]]:
    """Normalize pydantic/repo dicts for JSON storage."""
    if not repos_in:
        return []
    out: list[dict[str, Any]] = []
    for i, r in enumerate(repos_in):
        if hasattr(r, "model_dump"):
            d = r.model_dump()
        elif isinstance(r, dict):
            d = dict(r)
        else:
            continue
        # Normalize keys to snake_case storage
        url = d.get("url")
        local_path = d.get("local_path") or d.get("localPath")
        # Cloneable remotes always get a named directory (never workspace root)
        if is_cloneable_url(url):
            local_path = resolve_named_dest(
                url=url,
                label=d.get("label"),
                repo_id=d.get("id") or f"repo-{i}",
                local_path=local_path,
            )
        item = {
            "id": d.get("id") or f"repo-{i}",
            "label": d.get("label") or d.get("id") or f"repo-{i}",
            "url": url,
            "branch": d.get("branch") or "main",
            "provider": d.get("provider") or "github",
            "local_path": local_path,
            "active": bool(d.get("active")),
            "clone_status": d.get("clone_status") or ("pending" if url else "skipped"),
            "clone_error": d.get("clone_error"),
        }
        out.append(item)
    return out
