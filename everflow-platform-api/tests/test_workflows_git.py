"""Tests for the clean-room ``n8n-nodes-base.git`` executor.

Covers:

- ``clone`` via ``ctx.mocks['git']`` returns expected fields
- ``pull`` via mock
- ``commit`` via mock
- ``push`` via mock
- ``log`` via mock returns one item per commit
- No mock + no real backend → raises a clear ``RuntimeError``
- End-to-end: Manual Trigger → git (clone via mock) → Set sees repositoryPath
- Descriptor is registered
"""

from __future__ import annotations

import json

import pytest

from app.services.workflows.engine import EngineContext, WorkflowEngine
from app.services.workflows.graph import ExecGraph, ExecNode
from app.services.workflows.items import ExecutionItem
from app.services.workflows.nodes.git import _dulwich_available, _mock_key, exec_git


# ── Helpers ───────────────────────────────────────────────────────────


def _node(params: dict, name: str = "Git") -> ExecNode:
    return ExecNode(
        id="g1",
        name=name,
        type="n8n-nodes-base.git",
        type_version=1,
        parameters=params,
        credentials=None,
        position={"x": 0, "y": 0},
    )


def _ctx(mocks: dict | None = None) -> EngineContext:
    g = ExecGraph(nodes_by_id={}, nodes_by_name={})
    return EngineContext(graph=g, mocks=mocks or {})


def _k(operation: str, params: dict) -> str:
    return _mock_key(operation, {**params, "operation": operation})


# ── 1. clone via mock returns expected fields ────────────────────────


@pytest.mark.asyncio
async def test_clone_via_mock_returns_expected_fields() -> None:
    node = _node(
        {
            "operation": "clone",
            "repositoryUrl": "https://example.com/foo/bar.git",
            "targetPath": "/tmp/bar",
            "branch": "main",
        }
    )
    payload = {
        "repositoryUrl": "https://example.com/foo/bar.git",
        "targetPath": "/tmp/bar",
        "branch": "main",
        "commit": "deadbeef",
    }
    ctx = _ctx({"git": {_k("clone", {"repositoryUrl": "https://example.com/foo/bar.git", "targetPath": "/tmp/bar", "branch": "main"}): payload}})

    out = await exec_git(node, [ExecutionItem(json={})], ctx=ctx)
    assert len(out) == 1
    out_idx, items = out[0]
    assert out_idx == 0
    assert len(items) == 1
    assert items[0].json["repositoryUrl"] == payload["repositoryUrl"]
    assert items[0].json["targetPath"] == payload["targetPath"]
    assert items[0].json["branch"] == payload["branch"]
    assert items[0].json["commit"] == payload["commit"]


# ── 2. pull via mock ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pull_via_mock() -> None:
    node = _node({"operation": "pull", "repositoryPath": "/tmp/bar"})
    payload = {
        "repositoryPath": "/tmp/bar",
        "commit": "abc1234",
        "filesChanged": ["README.md", "src/main.py"],
    }
    ctx = _ctx(
        {
            "git": {
                _k("pull", {"repositoryPath": "/tmp/bar"}): payload,
            }
        }
    )

    out = await exec_git(node, [ExecutionItem(json={})], ctx=ctx)
    res = out[0][1][0].json
    assert res["repositoryPath"] == "/tmp/bar"
    assert res["commit"] == "abc1234"
    assert res["filesChanged"] == ["README.md", "src/main.py"]


# ── 3. commit via mock ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_commit_via_mock() -> None:
    node = _node(
        {
            "operation": "commit",
            "repositoryPath": "/tmp/bar",
            "message": "Initial commit",
            "files": ["a.txt", "b.txt"],
        }
    )
    payload = {
        "commit": "f00dface",
        "message": "Initial commit",
        "filesCommitted": ["a.txt", "b.txt"],
    }
    ctx = _ctx(
        {
            "git": {
                _k(
                    "commit",
                    {
                        "repositoryPath": "/tmp/bar",
                        "message": "Initial commit",
                        "files": ["a.txt", "b.txt"],
                    },
                ): payload,
            }
        }
    )

    out = await exec_git(node, [ExecutionItem(json={})], ctx=ctx)
    res = out[0][1][0].json
    assert res["commit"] == "f00dface"
    assert res["message"] == "Initial commit"
    assert res["filesCommitted"] == ["a.txt", "b.txt"]


# ── 4. push via mock ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_push_via_mock() -> None:
    node = _node(
        {"operation": "push", "repositoryPath": "/tmp/bar", "branch": "feature/x"}
    )
    payload = {"pushed": True, "branch": "feature/x"}
    ctx = _ctx(
        {
            "git": {
                _k("push", {"repositoryPath": "/tmp/bar", "branch": "feature/x"}): payload,
            }
        }
    )

    out = await exec_git(node, [ExecutionItem(json={})], ctx=ctx)
    res = out[0][1][0].json
    assert res["pushed"] is True
    assert res["branch"] == "feature/x"


# ── 5. log via mock returns multiple items (one per commit) ───────────


@pytest.mark.asyncio
async def test_log_via_mock_returns_one_item_per_commit() -> None:
    node = _node(
        {
            "operation": "log",
            "repositoryPath": "/tmp/bar",
            "maxLogEntries": 10,
        }
    )
    mock_commits = [
        {
            "hash": "aaaaaaa",
            "author": "Alice",
            "email": "alice@example.com",
            "date": 1_700_000_000,
            "message": "first",
        },
        {
            "hash": "bbbbbbb",
            "author": "Bob",
            "email": "bob@example.com",
            "date": 1_700_000_100,
            "message": "second",
        },
        {
            "hash": "ccccccc",
            "author": "Carol",
            "email": "carol@example.com",
            "date": 1_700_000_200,
            "message": "third",
        },
    ]
    ctx = _ctx(
        {
            "git": {
                _k("log", {"repositoryPath": "/tmp/bar", "maxLogEntries": 10}): mock_commits,
            }
        }
    )

    out = await exec_git(node, [ExecutionItem(json={})], ctx=ctx)
    out_idx, items = out[0]
    assert out_idx == 0
    assert len(items) == 3
    assert items[0].json["hash"] == "aaaaaaa"
    assert items[0].json["author"] == "Alice"
    assert items[0].json["email"] == "alice@example.com"
    assert items[0].json["date"] == 1_700_000_000
    assert items[0].json["message"] == "first"
    assert items[2].json["hash"] == "ccccccc"


@pytest.mark.asyncio
async def test_log_via_mock_with_commits_wrapper() -> None:
    """Allow ``{"commits": [...]}`` shape for log mocks."""
    node = _node(
        {
            "operation": "log",
            "repositoryPath": "/tmp/bar",
            "maxLogEntries": 2,
        }
    )
    ctx = _ctx(
        {
            "git": {
                _k("log", {"repositoryPath": "/tmp/bar", "maxLogEntries": 2}): {
                    "commits": [
                        {
                            "hash": "1111111",
                            "author": "A",
                            "email": "a@x",
                            "date": 1,
                            "message": "m1",
                        },
                        {
                            "hash": "2222222",
                            "author": "B",
                            "email": "b@x",
                            "date": 2,
                            "message": "m2",
                        },
                    ]
                }
            }
        }
    )
    out = await exec_git(node, [ExecutionItem(json={})], ctx=ctx)
    items = out[0][1]
    assert len(items) == 2
    assert items[0].json["hash"] == "1111111"
    assert items[1].json["hash"] == "2222222"


# ── 6. No mock + no backend → raises ─────────────────────────────────


@pytest.mark.asyncio
async def test_no_mock_no_backend_raises_for_clone() -> None:
    if _dulwich_available():
        pytest.skip("dulwich installed; would attempt real clone")

    node = _node(
        {
            "operation": "clone",
            "repositoryUrl": "https://example.com/x.git",
            "targetPath": "/tmp/x",
        }
    )
    ctx = _ctx({})

    with pytest.raises(RuntimeError) as exc:
        await exec_git(node, [ExecutionItem(json={})], ctx=ctx)
    msg = str(exc.value)
    assert "git" in msg.lower()
    assert "mock" in msg.lower()


@pytest.mark.asyncio
async def test_no_mock_no_backend_raises_for_log() -> None:
    if _dulwich_available():
        pytest.skip("dulwich installed; would attempt real log")

    node = _node({"operation": "log", "repositoryPath": "/tmp/x"})
    ctx = _ctx({})

    with pytest.raises(RuntimeError) as exc:
        await exec_git(node, [ExecutionItem(json={})], ctx=ctx)
    msg = str(exc.value)
    assert "git" in msg.lower()
    assert "mock" in msg.lower()


# ── 7. End-to-end: Manual Trigger → git (clone via mock) → Set ───────


def _doc(nodes, connections):
    return {"name": "git-e2e", "nodes": nodes, "connections": connections}


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
async def test_e2e_manual_git_clone_set_sees_repository_path() -> None:
    doc = _doc(
        [
            _n("t1", "Start", "n8n-nodes-base.manualTrigger"),
            _n(
                "g1",
                "CloneRepo",
                "n8n-nodes-base.git",
                {
                    "operation": "clone",
                    "repositoryUrl": "https://example.com/foo/bar.git",
                    "targetPath": "/tmp/bar",
                    "branch": "main",
                },
            ),
            _n(
                "x1",
                "Inspect",
                "n8n-nodes-base.set",
                {
                    "assignments": {
                        "assignments": [
                            {
                                "name": "repo",
                                "value": "={{ $json.repositoryUrl }}",
                                "type": "string",
                            },
                            {
                                "name": "path",
                                "value": "={{ $json.targetPath }}",
                                "type": "string",
                            },
                            {
                                "name": "sha",
                                "value": "={{ $json.commit }}",
                                "type": "string",
                            },
                        ]
                    },
                    "includeOtherFields": False,
                },
            ),
        ],
        {
            "Start": {"main": [[{"node": "CloneRepo", "type": "main", "index": 0}]]},
            "CloneRepo": {"main": [[{"node": "Inspect", "type": "main", "index": 0}]]},
        },
    )
    clone_key = _mock_key(
        "clone",
        {
            "operation": "clone",
            "repositoryUrl": "https://example.com/foo/bar.git",
            "targetPath": "/tmp/bar",
            "branch": "main",
        },
    )
    mocks = {
        "git": {
            clone_key: {
                "repositoryUrl": "https://example.com/foo/bar.git",
                "targetPath": "/tmp/bar",
                "branch": "main",
                "commit": "abc1234",
            }
        }
    }
    engine = WorkflowEngine(doc, mocks=mocks)
    result = await engine.run(trigger="manual")
    assert result.status == "success", result.error_message

    git_step = next(s for s in result.steps if s.node_name == "CloneRepo")
    assert git_step.status == "success"
    assert git_step.output_count == 1

    inspect_step = next(s for s in result.steps if s.node_name == "Inspect")
    assert inspect_step.status == "success"
    assert inspect_step.sample_output
    inspected = inspect_step.sample_output[0]["json"]
    assert inspected["repo"] == "https://example.com/foo/bar.git"
    assert inspected["path"] == "/tmp/bar"
    assert inspected["sha"] == "abc1234"

    final = result.final_items
    assert final
    assert final[0]["json"]["path"] == "/tmp/bar"
    assert final[0]["json"]["sha"] == "abc1234"


# ── 8. Descriptor is registered ──────────────────────────────────────


def test_descriptor_is_registered() -> None:
    from app.services.workflows.nodes import descriptors as _  # noqa: F401
    from app.services.workflows.registry import REGISTRY, SUPPORTED_NODE_TYPES

    assert "n8n-nodes-base.git" in REGISTRY
    assert "n8n-nodes-base.git" in SUPPORTED_NODE_TYPES
    assert SUPPORTED_NODE_TYPES["n8n-nodes-base.git"] == "input"
    desc = REGISTRY["n8n-nodes-base.git"]
    assert desc.executor.endswith(":exec_git")
    assert desc.category == "input"


# ── 9. Mock key format is stable / json-based ────────────────────────


def test_mock_key_is_deterministic_json() -> None:
    k1 = _mock_key(
        "clone",
        {
            "operation": "clone",
            "repositoryUrl": "x",
            "targetPath": "y",
            "branch": "main",
        },
    )
    k2 = _mock_key(
        "clone",
        {
            "branch": "main",
            "targetPath": "y",
            "repositoryUrl": "x",
            "operation": "clone",
        },
    )
    assert k1 == k2
    # Verify the JSON portion is exactly sorted
    assert k1.startswith("clone|")
    payload = json.loads(k1.split("|", 1)[1])
    assert payload == {
        "branch": "main",
        "operation": "clone",
        "repositoryUrl": "x",
        "targetPath": "y",
    }
