"""Index documentation-like files from the project sandbox into knowledge canvases."""

from __future__ import annotations

import fnmatch
import logging
import re
from collections import deque
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import KnowledgeCanvas, KnowledgeCollection, KnowledgeLink
from app.models.project import Project
from app.services.knowledge_embed import content_hash, reindex_canvas
from app.services.sandbox_agent_client import SandboxAgentClient, SandboxAgentError

logger = logging.getLogger(__name__)

# Patterns are matched with path-aware rules (see matches_doc_path), not raw fnmatch **.
DEFAULT_GLOBS = (
    "README*",
    "readme*",
    "AGENTS.md",
    "CLAUDE.md",
    "**/docs/**/*.md",
    "**/docs/**/*.mdx",
    "**/doc/**/*.md",
    "**/adr/**/*.md",
    "**/ADR/**/*.md",
    "**/openapi*.yaml",
    "**/openapi*.yml",
    "**/openapi*.json",
    "**/runbook*",
    "**/RUNBOOK*",
    "**/.github/**/*.md",
    "**/runbooks/**/*",
)

SKIP_DIR_NAMES = frozenset(
    {
        ".git",
        "node_modules",
        ".venv",
        "venv",
        "__pycache__",
        "dist",
        "build",
        ".next",
        ".turbo",
        "coverage",
        "vendor",
        ".cache",
        ".tox",
        ".mypy_cache",
        ".pytest_cache",
        "target",
        "bin",
        "obj",
        ".everflow",
    }
)

DOC_DIR_SEGMENTS = frozenset(
    {"docs", "doc", "adr", "runbook", "runbooks", ".github"}
)

MAX_WALK_DIRS = 300
MAX_WALK_DEPTH = 8


def _normalize_path(path: str) -> str:
    p = (path or "").replace("\\", "/").strip()
    while p.startswith("./"):
        p = p[2:]
    return p.lstrip("/")


def _basename(path: str) -> str:
    return _normalize_path(path).rsplit("/", 1)[-1]


def _path_segments(path: str) -> list[str]:
    return [s for s in _normalize_path(path).split("/") if s and s != "."]


def _is_skipped_dir(path: str) -> bool:
    return any(seg in SKIP_DIR_NAMES for seg in _path_segments(path))


def _under_doc_dir(path: str) -> bool:
    segs = _path_segments(path)
    if not segs:
        return False
    # Directory itself or any parent segment (exclude filename for files)
    dir_segs = segs[:-1] if len(segs) > 1 else segs
    return any(s.lower() in DOC_DIR_SEGMENTS or s in DOC_DIR_SEGMENTS for s in dir_segs)


def _fnmatch_path(path: str, pattern: str) -> bool:
    """Match path against a glob that may include ** (segment-aware)."""
    path = _normalize_path(path)
    pattern = pattern.replace("\\", "/").strip()
    if not pattern:
        return False

    # Basename-only patterns (no slash): match name only
    if "/" not in pattern:
        return fnmatch.fnmatch(_basename(path), pattern)

    # Convert ** / * to regex
    # Escape then restore glob tokens
    i = 0
    out: list[str] = ["^"]
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    out.append("$")
    try:
        return re.match("".join(out), path) is not None
    except re.error:
        return fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch(_basename(path), pattern)


def matches_doc_path(path: str, globs: tuple[str, ...] | list[str] | None = None) -> bool:
    """Return True if path should be indexed as project documentation."""
    path = _normalize_path(path)
    if not path or path.endswith("/"):
        return False
    name = _basename(path)
    if not name or name.startswith("."):
        # Allow .github markdown via explicit patterns / doc-dir rule below
        if not name.endswith((".md", ".mdx")):
            return False

    patterns = tuple(globs) if globs else DEFAULT_GLOBS

    # Always-useful root / basename docs
    lower = name.lower()
    if fnmatch.fnmatch(name, "README*") or fnmatch.fnmatch(name, "readme*"):
        return True
    if lower in ("agents.md", "claude.md", "contributing.md", "changelog.md", "license.md"):
        return True
    if fnmatch.fnmatch(lower, "openapi*.yaml") or fnmatch.fnmatch(lower, "openapi*.yml"):
        return True
    if fnmatch.fnmatch(lower, "openapi*.json"):
        return True
    if "runbook" in lower:
        return True

    # Markdown under known doc directories
    if lower.endswith((".md", ".mdx")) and _under_doc_dir(path):
        return True

    # Explicit user/default globs
    for g in patterns:
        if _fnmatch_path(path, g) or _fnmatch_path(name, g):
            return True
    return False


# Back-compat alias used by older callers/tests
def _matches(path: str, globs: tuple[str, ...] | list[str]) -> bool:
    return matches_doc_path(path, globs)


async def ensure_collection(
    session: AsyncSession,
    *,
    project_id: UUID,
    name: str,
) -> KnowledgeCollection:
    result = await session.execute(
        select(KnowledgeCollection).where(
            KnowledgeCollection.project_id == project_id,
            KnowledgeCollection.name == name,
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        return existing
    col = KnowledgeCollection(
        project_id=project_id,
        name=name,
        visibility="team",
    )
    session.add(col)
    await session.commit()
    await session.refresh(col)
    return col


def _entry_path(e: dict) -> str:
    return _normalize_path(str(e.get("path") or e.get("name") or ""))


def _dir_depth(path: str) -> int:
    return len(_path_segments(path))


async def collect_doc_paths(
    agent: SandboxAgentClient,
    sandbox_name: str,
    *,
    globs: tuple[str, ...] | list[str] | None = None,
) -> list[str]:
    """BFS walk workspace via list_fs; return matching relative paths."""
    patterns = tuple(globs) if globs else DEFAULT_GLOBS
    paths: list[str] = []

    try:
        listing = await agent.list_fs(sandbox_name, path=".")
    except SandboxAgentError:
        listing = await agent.list_fs(sandbox_name, path="")

    queue: deque[str] = deque()
    visited: set[str] = set()

    for e in listing:
        p = _entry_path(e)
        if not p:
            continue
        if e.get("is_dir"):
            if not _is_skipped_dir(p):
                queue.append(p)
        elif matches_doc_path(p, patterns):
            paths.append(p)

    while queue and len(visited) < MAX_WALK_DIRS:
        dp = queue.popleft()
        if not dp or dp in visited or _is_skipped_dir(dp):
            continue
        if _dir_depth(dp) > MAX_WALK_DEPTH:
            continue
        visited.add(dp)
        try:
            children = await agent.list_fs(sandbox_name, path=dp)
        except SandboxAgentError:
            continue
        for c in children:
            cp = _entry_path(c)
            if not cp:
                # Reconstruct relative path from parent + name
                name = str(c.get("name") or "")
                if not name:
                    continue
                cp = _normalize_path(f"{dp}/{name}")
            if c.get("is_dir"):
                if not _is_skipped_dir(cp) and cp not in visited:
                    queue.append(cp)
            elif matches_doc_path(cp, patterns):
                paths.append(cp)

    return sorted(set(paths))


async def index_sandbox_docs(
    session: AsyncSession,
    *,
    project: Project,
    agent: SandboxAgentClient,
    created_by: UUID | None,
    collection_name: str = "Repo docs",
    path_globs: list[str] | None = None,
) -> dict[str, object]:
    if not project.sandbox_name:
        raise SandboxAgentError("Sandbox is not provisioned")

    globs = tuple(path_globs) if path_globs else DEFAULT_GLOBS
    collection = await ensure_collection(
        session, project_id=project.id, name=collection_name
    )

    paths = await collect_doc_paths(agent, project.sandbox_name, globs=globs)

    created = updated = skipped = 0
    canvas_ids: list[UUID] = []

    for path in paths:
        try:
            content = await agent.read_fs(project.sandbox_name, path)
        except SandboxAgentError as exc:
            logger.warning("skip %s: %s", path, exc)
            skipped += 1
            continue
        if not isinstance(content, str):
            # Sandbox client may return str; agent backends sometimes return bytes
            if isinstance(content, (bytes, bytearray)):
                try:
                    content = content.decode("utf-8")
                except UnicodeDecodeError:
                    skipped += 1
                    continue
            else:
                content = str(content)
        if not content.strip():
            skipped += 1
            continue

        name = path.rsplit("/", 1)[-1][:200]
        digest = content_hash(content)
        existing = await session.execute(
            select(KnowledgeCanvas).where(
                KnowledgeCanvas.project_id == project.id,
                KnowledgeCanvas.repo_path == path,
            )
        )
        canvas = existing.scalar_one_or_none()
        if canvas:
            if canvas.content_hash == digest:
                skipped += 1
                canvas_ids.append(canvas.id)
                continue
            canvas.content_md = content
            canvas.name = name
            canvas.collection_id = collection.id
            canvas.origin = "repo"
            canvas.status = "stale"
            canvas.content_hash = digest
            updated += 1
        else:
            canvas = KnowledgeCanvas(
                project_id=project.id,
                collection_id=collection.id,
                name=name,
                description=f"Repo: {path}",
                content_md=content,
                origin="repo",
                status="ready",
                repo_path=path,
                content_hash=digest,
                created_by=created_by,
            )
            session.add(canvas)
            created += 1
        await session.commit()
        await session.refresh(canvas)
        session.add(
            KnowledgeLink(
                project_id=project.id,
                from_type="repo_path",
                from_id=path[:64],
                to_type="canvas",
                to_id=str(canvas.id),
                rel="derived_from",
            )
        )
        await session.commit()
        try:
            await reindex_canvas(session, canvas)
        except Exception:  # noqa: BLE001
            logger.exception("reindex failed for %s", path)
        canvas_ids.append(canvas.id)

    message: str | None = None
    if not paths:
        message = (
            "No documentation files matched (README*, AGENTS.md, docs/**, ADR, "
            "openapi*, runbooks, .github/**/*.md). Add docs under those paths or "
            "ensure the sandbox workspace is populated."
        )
    elif created == 0 and updated == 0:
        message = (
            f"Found {len(paths)} doc file(s) but none needed updates "
            f"({skipped} unchanged/skipped)."
        )

    return {
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "canvas_ids": canvas_ids,
        "matched_paths": paths[:40],
        "matched_count": len(paths),
        "message": message,
    }
