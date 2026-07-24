"""Unit tests for in-sandbox SSH key generation."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.deploy_keys import generate_ssh_keypair_in_sandbox
from app.services.sandbox_agent_client import SandboxAgentError

_PUB = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFakePublicKeyMaterial everflow-deploy\n"
_PRIV = "-----BEGIN OPENSSH PRIVATE KEY-----\nTEST\n-----END OPENSSH PRIVATE KEY-----\n"
_FP_STDOUT = "256 SHA256:abcdefghijklmnopqrstuvwxyz0123456789ABCD everflow-deploy (ED25519)\n"


@pytest.mark.asyncio
async def test_generate_ssh_keypair_in_sandbox_happy_path():
    exec_calls: list[tuple[str, list[str]]] = []
    read_paths: list[str] = []

    async def fake_exec(sandbox_name: str, *, cmd: str, args: list[str] | None = None, **_kw):
        assert sandbox_name == "sb-demo"
        argv = list(args or [])
        exec_calls.append((cmd, argv))
        if cmd == "mkdir":
            return {"exit_code": 0, "stdout": "", "stderr": ""}
        if cmd == "ssh-keygen" and "-lf" in argv:
            return {"exit_code": 0, "stdout": _FP_STDOUT, "stderr": ""}
        if cmd == "ssh-keygen":
            return {"exit_code": 0, "stdout": "", "stderr": ""}
        if cmd == "rm":
            return {"exit_code": 0, "stdout": "", "stderr": ""}
        return {"exit_code": 1, "stdout": "", "stderr": f"unexpected cmd {cmd}"}

    async def fake_read_fs(sandbox_name: str, path: str):
        assert sandbox_name == "sb-demo"
        read_paths.append(path)
        if path.endswith(".pub"):
            return _PUB
        return _PRIV

    client = MagicMock()
    client.exec = AsyncMock(side_effect=fake_exec)
    client.read_fs = AsyncMock(side_effect=fake_read_fs)

    result = await generate_ssh_keypair_in_sandbox(client, "sb-demo")

    assert result["public_key"] == _PUB
    assert result["private_key"] == _PRIV
    assert result["fingerprint"] == "SHA256:abcdefghijklmnopqrstuvwxyz0123456789ABCD"

    cmds = [c for c, _ in exec_calls]
    assert cmds[0] == "mkdir"
    assert cmds[1] == "ssh-keygen"
    assert "-t" in exec_calls[1][1] and "ed25519" in exec_calls[1][1]
    assert "-N" in exec_calls[1][1]
    assert cmds[2] == "ssh-keygen" and "-lf" in exec_calls[2][1]
    assert cmds[-1] == "rm"

    assert len(read_paths) == 2
    assert read_paths[0].endswith(".pub")
    assert read_paths[1] == read_paths[0].removesuffix(".pub")
    assert all(p.startswith("/workspace/.everflow/deploy-keys/") for p in read_paths)


@pytest.mark.asyncio
async def test_generate_ssh_keypair_raises_when_ssh_keygen_missing():
    async def fake_exec(_sandbox_name: str, *, cmd: str, args: list[str] | None = None, **_kw):
        if cmd == "mkdir":
            return {"exit_code": 0, "stdout": "", "stderr": ""}
        if cmd == "ssh-keygen":
            return {
                "exit_code": 127,
                "stdout": "",
                "stderr": "ssh-keygen: command not found",
            }
        return {"exit_code": 0, "stdout": "", "stderr": ""}

    client = MagicMock()
    client.exec = AsyncMock(side_effect=fake_exec)
    client.read_fs = AsyncMock()

    with pytest.raises(SandboxAgentError, match="ssh-keygen failed"):
        await generate_ssh_keypair_in_sandbox(client, "sb-demo")

    client.read_fs.assert_not_awaited()
