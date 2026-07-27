"""Redis executor (clean-room n8n ``n8n-nodes-base.redis``).

v1 supports the seven operations most commonly used in n8n templates:

- ``get``    — read a key; emit one item per input with
  ``{key, value, exists, ttl, source: 'redis'}``.
- ``set``    — write a key/value; emit one item per input with
  ``{key, value, ok, expire, source: 'redis'}``.
- ``delete`` — remove a key; emit one item per input with
  ``{key, deleted, source: 'redis'}``.
- ``incr``   — increment a key; emit one item per input with
  ``{key, value, incrementedBy, source: 'redis'}``.
- ``decr``   — decrement a key; emit one item per input with
  ``{key, value, decrementedBy, source: 'redis'}``.
- ``keys``   — list keys matching a pattern; emit one item per input
  with ``{keys, count, source: 'redis'}``.
- ``publish``— publish a message to a channel; emit one item per input
  with ``{channel, message, subscribers, source: 'redis'}``.

When a ``redis`` (or ``redisApi``) credential is attached and no mock
is present, real calls are made via the ``redis`` async driver.
Otherwise the executor is mock-driven with an offline synthetic
fallback.

Parameters honored:

- ``operation`` (``"get"`` / ``"set"`` / ``"delete"`` / ``"incr"`` /
  ``"decr"`` / ``"keys"`` / ``"publish"``; default ``"get"``)
- ``key``      (string; ``$json.key`` / ``$json.redisKey`` fallback;
  required for get/set/delete/incr/decr)
- ``value``    (any; ``$json.value`` / ``$json.data`` fallback; set only)
- ``expire``   (int seconds; optional; set only; default 0)
- ``by``       (int; default 1; incr/decr only)
- ``pattern``  (string; default ``"*"``; keys only)
- ``channel``  (string; ``$json.channel`` / ``$json.key`` fallback;
  required for publish)
- ``message``  (any; ``$json.message`` / ``$json.value`` fallback;
  publish only)

Behavior precedence:

1. ``ctx.mocks['redis_response']`` — when present, the value drives the
   executor. A dict is used as the operation-specific response envelope;
   a callable is invoked as
   ``mock(operation, key, params, item, ctx)`` and may return a dict
   (used as the envelope) or a non-dict value (coerced per operation).
2. ``ctx.mocks['db_response']`` — generic database-response fallback
   (dict envelope or callable with the same signature).
3. ``ctx.mocks['http_response']`` — final fallback
   (``{status_code, body, headers}``); a JSON ``body`` dict is unwrapped
   into the operation envelope.
4. If a ``redis`` (or ``redisApi``) credential resolves, a real Redis
   call is made via the ``redis`` async driver; the result is merged
   into the operation envelope.
5. Offline synthetic response with deterministic-looking values.

Items with an empty resolved ``key`` on get/set/delete/incr/decr are
skipped (no item emitted). Items with an empty ``channel`` on publish
are also skipped.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from app.services.workflows.expression import ExpressionContext, evaluate
from app.services.workflows.items import ExecutionItem
from app.services.workflows.nodes._http_helpers import resolve_credential
import redis.asyncio as aioredis
from urllib.parse import quote_plus

if TYPE_CHECKING:
    from app.services.workflows.engine import EngineContext
    from app.services.workflows.graph import ExecNode

logger = logging.getLogger(__name__)


REDIS_OPERATIONS: tuple[str, ...] = (
    "get",
    "set",
    "delete",
    "incr",
    "decr",
    "keys",
    "publish",
)
REDIS_DEFAULT_OPERATION: str = "get"
REDIS_DEFAULT_PATTERN: str = "*"
REDIS_DEFAULT_BY: int = 1
REDIS_DEFAULT_EXPIRE: int = 0
REDIS_OFFLINE_KEY_COUNT: int = 3


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
        for key in ("value", "name", "id", "text", "content"):
            if key in value and value[key] is not None:
                return _coerce_str(value[key])
    return str(value)


def _coerce_int(value: Any, default: int) -> int:
    if value is None or isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return default
        try:
            return int(s)
        except ValueError:
            try:
                return int(float(s))
            except ValueError:
                return default
    return default


def _coerce_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes")
    if isinstance(value, (int, float)):
        return bool(value)
    return default


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
    return _coerce_str(_resolve_param(params, key, item, ectx, json_fallbacks))


# ── Synthetic responses ────────────────────────────────────────────────


def _offline_envelope(operation: str, resolved: dict[str, Any]) -> dict[str, Any]:
    """Offline fallback: a fake Redis response envelope (response fields only)."""
    if operation == "get":
        return {
            "value": f'mock_value_for_{resolved["key"]}',
            "exists": True,
            "ttl": -1,
        }
    if operation == "set":
        return {"ok": True}
    if operation == "delete":
        return {"deleted": 1}
    if operation == "incr":
        return {"value": 1}
    if operation == "decr":
        return {"value": -1}
    if operation == "keys":
        return {
            "keys": [
                f"mock_key_{i}"
                for i in range(1, REDIS_OFFLINE_KEY_COUNT + 1)
            ],
            "count": REDIS_OFFLINE_KEY_COUNT,
        }
    if operation == "publish":
        return {"subscribers": 1}
    return {}


def _coerce_mock_value(raw: Any, operation: str) -> dict[str, Any]:
    """Coerce a mock return value into an operation envelope dict."""
    if isinstance(raw, dict):
        return raw
    if operation == "get":
        return {"value": raw}
    if operation == "set":
        return {"ok": bool(raw)}
    if operation == "delete":
        return {"deleted": _coerce_int(raw, 1)}
    if operation == "incr":
        return {"value": _coerce_int(raw, 1)}
    if operation == "decr":
        return {"value": _coerce_int(raw, -1)}
    if operation == "keys":
        if isinstance(raw, list):
            return {"keys": list(raw), "count": len(raw)}
        return {"keys": [raw], "count": 1}
    if operation == "publish":
        return {"subscribers": _coerce_int(raw, 1)}
    return {}


# ── Real driver ────────────────────────────────────────────────────────


def _build_redis_config(cred: dict[str, Any]) -> dict[str, Any] | None:
    """Build a Redis connection config from a credential dict.

    Returns a dict with a ``connectionString`` key, or ``None`` when no
    usable connection info is present.
    """
    conn_str = str(cred.get("connectionString") or cred.get("url") or "").strip()
    if conn_str:
        return {"connectionString": conn_str}

    host = str(cred.get("host") or "").strip()
    if not host:
        return None

    port = _coerce_int(cred.get("port"), 6379)
    database = _coerce_int(cred.get("database") or cred.get("db"), 0)
    password = cred.get("password")
    username = cred.get("username")
    ssl = _coerce_bool(cred.get("ssl"), False)

    scheme = "rediss" if ssl else "redis"
    parts: list[str] = [f"{scheme}://"]
    if password:
        if username:
            parts.append(
                f"{quote_plus(str(username))}:{quote_plus(str(password))}@"
            )
        else:
            parts.append(f":{quote_plus(str(password))}@")
    parts.append(host)
    if port and port != 6379:
        parts.append(f":{port}")
    parts.append(f"/{database}")

    return {"connectionString": "".join(parts)}


async def _execute_redis_operation(
    conn_params: dict[str, Any],
    operation: str,
    params: dict[str, Any],
    item: ExecutionItem,
    resolved: dict[str, Any],
) -> dict[str, Any] | None:
    """Connect to Redis and run a single operation.

    Returns a result dict with operation-specific fields, or ``None`` if
    the operation cannot be performed.
    """
    conn_str = conn_params["connectionString"]
    client = aioredis.from_url(conn_str, decode_responses=True)
    try:
        if operation == "get":
            key = resolved["key"]
            value = await client.get(key)
            if value is None:
                return {"value": None, "exists": False, "ttl": -1}
            ttl = await client.ttl(key)
            return {"value": value, "exists": True, "ttl": ttl}

        if operation == "set":
            key = resolved["key"]
            value = resolved["value"]
            expire = resolved["expire"]
            if expire and expire > 0:
                await client.set(key, value, ex=expire)
            else:
                await client.set(key, value)
            return {"ok": True}

        if operation == "delete":
            key = resolved["key"]
            deleted = await client.delete(key)
            return {"deleted": deleted}

        if operation == "incr":
            key = resolved["key"]
            by = resolved["by"]
            value = await client.incrby(key, by)
            return {"value": value}

        if operation == "decr":
            key = resolved["key"]
            by = resolved["by"]
            value = await client.decrby(key, by)
            return {"value": value}

        if operation == "keys":
            pattern = resolved["pattern"]
            keys = await client.keys(pattern)
            return {"keys": list(keys), "count": len(keys)}

        if operation == "publish":
            channel = resolved["channel"]
            message = resolved["message"]
            subscribers = await client.publish(channel, message)
            return {"subscribers": subscribers}

        return None
    finally:
        await client.aclose()


# ── Response resolution ────────────────────────────────────────────────


async def _resolve_envelope(
    *,
    operation: str,
    key: str,
    params: dict[str, Any],
    item: ExecutionItem,
    node: "ExecNode",
    ctx: "EngineContext",
    resolved: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    """Return ``(envelope, source)`` for the current call.

    ``source`` is one of ``"redis_response"``, ``"db_response"``,
    ``"http_response"``, ``"redis_api"``, ``"offline"``.
    """
    mocks = ctx.mocks or {}
    base = _offline_envelope(operation, resolved)

    rmock = mocks.get("redis_response")
    if rmock is not None:
        raw = (
            rmock(operation, key, params, item, ctx)
            if callable(rmock)
            else rmock
        )
        env = _coerce_mock_value(raw, operation)
        return {**base, **env}, "redis_response"

    dmock = mocks.get("db_response")
    if dmock is not None:
        raw = (
            dmock(operation, key, params, item, ctx)
            if callable(dmock)
            else dmock
        )
        env = _coerce_mock_value(raw, operation)
        return {**base, **env}, "db_response"

    hmock = mocks.get("http_response")
    if hmock is not None:
        raw = (
            hmock(operation, key, params, item, ctx)
            if callable(hmock)
            else hmock
        )
        if isinstance(raw, dict) and isinstance(raw.get("body"), dict):
            env = _coerce_mock_value(raw["body"], operation)
        else:
            env = _coerce_mock_value(raw, operation)
        return {**base, **env}, "http_response"

    cred = resolve_credential(node, ctx, "redis") or resolve_credential(
        node, ctx, "redisApi"
    )
    if cred:
        conn_params = _build_redis_config(cred)
        if conn_params is not None:
            logger.info(
                "redis real call operation=%s key=%r",
                operation,
                key[:80],
            )
            try:
                result = await _execute_redis_operation(
                    conn_params, operation, params, item, resolved
                )
                if result is not None:
                    return {**base, **result}, "redis_api"
            except Exception as exc:
                logger.warning("redis real call failed: %s", exc)

    return base, "offline"


# ── Output builder ─────────────────────────────────────────────────────


def _build_output(
    operation: str,
    envelope: dict[str, Any],
    source: str,
    resolved: dict[str, Any],
    item: ExecutionItem,
) -> ExecutionItem:
    payload: dict[str, Any] = {"operation": operation, "source": "redis"}

    if operation == "get":
        payload["key"] = resolved["key"]
        payload["value"] = envelope.get("value")
        payload["exists"] = envelope.get("exists")
        payload["ttl"] = envelope.get("ttl")
    elif operation == "set":
        payload["key"] = resolved["key"]
        payload["value"] = resolved["value"]
        payload["ok"] = envelope.get("ok")
        payload["expire"] = resolved["expire"]
    elif operation == "delete":
        payload["key"] = resolved["key"]
        payload["deleted"] = envelope.get("deleted")
    elif operation == "incr":
        payload["key"] = resolved["key"]
        payload["value"] = envelope.get("value")
        payload["incrementedBy"] = resolved["by"]
    elif operation == "decr":
        payload["key"] = resolved["key"]
        payload["value"] = envelope.get("value")
        payload["decrementedBy"] = resolved["by"]
    elif operation == "keys":
        payload["keys"] = envelope.get("keys")
        payload["count"] = envelope.get("count")
    elif operation == "publish":
        payload["channel"] = resolved["channel"]
        payload["message"] = resolved["message"]
        payload["subscribers"] = envelope.get("subscribers")

    ni = item.clone()
    ni.json = {**item.json, **payload}
    return ni


# ── Main executor ──────────────────────────────────────────────────────


async def exec_redis(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Redis node — get/set/delete/incr/decr/keys/publish per input item.

    - ``get``    → emits one item per input with ``key, value, exists, ttl``.
    - ``set``    → emits one item per input with ``key, value, ok, expire``.
    - ``delete`` → emits one item per input with ``key, deleted``.
    - ``incr``   → emits one item per input with ``key, value, incrementedBy``.
    - ``decr``   → emits one item per input with ``key, value, decrementedBy``.
    - ``keys``   → emits one item per input with ``keys, count``.
    - ``publish``→ emits one item per input with ``channel, message, subscribers``.

    Items with an empty resolved ``key`` on get/set/delete/incr/decr are
    skipped. Items with an empty ``channel`` on publish are also skipped.
    """
    params = node.parameters or {}
    operation = str(
        params.get("operation") or REDIS_DEFAULT_OPERATION
    ).strip().lower()
    if operation not in REDIS_OPERATIONS:
        raise ValueError(
            f"redis: unsupported operation {operation!r}; "
            f"expected one of {REDIS_OPERATIONS}"
        )

    out: list[ExecutionItem] = []

    for item in items:
        ectx = _ectx(item, ctx)
        key = _resolve_str_param(
            params, "key", item, ectx, ("key", "redisKey")
        ).strip()

        # Operation-specific param resolution and gating
        value: Any = None
        expire: int = REDIS_DEFAULT_EXPIRE
        by: int = REDIS_DEFAULT_BY
        channel: str = ""
        message: Any = None
        pattern: str = REDIS_DEFAULT_PATTERN

        if operation in ("get", "set", "delete", "incr", "decr"):
            if not key:
                logger.info(
                    "redis %s skipped: empty key on node %r",
                    operation,
                    node.name,
                )
                continue

        if operation == "set":
            value = _resolve_param(
                params, "value", item, ectx, ("value", "data")
            )
            expire = _coerce_int(
                _resolve_param(params, "expire", item, ectx),
                REDIS_DEFAULT_EXPIRE,
            )
        elif operation in ("incr", "decr"):
            by = _coerce_int(
                _resolve_param(params, "by", item, ectx), REDIS_DEFAULT_BY
            )
        elif operation == "keys":
            pattern = (
                _resolve_str_param(params, "pattern", item, ectx)
                or REDIS_DEFAULT_PATTERN
            )
        elif operation == "publish":
            channel = _resolve_str_param(
                params, "channel", item, ectx, ("channel", "key")
            ).strip()
            message = _resolve_param(
                params, "message", item, ectx, ("message", "value")
            )
            if not channel:
                logger.info(
                    "redis publish skipped: empty channel on node %r",
                    node.name,
                )
                continue

        resolved: dict[str, Any] = {
            "key": key,
            "value": value,
            "expire": expire,
            "by": by,
            "channel": channel,
            "message": message,
            "pattern": pattern,
        }

        envelope, source = await _resolve_envelope(
            operation=operation,
            key=key,
            params=params,
            item=item,
            node=node,
            ctx=ctx,
            resolved=resolved,
        )

        out.append(_build_output(operation, envelope, source, resolved, item))

        logger.info(
            "redis %s key=%r channel=%r source=%s",
            operation,
            key[:80],
            channel[:80],
            source,
        )

    return [(0, out)]


__all__ = [
    "exec_redis",
    "REDIS_OPERATIONS",
    "REDIS_DEFAULT_OPERATION",
    "REDIS_DEFAULT_PATTERN",
    "REDIS_DEFAULT_BY",
    "REDIS_DEFAULT_EXPIRE",
]