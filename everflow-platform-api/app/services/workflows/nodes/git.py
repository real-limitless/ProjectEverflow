"""Git node executor (clean-room ``n8n-nodes-base.git`` v1).

Supports the 80% operations used in templates:

- ``clone`` — shallow clone a repo to a local path
- ``pull``  — fetch + fast-forward
- ``commit``— stage + commit
- ``push``  — push a branch
- ``log``   — return the last N commits as items

The executor is **mock-first**: tests should set ``ctx.mocks['git']`` keyed
by ``(operation, params_dict_as_json)`` to short-circuit calls. When no
mock entry is found, the executor falls back to a real implementation via
:mod:`dulwich` (pure-Python git library). If neither is available the
executor raises a clear ``RuntimeError`` so the run fails loudly instead
of silently no-op'ing.
"""

from __future__ import annotations

import json
import logging
import os
from typing import TYPE_CHECKING, Any

from app.services.workflows.graph import ExecNode
from app.services.workflows.items import ExecutionItem

if TYPE_CHECKING:
    from app.services.workflows.engine import EngineContext

logger = logging.getLogger(__name__)


_GIT_OPERATIONS: tuple[str, ...] = (
    "clone",
    "pull",
    "commit",
    "push",
    "log",
)

# Per-operation param keys that should be normalised into the mock key.
# Keeps tests deterministic regardless of which UI sub-panel a parameter
# was configured in.
_MOCK_KEY_FIELDS: dict[str, tuple[str, ...]] = {
    "clone": ("operation", "repositoryUrl", "targetPath", "branch"),
    "pull": ("operation", "repositoryPath", "branch"),
    "commit": ("operation", "repositoryPath", "message", "files"),
    "push": ("operation", "repositoryPath", "branch"),
    "log": ("operation", "repositoryPath", "maxLogEntries"),
}


def _ectx(item: ExecutionItem, ctx: "EngineContext"):  # noqa: ANN001
    from app.services.workflows.expression import ExpressionContext

    return ExpressionContext(item=item, node_outputs=ctx.node_outputs, now=ctx.now)


def _mock_key(operation: str, params: dict[str, Any]) -> str:
    """Stable string key for ``(operation, params)`` mock lookups."""
    keys = _MOCK_KEY_FIELDS.get(operation, ("operation",))
    pruned: dict[str, Any] = {}
    for k in keys:
        if k == "operation":
            pruned[k] = operation
            continue
        if k in params:
            pruned[k] = params[k]
    return f"{operation}|" + json.dumps(pruned, default=str, sort_keys=True)


def _params_for_key(params: dict[str, Any], operation: str) -> dict[str, Any]:
    """Return the param subset used as the mock key (for error messages)."""
    keys = _MOCK_KEY_FIELDS.get(operation, ("operation",))
    return {k: params.get(k) for k in keys if k in params or k == "operation"}


def _is_scalar(v: Any) -> bool:
    return isinstance(v, (str, int, float, bool)) or v is None


def _mock_lookup(
    ctx: "EngineContext",
    operation: str,
    params: dict[str, Any],
) -> Any:
    """Return a canned result for ``(operation, params)`` from
    ``ctx.mocks['git']`` or ``None`` when no mock matches.
    """
    if not isinstance(ctx.mocks, dict):
        return None
    raw = ctx.mocks.get("git")
    if not isinstance(raw, dict):
        return None

    str_key = _mock_key(operation, params)
    if str_key in raw:
        return raw[str_key]

    # Flat ``{operation: result}`` shortcut for simple cases.
    if operation in raw and not isinstance(raw[operation], dict):
        return raw[operation]

    # Tuple key for tests that pre-build keys.
    sub = _params_for_key(params, operation)
    if all(_is_scalar(v) for v in sub.values()):
        tuple_key = (operation, *((k, sub[k]) for k in sorted(sub)))
        if tuple_key in raw:
            return raw[tuple_key]

    return None


def _dulwich_available() -> bool:
    try:
        import dulwich  # type: ignore[import-not-found]  # noqa: F401
    except Exception:
        return False
    return True


def _is_repo(repository_path: str) -> bool:
    if not repository_path:
        return False
    return os.path.isdir(os.path.join(repository_path, ".git"))


# ── Real git backend (dulwich) ────────────────────────────────────────


def _real_clone(params: dict[str, Any]) -> dict[str, Any]:
    from dulwich import porcelain

    repository_url = str(params.get("repositoryUrl") or "")
    target_path = str(params.get("targetPath") or "")
    branch = params.get("branch")
    if not repository_url:
        raise ValueError("git: parameters.repositoryUrl is required for clone")
    if not target_path:
        raise ValueError("git: parameters.targetPath is required for clone")

    os.makedirs(os.path.dirname(target_path) or ".", exist_ok=True)
    if branch:
        porcelain.clone(repository_url, target_path, branch=branch, depth=1)
    else:
        porcelain.clone(repository_url, target_path, depth=1)

    commit = _head_commit_sha(target_path)
    return {
        "repositoryUrl": repository_url,
        "targetPath": target_path,
        "branch": branch or _default_branch(target_path),
        "commit": commit,
    }


def _real_pull(params: dict[str, Any]) -> dict[str, Any]:
    from dulwich import porcelain

    repository_path = str(params.get("repositoryPath") or "")
    if not repository_path:
        raise ValueError("git: parameters.repositoryPath is required for pull")
    if not _is_repo(repository_path):
        raise ValueError(f"git: not a repository: {repository_path}")

    before = _head_commit_sha(repository_path)
    porcelain.pull(repository_path)
    after = _head_commit_sha(repository_path)
    return {
        "repositoryPath": repository_path,
        "commit": after,
        "filesChanged": [] if before == after else _working_tree_changes(repository_path),
    }


def _real_commit(params: dict[str, Any]) -> dict[str, Any]:
    from dulwich import porcelain

    repository_path = str(params.get("repositoryPath") or "")
    message = str(params.get("message") or "")
    files = params.get("files")
    if not repository_path:
        raise ValueError("git: parameters.repositoryPath is required for commit")
    if not _is_repo(repository_path):
        raise ValueError(f"git: not a repository: {repository_path}")
    if not message:
        raise ValueError("git: parameters.message is required for commit")

    if not files:
        files = _working_tree_changes(repository_path)
    if not files:
        raise ValueError("git: no files to commit (parameters.files is empty and working tree is clean)")

    paths = [str(f) for f in files if isinstance(f, (str, bytes))]
    porcelain.add(repository_path, paths=paths)
    sha = porcelain.commit(repository_path, message=message)
    return {
        "commit": sha.decode("ascii") if isinstance(sha, bytes) else str(sha),
        "message": message,
        "filesCommitted": paths,
    }


def _real_push(params: dict[str, Any]) -> dict[str, Any]:
    from dulwich import porcelain

    repository_path = str(params.get("repositoryPath") or "")
    branch = str(params.get("branch") or _default_branch(repository_path))
    if not repository_path:
        raise ValueError("git: parameters.repositoryPath is required for push")
    if not _is_repo(repository_path):
        raise ValueError(f"git: not a repository: {repository_path}")

    porcelain.push(repository_path, branch, branch)
    return {"pushed": True, "branch": branch}


def _real_log(params: dict[str, Any]) -> list[dict[str, Any]]:
    from dulwich import porcelain

    repository_path = str(params.get("repositoryPath") or "")
    max_log = int(params.get("maxLogEntries") or 10)
    if not repository_path:
        raise ValueError("git: parameters.repositoryPath is required for log")
    if not _is_repo(repository_path):
        raise ValueError(f"git: not a repository: {repository_path}")

    entries: list[dict[str, Any]] = []
    walker = porcelain.log(repository_path, max_entries=max_log)
    for entry in walker:
        commit = entry.commit
        sha = entry.sha.decode("ascii") if isinstance(entry.sha, bytes) else str(entry.sha)
        entries.append(
            {
                "hash": sha,
                "author": commit.author.decode("utf-8", "replace"),
                "email": commit.email.decode("utf-8", "replace") if commit.email else "",
                "date": commit.author_time,
                "message": commit.message.decode("utf-8", "replace") if commit.message else "",
            }
        )
    return entries


# ── dulwich helpers ───────────────────────────────────────────────────


def _head_commit_sha(repository_path: str) -> str:
    from dulwich import porcelain

    try:
        return porcelain.head(repository_path).decode("ascii")
    except Exception:
        return ""


def _default_branch(repository_path: str) -> str:
    from dulwich import porcelain

    try:
        return str(porcelain.active_branch(repository_path))
    except Exception:
        return "main"


def _working_tree_changes(repository_path: str) -> list[str]:
    """Best-effort list of working-tree changes. Empty if unavailable."""
    try:
        from dulwich import porcelain

        status = porcelain.status(repository_path)
        out: list[str] = []
        for attr in ("unstaged", "staged", "untracked"):
            for path in status.staged.items() if attr == "staged" else []:
                out.append(str(path[0]))
            entries = getattr(getattr(status, attr, None), "items", lambda: [])()
            for path in entries:
                out.append(str(path))
        # de-duplicate while preserving order
        seen: set[str] = set()
        uniq: list[str] = []
        for p in out:
            if p in seen:
                continue
            seen.add(p)
            uniq.append(p)
        return uniq
    except Exception:
        return []


# ── Top-level dispatch ────────────────────────────────────────────────


async def exec_git(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Git node v1.

    See module docstring for the supported operations. The mock path
    (``ctx.mocks['git']``) takes precedence; the real backend is invoked
    only when the mock has no entry for the request.
    """
    params = node.parameters or {}
    operation = str(params.get("operation") or "log").lower()
    if operation not in _GIT_OPERATIONS:
        raise ValueError(
            f"git: unsupported operation {operation!r}; "
            f"expected one of {_GIT_OPERATIONS}"
        )

    base_name = node.name or node.id or "Git"

    # Most operations are 1:1 with the input item stream. ``log`` is the
    # exception: it expands into one item per commit regardless of the
    # input item count.
    if operation == "log":
        return [(0, _exec_log(node, items, ctx=ctx, base_name=base_name))]

    out: list[ExecutionItem] = []
    for item in items:
        ectx = _ectx(item, ctx)
        resolved = _resolve_params(params, operation, ectx)

        mock_result = _mock_lookup(ctx, operation, resolved)
        if mock_result is not None:
            payload = _payload_from_mock(operation, mock_result, resolved)
        else:
            payload = _run_real_or_raise(operation, resolved, base_name)

        ni = item.clone()
        ni.json = {**item.json, **payload}
        out.append(ni)

    return [(0, out)]


def _resolve_params(
    params: dict[str, Any],
    operation: str,
    ectx: Any,
) -> dict[str, Any]:
    """Evaluate ``{{...}}`` expressions in the operation's parameter keys."""
    resolved: dict[str, Any] = {"operation": operation}
    for key in _MOCK_KEY_FIELDS.get(operation, ()):
        if key == "operation":
            continue
        raw = params.get(key)
        if raw is None:
            continue
        value = raw
        try:
            from app.services.workflows.expression import evaluate

            value = evaluate(raw, ectx)
        except Exception:
            value = raw
        resolved[key] = value
    return resolved


def _exec_log(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
    base_name: str,
) -> list[ExecutionItem]:
    """Run the ``log`` operation and fan out one item per commit.

    Uses the first input item for expression evaluation (if any). Emits
    one output item per commit; when the input stream is empty, emits a
    single empty item so the engine still walks the successor edge.
    """
    params = node.parameters or {}
    seed = items[0] if items else ExecutionItem(json={})
    ectx = _ectx(seed, ctx)
    resolved = _resolve_params(params, "log", ectx)

    mock_result = _mock_lookup(ctx, "log", resolved)
    if mock_result is not None:
        commits = _commits_from_mock(mock_result)
    else:
        commits = _run_real_log(resolved, base_name)

    out: list[ExecutionItem] = []
    for c in commits:
        ni = seed.clone()
        ni.json = {**seed.json, **c}
        out.append(ni)
    if not out:
        out.append(seed.clone())
    return out


def _commits_from_mock(mock: Any) -> list[dict[str, Any]]:
    """Extract a list-of-commits from a log mock entry."""
    if isinstance(mock, list):
        return [dict(c) for c in mock if isinstance(c, dict)]
    if isinstance(mock, dict):
        if "commits" in mock and isinstance(mock["commits"], list):
            return [dict(c) for c in mock["commits"] if isinstance(c, dict)]
        if {"hash", "author", "email", "date", "message"} <= set(mock.keys()):
            return [dict(mock)]
    raise RuntimeError(
        "git: mock entry for 'log' must be a list of commit dicts or "
        "a dict with a 'commits' list",
    )


def _run_real_log(
    resolved: dict[str, Any],
    base_name: str,
) -> list[dict[str, Any]]:
    if not _dulwich_available():
        raise RuntimeError(
            "git: no mock and no git backend available "
            "(set ctx.mocks['git'] or install dulwich)",
        )
    logger.info("git log on %s via dulwich", base_name)
    return _real_log(resolved)


def _payload_from_mock(
    operation: str,
    mock: Any,
    resolved: dict[str, Any],
) -> dict[str, Any]:
    """Normalise a mock result into the per-operation output payload."""
    if not isinstance(mock, dict):
        raise RuntimeError(
            f"git: mock entry for operation {operation!r} must be a dict, "
            f"got {type(mock).__name__}",
        )
    return dict(mock)


def _run_real_or_raise(
    operation: str,
    resolved: dict[str, Any],
    base_name: str,
) -> dict[str, Any]:
    """Run the dulwich backend. Raise a clear error if not available."""
    if not _dulwich_available():
        raise RuntimeError(
            f"git: no mock and no git backend available "
            f"(set ctx.mocks['git'] or install dulwich)",
        )
    logger.info("git %s on %s via dulwich", operation, base_name)
    if operation == "clone":
        return _real_clone(resolved)
    if operation == "pull":
        return _real_pull(resolved)
    if operation == "commit":
        return _real_commit(resolved)
    if operation == "push":
        return _real_push(resolved)
    raise RuntimeError(f"git: unhandled operation {operation!r}")
