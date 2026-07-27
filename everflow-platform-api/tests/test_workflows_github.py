"""Tests for the GitHub node executors (``n8n-nodes-base.github`` and
``n8n-nodes-base.githubTrigger``).

Covers:

- ``github``:
    - ``github_response`` dict mock → response used verbatim
    - ``github_response`` callable mock receives ``(operation, owner, repo, params, item, ctx)``
    - ``http_response`` fallback unwraps a JSON body
    - Offline ``createIssue`` (number present, html_url contains owner/repo)
    - Offline ``getIssue``
    - Offline ``updateIssue``
    - Offline ``createPR``
    - Offline ``getPR``
    - Offline ``mergePR`` (merged=True)
    - Offline ``createRepo``
    - Offline ``getRepo``
    - Operation reflected in emitted item
    - owner/repo defaults from ``$json``
    - Empty owner → no item
    - End-to-end: Manual → github (getIssue mock) → Set sees ``number``
- ``githubTrigger``:
    - ``github_event`` dict mock → fields extracted
    - ``github_event`` callable mock receives ``(node, ctx)``
    - ``trigger_payload`` fallback
    - Offline synthetic push event
    - End-to-end: githubTrigger as workflow start → Set sees ``ref`` and ``repository``
- Descriptor registration (CI invariant) for both types
"""

from __future__ import annotations

from typing import Any

import pytest

from app.services.workflows.engine import EngineContext, WorkflowEngine
from app.services.workflows.graph import ExecNode
from app.services.workflows.items import ExecutionItem
from app.services.workflows.nodes.github import (
    GITHUB_DEFAULT_OPERATION,
    GITHUB_DEFAULT_TRIGGER_EVENTS,
    GITHUB_OPERATIONS,
    exec_github,
    exec_github_trigger,
)


# ── Helpers ───────────────────────────────────────────────────────────


def _node(
    params: dict[str, Any],
    *,
    type_: str = "n8n-nodes-base.github",
    id_: str = "gh1",
    name: str = "GitHub",
    credentials: dict[str, Any] | None = None,
) -> ExecNode:
    return ExecNode(
        id=id_,
        name=name,
        type=type_,
        type_version=1,
        parameters=params,
        credentials=credentials,
        position={"x": 0, "y": 0},
    )


def _ctx(mocks: dict[str, Any] | None = None) -> EngineContext:
    g = type("G", (), {})()
    g.ai_inputs = lambda *a, **k: []
    g.trigger_nodes = lambda preferred=None: []
    g.nodes_by_id = {}
    g.out_edges = {}
    g.main_successors = lambda *a, **k: []
    return EngineContext(graph=g, mocks=mocks or {})  # type: ignore[arg-type]


def _out_items(result) -> list[ExecutionItem]:
    out: list[ExecutionItem] = []
    for _idx, items in result:
        out.extend(items)
    return out


# ══════════════════════════════════════════════════════════════════════
#  github (action)
# ══════════════════════════════════════════════════════════════════════


# ── 1. github_response dict mock ─────────────────────────────────────


@pytest.mark.asyncio
async def test_github_response_dict_mock_is_used_verbatim() -> None:
    node = _node(
        {
            "operation": "getIssue",
            "owner": "octocat",
            "repository": "hello-world",
            "issueNumber": 42,
        }
    )
    ctx = _ctx(
        {
            "github_response": {
                "number": 42,
                "title": "Found a bug",
                "body": "Something is broken",
                "state": "open",
                "user": {"login": "octocat"},
                "html_url": "https://github.com/octocat/hello-world/issues/42",
            }
        }
    )
    out = _out_items(await exec_github(node, [ExecutionItem(json={})], ctx=ctx))
    assert len(out) == 1
    p = out[0].json
    assert p["number"] == 42
    assert p["title"] == "Found a bug"
    assert p["body"] == "Something is broken"
    assert p["state"] == "open"
    assert p["user"]["login"] == "octocat"
    assert p["htmlUrl"] == "https://github.com/octocat/hello-world/issues/42"
    assert p["operation"] == "getIssue"
    assert p["owner"] == "octocat"
    assert p["repository"] == "hello-world"
    assert p["source"] == "github"


# ── 2. github_response callable mock signature ───────────────────────


@pytest.mark.asyncio
async def test_github_response_callable_mock_receives_args() -> None:
    captured: dict[str, Any] = {}

    def _mock(operation, owner, repo, params, item, ctx):
        captured["operation"] = operation
        captured["owner"] = owner
        captured["repo"] = repo
        captured["params"] = params
        captured["item"] = item
        captured["ctx"] = ctx
        return {
            "number": 7,
            "title": "from callable",
            "html_url": "https://github.com/octocat/hello-world/issues/7",
        }

    node = _node(
        {
            "operation": "getIssue",
            "owner": "octocat",
            "repository": "hello-world",
            "issueNumber": 7,
            "extra": "keep",
        }
    )
    ctx = _ctx({"github_response": _mock})
    item = ExecutionItem(json={"hint": 1})
    out = _out_items(await exec_github(node, [item], ctx=ctx))

    assert captured["operation"] == "getIssue"
    assert captured["owner"] == "octocat"
    assert captured["repo"] == "hello-world"
    assert captured["params"]["extra"] == "keep"
    assert captured["item"] is item
    assert captured["ctx"] is ctx

    assert out[0].json["number"] == 7
    assert out[0].json["title"] == "from callable"
    assert out[0].json["htmlUrl"] == "https://github.com/octocat/hello-world/issues/7"


# ── 3. http_response fallback ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_http_response_fallback_unwraps_json_body() -> None:
    node = _node(
        {
            "operation": "getIssue",
            "owner": "octocat",
            "repository": "hello-world",
            "issueNumber": 99,
        }
    )
    ctx = _ctx(
        {
            "http_response": {
                "status_code": 200,
                "body": {
                    "number": 99,
                    "title": "via http",
                    "html_url": "https://github.com/octocat/hello-world/issues/99",
                },
            }
        }
    )
    out = _out_items(await exec_github(node, [ExecutionItem(json={})], ctx=ctx))
    p = out[0].json
    assert p["number"] == 99
    assert p["title"] == "via http"
    assert p["mockSource"] == "http_response"
    assert p["source"] == "github"


# ── 4. Offline createIssue ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_offline_create_issue() -> None:
    node = _node(
        {
            "operation": "createIssue",
            "owner": "octocat",
            "repository": "hello-world",
            "title": "New bug",
            "body": "Steps to reproduce",
        }
    )
    out = _out_items(await exec_github(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert len(out) == 1
    p = out[0].json
    assert isinstance(p["number"], int)
    assert p["title"] == "New bug"
    assert p["body"] == "Steps to reproduce"
    assert p["state"] == "open"
    assert p["user"]["login"] == "mock-user"
    assert "created_at" in p
    assert p["html_url"] == f"https://github.com/octocat/hello-world/issues/{p['number']}"
    assert p["htmlUrl"] == p["html_url"]
    assert p["operation"] == "createIssue"
    assert p["source"] == "github"
    assert p["mockSource"] == "offline"


# ── 5. Offline getIssue ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_offline_get_issue() -> None:
    node = _node(
        {
            "operation": "getIssue",
            "owner": "octocat",
            "repository": "hello-world",
            "issueNumber": 55,
        }
    )
    out = _out_items(await exec_github(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert len(out) == 1
    p = out[0].json
    assert p["number"] == 55
    assert p["title"] == "Mock Issue"
    assert p["body"] == "Mock issue body"
    assert p["state"] == "open"
    assert p["html_url"] == "https://github.com/octocat/hello-world/issues/55"
    assert p["htmlUrl"] == p["html_url"]
    assert p["mockSource"] == "offline"


# ── 6. Offline updateIssue ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_offline_update_issue() -> None:
    node = _node(
        {
            "operation": "updateIssue",
            "owner": "octocat",
            "repository": "hello-world",
            "issueNumber": 33,
            "title": "Updated title",
            "state": "closed",
        }
    )
    out = _out_items(await exec_github(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert len(out) == 1
    p = out[0].json
    assert p["number"] == 33
    assert p["title"] == "Updated title"
    assert p["state"] == "closed"
    assert "updated_at" in p
    assert p["html_url"] == "https://github.com/octocat/hello-world/issues/33"
    assert p["htmlUrl"] == p["html_url"]
    assert p["mockSource"] == "offline"


@pytest.mark.asyncio
async def test_offline_update_issue_defaults_title() -> None:
    node = _node(
        {
            "operation": "updateIssue",
            "owner": "octocat",
            "repository": "hello-world",
            "issueNumber": 10,
        }
    )
    out = _out_items(await exec_github(node, [ExecutionItem(json={})], ctx=_ctx()))
    p = out[0].json
    assert p["title"] == "Mock Issue"
    assert p["state"] == "open"


# ── 7. Offline createPR ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_offline_create_pr() -> None:
    node = _node(
        {
            "operation": "createPR",
            "owner": "octocat",
            "repository": "hello-world",
            "title": "Add feature",
            "head": "feature-branch",
            "base": "main",
        }
    )
    out = _out_items(await exec_github(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert len(out) == 1
    p = out[0].json
    assert isinstance(p["number"], int)
    assert p["title"] == "Add feature"
    assert p["head"] == "feature-branch"
    assert p["base"] == "main"
    assert p["state"] == "open"
    assert p["user"]["login"] == "mock-user"
    assert p["html_url"] == f"https://github.com/octocat/hello-world/pull/{p['number']}"
    assert p["htmlUrl"] == p["html_url"]
    assert p["mergeMethod"] == "merge"
    assert p["mockSource"] == "offline"


# ── 8. Offline getPR ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_offline_get_pr() -> None:
    node = _node(
        {
            "operation": "getPR",
            "owner": "octocat",
            "repository": "hello-world",
            "pullNumber": 88,
        }
    )
    out = _out_items(await exec_github(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert len(out) == 1
    p = out[0].json
    assert p["number"] == 88
    assert p["title"] == "Mock PR"
    assert p["head"] == "feature-branch"
    assert p["base"] == "main"
    assert p["state"] == "open"
    assert p["merged"] is False
    assert p["html_url"] == "https://github.com/octocat/hello-world/pull/88"
    assert p["htmlUrl"] == p["html_url"]
    assert p["mockSource"] == "offline"


# ── 9. Offline mergePR ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_offline_merge_pr() -> None:
    node = _node(
        {
            "operation": "mergePR",
            "owner": "octocat",
            "repository": "hello-world",
            "pullNumber": 77,
            "mergeMethod": "squash",
        }
    )
    out = _out_items(await exec_github(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert len(out) == 1
    p = out[0].json
    assert p["merged"] is True
    assert p["number"] == 77
    assert p["message"] == "Pull Request successfully merged"
    assert isinstance(p["sha"], str)
    assert len(p["sha"]) == 32  # uuid4().hex
    assert p["mergeMethod"] == "squash"
    assert p["htmlUrl"] == "https://github.com/octocat/hello-world/pull/77"
    assert p["mockSource"] == "offline"


# ── 10. Offline createRepo ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_offline_create_repo() -> None:
    node = _node(
        {
            "operation": "createRepo",
            "owner": "octocat",
            "name": "new-project",
            "description": "A new project",
            "private": True,
        }
    )
    out = _out_items(await exec_github(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert len(out) == 1
    p = out[0].json
    assert isinstance(p["id"], int)
    assert p["name"] == "new-project"
    assert p["full_name"] == "octocat/new-project"
    assert p["description"] == "A new project"
    assert p["private"] is True
    assert p["html_url"] == "https://github.com/octocat/new-project"
    assert p["htmlUrl"] == p["html_url"]
    assert "created_at" in p
    assert p["repository"] == "new-project"  # falls back to name
    assert p["mockSource"] == "offline"


# ── 11. Offline getRepo ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_offline_get_repo() -> None:
    node = _node(
        {
            "operation": "getRepo",
            "owner": "octocat",
            "repository": "hello-world",
        }
    )
    out = _out_items(await exec_github(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert len(out) == 1
    p = out[0].json
    assert isinstance(p["id"], int)
    assert p["name"] == "hello-world"
    assert p["full_name"] == "octocat/hello-world"
    assert p["description"] == "Mock repository"
    assert p["private"] is False
    assert p["html_url"] == "https://github.com/octocat/hello-world"
    assert p["htmlUrl"] == p["html_url"]
    assert p["default_branch"] == "main"
    assert p["mockSource"] == "offline"


# ── 12. Operation reflected ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_operation_reflected_in_emitted_item() -> None:
    for op in GITHUB_OPERATIONS:
        params: dict[str, Any] = {
            "operation": op,
            "owner": "octocat",
            "repository": "hello-world",
            "issueNumber": 1,
            "pullNumber": 1,
            "name": "test-repo",
            "title": "T",
            "head": "h",
            "base": "b",
        }
        node = _node(params)
        out = _out_items(await exec_github(node, [ExecutionItem(json={})], ctx=_ctx()))
        assert len(out) == 1, f"no output for {op}"
        assert out[0].json["operation"] == op, f"operation not reflected for {op}"


# ── 13. owner/repo defaults from $json ────────────────────────────────


@pytest.mark.asyncio
async def test_owner_and_repo_default_from_json() -> None:
    node = _node({"operation": "getIssue", "issueNumber": 5})
    item = ExecutionItem(
        json={"owner": "from-json-owner", "repository": "from-json-repo"}
    )
    out = _out_items(await exec_github(node, [item], ctx=_ctx()))
    assert len(out) == 1
    p = out[0].json
    assert p["owner"] == "from-json-owner"
    assert p["repository"] == "from-json-repo"


@pytest.mark.asyncio
async def test_owner_alias_repo_owner_from_json() -> None:
    node = _node({"operation": "getIssue", "issueNumber": 5})
    item = ExecutionItem(json={"repoOwner": "alias-owner", "repo": "alias-repo"})
    out = _out_items(await exec_github(node, [item], ctx=_ctx()))
    assert len(out) == 1
    assert out[0].json["owner"] == "alias-owner"
    assert out[0].json["repository"] == "alias-repo"


@pytest.mark.asyncio
async def test_issue_number_defaults_from_json() -> None:
    node = _node({"operation": "getIssue", "owner": "o", "repository": "r"})
    item = ExecutionItem(json={"number": 123})
    out = _out_items(await exec_github(node, [item], ctx=_ctx()))
    assert out[0].json["number"] == 123


# ── 14. Empty owner → no item ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_empty_owner_skips_item() -> None:
    node = _node(
        {
            "operation": "getIssue",
            "owner": "",
            "repository": "hello-world",
            "issueNumber": 1,
        }
    )
    out = _out_items(await exec_github(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert out == []


@pytest.mark.asyncio
async def test_empty_repository_skips_item() -> None:
    node = _node(
        {
            "operation": "getIssue",
            "owner": "octocat",
            "repository": "",
            "issueNumber": 1,
        }
    )
    out = _out_items(await exec_github(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert out == []


@pytest.mark.asyncio
async def test_empty_owner_and_repo_from_json_skips_item() -> None:
    node = _node({"operation": "getIssue", "issueNumber": 1})
    out = _out_items(await exec_github(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert out == []


# ── 15. Default operation is getIssue ─────────────────────────────────


@pytest.mark.asyncio
async def test_default_operation_is_get_issue() -> None:
    node = _node({"owner": "octocat", "repository": "hello-world", "issueNumber": 1})
    out = _out_items(await exec_github(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert len(out) == 1
    assert out[0].json["operation"] == "getIssue"
    assert GITHUB_DEFAULT_OPERATION == "getIssue"


# ── 16. One output item per input ─────────────────────────────────────


@pytest.mark.asyncio
async def test_one_output_item_per_input() -> None:
    node = _node(
        {"operation": "getIssue", "owner": "o", "repository": "r"}
    )
    items = [
        ExecutionItem(json={"number": 10}),
        ExecutionItem(json={"number": 20}),
        ExecutionItem(json={"number": 30}),
    ]
    out = _out_items(await exec_github(node, items, ctx=_ctx()))
    assert len(out) == 3
    numbers = [o.json["number"] for o in out]
    assert numbers == [10, 20, 30]
    assert all(o.json["source"] == "github" for o in out)


# ── 17. Descriptor registration (action) ──────────────────────────────


def test_github_descriptor_is_registered() -> None:
    from app.services.workflows.nodes import descriptors as _  # noqa: F401
    from app.services.workflows.registry import REGISTRY, SUPPORTED_NODE_TYPES

    assert "n8n-nodes-base.github" in REGISTRY
    assert "n8n-nodes-base.github" in SUPPORTED_NODE_TYPES
    assert SUPPORTED_NODE_TYPES["n8n-nodes-base.github"] == "output"
    desc = REGISTRY["n8n-nodes-base.github"]
    assert desc.executor.endswith(":exec_github")
    assert desc.category == "output"


# ── 18. End-to-end: Manual → github (getIssue mock) → Set sees number ─


def _doc(nodes, connections):
    return {"name": "github-test", "nodes": nodes, "connections": connections}


def _n(id_, name, type_, params=None, position=(0, 0)):
    return {
        "id": id_,
        "name": name,
        "type": type_,
        "typeVersion": 1,
        "position": list(position),
        "parameters": params or {},
    }


@pytest.mark.asyncio
async def test_end_to_end_manual_github_set_sees_number() -> None:
    mocks = {
        "github_response": {
            "number": 42,
            "title": "E2E Issue",
            "body": "from e2e",
            "state": "open",
            "user": {"login": "octocat"},
            "html_url": "https://github.com/octocat/hello-world/issues/42",
        }
    }
    doc = _doc(
        [
            _n("t1", "Start", "n8n-nodes-base.manualTrigger"),
            _n(
                "gh1",
                "GitHub",
                "n8n-nodes-base.github",
                {
                    "operation": "getIssue",
                    "owner": "octocat",
                    "repository": "hello-world",
                    "issueNumber": 42,
                },
            ),
            _n(
                "s1",
                "Downstream",
                "n8n-nodes-base.set",
                {
                    "assignments": {
                        "assignments": [
                            {"name": "result_number", "value": "={{ $json.number }}", "type": "number"},
                            {"name": "result_title", "value": "={{ $json.title }}", "type": "string"},
                            {"name": "result_owner", "value": "={{ $json.owner }}", "type": "string"},
                        ]
                    }
                },
            ),
        ],
        {
            "Start": {"main": [[{"node": "GitHub", "type": "main", "index": 0}]]},
            "GitHub": {"main": [[{"node": "Downstream", "type": "main", "index": 0}]]},
        },
    )
    engine = WorkflowEngine(doc, mocks=mocks)
    result = await engine.run(trigger="manual")
    assert result.status == "success", result.error_message

    gh_step = next(s for s in result.steps if s.node_name == "GitHub")
    assert gh_step.status == "success", gh_step.error
    assert gh_step.output_count == 1
    sample = gh_step.sample_output[0]
    assert sample["json"]["number"] == 42
    assert sample["json"]["title"] == "E2E Issue"
    assert sample["json"]["owner"] == "octocat"

    final = result.final_items
    assert final, "expected at least one final item"
    fjson = final[0].get("json") if isinstance(final[0], dict) else None
    assert fjson is not None
    assert fjson.get("result_number") == 42
    assert fjson.get("result_title") == "E2E Issue"
    assert fjson.get("result_owner") == "octocat"


# ══════════════════════════════════════════════════════════════════════
#  githubTrigger
# ══════════════════════════════════════════════════════════════════════


def _trigger_node(
    params: dict[str, Any] | None = None,
    *,
    id_: str = "ght1",
    name: str = "GitHubTrigger",
) -> ExecNode:
    return ExecNode(
        id=id_,
        name=name,
        type="n8n-nodes-base.githubTrigger",
        type_version=1,
        parameters=params or {},
        credentials=None,
        position={"x": 0, "y": 0},
    )


# ── 19. github_event dict mock → fields extracted ────────────────────


@pytest.mark.asyncio
async def test_github_event_dict_mock_extracts_fields() -> None:
    payload = {
        "ref": "refs/heads/develop",
        "before": "0" * 40,
        "after": "1" * 40,
        "repository": {
            "id": 999,
            "name": "my-repo",
            "full_name": "me/my-repo",
            "html_url": "https://github.com/me/my-repo",
        },
        "pusher": {"name": "me", "email": "me@example.com"},
        "head_commit": {
            "id": "abc123",
            "message": "real commit",
            "author": {"name": "me"},
        },
        "commits": [{"id": "abc123", "message": "real commit"}],
        "compare": "https://github.com/me/my-repo/compare/0...1",
    }
    ctx = _ctx({"github_event": payload})
    node = _trigger_node({"events": ["push"]})

    out = await exec_github_trigger(node, items=[], ctx=ctx)
    assert len(out) == 1
    items = out[0][1]
    assert len(items) == 1
    p = items[0].json
    assert p["event"] == "push"
    assert p["ref"] == "refs/heads/develop"
    assert p["repository"]["name"] == "my-repo"
    assert p["pusher"]["name"] == "me"
    assert p["headCommit"]["id"] == "abc123"
    assert p["headCommit"]["message"] == "real commit"
    assert p["commits"][0]["id"] == "abc123"
    assert p["compare"] == "https://github.com/me/my-repo/compare/0...1"
    assert p["source"] == "githubTrigger"
    assert p["mockSource"] == "github_event"


# ── 20. github_event callable mock signature ─────────────────────────


@pytest.mark.asyncio
async def test_github_event_callable_mock_receives_args() -> None:
    captured: dict[str, Any] = {}

    def _mock(node, ctx):
        captured["node"] = node
        captured["ctx"] = ctx
        return {
            "ref": "refs/heads/main",
            "repository": {"name": "callable-repo"},
            "pusher": {"name": "caller"},
            "head_commit": {"id": "c1", "message": "from callable"},
            "commits": [],
            "compare": "https://github.com/me/callable-repo/compare/a...b",
        }

    ctx = _ctx({"github_event": _mock})
    node = _trigger_node()

    out = await exec_github_trigger(node, items=[], ctx=ctx)
    assert captured["node"] is node
    assert captured["ctx"] is ctx

    items = out[0][1]
    p = items[0].json
    assert p["ref"] == "refs/heads/main"
    assert p["repository"]["name"] == "callable-repo"
    assert p["pusher"]["name"] == "caller"
    assert p["headCommit"]["message"] == "from callable"


# ── 21. trigger_payload fallback ──────────────────────────────────────


@pytest.mark.asyncio
async def test_trigger_payload_fallback_used() -> None:
    fallback = {
        "ref": "refs/heads/fallback",
        "repository": {"name": "fallback-repo"},
        "pusher": {"name": "fb"},
        "head_commit": {"id": "fb1", "message": "fallback commit"},
        "commits": [],
        "compare": "https://github.com/me/fallback-repo/compare/a...b",
    }
    ctx = _ctx({"trigger_payload": fallback})
    node = _trigger_node()

    out = await exec_github_trigger(node, items=[], ctx=ctx)
    items = out[0][1]
    p = items[0].json
    assert p["ref"] == "refs/heads/fallback"
    assert p["repository"]["name"] == "fallback-repo"
    assert p["pusher"]["name"] == "fb"
    assert p["headCommit"]["message"] == "fallback commit"
    assert p["mockSource"] == "trigger_payload"


# ── 22. Offline synthetic push event ──────────────────────────────────


@pytest.mark.asyncio
async def test_offline_synthetic_push_event() -> None:
    node = _trigger_node()
    out = await exec_github_trigger(node, items=[], ctx=_ctx())
    items = out[0][1]
    assert len(items) == 1
    p = items[0].json
    assert p["event"] == "push"
    assert p["ref"] == "refs/heads/main"
    assert p["repository"]["name"] == "mock-repo"
    assert p["repository"]["full_name"] == "mock-owner/mock-repo"
    assert p["pusher"]["name"] == "mock-user"
    assert p["pusher"]["email"] == "mock@example.com"
    assert p["headCommit"]["id"] == "c" * 40
    assert p["headCommit"]["message"] == "Mock commit message"
    assert p["headCommit"]["author"]["name"] == "mock-user"
    assert len(p["commits"]) == 1
    assert p["commits"][0]["id"] == "d" * 40
    assert p["commits"][0]["message"] == "Mock commit"
    assert p["compare"] == "https://github.com/mock-owner/mock-repo/compare/a...b"
    assert p["source"] == "githubTrigger"


@pytest.mark.asyncio
async def test_offline_event_respects_owner_and_repo_params() -> None:
    node = _trigger_node({"owner": "octocat", "repository": "hello-world"})
    out = await exec_github_trigger(node, items=[], ctx=_ctx())
    p = out[0][1][0].json
    assert p["repository"]["name"] == "hello-world"
    assert p["repository"]["full_name"] == "octocat/hello-world"
    assert p["compare"] == "https://github.com/octocat/hello-world/compare/a...b"


@pytest.mark.asyncio
async def test_offline_event_respects_branch_param() -> None:
    node = _trigger_node({"branch": "develop"})
    out = await exec_github_trigger(node, items=[], ctx=_ctx())
    p = out[0][1][0].json
    assert p["ref"] == "refs/heads/develop"


@pytest.mark.asyncio
async def test_offline_event_respects_events_param() -> None:
    node = _trigger_node({"events": ["pull_request"]})
    out = await exec_github_trigger(node, items=[], ctx=_ctx())
    p = out[0][1][0].json
    assert p["event"] == "pull_request"


@pytest.mark.asyncio
async def test_default_trigger_events_is_push() -> None:
    assert "push" in GITHUB_DEFAULT_TRIGGER_EVENTS


# ── 23. Input items passed through with trigger context merged ────────


@pytest.mark.asyncio
async def test_input_items_passed_through_with_context() -> None:
    payload = {
        "ref": "refs/heads/main",
        "repository": {"name": "merge-repo"},
        "pusher": {"name": "merger"},
        "head_commit": {"id": "m1", "message": "merge me"},
        "commits": [],
        "compare": "https://github.com/me/merge-repo/compare/a...b",
    }
    ctx = _ctx({"github_event": payload})
    node = _trigger_node()
    in_items = [ExecutionItem(json={"existing": "data"})]

    out = await exec_github_trigger(node, items=in_items, ctx=ctx)
    items = out[0][1]
    assert len(items) == 1
    p = items[0].json
    assert p["existing"] == "data"
    assert p["ref"] == "refs/heads/main"
    assert p["source"] == "githubTrigger"


# ── 24. Descriptor registration (trigger) ─────────────────────────────


def test_github_trigger_descriptor_is_registered() -> None:
    from app.services.workflows.nodes import descriptors as _  # noqa: F401
    from app.services.workflows.registry import REGISTRY, SUPPORTED_NODE_TYPES

    assert "n8n-nodes-base.githubTrigger" in REGISTRY
    assert "n8n-nodes-base.githubTrigger" in SUPPORTED_NODE_TYPES
    assert SUPPORTED_NODE_TYPES["n8n-nodes-base.githubTrigger"] == "trigger"
    desc = REGISTRY["n8n-nodes-base.githubTrigger"]
    assert desc.executor.endswith(":exec_github_trigger")
    assert desc.category == "trigger"


# ── 25. End-to-end: githubTrigger → Set sees ref and repository ──────


@pytest.mark.asyncio
async def test_end_to_end_github_trigger_set_sees_ref_and_repository() -> None:
    mocks = {
        "github_event": {
            "ref": "refs/heads/main",
            "before": "0" * 40,
            "after": "1" * 40,
            "repository": {
                "id": 42,
                "name": "e2e-repo",
                "full_name": "octocat/e2e-repo",
                "html_url": "https://github.com/octocat/e2e-repo",
            },
            "pusher": {"name": "octocat", "email": "octo@example.com"},
            "head_commit": {
                "id": "c" * 40,
                "message": "E2E commit",
                "author": {"name": "octocat"},
            },
            "commits": [{"id": "d" * 40, "message": "E2E commit"}],
            "compare": "https://github.com/octocat/e2e-repo/compare/0...1",
        }
    }
    doc = _doc(
        [
            _n(
                "ght1",
                "GitHubTrigger",
                "n8n-nodes-base.githubTrigger",
                {"events": ["push"], "owner": "octocat", "repository": "e2e-repo"},
            ),
            _n(
                "s1",
                "Stamp",
                "n8n-nodes-base.set",
                {
                    "assignments": {
                        "assignments": [
                            {"name": "result_ref", "value": "={{ $json.ref }}", "type": "string"},
                            {"name": "result_repo_name", "value": "={{ $json.repository.name }}", "type": "string"},
                            {"name": "result_compare", "value": "={{ $json.compare }}", "type": "string"},
                            {"name": "result_event", "value": "={{ $json.event }}", "type": "string"},
                        ]
                    }
                },
            ),
        ],
        {
            "GitHubTrigger": {"main": [[{"node": "Stamp", "type": "main", "index": 0}]]},
        },
    )
    engine = WorkflowEngine(doc, mocks=mocks)
    result = await engine.run(trigger="githubTrigger")
    assert result.status == "success", result.error_message

    trigger_step = next(s for s in result.steps if s.node_name == "GitHubTrigger")
    assert trigger_step.status == "success", trigger_step.error
    assert trigger_step.output_count == 1
    sample = trigger_step.sample_output[0]
    assert sample["json"]["ref"] == "refs/heads/main"
    assert sample["json"]["repository"]["name"] == "e2e-repo"
    assert sample["json"]["event"] == "push"

    final = result.final_items
    assert final, "expected final items from Stamp"
    fjson = final[0].get("json") if isinstance(final[0], dict) else None
    assert fjson is not None
    assert fjson.get("result_ref") == "refs/heads/main"
    assert fjson.get("result_repo_name") == "e2e-repo"
    assert fjson.get("result_compare") == "https://github.com/octocat/e2e-repo/compare/0...1"
    assert fjson.get("result_event") == "push"