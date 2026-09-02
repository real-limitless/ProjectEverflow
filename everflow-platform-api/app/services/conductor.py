"""Compile a room sentence into a Conductor-owned run graph."""

from __future__ import annotations

import re
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bus import OrgRun, OrgRunNode
from app.models.org import Seat
from app.models.project import Project
from app.models.user import User

# Canonical ship-train sentence (and close paraphrases).
_SHIP_HINTS = (
    ("product", ("product",)),
    ("eng", ("eng", "engineering", "eng team")),
    ("devops", ("devops", "deploy")),
    ("qa", ("qa", "test everything", "test")),
)

_CANONICAL = [
    {"key": "product", "slug": "product", "label": "Product", "brief": "Brief, acceptance, scope"},
    {"key": "eng-build", "slug": "eng-build", "label": "Eng.Build", "brief": "Implement against acceptance"},
    {"key": "eng-review", "slug": "eng-review", "label": "Eng.Review", "brief": "Adversarial gate"},
    {"key": "gate", "slug": "you", "label": "You confirm", "brief": "Human or policy: merge ok?"},
    {"key": "devops", "slug": "devops", "label": "DevOps", "brief": "Deploy staging (confirm)"},
    {"key": "qa", "slug": "qa", "label": "QA", "brief": "Smoke + critical paths"},
]


def looks_like_ship_train(sentence: str) -> bool:
    text = sentence.lower()
    return all(
        any(hint in text for hint in hints) for _, hints in _SHIP_HINTS
    )


def parse_mentions(body: str) -> list[dict[str, str]]:
    found: list[dict[str, str]] = []
    for raw in re.findall(r"@([a-z0-9][a-z0-9-]*)", body.lower()):
        kind = "team" if raw in {"eng", "qa", "devops", "services", "product", "floor"} else "seat"
        if raw == "product":
            kind = "seat"
        found.append({"kind": kind, "slug": raw})
    return found


async def compile_run(
    session: AsyncSession,
    project: Project,
    *,
    sentence: str,
    title: str | None = None,
    channel_id: UUID | None = None,
    thread_id: UUID | None = None,
    created_by: User | None = None,
    start: bool = True,
    commit: bool = True,
) -> OrgRun:
    seats_result = await session.execute(
        select(Seat).where(Seat.project_id == project.id, Seat.fired.is_(False))
    )
    seats = {s.slug: s for s in seats_result.scalars().all()}

    if looks_like_ship_train(sentence):
        spec_nodes = list(_CANONICAL)
    else:
        spec_nodes = _nodes_from_mentions(sentence, seats)

    run = OrgRun(
        project_id=project.id,
        channel_id=channel_id,
        thread_id=thread_id,
        title=title or _title_from_sentence(sentence),
        sentence=sentence.strip(),
        status="running" if start else "compiled",
        created_by=created_by.id if created_by else None,
    )
    session.add(run)
    await session.flush()

    nodes: list[OrgRunNode] = []
    prev_key: str | None = None
    for i, spec in enumerate(spec_nodes):
        seat = seats.get(spec["slug"])
        depends = [prev_key] if prev_key else []
        status = "waiting"
        if start and i == 0:
            status = "running"
        node = OrgRunNode(
            run_id=run.id,
            seat_id=seat.id if seat else None,
            key=spec["key"],
            label=spec["label"],
            status=status,
            brief=spec.get("brief") or "",
            sort_order=i,
            depends_on=depends,
        )
        session.add(node)
        nodes.append(node)
        prev_key = spec["key"]

    run.compiled_graph = {
        "title": run.title,
        "nodes": [
            {
                "key": n.key,
                "label": n.label,
                "seat_slug": next((s for s, seat in seats.items() if seat.id == n.seat_id), None),
                "depends_on": list(n.depends_on or []),
            }
            for n in nodes
        ],
    }
    if commit:
        await session.commit()
        await session.refresh(run)
    else:
        await session.flush()
    return run


def _title_from_sentence(sentence: str) -> str:
    cleaned = " ".join(sentence.strip().split())
    return cleaned[:80] + ("…" if len(cleaned) > 80 else "")


def _nodes_from_mentions(sentence: str, seats: dict[str, Seat]) -> list[dict[str, Any]]:
    mentions = parse_mentions(sentence)
    nodes: list[dict[str, Any]] = []
    seen: set[str] = set()
    # Floor always compiles first
    if "floor" in seats and "floor" not in seen:
        nodes.append(
            {"key": "floor", "slug": "floor", "label": "Floor", "brief": "Compile run"}
        )
        seen.add("floor")
    for m in mentions:
        slug = m["slug"]
        if slug == "eng":
            for extra in ("eng-build", "eng-review"):
                if extra in seats and extra not in seen:
                    seat = seats[extra]
                    nodes.append(
                        {
                            "key": extra,
                            "slug": extra,
                            "label": seat.name,
                            "brief": seat.description,
                        }
                    )
                    seen.add(extra)
            continue
        if slug in seen:
            continue
        seat = seats.get(slug)
        if seat is None:
            continue
        nodes.append(
            {"key": slug, "slug": slug, "label": seat.name, "brief": seat.description}
        )
        seen.add(slug)
    if not nodes:
        # Fallback: Floor only
        floor = seats.get("floor")
        if floor:
            nodes.append(
                {"key": "floor", "slug": "floor", "label": floor.name, "brief": floor.description}
            )
    return nodes
