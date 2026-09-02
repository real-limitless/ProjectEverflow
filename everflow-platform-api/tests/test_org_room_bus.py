"""Org chart, room, bus, roster, constitution, session binding."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


async def _project(client: AsyncClient, headers: dict[str, str], slug: str = "org-app") -> str:
    org = await client.post(
        "/api/v1/orgs",
        headers=headers,
        json={"name": "Chart Org", "slug": f"{slug}-org"},
    )
    assert org.status_code == 201, org.text
    proj = await client.post(
        f"/api/v1/orgs/{org.json()['id']}/projects",
        headers=headers,
        json={"name": "Chart App", "slug": slug},
    )
    assert proj.status_code == 201, proj.text
    return proj.json()["id"]


@pytest.mark.asyncio
async def test_ensure_starter_roster_and_chart(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    pid = await _project(client, auth_headers, "starter")
    ensure = await client.post(f"/api/v1/projects/{pid}/org/ensure", headers=auth_headers)
    assert ensure.status_code == 200, ensure.text
    data = ensure.json()
    slugs = {s["slug"] for s in data["seats"]}
    assert {
        "you",
        "floor",
        "product",
        "eng-build",
        "eng-review",
        "devops",
        "qa",
        "scout",
        "docs",
        "sec",
        "scribe",
    } <= slugs
    teams = {t["slug"] for t in data["teams"]}
    assert "eng" in teams and "services" in teams
    floor = next(s for s in data["seats"] if s["slug"] == "floor")
    you = next(s for s in data["seats"] if s["slug"] == "you")
    assert floor["reports_to_id"] == you["id"]
    assert floor["is_conductor"] is True
    assert floor["permission"].get("edit") == "deny"
    build = next(s for s in data["seats"] if s["slug"] == "eng-build")
    assert build["worktree_path"] == ".everflow/worktrees/eng-build"
    review = next(s for s in data["seats"] if s["slug"] == "eng-review")
    assert review["worktree_path"] == build["worktree_path"]
    assert review["permission"].get("edit") == "deny"
    devops = next(s for s in data["seats"] if s["slug"] == "devops")
    assert devops["permission"].get("bash") == "ask"
    assert "constitution.md" in data["constitution_md"].lower() or "constitution" in data[
        "constitution_md"
    ].lower()

    again = await client.post(f"/api/v1/projects/{pid}/org/ensure", headers=auth_headers)
    assert again.status_code == 200
    assert len(again.json()["seats"]) == len(data["seats"])


@pytest.mark.asyncio
async def test_constitution_and_roster_agents(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    pid = await _project(client, auth_headers, "law")
    got = await client.get(f"/api/v1/projects/{pid}/constitution", headers=auth_headers)
    assert got.status_code == 200
    assert "One job per seat" in got.json()["constitution_md"]
    put = await client.put(
        f"/api/v1/projects/{pid}/constitution",
        headers=auth_headers,
        json={"constitution_md": "# Law\n\nNo god-bots.\n"},
    )
    assert put.status_code == 200
    assert "No god-bots" in put.json()["constitution_md"]

    agents = await client.get(f"/api/v1/projects/{pid}/roster/agents", headers=auth_headers)
    assert agents.status_code == 200
    names = {a["name"] for a in agents.json()["agents"]}
    assert "floor" in names and "eng-build" in names
    floor = next(a for a in agents.json()["agents"] if a["name"] == "floor")
    assert floor["permission"]["edit"] == "deny"


@pytest.mark.asyncio
async def test_seat_attach_pause_fire_reparent(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    pid = await _project(client, auth_headers, "bind")
    await client.post(f"/api/v1/projects/{pid}/org/ensure", headers=auth_headers)
    seats = (
        await client.get(
            f"/api/v1/projects/{pid}/seats?include_system=true", headers=auth_headers
        )
    ).json()
    floor = next(s for s in seats if s["slug"] == "floor")
    product = next(s for s in seats if s["slug"] == "product")
    you = next(s for s in seats if s["slug"] == "you")

    attach = await client.post(
        f"/api/v1/projects/{pid}/seats/{floor['id']}/attach", headers=auth_headers
    )
    assert attach.status_code == 200, attach.text
    assert attach.json()["opencode_session_id"]
    assert attach.json()["opencode_session_id"].startswith("ses_")

    pause = await client.post(
        f"/api/v1/projects/{pid}/seats/{floor['id']}/pause", headers=auth_headers
    )
    assert pause.json()["paused"] is True
    blocked = await client.post(
        f"/api/v1/projects/{pid}/seats/{floor['id']}/attach", headers=auth_headers
    )
    assert blocked.status_code == 409

    resume = await client.post(
        f"/api/v1/projects/{pid}/seats/{floor['id']}/resume", headers=auth_headers
    )
    assert resume.json()["paused"] is False

    # Cycle: you -> floor already; floor cannot report to product if product reports to floor
    # product reports to floor; reparent floor to product would cycle
    cycle = await client.post(
        f"/api/v1/projects/{pid}/seats/{floor['id']}/reparent",
        headers=auth_headers,
        json={"reports_to_id": product["id"]},
    )
    assert cycle.status_code == 400

    ok = await client.post(
        f"/api/v1/projects/{pid}/seats/{product['id']}/reparent",
        headers=auth_headers,
        json={"reports_to_id": you["id"]},
    )
    assert ok.status_code == 200
    assert ok.json()["reports_to_id"] == you["id"]

    fire = await client.post(
        f"/api/v1/projects/{pid}/seats/{product['id']}/fire", headers=auth_headers
    )
    assert fire.json()["fired"] is True
    assert fire.json()["opencode_session_id"] is None


@pytest.mark.asyncio
async def test_room_ship_sentence_compiles_run(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    pid = await _project(client, auth_headers, "ship")
    channels = await client.get(f"/api/v1/projects/{pid}/channels", headers=auth_headers)
    assert channels.status_code == 200
    ship = next(c for c in channels.json() if c["slug"] == "ship")
    sentence = (
        "Talk to Product and the Eng team. When they complete, "
        "have DevOps deploy to staging and QA test everything."
    )
    msg = await client.post(
        f"/api/v1/projects/{pid}/channels/{ship['id']}/messages",
        headers=auth_headers,
        json={"body": sentence},
    )
    assert msg.status_code == 201, msg.text
    assert msg.json()["run_id"]
    mentions = {m["slug"] for m in msg.json()["mentions"]}
    # sentence has no @mentions; compile still happens
    assert msg.json()["run_id"]

    run = await client.get(
        f"/api/v1/projects/{pid}/runs/{msg.json()['run_id']}", headers=auth_headers
    )
    assert run.status_code == 200
    keys = [n["key"] for n in run.json()["nodes"]]
    assert keys == ["product", "eng-build", "eng-review", "gate", "devops", "qa"]
    assert run.json()["status"] == "running"


@pytest.mark.asyncio
async def test_room_at_team_mention(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    pid = await _project(client, auth_headers, "mention")
    channels = (await client.get(f"/api/v1/projects/{pid}/channels", headers=auth_headers)).json()
    ship = next(c for c in channels if c["slug"] == "ship")
    msg = await client.post(
        f"/api/v1/projects/{pid}/channels/{ship['id']}/messages",
        headers=auth_headers,
        json={"body": "Need a look from @eng and @qa"},
    )
    assert msg.status_code == 201, msg.text
    slugs = {m["slug"]: m["kind"] for m in msg.json()["mentions"]}
    assert slugs.get("eng") == "team"
    assert slugs.get("qa") in {"team", "seat"}


@pytest.mark.asyncio
async def test_bus_ask_human_walks_reports_to(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    pid = await _project(client, auth_headers, "ask")
    await client.post(f"/api/v1/projects/{pid}/org/ensure", headers=auth_headers)
    seats = (await client.get(f"/api/v1/projects/{pid}/seats", headers=auth_headers)).json()
    devops = next(s for s in seats if s["slug"] == "devops")
    you = next(s for s in seats if s["slug"] == "you")
    compile = await client.post(
        f"/api/v1/projects/{pid}/runs/compile",
        headers=auth_headers,
        json={
            "sentence": (
                "Talk to Product and the Eng team. When they complete, "
                "have DevOps deploy to staging and QA test everything."
            )
        },
    )
    assert compile.status_code == 201, compile.text
    run_id = compile.json()["id"]

    ev = await client.post(
        f"/api/v1/projects/{pid}/bus",
        headers=auth_headers,
        json={
            "verb": "ask_human",
            "from_seat_id": devops["id"],
            "run_id": run_id,
            "payload": {"reason": "confirm staging deploy"},
        },
    )
    assert ev.status_code == 200, ev.text
    assert ev.json()["status"] == "ok"
    assert ev.json()["to_seat_id"] == you["id"]
    assert ev.json()["payload"]["escalated_to"] == "you"


@pytest.mark.asyncio
async def test_bus_cycle_detector(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    pid = await _project(client, auth_headers, "cycle")
    await client.post(f"/api/v1/projects/{pid}/org/ensure", headers=auth_headers)
    seats = (await client.get(f"/api/v1/projects/{pid}/seats", headers=auth_headers)).json()
    a = next(s for s in seats if s["slug"] == "product")
    b = next(s for s in seats if s["slug"] == "qa")
    compile = await client.post(
        f"/api/v1/projects/{pid}/runs/compile",
        headers=auth_headers,
        json={"sentence": "Talk to Product and QA", "start": False},
    )
    run_id = compile.json()["id"]
    first = await client.post(
        f"/api/v1/projects/{pid}/bus",
        headers=auth_headers,
        json={
            "verb": "send_message",
            "from_seat_id": a["id"],
            "to_seat_id": b["id"],
            "run_id": run_id,
            "payload": {"body": "need tests"},
        },
    )
    assert first.json()["status"] == "ok"
    loop = await client.post(
        f"/api/v1/projects/{pid}/bus",
        headers=auth_headers,
        json={
            "verb": "send_message",
            "from_seat_id": b["id"],
            "to_seat_id": a["id"],
            "run_id": run_id,
            "payload": {"body": "back at you"},
        },
    )
    assert loop.status_code == 200
    assert loop.json()["status"] == "cycle_blocked"


@pytest.mark.asyncio
async def test_bus_handoff_and_export(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    pid = await _project(client, auth_headers, "hand")
    await client.post(f"/api/v1/projects/{pid}/org/ensure", headers=auth_headers)
    seats = (await client.get(f"/api/v1/projects/{pid}/seats", headers=auth_headers)).json()
    product = next(s for s in seats if s["slug"] == "product")
    build = next(s for s in seats if s["slug"] == "eng-build")
    compile = await client.post(
        f"/api/v1/projects/{pid}/runs/compile",
        headers=auth_headers,
        json={
            "sentence": (
                "Talk to Product and the Eng team. When they complete, "
                "have DevOps deploy to staging and QA test everything."
            )
        },
    )
    run_id = compile.json()["id"]
    ev = await client.post(
        f"/api/v1/projects/{pid}/bus",
        headers=auth_headers,
        json={
            "verb": "handoff",
            "from_seat_id": product["id"],
            "to_seat_id": build["id"],
            "run_id": run_id,
            "payload": {"brief": "acceptance ready"},
        },
    )
    assert ev.json()["status"] == "ok"
    run = (await client.get(f"/api/v1/projects/{pid}/runs/{run_id}", headers=auth_headers)).json()
    prod_node = next(n for n in run["nodes"] if n["key"] == "product")
    build_node = next(n for n in run["nodes"] if n["key"] == "eng-build")
    assert prod_node["status"] == "done"
    assert build_node["status"] == "running"

    yaml = await client.get(f"/api/v1/projects/{pid}/org/export.yaml", headers=auth_headers)
    assert yaml.status_code == 200
    assert "eng-build" in yaml.text
    assert "reports_to:" in yaml.text


@pytest.mark.asyncio
async def test_chart_hides_conductor_unless_include_system(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    pid = await _project(client, auth_headers, "hide-floor")
    await client.post(f"/api/v1/projects/{pid}/org/ensure", headers=auth_headers)
    hidden = await client.get(f"/api/v1/projects/{pid}/chart", headers=auth_headers)
    assert hidden.status_code == 200
    slugs = {s["slug"] for s in hidden.json()["seats"]}
    assert "floor" not in slugs
    assert "you" in slugs and "product" in slugs
    shown = await client.get(
        f"/api/v1/projects/{pid}/chart?include_system=true", headers=auth_headers
    )
    assert "floor" in {s["slug"] for s in shown.json()["seats"]}
    roster = await client.get(f"/api/v1/projects/{pid}/seats", headers=auth_headers)
    assert "floor" not in {s["slug"] for s in roster.json()}


@pytest.mark.asyncio
async def test_patch_seat_prompt_skills_models(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    pid = await _project(client, auth_headers, "patch-seat")
    await client.post(f"/api/v1/projects/{pid}/org/ensure", headers=auth_headers)
    seats = (await client.get(f"/api/v1/projects/{pid}/seats", headers=auth_headers)).json()
    product = next(s for s in seats if s["slug"] == "product")
    assert "prompt" in product
    patch = await client.patch(
        f"/api/v1/projects/{pid}/seats/{product['id']}",
        headers=auth_headers,
        json={
            "description": "Own the ship sentence.",
            "prompt": "You are Product. Gate scope.",
            "skills": ["ship-review"],
            "preferred_models": ["anthropic/claude-sonnet-4"],
            "tools": ["read", "webfetch"],
        },
    )
    assert patch.status_code == 200, patch.text
    body = patch.json()
    assert body["description"] == "Own the ship sentence."
    assert "Gate scope" in body["prompt"]
    assert body["skills"] == ["ship-review"]
    assert body["preferred_models"] == ["anthropic/claude-sonnet-4"]
    assert "webfetch" in body["tools"]


@pytest.mark.asyncio
async def test_add_and_remove_seat(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    pid = await _project(client, auth_headers, "add-rm")
    await client.post(f"/api/v1/projects/{pid}/org/ensure", headers=auth_headers)
    created = await client.post(
        f"/api/v1/projects/{pid}/seats",
        headers=auth_headers,
        json={"name": "Intern", "slug": "intern", "template": "scout", "kind": "bot"},
    )
    assert created.status_code == 201, created.text
    sid = created.json()["id"]
    removed = await client.post(
        f"/api/v1/projects/{pid}/seats/{sid}/fire", headers=auth_headers
    )
    assert removed.json()["fired"] is True


@pytest.mark.asyncio
async def test_channel_and_team_create_delete(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    pid = await _project(client, auth_headers, "ch-team")
    await client.post(f"/api/v1/projects/{pid}/org/ensure", headers=auth_headers)
    team = await client.post(
        f"/api/v1/projects/{pid}/teams",
        headers=auth_headers,
        json={"name": "QA", "slug": "qa-desk", "mention": "qa-desk", "lane": "line"},
    )
    assert team.status_code == 201, team.text
    tid = team.json()["id"]
    ch = await client.post(
        f"/api/v1/projects/{pid}/channels",
        headers=auth_headers,
        json={"name": "qa", "slug": "qa", "team_id": tid},
    )
    assert ch.status_code == 201, ch.text
    gone_ch = await client.delete(
        f"/api/v1/projects/{pid}/channels/{ch.json()['id']}", headers=auth_headers
    )
    assert gone_ch.status_code == 204
    gone_team = await client.delete(
        f"/api/v1/projects/{pid}/teams/{tid}", headers=auth_headers
    )
    assert gone_team.status_code == 204
    blocked = await client.delete(
        f"/api/v1/projects/{pid}/teams/"
        + (
            await client.get(f"/api/v1/projects/{pid}/teams", headers=auth_headers)
        ).json()[0]["id"],
        headers=auth_headers,
    )
    # Starter teams still have seats
    assert blocked.status_code == 409


@pytest.mark.asyncio
async def test_patch_reports_to_rejects_cycle(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    pid = await _project(client, auth_headers, "cycle-seat")
    await client.post(f"/api/v1/projects/{pid}/org/ensure", headers=auth_headers)
    seats = (await client.get(f"/api/v1/projects/{pid}/seats", headers=auth_headers)).json()
    you = next(s for s in seats if s["slug"] == "you")
    product = next(s for s in seats if s["slug"] == "product")
    bad = await client.patch(
        f"/api/v1/projects/{pid}/seats/{you['id']}",
        headers=auth_headers,
        json={"reports_to_id": product["id"]},
    )
    assert bad.status_code == 400
    ok = await client.patch(
        f"/api/v1/projects/{pid}/seats/{product['id']}",
        headers=auth_headers,
        json={"reports_to_id": you["id"]},
    )
    assert ok.status_code == 200
    assert ok.json()["reports_to_id"] == you["id"]
