"""GitHub executors (clean-room n8n ``n8n-nodes-base.github`` and
``n8n-nodes-base.githubTrigger``).

v1 covers the operations most commonly used in n8n templates:

- ``github`` — create/read/update issues, PRs, and repos via the GitHub
  REST API. Emits one item per input with
  ``{operation, owner, repository, <operation-specific fields>, htmlUrl,
  source: 'github'}``.
- ``githubTrigger`` — fire on GitHub webhook events. Emits one item with
  ``{event, ref, repository, pusher, headCommit, commits, compare,
  source: 'githubTrigger'}``.

When a ``githubApi`` credential is attached and no mock is present,
real issue API calls are made via :func:`execute_http_request`.
Otherwise the executor is mock-driven with an offline synthetic
fallback.

Parameters honored by ``github``:

- ``operation``      (one of ``createIssue`` / ``getIssue`` /
  ``updateIssue`` / ``createPR`` / ``getPR`` / ``mergePR`` /
  ``createRepo`` / ``getRepo``; default ``getIssue``)
- ``owner``          (string; ``$json.owner`` / ``$json.repoOwner``
  fallback)
- ``repository``     (string; ``$json.repository`` / ``$json.repo``
  fallback; for ``createRepo`` falls back to ``name``)
- Issue ops:
  - ``issueNumber``  (``$json.issueNumber`` / ``$json.number`` fallback)
  - ``title``        (``$json.title`` fallback)
  - ``body``         (``$json.body`` / ``$json.description`` fallback)
  - ``labels``       (list; optional)
  - ``assignees``    (list; optional)
  - ``state``        (``open`` / ``closed``; optional)
- PR ops:
  - ``pullNumber``   (``$json.pullNumber`` / ``$json.number`` fallback)
  - ``title``        (``$json.title`` fallback)
  - ``head``         (string)
  - ``base``         (string)
  - ``mergeMethod``  (``merge`` / ``squash`` / ``rebase``; default
    ``merge``)
- Repo ops:
  - ``name``         (``$json.name`` fallback)
  - ``description``  (string; optional)
  - ``private``      (bool; default ``False``)

Behavior precedence for ``github``:

1. ``ctx.mocks['github_response']`` — when present, the value drives the
   executor. A callable is invoked as
   ``mock(operation, owner, repo, params, item, ctx)`` and may return a
   dict (used as the response) or any other value (falls back to offline
   synthesis, tagged ``github_response``). A non-callable dict is used
   directly as the response.
2. ``ctx.mocks['http_response']`` — generic HTTP-response fallback
   (``{status_code, body, headers}``); a JSON ``body`` dict is used as
   the response.
3. If a ``githubApi`` credential resolves (``token``/``accessToken``
   present), a real GitHub REST call is made for supported issue ops
   and the JSON body is used (source ``github_api``).
4. Offline synthetic response with deterministic-looking numbers and
   timestamps.

Items with an empty resolved ``owner`` or ``repository`` are skipped
(no item emitted). For ``createRepo``, ``repository`` falls back to
``name`` before the skip check.

Behavior precedence for ``githubTrigger``:

1. ``ctx.mocks['github_event']`` — when present, the value drives the
   trigger. A callable is invoked as ``mock(node, ctx)`` and may return
   a dict (used as the raw webhook payload) or any other value (falls
   back to offline synthesis, tagged ``github_event``). A non-callable
   dict is used as the raw webhook payload.
2. ``ctx.mocks['trigger_payload']`` — generic trigger-payload fallback.
3. Offline synthetic GitHub push event.
"""

from __future__ import annotations

import logging
import random
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from app.services.workflows.expression import ExpressionContext, evaluate
from app.services.workflows.http_client import HttpRequestConfig, execute_http_request
from app.services.workflows.items import ExecutionItem
from app.services.workflows.nodes._http_helpers import resolve_credential

if TYPE_CHECKING:
    from app.services.workflows.engine import EngineContext
    from app.services.workflows.graph import ExecNode

logger = logging.getLogger(__name__)

GITHUB_API_BASE = "https://api.github.com"


GITHUB_OPERATIONS: tuple[str, ...] = (
    "createIssue",
    "getIssue",
    "updateIssue",
    "createPR",
    "getPR",
    "mergePR",
    "createRepo",
    "getRepo",
)
GITHUB_DEFAULT_OPERATION: str = "getIssue"
GITHUB_ISSUE_OPERATIONS: tuple[str, ...] = (
    "createIssue",
    "getIssue",
    "updateIssue",
)
GITHUB_PR_OPERATIONS: tuple[str, ...] = ("createPR", "getPR", "mergePR")
GITHUB_REPO_OPERATIONS: tuple[str, ...] = ("createRepo", "getRepo")
GITHUB_MERGE_METHODS: tuple[str, ...] = ("merge", "squash", "rebase")
GITHUB_DEFAULT_MERGE_METHOD: str = "merge"
GITHUB_ISSUE_STATES: tuple[str, ...] = ("open", "closed")
GITHUB_DEFAULT_TRIGGER_EVENTS: tuple[str, ...] = ("push",)


# ── Helpers ───────────────────────────────────────────────────────────


def _ectx(item: ExecutionItem, ctx: "EngineContext") -> ExpressionContext:
    return ExpressionContext(item=item, node_outputs=ctx.node_outputs, now=ctx.now)


def _coerce_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, (list, tuple)):
        return ", ".join(_coerce_str(v) for v in value if v is not None)
    if isinstance(value, dict):
        for key in ("value", "name", "id", "login", "title"):
            if key in value and value[key] is not None:
                return _coerce_str(value[key])
    return str(value)


def _coerce_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        s = value.strip().lower()
        if s in ("true", "1", "yes", "on"):
            return True
        if s in ("false", "0", "no", "off", ""):
            return False
        return default
    return default


def _coerce_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [_coerce_str(v).strip() for v in value if _coerce_str(v).strip()]
    s = _coerce_str(value).strip()
    if not s:
        return []
    return [part.strip() for part in s.split(",") if part.strip()]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _random_number() -> int:
    return random.randint(1000, 99999)


def _resolve_param(
    params: dict[str, Any],
    key: str,
    item: ExecutionItem,
    ectx: ExpressionContext,
    json_fallbacks: tuple[str, ...] = (),
) -> Any:
    """Return ``params[key]`` (evaluated) or the first present ``$json`` fallback."""
    raw = params.get(key)
    if raw is not None:
        return evaluate(raw, ectx)
    for fk in json_fallbacks:
        if fk in item.json:
            return item.json[fk]
    return None


def _resolve_str_param(
    params: dict[str, Any],
    key: str,
    item: ExecutionItem,
    ectx: ExpressionContext,
    json_fallbacks: tuple[str, ...] = (),
) -> str:
    value = _resolve_param(params, key, item, ectx, json_fallbacks)
    return _coerce_str(value)


def _resolve_list_param(
    params: dict[str, Any],
    key: str,
    item: ExecutionItem,
    ectx: ExpressionContext,
    json_fallbacks: tuple[str, ...] = (),
) -> list[str]:
    raw = params.get(key)
    if raw is not None:
        resolved = evaluate(raw, ectx)
    else:
        resolved = None
        for fk in json_fallbacks:
            if fk in item.json:
                resolved = item.json[fk]
                break
    return _coerce_str_list(resolved)


def _resolve_bool_param(
    params: dict[str, Any],
    key: str,
    item: ExecutionItem,
    ectx: ExpressionContext,
    json_fallbacks: tuple[str, ...] = (),
    default: bool = False,
) -> bool:
    raw = params.get(key)
    if raw is not None:
        resolved = evaluate(raw, ectx)
    else:
        resolved = None
        for fk in json_fallbacks:
            if fk in item.json:
                resolved = item.json[fk]
                break
    return _coerce_bool(resolved, default)


# ── Offline synthesis ─────────────────────────────────────────────────


def _synthesize_create_issue(
    owner: str, repo: str, title: str, body: str
) -> dict[str, Any]:
    number = _random_number()
    return {
        "number": number,
        "title": title,
        "body": body,
        "state": "open",
        "user": {"login": "mock-user"},
        "created_at": _now_iso(),
        "html_url": f"https://github.com/{owner}/{repo}/issues/{number}",
    }


def _synthesize_get_issue(
    owner: str, repo: str, issue_number: Any
) -> dict[str, Any]:
    num_str = _coerce_str(issue_number)
    return {
        "number": issue_number,
        "title": "Mock Issue",
        "body": "Mock issue body",
        "state": "open",
        "user": {"login": "mock-user"},
        "created_at": _now_iso(),
        "html_url": f"https://github.com/{owner}/{repo}/issues/{num_str}",
    }


def _synthesize_update_issue(
    owner: str,
    repo: str,
    issue_number: Any,
    title: str,
    state: str,
) -> dict[str, Any]:
    num_str = _coerce_str(issue_number)
    return {
        "number": issue_number,
        "title": title or "Mock Issue",
        "state": state or "open",
        "updated_at": _now_iso(),
        "html_url": f"https://github.com/{owner}/{repo}/issues/{num_str}",
    }


def _synthesize_create_pr(
    owner: str, repo: str, title: str, head: str, base: str
) -> dict[str, Any]:
    number = _random_number()
    return {
        "number": number,
        "title": title,
        "head": head,
        "base": base,
        "state": "open",
        "user": {"login": "mock-user"},
        "html_url": f"https://github.com/{owner}/{repo}/pull/{number}",
    }


def _synthesize_get_pr(
    owner: str, repo: str, pull_number: Any
) -> dict[str, Any]:
    num_str = _coerce_str(pull_number)
    return {
        "number": pull_number,
        "title": "Mock PR",
        "head": "feature-branch",
        "base": "main",
        "state": "open",
        "merged": False,
        "html_url": f"https://github.com/{owner}/{repo}/pull/{num_str}",
    }


def _synthesize_merge_pr(pull_number: Any) -> dict[str, Any]:
    return {
        "sha": uuid.uuid4().hex,
        "merged": True,
        "message": "Pull Request successfully merged",
        "number": pull_number,
    }


def _synthesize_create_repo(
    owner: str, name: str, description: str, private: bool
) -> dict[str, Any]:
    return {
        "id": _random_number(),
        "name": name,
        "full_name": f"{owner}/{name}",
        "description": description or "",
        "private": private,
        "html_url": f"https://github.com/{owner}/{name}",
        "created_at": _now_iso(),
    }


def _synthesize_get_repo(owner: str, repo: str) -> dict[str, Any]:
    return {
        "id": _random_number(),
        "name": repo,
        "full_name": f"{owner}/{repo}",
        "description": "Mock repository",
        "private": False,
        "html_url": f"https://github.com/{owner}/{repo}",
        "default_branch": "main",
    }


def _synthesize_offline(
    operation: str,
    *,
    owner: str,
    repo: str,
    issue_number: Any,
    title: str,
    body: str,
    state: str,
    pull_number: Any,
    head: str,
    base: str,
    name: str,
    description: str,
    private: bool,
) -> dict[str, Any]:
    if operation == "createIssue":
        return _synthesize_create_issue(owner, repo, title, body)
    if operation == "getIssue":
        return _synthesize_get_issue(owner, repo, issue_number)
    if operation == "updateIssue":
        return _synthesize_update_issue(owner, repo, issue_number, title, state)
    if operation == "createPR":
        return _synthesize_create_pr(owner, repo, title, head, base)
    if operation == "getPR":
        return _synthesize_get_pr(owner, repo, pull_number)
    if operation == "mergePR":
        return _synthesize_merge_pr(pull_number)
    if operation == "createRepo":
        return _synthesize_create_repo(owner, name, description, private)
    if operation == "getRepo":
        return _synthesize_get_repo(owner, repo)
    return {}


def _construct_html_url(
    operation: str,
    owner: str,
    repo: str,
    issue_number: Any,
    pull_number: Any,
    name: str,
) -> str:
    if operation in GITHUB_ISSUE_OPERATIONS:
        return f"https://github.com/{owner}/{repo}/issues/{_coerce_str(issue_number)}"
    if operation in GITHUB_PR_OPERATIONS:
        return f"https://github.com/{owner}/{repo}/pull/{_coerce_str(pull_number)}"
    if operation == "createRepo":
        return f"https://github.com/{owner}/{name}"
    if operation == "getRepo":
        return f"https://github.com/{owner}/{repo}"
    return ""


# ── Real HTTP ─────────────────────────────────────────────────────────


def _github_token(cred: dict[str, Any]) -> str:
    return str(cred.get("token") or cred.get("accessToken") or cred.get("access_token") or "")


def _github_auth_header(token: str) -> str:
    """Build Authorization value: prefer Bearer; honor pre-prefixed tokens."""
    t = token.strip()
    lower = t.lower()
    if lower.startswith("bearer ") or lower.startswith("token "):
        return t
    # Classic PATs (ghp_*) historically use the "token" scheme; OAuth /
    # fine-grained tokens use Bearer. Both are accepted by the API.
    if t.startswith("ghp_"):
        return f"token {t}"
    return f"Bearer {t}"


def _build_github_request(
    cred: dict[str, Any],
    *,
    operation: str,
    owner: str,
    repo: str,
    issue_number: Any,
    title: str,
    body: str,
    labels: list[str],
    assignees: list[str],
    state: str,
) -> HttpRequestConfig | None:
    """Build a real GitHub REST request for supported issue operations.

    Returns ``None`` when the credential has no token or the operation
    is not mapped to a real HTTP call (PR/repo ops fall through offline).
    """
    token = _github_token(cred)
    if not token:
        return None

    headers = {
        "Authorization": _github_auth_header(token),
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    base = f"{GITHUB_API_BASE}/repos/{owner}/{repo}"

    if operation == "createIssue":
        payload: dict[str, Any] = {"title": title or "Untitled"}
        if body:
            payload["body"] = body
        if labels:
            payload["labels"] = labels
        if assignees:
            payload["assignees"] = assignees
        return HttpRequestConfig(
            url=f"{base}/issues",
            method="POST",
            headers=headers,
            body=payload,
            body_mode="json",
            response_mode="json",
            timeout=30.0,
        )

    if operation == "getIssue":
        num = _coerce_str(issue_number).strip()
        if not num:
            return None
        return HttpRequestConfig(
            url=f"{base}/issues/{num}",
            method="GET",
            headers=headers,
            response_mode="json",
            timeout=30.0,
        )

    if operation == "updateIssue":
        num = _coerce_str(issue_number).strip()
        if not num:
            return None
        payload = {}
        if title:
            payload["title"] = title
        if body:
            payload["body"] = body
        if state:
            payload["state"] = state
        if labels:
            payload["labels"] = labels
        if assignees:
            payload["assignees"] = assignees
        return HttpRequestConfig(
            url=f"{base}/issues/{num}",
            method="PATCH",
            headers=headers,
            body=payload,
            body_mode="json",
            response_mode="json",
            timeout=30.0,
        )

    return None


# ── Mock / credential resolution ──────────────────────────────────────


async def _resolve_github_response(
    *,
    operation: str,
    owner: str,
    repo: str,
    params: dict[str, Any],
    item: ExecutionItem,
    node: "ExecNode",
    ctx: "EngineContext",
    synth: Any,
    issue_number: Any = None,
    title: str = "",
    body: str = "",
    labels: list[str] | None = None,
    assignees: list[str] | None = None,
    state: str = "",
) -> tuple[dict[str, Any], str]:
    """Return ``(response, source)`` for the current call.

    ``source`` is one of ``"github_response"``, ``"http_response"``,
    ``"github_api"``, ``"offline"``.
    """
    mocks = ctx.mocks or {}
    gmock = mocks.get("github_response")
    if gmock is not None:
        if callable(gmock):
            raw = gmock(operation, owner, repo, params, item, ctx)
        else:
            raw = gmock
        if isinstance(raw, dict):
            return raw, "github_response"
        return synth(), "github_response"

    hmock = mocks.get("http_response")
    if hmock is not None and isinstance(hmock, dict):
        body_mock = hmock.get("body")
        if isinstance(body_mock, dict):
            return body_mock, "http_response"

    cred = resolve_credential(node, ctx, "githubApi")
    if cred:
        cfg = _build_github_request(
            cred,
            operation=operation,
            owner=owner,
            repo=repo,
            issue_number=issue_number,
            title=title,
            body=body,
            labels=labels or [],
            assignees=assignees or [],
            state=state,
        )
        if cfg is not None:
            logger.info(
                "github real HTTP call operation=%s owner=%s repo=%s",
                operation,
                owner,
                repo,
            )
            try:
                resp = await execute_http_request(cfg, ctx=ctx)
                if isinstance(resp.body, dict):
                    return resp.body, "github_api"
            except Exception as exc:
                logger.warning("github HTTP call failed: %s", exc)

    return synth(), "offline"


# ── Action executor ───────────────────────────────────────────────────


async def exec_github(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """GitHub node — routes on ``parameters.operation``."""
    params = node.parameters or {}
    operation = str(params.get("operation") or GITHUB_DEFAULT_OPERATION)
    if operation not in GITHUB_OPERATIONS:
        raise ValueError(
            f"github: unsupported operation {operation!r}; "
            f"expected one of {GITHUB_OPERATIONS}"
        )

    out: list[ExecutionItem] = []
    for item in items:
        ectx = _ectx(item, ctx)

        owner = _resolve_str_param(
            params, "owner", item, ectx, ("owner", "repoOwner")
        )
        repository = _resolve_str_param(
            params, "repository", item, ectx, ("repository", "repo")
        )

        # Operation-specific params
        issue_number: Any = None
        title: str = ""
        body: str = ""
        state: str = ""
        labels: list[str] = []
        assignees: list[str] = []
        pull_number: Any = None
        head: str = ""
        base: str = ""
        merge_method: str = GITHUB_DEFAULT_MERGE_METHOD
        name: str = ""
        description: str = ""
        private: bool = False

        if operation in GITHUB_ISSUE_OPERATIONS:
            issue_number = _resolve_param(
                params, "issueNumber", item, ectx, ("issueNumber", "number")
            )
            title = _resolve_str_param(params, "title", item, ectx, ("title",))
            body = _resolve_str_param(
                params, "body", item, ectx, ("body", "description")
            )
            labels = _resolve_list_param(
                params, "labels", item, ectx, ("labels",)
            )
            assignees = _resolve_list_param(
                params, "assignees", item, ectx, ("assignees",)
            )
            state_raw = _resolve_str_param(
                params, "state", item, ectx, ("state",)
            )
            state = state_raw if state_raw in GITHUB_ISSUE_STATES else ""

        elif operation in GITHUB_PR_OPERATIONS:
            pull_number = _resolve_param(
                params, "pullNumber", item, ectx, ("pullNumber", "number")
            )
            title = _resolve_str_param(params, "title", item, ectx, ("title",))
            head = _resolve_str_param(params, "head", item, ectx, ("head",))
            base = _resolve_str_param(params, "base", item, ectx, ("base",))
            merge_method_raw = _resolve_str_param(
                params, "mergeMethod", item, ectx, ("mergeMethod",)
            )
            merge_method = (
                merge_method_raw
                if merge_method_raw in GITHUB_MERGE_METHODS
                else GITHUB_DEFAULT_MERGE_METHOD
            )

        else:  # repo ops
            name = _resolve_str_param(params, "name", item, ectx, ("name",))
            description = _resolve_str_param(
                params, "description", item, ectx, ("description",)
            )
            private = _resolve_bool_param(
                params, "private", item, ectx, ("private",), False
            )

        # For createRepo, fall back to name when repository is empty
        if operation == "createRepo" and not repository:
            repository = name

        # Skip items with empty owner or repository
        if not owner or not repository:
            logger.info(
                "github %s skipped: empty owner or repository on node %r",
                operation,
                node.name,
            )
            continue

        def _synth() -> dict[str, Any]:
            return _synthesize_offline(
                operation,
                owner=owner,
                repo=repository,
                issue_number=issue_number,
                title=title,
                body=body,
                state=state,
                pull_number=pull_number,
                head=head,
                base=base,
                name=name,
                description=description,
                private=private,
            )

        response, source = await _resolve_github_response(
            operation=operation,
            owner=owner,
            repo=repository,
            params=params,
            item=item,
            node=node,
            ctx=ctx,
            synth=_synth,
            issue_number=issue_number,
            title=title,
            body=body,
            labels=labels,
            assignees=assignees,
            state=state,
        )

        # Build htmlUrl
        html_url = _coerce_str(response.get("html_url"))
        if not html_url:
            html_url = _construct_html_url(
                operation, owner, repository, issue_number, pull_number, name
            )

        payload: dict[str, Any] = {
            "operation": operation,
            "owner": owner,
            "repository": repository,
            **response,
            "htmlUrl": html_url,
            "source": "github",
        }
        if source not in ("github_response", "github_api"):
            payload["mockSource"] = source

        # Echo optional resolved fields
        if operation in GITHUB_ISSUE_OPERATIONS:
            if labels:
                payload["labels"] = labels
            if assignees:
                payload["assignees"] = assignees
            if state:
                payload["state"] = state
        if operation in GITHUB_PR_OPERATIONS:
            payload["mergeMethod"] = merge_method

        ni = item.clone()
        ni.json = {**item.json, **payload}
        out.append(ni)

        logger.info(
            "github %s owner=%s repo=%s source=%s",
            operation,
            owner,
            repository,
            source,
        )

    return [(0, out)]


# ── Trigger ───────────────────────────────────────────────────────────


def _synthesize_push_event(
    owner: str, repo: str, branch: str
) -> dict[str, Any]:
    """Offline fallback: a fake GitHub ``push`` webhook payload."""
    owner_or_mock = owner or "mock-owner"
    repo_or_mock = repo or "mock-repo"
    return {
        "ref": f"refs/heads/{branch or 'main'}",
        "before": "a" * 40,
        "after": "b" * 40,
        "repository": {
            "id": 12345,
            "name": repo_or_mock,
            "full_name": f"{owner_or_mock}/{repo_or_mock}",
            "html_url": f"https://github.com/{owner_or_mock}/{repo_or_mock}",
        },
        "pusher": {"name": "mock-user", "email": "mock@example.com"},
        "head_commit": {
            "id": "c" * 40,
            "message": "Mock commit message",
            "timestamp": _now_iso(),
            "author": {"name": "mock-user", "email": "mock@example.com"},
        },
        "created": False,
        "deleted": False,
        "forced": False,
        "compare": f"https://github.com/{owner_or_mock}/{repo_or_mock}/compare/a...b",
        "commits": [
            {
                "id": "d" * 40,
                "message": "Mock commit",
                "author": {"name": "mock-user"},
            }
        ],
    }


def _resolve_trigger_event(
    node: "ExecNode",
    ctx: "EngineContext",
    owner: str,
    repo: str,
    branch: str,
) -> tuple[dict[str, Any], str]:
    """Pick the GitHub webhook payload from mocks or fall back to offline synth."""
    mocks = ctx.mocks if isinstance(ctx.mocks, dict) else {}
    gmock = mocks.get("github_event")
    if gmock is not None:
        if callable(gmock):
            raw = gmock(node, ctx)
        else:
            raw = gmock
        if isinstance(raw, dict):
            return raw, "github_event"
        return _synthesize_push_event(owner, repo, branch), "github_event"

    tmock = mocks.get("trigger_payload")
    if isinstance(tmock, dict):
        return tmock, "trigger_payload"

    return _synthesize_push_event(owner, repo, branch), "offline"


async def exec_github_trigger(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """GitHub Trigger — emit one item per received GitHub webhook event.

    Resolution order:

    1. ``ctx.mocks['github_event']`` (dict or callable ``(node, ctx)``)
    2. ``ctx.mocks['trigger_payload']`` (dict)
    3. Offline synthetic push event.

    The emitted item carries flat fields downstream nodes typically read
    (``event``, ``ref``, ``repository``, ``pusher``, ``headCommit``,
    ``commits``, ``compare``) plus a ``source: 'githubTrigger'`` marker.

    If items list is non-empty (upstream pre-seeded), each existing item
    is passed through with the trigger context fields merged in.
    """
    params = node.parameters or {}
    seed_item = items[0] if items else ExecutionItem()
    ectx = ExpressionContext(
        item=seed_item,
        node_outputs=ctx.node_outputs,
        now=ctx.now,
    )

    # events
    events_raw = params.get("events")
    if events_raw is not None:
        events_raw = evaluate(events_raw, ectx)
    else:
        events_raw = seed_item.json.get("events")
    events = _coerce_str_list(events_raw) or list(GITHUB_DEFAULT_TRIGGER_EVENTS)

    owner = _resolve_str_param(params, "owner", seed_item, ectx, ("owner",))
    repository = _resolve_str_param(
        params, "repository", seed_item, ectx, ("repository", "repo")
    )
    branch = _resolve_str_param(params, "branch", seed_item, ectx, ("branch",))

    event_type = events[0] if events else "push"

    payload, source = _resolve_trigger_event(node, ctx, owner, repository, branch)

    ref = _coerce_str(payload.get("ref")) or f"refs/heads/{branch or 'main'}"
    repository_obj = payload.get("repository")
    if not isinstance(repository_obj, dict):
        owner_or_mock = owner or "mock-owner"
        repo_or_mock = repository or "mock-repo"
        repository_obj = {
            "id": 12345,
            "name": repo_or_mock,
            "full_name": f"{owner_or_mock}/{repo_or_mock}",
            "html_url": f"https://github.com/{owner_or_mock}/{repo_or_mock}",
        }
    pusher = payload.get("pusher")
    if not isinstance(pusher, dict):
        pusher = {"name": "mock-user", "email": "mock@example.com"}
    head_commit = payload.get("head_commit")
    if not isinstance(head_commit, dict):
        head_commit = {}
    commits = payload.get("commits")
    if not isinstance(commits, list):
        commits = []
    compare = _coerce_str(payload.get("compare"))

    base: dict[str, Any] = {
        "event": event_type,
        "ref": ref,
        "repository": repository_obj,
        "pusher": pusher,
        "headCommit": head_commit,
        "commits": commits,
        "compare": compare,
        "source": "githubTrigger",
    }
    if source != "offline":
        base["mockSource"] = source

    if items:
        out: list[ExecutionItem] = []
        for item in items:
            merged = dict(item.json)
            for key, value in base.items():
                merged.setdefault(key, value)
            ni = item.clone()
            ni.json = merged
            out.append(ni)
        return [(0, out)]

    logger.info(
        "githubTrigger event=%s owner=%s repo=%s branch=%s source=%s",
        event_type,
        owner,
        repository,
        branch,
        source,
    )
    return [(0, [ExecutionItem(json=base)])]


__all__ = [
    "exec_github",
    "exec_github_trigger",
    "GITHUB_OPERATIONS",
    "GITHUB_DEFAULT_OPERATION",
    "GITHUB_ISSUE_OPERATIONS",
    "GITHUB_PR_OPERATIONS",
    "GITHUB_REPO_OPERATIONS",
    "GITHUB_MERGE_METHODS",
    "GITHUB_DEFAULT_MERGE_METHOD",
    "GITHUB_ISSUE_STATES",
    "GITHUB_DEFAULT_TRIGGER_EVENTS",
]