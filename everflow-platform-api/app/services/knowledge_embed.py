"""Chunk Markdown and embed into knowledge_chunks (JSON vectors, SQLite-safe)."""

from __future__ import annotations

import hashlib
import math
import re
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import KnowledgeCanvas, KnowledgeChunk

EMBED_DIM = 256
_MAX_CHUNK_CHARS = 1200


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def chunk_markdown(text: str) -> list[tuple[str, str | None]]:
    """Split markdown into (chunk_text, heading) pairs."""
    raw = (text or "").strip()
    if not raw:
        return []

    sections: list[tuple[str | None, str]] = []
    current_heading: str | None = None
    buf: list[str] = []

    def flush() -> None:
        nonlocal buf
        body = "\n".join(buf).strip()
        if body:
            sections.append((current_heading, body))
        buf = []

    for line in raw.splitlines():
        if re.match(r"^#{1,6}\s+\S", line):
            flush()
            current_heading = line.lstrip("#").strip()
            buf.append(line)
        else:
            buf.append(line)
    flush()

    if not sections:
        sections = [(None, raw)]

    out: list[tuple[str, str | None]] = []
    for heading, body in sections:
        if len(body) <= _MAX_CHUNK_CHARS:
            out.append((body, heading))
            continue
        # Soft-split long sections on paragraphs
        paras = re.split(r"\n\s*\n", body)
        acc = ""
        for p in paras:
            candidate = f"{acc}\n\n{p}".strip() if acc else p
            if len(candidate) > _MAX_CHUNK_CHARS and acc:
                out.append((acc, heading))
                acc = p
            else:
                acc = candidate
        if acc:
            out.append((acc, heading))
    return out


def local_embed(text: str, dim: int = EMBED_DIM) -> list[float]:
    """Deterministic hashed bag-of-tokens embedding (offline / test fallback)."""
    vec = [0.0] * dim
    tokens = re.findall(r"[a-z0-9_]{2,}", (text or "").lower())
    if not tokens:
        tokens = ["empty"]
    for tok in tokens:
        h = hashlib.sha256(tok.encode("utf-8")).digest()
        idx = int.from_bytes(h[:4], "big") % dim
        sign = 1.0 if h[4] % 2 == 0 else -1.0
        vec[idx] += sign
    # L2 normalize
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return float(sum(x * y for x, y in zip(a, b, strict=True)))


async def repair_canvas_index_status(
    session: AsyncSession,
    canvas: KnowledgeCanvas,
) -> KnowledgeCanvas:
    """If chunks exist but status stuck on chunking/embedding, mark indexed.

    Intermediate commits during reindex can leave status lagging after a crash
    or cancelled request even when knowledge_chunks rows are present.
    """
    if canvas.status not in ("chunking", "embedding"):
        return canvas
    result = await session.execute(
        select(KnowledgeChunk.id).where(KnowledgeChunk.canvas_id == canvas.id)
    )
    n = len(list(result.scalars().all()))
    if n <= 0:
        return canvas
    canvas.status = "indexed"
    canvas.chunks = n
    canvas.content_hash = content_hash(canvas.content_md or "")
    await session.commit()
    await session.refresh(canvas)
    return canvas


async def reindex_canvas(session: AsyncSession, canvas: KnowledgeCanvas) -> KnowledgeCanvas:
    """Replace chunks for a canvas and mark indexed (or error)."""
    pieces = chunk_markdown(canvas.content_md or "")
    canvas.status = "embedding"
    # Keep previous chunks visible until replace succeeds (status only).
    await session.commit()

    try:
        await session.execute(
            delete(KnowledgeChunk).where(KnowledgeChunk.canvas_id == canvas.id)
        )

        if not pieces:
            canvas.status = "indexed"
            canvas.chunks = 0
            canvas.content_hash = content_hash(canvas.content_md or "")
            await session.commit()
            await session.refresh(canvas)
            return canvas

        for i, (text, heading) in enumerate(pieces):
            emb = local_embed(text)
            session.add(
                KnowledgeChunk(
                    project_id=canvas.project_id,
                    canvas_id=canvas.id,
                    collection_id=canvas.collection_id,
                    ordinal=i,
                    text=text,
                    embedding=emb,
                    token_count=len(text.split()),
                    meta={
                        "heading": heading,
                        "source_url": canvas.source_url,
                        "path": canvas.repo_path,
                    },
                )
            )
        canvas.status = "indexed"
        canvas.chunks = len(pieces)
        canvas.content_hash = content_hash(canvas.content_md or "")
        await session.commit()
    except Exception:
        await session.rollback()
        # Re-load canvas after rollback
        await session.refresh(canvas)
        canvas.status = "error"
        await session.commit()
        raise

    await session.refresh(canvas)
    return canvas


async def get_canvas_chunks(
    session: AsyncSession,
    *,
    project_id: UUID,
    canvas_id: UUID | None = None,
    collection_ids: list[UUID] | None = None,
) -> list[KnowledgeChunk]:
    q = select(KnowledgeChunk).where(KnowledgeChunk.project_id == project_id)
    if canvas_id is not None:
        q = q.where(KnowledgeChunk.canvas_id == canvas_id)
    if collection_ids is not None:
        q = q.where(KnowledgeChunk.collection_id.in_(collection_ids))
    result = await session.execute(q)
    return list(result.scalars().all())
