"""Index documentation-like files from the project sandbox into knowledge canvases."""

from __future__ import annotations

import fnmatch
import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import KnowledgeCanvas, KnowledgeCollection, KnowledgeLink
from app.models.project import Project
from app.services.knowledge_embed import content_hash, reindex_canvas
from app.services.sandbox_agent_client import SandboxAgentClient, SandboxAgentError

logger = logging.getLogger(__name__)

DEFAULT_GLOBS = (
    "README*",
    "readme*",
    "**/docs/**/*.md",
    "**/docs/**/*.mdx",
    "**/adr/**/*.md",
    "**/ADR/**/*.md",
    "**/openapi*.yaml",
    "**/openapi*.yml",
    "**/openapi*.json",
    "**/runbook*",
    "**/RUNBOOK*",
)


def _matches(path: str, globs: tuple[str, ...] | list[str]) -> bool:
    name = path.rsplit("/", 1)[-1]
    for g in globs:
        if fnmatch.fnmatch(path, g) or fnmatch.fnmatch(name, g):
            return True
        # Also match basename-style globs against full path segments
        if "**" in g and fnmatch.fnmatch(path, g):
            return True
    return False


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

    # Walk from workspace root via recursive listing heuristic
    try:
        listing = await agent.list_fs(project.sandbox_name, path=".")
    except SandboxAgentError:
        listing = await agent.list_fs(project.sandbox_name, path="")

    def entry_path(e: dict) -> str:
        return str(e.get("path") or e.get("name") or "")

    paths: list[str] = []
    stack = [e for e in listing if e.get("is_dir")]
    for e in listing:
        if not e.get("is_dir"):
            p = entry_path(e)
            if p and _matches(p, globs):
                paths.append(p)

    visited: set[str] = set()
    while stack and len(visited) < 80:
        d = stack.pop()
        dp = entry_path(d)
        if not dp or dp in visited:
            continue
        visited.add(dp)
        interesting = any(
            seg in dp.lower() for seg in ("docs", "adr", "doc", ".github", "runbook")
        )
        if not interesting and dp not in (".", ""):
            continue
        try:
            children = await agent.list_fs(project.sandbox_name, path=dp)
        except SandboxAgentError:
            continue
        for c in children:
            cp = entry_path(c)
            if c.get("is_dir"):
                stack.append(c)
            elif cp and _matches(cp, globs):
                paths.append(cp)

    # Deduplicate
    paths = sorted(set(paths))
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

    return {
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "canvas_ids": canvas_ids,
    }
