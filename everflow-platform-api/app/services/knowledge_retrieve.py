"""Retrieve top-k knowledge chunks with cosine similarity over JSON embeddings."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import (
    AgentCollectionGrant,
    KnowledgeCanvas,
    KnowledgeChunk,
    KnowledgeCollection,
    KnowledgeLink,
)
from app.schemas.knowledge import KnowledgeRetrieveHit
from app.services.knowledge_embed import cosine, local_embed


async def allowed_collection_ids(
    session: AsyncSession,
    *,
    project_id: UUID,
    user_id: UUID,
    agent_id: UUID | None,
    explicit: list[UUID] | None,
) -> list[UUID] | None:
    """
    Return collection ids the caller may retrieve, or None = all project chunks.
    Personal collections require ownership; agent visibility requires a grant.
    """
    cols = await session.execute(
        select(KnowledgeCollection).where(KnowledgeCollection.project_id == project_id)
    )
    collections = list(cols.scalars().all())
    if not collections:
        return None

    allowed: set[UUID] = set()
    grant_map: dict[UUID, AgentCollectionGrant] = {}
    if agent_id is not None:
        grants = await session.execute(
            select(AgentCollectionGrant).where(
                AgentCollectionGrant.agent_id == agent_id,
                AgentCollectionGrant.can_retrieve.is_(True),
            )
        )
        for g in grants.scalars().all():
            grant_map[g.collection_id] = g

    for c in collections:
        if c.visibility == "team":
            allowed.add(c.id)
        elif c.visibility == "personal":
            if c.owner_user_id == user_id:
                allowed.add(c.id)
        elif c.visibility == "agent":
            if agent_id is not None and c.id in grant_map:
                allowed.add(c.id)
            elif agent_id is None:
                # Human with knowledge:read can see agent collections in studio
                allowed.add(c.id)

    if explicit is not None:
        allowed &= set(explicit)

    return list(allowed)


async def retrieve(
    session: AsyncSession,
    *,
    project_id: UUID,
    query: str,
    top_k: int = 5,
    collection_ids: list[UUID] | None = None,
    agent_id: UUID | None = None,
    user_id: UUID,
) -> list[KnowledgeRetrieveHit]:
    allowed = await allowed_collection_ids(
        session,
        project_id=project_id,
        user_id=user_id,
        agent_id=agent_id,
        explicit=collection_ids,
    )

    q = select(KnowledgeChunk).where(KnowledgeChunk.project_id == project_id)
    if allowed is not None:
        # Include unscoped chunks (collection_id NULL) plus allowed collections
        from sqlalchemy import or_

        if allowed:
            q = q.where(
                or_(
                    KnowledgeChunk.collection_id.is_(None),
                    KnowledgeChunk.collection_id.in_(allowed),
                )
            )
        else:
            q = q.where(KnowledgeChunk.collection_id.is_(None))

    result = await session.execute(q)
    chunks = list(result.scalars().all())
    if not chunks:
        return []

    qvec = local_embed(query)
    q_tokens = set(re_tokens(query))
    q_lower = (query or "").lower().strip()
    secretish = bool(
        re_tokens(query)
        and any(
            t in q_lower
            for t in (
                "password",
                "secret",
                "api_key",
                "apikey",
                "token",
                "credential",
                "knowledge key",
                "passphrase",
            )
        )
    )
    scored: list[tuple[float, KnowledgeChunk]] = []
    for ch in chunks:
        emb = ch.embedding or []
        # Also boost lexical overlap lightly (helps short secrets / exact terms)
        score = cosine(qvec, emb) if emb else 0.0
        c_text = ch.text or ""
        c_lower = c_text.lower()
        c_tokens = set(re_tokens(c_text))
        if q_tokens and c_tokens:
            overlap = len(q_tokens & c_tokens) / max(len(q_tokens), 1)
            score = 0.65 * score + 0.35 * overlap
        # Exact / substring boost for passwords, keys, titled sections
        if q_lower and len(q_lower) >= 3 and q_lower in c_lower:
            score = max(score, 0.92)
        if secretish and any(
            k in c_lower for k in ("password", "secret", "api_key", "token", "knowledge key")
        ):
            score = min(1.0, score + 0.15)
        scored.append((score, ch))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:top_k]

    canvas_ids = {ch.canvas_id for _, ch in top}
    canvases: dict[UUID, KnowledgeCanvas] = {}
    if canvas_ids:
        cres = await session.execute(
            select(KnowledgeCanvas).where(KnowledgeCanvas.id.in_(canvas_ids))
        )
        canvases = {c.id: c for c in cres.scalars().all()}

    hits: list[KnowledgeRetrieveHit] = []
    for score, ch in top:
        canvas = canvases.get(ch.canvas_id)
        meta = ch.meta or {}
        hits.append(
            KnowledgeRetrieveHit(
                canvas_id=ch.canvas_id,
                canvas_name=canvas.name if canvas else "Unknown",
                chunk_id=ch.id,
                text=ch.text,
                score=round(score, 4),
                source_url=(canvas.source_url if canvas else None) or meta.get("source_url"),
                path=(canvas.repo_path if canvas else None) or meta.get("path"),
                collection_id=ch.collection_id,
            )
        )

    # Record consumption edges for graph (agent retrieve)
    if agent_id is not None:
        for hit in hits[:3]:
            session.add(
                KnowledgeLink(
                    project_id=project_id,
                    from_type="agent",
                    from_id=str(agent_id),
                    to_type="canvas",
                    to_id=str(hit.canvas_id),
                    rel="consumed_by",
                )
            )
        await session.commit()

    return hits


def re_tokens(text: str) -> list[str]:
    import re

    return re.findall(r"[a-z0-9_]{2,}", (text or "").lower())
