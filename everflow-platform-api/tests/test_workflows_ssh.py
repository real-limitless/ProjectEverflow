"""Tests for the ``n8n-nodes-base.ssh`` clean-room executor.

Covers:

- executeCommand via ``ctx.mocks['ssh']`` returns stdout/stderr/exitCode.
- ``command`` parameter expression evaluation per item.
- ``cwd`` parameter is captured on the output item.
- No mock + no real backend → raises a clear ``RuntimeError``.
- End-to-end: Manual Trigger → ssh (mocked) → Set sees stdout.
"""

from __future__ import annotations

import pytest

from app.services.workflows.engine import EngineContext, WorkflowEngine
from app.services.workflows.graph import ExecGraph, ExecNode
from app.services.workflows.items import ExecutionItem
from app.services.workflows.nodes.data_io import exec_ssh


# ── Helpers ───────────────────────────────────────────────────────────


def _node(params: dict, name: str = "SSH") -> ExecNode:
    return ExecNode(
        id="ssh1",
        name=name,
        type="n8n-nodes-base.ssh",
        type_version=1,
        parameters=params,
        credentials=None,
        position={"x": 0, "y": 0},
    )


def _ctx(mocks: dict | None = None) -> EngineContext:
    g = ExecGraph(nodes_by_id={}, nodes_by_name={})
    return EngineContext(graph=g, mocks=mocks or {})


# ── 1. executeCommand via mock returns stdout/stderr/exitCode ─────────


@pytest.mark.asyncio
async def test_execute_command_via_mock_returns_streams() -> None:
    node = _node({"operation": "executeCommand", "command": "ls -la"})
    ctx = _ctx(
        {
            "ssh": {
                "ls -la": {
                    "stdout": "file1.txt\nfile2.txt\n",
                    "stderr": "",
                    "exitCode": 0,
                }
            }
        }
    )

    out = await exec_ssh(node, [ExecutionItem(json={})], ctx=ctx)

    assert len(out) == 1
    out_idx, items = out[0]
    assert out_idx == 0
    assert len(items) == 1
    payload = items[0].json
    assert payload["command"] == "ls -la"
    assert payload["stdout"] == "file1.txt\nfile2.txt\n"
    assert payload["stderr"] == ""
    assert payload["exitCode"] == 0


# ── 2. command expression evaluation per item ────────────────────────


@pytest.mark.asyncio
async def test_command_expression_evaluated_per_item() -> None:
    node = _node(
        {
            "operation": "executeCommand",
            "command": "={{ 'echo ' + $json.greet }}",
        }
    )
    ctx = _ctx(
        {
            "ssh": {
                "echo hello": {
                    "stdout": "hello\n",
                    "stderr": "",
                    "exitCode": 0,
                },
                "echo hi": {
                    "stdout": "hi\n",
                    "stderr": "",
                    "exitCode": 0,
                },
            }
        }
    )

    items = [
        ExecutionItem(json={"greet": "hello"}),
        ExecutionItem(json={"greet": "hi"}),
    ]
    out = await exec_ssh(node, items, ctx=ctx)
    _, produced = out[0]
    assert len(produced) == 2
    assert produced[0].json["stdout"] == "hello\n"
    assert produced[0].json["command"] == "echo hello"
    assert produced[1].json["stdout"] == "hi\n"
    assert produced[1].json["command"] == "echo hi"


# ── 3. cwd parameter is captured ─────────────────────────────────────


@pytest.mark.asyncio
async def test_cwd_parameter_captured_on_output() -> None:
    node = _node(
        {
            "operation": "executeCommand",
            "command": "pwd",
            "cwd": "/var/log",
        }
    )
    ctx = _ctx(
        {
            "ssh": {
                "pwd": {
                    "stdout": "/var/log\n",
                    "stderr": "",
                    "exitCode": 0,
                }
            }
        }
    )

    out = await exec_ssh(node, [ExecutionItem(json={})], ctx=ctx)
    payload = out[0][1][0].json
    assert payload["cwd"] == "/var/log"
    assert payload["stdout"] == "/var/log\n"


# ── 4. No mock + no real backend → raises clear error ─────────────────


@pytest.mark.asyncio
async def test_no_mock_no_real_backend_raises() -> None:
    node = _node({"operation": "executeCommand", "command": "whoami"})
    ctx = _ctx({})

    with pytest.raises(RuntimeError) as exc:
        await exec_ssh(node, [ExecutionItem(json={})], ctx=ctx)
    msg = str(exc.value)
    assert "ssh" in msg.lower()
    assert ("mock" in msg.lower()) or ("asyncssh" in msg.lower())


@pytest.mark.asyncio
async def test_missing_command_parameter_raises() -> None:
    node = _node({"operation": "executeCommand"})
    ctx = _ctx({"ssh": {}})

    with pytest.raises(ValueError, match="command"):
        await exec_ssh(node, [ExecutionItem(json={})], ctx=ctx)


@pytest.mark.asyncio
async def test_unsupported_operation_raises() -> None:
    node = _node({"operation": "download", "command": "ls"})
    ctx = _ctx({"ssh": {"ls": {"stdout": "", "stderr": "", "exitCode": 0}}})

    with pytest.raises(ValueError, match="unsupported operation"):
        await exec_ssh(node, [ExecutionItem(json={})], ctx=ctx)


# ── 5. Mock present but command not found raises clearly ─────────────


@pytest.mark.asyncio
async def test_mock_without_matching_entry_raises() -> None:
    node = _node({"operation": "executeCommand", "command": "uname -a"})
    ctx = _ctx({"ssh": {"ls": {"stdout": "", "stderr": "", "exitCode": 0}}})

    with pytest.raises(RuntimeError, match="mock present"):
        await exec_ssh(node, [ExecutionItem(json={})], ctx=ctx)


# ── 6. End-to-end: Manual Trigger → ssh (mocked) → Set ───────────────


def _doc(nodes, connections):
    return {"name": "ssh-e2e", "nodes": nodes, "connections": connections}


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
async def test_e2e_manual_ssh_set_sees_stdout() -> None:
    doc = _doc(
        [
            _n("t1", "Start", "n8n-nodes-base.manualTrigger"),
            _n(
                "s1",
                "RunSSH",
                "n8n-nodes-base.ssh",
                {
                    "operation": "executeCommand",
                    "command": "hostname",
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
                                "name": "out",
                                "value": "={{ $json.stdout }}",
                                "type": "string",
                            },
                            {
                                "name": "rc",
                                "value": "={{ $json.exitCode }}",
                                "type": "number",
                            },
                            {
                                "name": "cmd",
                                "value": "={{ $json.command }}",
                                "type": "string",
                            },
                        ]
                    },
                    "includeOtherFields": False,
                },
            ),
        ],
        {
            "Start": {"main": [[{"node": "RunSSH", "type": "main", "index": 0}]]},
            "RunSSH": {"main": [[{"node": "Inspect", "type": "main", "index": 0}]]},
        },
    )
    mocks = {
        "ssh": {
            "hostname": {
                "stdout": "edge-node-01\n",
                "stderr": "",
                "exitCode": 0,
            }
        }
    }
    engine = WorkflowEngine(doc, mocks=mocks)
    result = await engine.run(trigger="manual")
    assert result.status == "success", result.error_message

    ssh_step = next(s for s in result.steps if s.node_name == "RunSSH")
    assert ssh_step.status == "success"
    assert ssh_step.output_count == 1

    inspect_step = next(s for s in result.steps if s.node_name == "Inspect")
    assert inspect_step.status == "success"
    assert inspect_step.sample_output
    inspected = inspect_step.sample_output[0]["json"]
    assert inspected["out"] == "edge-node-01\n"
    assert inspected["rc"] == 0
    assert inspected["cmd"] == "hostname"

    # final items also carry the mapped fields
    final = result.final_items
    assert final
    assert final[0]["json"]["out"] == "edge-node-01\n"
    assert final[0]["json"]["rc"] == 0


# ── 7. Descriptor is registered ─────────────────────────────────────


def test_descriptor_is_registered() -> None:
    from app.services.workflows.nodes import descriptors as _  # noqa: F401
    from app.services.workflows.registry import REGISTRY, SUPPORTED_NODE_TYPES

    assert "n8n-nodes-base.ssh" in REGISTRY
    assert "n8n-nodes-base.ssh" in SUPPORTED_NODE_TYPES
    assert SUPPORTED_NODE_TYPES["n8n-nodes-base.ssh"] == "input"
    desc = REGISTRY["n8n-nodes-base.ssh"]
    assert desc.executor.endswith(":exec_ssh")
    assert desc.category == "input"
