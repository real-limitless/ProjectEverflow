"""Unit tests for detached job spawn (setsid detach + pid capture)."""

from __future__ import annotations

import asyncio

from app.jobs import _build_spawn_script, _pid_path_for_log, start_job


def test_pid_path_for_log() -> None:
    assert _pid_path_for_log("/workspace/.everflow/jobs/abc.log") == (
        "/workspace/.everflow/jobs/abc.pid"
    )
    assert _pid_path_for_log("/tmp/out") == "/tmp/out.pid"


def test_build_spawn_script_uses_setsid_and_redirects_stdio() -> None:
    script = _build_spawn_script(
        command="sleep 300",
        cwd="/workspace/app",
        log_path="/workspace/.everflow/jobs/j1.log",
        append_log=False,
    )
    assert "setsid -f" in script
    assert "</dev/null" in script
    assert "/workspace/.everflow/jobs/j1.log" in script
    assert "j1.pid" in script
    assert "sleep 300" in script
    assert " > " in script or ">>" in script
    # Fallback only after setsid path.
    assert "nohup sh -c" in script
    assert script.index("setsid -f") < script.index("nohup sh -c")


def test_build_spawn_script_append_log() -> None:
    script = _build_spawn_script(
        command="npm run dev",
        cwd="/workspace",
        log_path="/workspace/.everflow/jobs/j2.log",
        append_log=True,
    )
    assert ">>" in script
    assert "npm run dev" in script


class _FakeBackend:
    def __init__(self, stdout: str = "4242\n", code: int = 0) -> None:
        self.stdout = stdout
        self.code = code
        self.calls: list[tuple] = []

    async def exec(self, name, cmd, args, **kwargs):  # noqa: ANN001, ANN003
        self.calls.append((name, cmd, args, kwargs))
        return self.code, self.stdout, ""

    async def write_fs(self, name, path, content):  # noqa: ANN001
        self.calls.append(("write_fs", name, path, content))

    async def read_fs(self, name, path):  # noqa: ANN001
        raise FileNotFoundError(path)

    async def list_fs(self, name, path):  # noqa: ANN001
        return []


def test_start_job_uses_detached_spawn_script() -> None:
    backend = _FakeBackend(stdout="999\n")

    async def _run() -> dict:
        return await start_job(
            backend,  # type: ignore[arg-type]
            "sb-test",
            title="sleep",
            command="sleep 60",
            cwd="/workspace",
        )

    meta = asyncio.run(_run())
    assert meta["pid"] == 999
    assert meta["status"] == "running"
    assert meta["command"] == "sleep 60"
    # First call is mkdir, second is spawn
    spawn_calls = [c for c in backend.calls if c[0] == "sb-test" and c[1] == "sh"]
    assert len(spawn_calls) >= 1
    script = spawn_calls[-1][2][1]
    assert "setsid -f" in script
    assert "sleep 60" in script
