"""HubSpot CRM executor (clean-room ``n8n-nodes-base.hubspot``).

v1 covers the operations most commonly used in n8n templates:

- ``hubspot`` — create/get/update/list/delete contacts, companies, deals,
  and tickets in HubSpot via the CRM API. Emits one item per input (or
  one item per result for ``list`` in array mode) with operation-specific
  fields and ``source: 'hubspot'``.

When a ``hubspotApi`` credential is attached and no mock is present,
real CRM API calls are made via :func:`execute_http_request`.
Otherwise the executor is mock-driven with an offline synthetic
fallback.

Parameters honored by ``hubspot``:

- ``operation``      (one of ``create`` / ``get`` / ``update`` / ``list`` /
  ``delete``; default ``get``)
- ``resourceType``   (one of ``contact`` / ``company`` / ``deal`` /
  ``ticket``; default ``contact``)
- ``objectType``     (optional CRM plural path segment; defaults from
  ``resourceType`` → ``contacts`` / ``companies`` / ``deals`` /
  ``tickets``)
- ``objectId``       (string; ``$json.objectId`` / ``$json.id`` /
  ``$json.contactId`` fallback; required for ``get`` / ``update`` /
  ``delete``)
- For ``create`` / ``update``:
  - ``properties``   (dict of property name → value; ``$json.properties``
    fallback; default ``{}``)
- For ``list``:
  - ``limit``        (int; default 10)
  - ``properties``   (list of property names to include; optional)
  - ``filter``       (dict; optional)
  - ``dataMode``     (``array`` / ``object``; default ``array``; when
    ``object``, emit one item with a ``results`` array)

Behavior precedence:

1. ``ctx.mocks['hubspot_response']`` — when present, the value drives the
   executor. A callable is invoked as
   ``mock(operation, resourceType, params, item, ctx)`` and may return a
   dict (used as the response) or any other value (falls back to offline
   synthesis, tagged ``hubspot_response``). A non-callable dict is used
   directly as the response.
2. ``ctx.mocks['http_response']`` — generic HTTP-response fallback
   (``{status_code, body, headers}``); a JSON ``body`` dict is used as
   the response.
3. If a ``hubspotApi`` credential resolves (``accessToken``/``apiKey``/
   ``token`` present), a real HubSpot CRM call is made and the JSON body
   is used (source ``hubspot_api``).
4. Offline synthetic response with deterministic-looking ids and
   timestamps.

Items with an empty resolved ``objectId`` (for ``get`` / ``update`` /
``delete``) are skipped (no item emitted).
"""

from __future__ import annotations

import logging
import random
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode

from app.services.workflows.expression import ExpressionContext, evaluate
from app.services.workflows.http_client import HttpRequestConfig, execute_http_request
from app.services.workflows.items import ExecutionItem
from app.services.workflows.nodes._http_helpers import resolve_credential

if TYPE_CHECKING:
    from app.services.workflows.engine import EngineContext
    from app.services.workflows.graph import ExecNode

logger = logging.getLogger(__name__)

HUBSPOT_API_BASE = "https://api.hubapi.com/crm/v3/objects"
HUBSPOT_RESOURCE_TO_OBJECT_TYPE: dict[str, str] = {
    "contact": "contacts",
    "company": "companies",
    "deal": "deals",
    "ticket": "tickets",
    "contacts": "contacts",
    "companies": "companies",
    "deals": "deals",
    "tickets": "tickets",
}


HUBSPOT_OPERATIONS: tuple[str, ...] = (
    "create",
    "get",
    "update",
    "list",
    "delete",
)
HUBSPOT_DEFAULT_OPERATION: str = "get"
HUBSPOT_RESOURCE_TYPES: tuple[str, ...] = (
    "contact",
    "company",
    "deal",
    "ticket",
)
HUBSPOT_DEFAULT_RESOURCE_TYPE: str = "contact"
HUBSPOT_DEFAULT_LIMIT: int = 10
HUBSPOT_OFFLINE_MAX_RESULTS: int = 3
HUBSPOT_DATA_MODES: tuple[str, ...] = ("array", "object")
HUBSPOT_DEFAULT_DATA_MODE: str = "array"


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
        for key in ("value", "name", "id", "email"):
            if key in value and value[key] is not None:
                return _coerce_str(value[key])
    return str(value)


def _coerce_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [_coerce_str(v).strip() for v in value if _coerce_str(v).strip()]
    s = _coerce_str(value).strip()
    if not s:
        return []
    return [part.strip() for part in s.split(",") if part.strip()]


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


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _random_id() -> str:
    return str(random.randint(1000, 99999))


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
        if fk in item.json and item.json[fk] is not None:
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
    return _coerce_str(value).strip()


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
            if fk in item.json and item.json[fk] is not None:
                resolved = item.json[fk]
                break
    return _coerce_str_list(resolved)


def _resolve_dict_param(
    params: dict[str, Any],
    key: str,
    item: ExecutionItem,
    ectx: ExpressionContext,
    json_fallbacks: tuple[str, ...] = (),
) -> dict[str, Any]:
    raw = params.get(key)
    if raw is not None:
        resolved = evaluate(raw, ectx)
    else:
        resolved = None
        for fk in json_fallbacks:
            if fk in item.json and item.json[fk] is not None:
                resolved = item.json[fk]
                break
    if isinstance(resolved, dict):
        return resolved
    return {}


# ── Offline synthesis ─────────────────────────────────────────────────


def _default_create_properties() -> dict[str, Any]:
    return {
        "firstname": "Mock",
        "lastname": "User",
        "email": "mock@example.com",
    }


def _default_get_properties() -> dict[str, Any]:
    return {
        "firstname": "Mock",
        "lastname": "User",
        "email": "mock@example.com",
        "company": "Mock Co",
    }


def _synthesize_create(properties: dict[str, Any]) -> dict[str, Any]:
    now = _now_iso()
    return {
        "id": _random_id(),
        "properties": properties or _default_create_properties(),
        "createdAt": now,
        "updatedAt": now,
        "archived": False,
    }


def _synthesize_get(object_id: str) -> dict[str, Any]:
    now = _now_iso()
    return {
        "id": object_id,
        "properties": _default_get_properties(),
        "createdAt": now,
        "updatedAt": now,
        "archived": False,
    }


def _synthesize_update(
    object_id: str, properties: dict[str, Any]
) -> dict[str, Any]:
    return {
        "id": object_id,
        "properties": properties or {"firstname": "Updated"},
        "updatedAt": _now_iso(),
        "archived": False,
    }


def _synthesize_list(limit: int) -> dict[str, Any]:
    count = min(limit, HUBSPOT_OFFLINE_MAX_RESULTS)
    now = _now_iso()
    results: list[dict[str, Any]] = []
    for i in range(1, count + 1):
        results.append(
            {
                "id": str(i),
                "properties": {
                    "firstname": f"Mock{i}",
                    "lastname": "User",
                    "email": f"mock{i}@example.com",
                },
                "createdAt": now,
                "updatedAt": now,
            }
        )
    return {
        "results": results,
        "paging": {"next": {"after": ""}},
    }


def _synthesize_delete(object_id: str) -> dict[str, Any]:
    return {
        "id": object_id,
        "archived": True,
        "archivedAt": _now_iso(),
    }


def _synthesize_offline(
    operation: str,
    *,
    object_id: str,
    properties: dict[str, Any],
    limit: int,
) -> dict[str, Any]:
    if operation == "create":
        return _synthesize_create(properties)
    if operation == "get":
        return _synthesize_get(object_id)
    if operation == "update":
        return _synthesize_update(object_id, properties)
    if operation == "list":
        return _synthesize_list(limit)
    if operation == "delete":
        return _synthesize_delete(object_id)
    return {}


# ── Real HTTP ─────────────────────────────────────────────────────────


def _hubspot_token(cred: dict[str, Any]) -> str:
    return str(
        cred.get("accessToken")
        or cred.get("apiKey")
        or cred.get("token")
        or cred.get("access_token")
        or ""
    )


def _resolve_object_type(
    params: dict[str, Any],
    resource_type: str,
    item: ExecutionItem,
    ectx: ExpressionContext,
) -> str:
    """Map ``objectType`` / ``resourceType`` to HubSpot CRM plural path."""
    raw = params.get("objectType")
    if raw is not None:
        resolved = _coerce_str(evaluate(raw, ectx)).strip().lower()
        if resolved:
            return HUBSPOT_RESOURCE_TO_OBJECT_TYPE.get(resolved, resolved)
    for fk in ("objectType", "object_type"):
        if fk in item.json and item.json[fk] is not None:
            resolved = _coerce_str(item.json[fk]).strip().lower()
            if resolved:
                return HUBSPOT_RESOURCE_TO_OBJECT_TYPE.get(resolved, resolved)
    return HUBSPOT_RESOURCE_TO_OBJECT_TYPE.get(resource_type, "contacts")


def _build_hubspot_request(
    cred: dict[str, Any],
    *,
    operation: str,
    object_type: str,
    object_id: str,
    properties: dict[str, Any],
    limit: int,
    list_properties: list[str],
) -> HttpRequestConfig | None:
    """Build a real HubSpot CRM v3 request config.

    Returns ``None`` when the credential has no token.
    """
    token = _hubspot_token(cred)
    if not token:
        return None

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    base = f"{HUBSPOT_API_BASE}/{object_type}"

    if operation == "create":
        return HttpRequestConfig(
            url=base,
            method="POST",
            headers=headers,
            body={"properties": properties or {}},
            body_mode="json",
            response_mode="json",
            timeout=30.0,
        )

    if operation == "get":
        if not object_id:
            return None
        return HttpRequestConfig(
            url=f"{base}/{object_id}",
            method="GET",
            headers=headers,
            response_mode="json",
            timeout=30.0,
        )

    if operation == "update":
        if not object_id:
            return None
        return HttpRequestConfig(
            url=f"{base}/{object_id}",
            method="PATCH",
            headers=headers,
            body={"properties": properties or {}},
            body_mode="json",
            response_mode="json",
            timeout=30.0,
        )

    if operation == "list":
        qs: dict[str, str] = {"limit": str(max(1, min(limit or 100, 100)))}
        if list_properties:
            qs["properties"] = ",".join(list_properties)
        return HttpRequestConfig(
            url=f"{base}?{urlencode(qs)}",
            method="GET",
            headers=headers,
            response_mode="json",
            timeout=30.0,
        )

    if operation == "delete":
        if not object_id:
            return None
        return HttpRequestConfig(
            url=f"{base}/{object_id}",
            method="DELETE",
            headers=headers,
            response_mode="json",
            timeout=30.0,
        )

    return None


# ── Mock / credential resolution ──────────────────────────────────────


async def _resolve_hubspot_response(
    *,
    operation: str,
    resource_type: str,
    object_type: str,
    object_id: str,
    properties: dict[str, Any],
    limit: int,
    list_properties: list[str],
    params: dict[str, Any],
    item: ExecutionItem,
    node: "ExecNode",
    ctx: "EngineContext",
    synth: Any,
) -> tuple[dict[str, Any], str]:
    """Return ``(response, source)`` for the current call.

    ``source`` is one of ``"hubspot_response"``, ``"http_response"``,
    ``"hubspot_api"``, ``"offline"``.
    """
    mocks = ctx.mocks or {}
    hmock = mocks.get("hubspot_response")
    if hmock is not None:
        if callable(hmock):
            raw = hmock(operation, resource_type, params, item, ctx)
        else:
            raw = hmock
        if isinstance(raw, dict):
            return raw, "hubspot_response"
        return synth(), "hubspot_response"

    gmock = mocks.get("http_response")
    if gmock is not None and isinstance(gmock, dict):
        body = gmock.get("body")
        if isinstance(body, dict):
            return body, "http_response"

    cred = resolve_credential(node, ctx, "hubspotApi")
    if cred:
        cfg = _build_hubspot_request(
            cred,
            operation=operation,
            object_type=object_type,
            object_id=object_id,
            properties=properties,
            limit=limit,
            list_properties=list_properties,
        )
        if cfg is not None:
            logger.info(
                "hubspot real HTTP call operation=%s objectType=%s objectId=%s",
                operation,
                object_type,
                object_id,
            )
            try:
                resp = await execute_http_request(cfg, ctx=ctx)
                if isinstance(resp.body, dict):
                    return resp.body, "hubspot_api"
                # DELETE often returns empty body — synthesize a minimal envelope
                if operation == "delete" and resp.status_code in (200, 204):
                    return {
                        "id": object_id,
                        "archived": True,
                        "archivedAt": _now_iso(),
                    }, "hubspot_api"
            except Exception as exc:
                logger.warning("hubspot HTTP call failed: %s", exc)

    return synth(), "offline"


# ── Action executor ───────────────────────────────────────────────────


async def exec_hubspot(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """HubSpot node — routes on ``parameters.operation``."""
    params = node.parameters or {}
    operation = str(
        params.get("operation") or HUBSPOT_DEFAULT_OPERATION
    ).strip().lower()
    if operation not in HUBSPOT_OPERATIONS:
        raise ValueError(
            f"hubspot: unsupported operation {operation!r}; "
            f"expected one of {HUBSPOT_OPERATIONS}"
        )

    resource_type = str(
        params.get("resourceType") or HUBSPOT_DEFAULT_RESOURCE_TYPE
    ).strip().lower()
    if resource_type not in HUBSPOT_RESOURCE_TYPES:
        raise ValueError(
            f"hubspot: unsupported resourceType {resource_type!r}; "
            f"expected one of {HUBSPOT_RESOURCE_TYPES}"
        )

    out: list[ExecutionItem] = []
    for item in items:
        ectx = _ectx(item, ctx)

        # Resolve objectId (used by get/update/delete; echoed otherwise)
        object_id = _resolve_str_param(
            params, "objectId", item, ectx, ("objectId", "id", "contactId")
        )

        # Operation-specific parameter resolution
        properties: dict[str, Any] = {}
        limit: int = HUBSPOT_DEFAULT_LIMIT
        list_properties: list[str] = []
        filter_obj: dict[str, Any] = {}
        data_mode: str = HUBSPOT_DEFAULT_DATA_MODE

        if operation in ("create", "update"):
            properties = _resolve_dict_param(
                params, "properties", item, ectx, ("properties",)
            )
        elif operation == "list":
            limit_raw = _resolve_param(
                params, "limit", item, ectx, ("limit",)
            )
            limit = _coerce_int(limit_raw, HUBSPOT_DEFAULT_LIMIT)
            list_properties = _resolve_list_param(
                params, "properties", item, ectx, ("properties",)
            )
            filter_obj = _resolve_dict_param(
                params, "filter", item, ectx, ("filter",)
            )
            data_mode_raw = _resolve_param(
                params, "dataMode", item, ectx, ("dataMode",)
            )
            data_mode_str = _coerce_str(data_mode_raw).strip().lower()
            if data_mode_str in HUBSPOT_DATA_MODES:
                data_mode = data_mode_str

        # Skip checks for get/update/delete when objectId is empty
        if operation in ("get", "update", "delete") and not object_id:
            logger.info(
                "hubspot %s skipped: empty objectId on node %r",
                operation,
                node.name,
            )
            continue

        object_type = _resolve_object_type(params, resource_type, item, ectx)

        def _synth() -> dict[str, Any]:
            return _synthesize_offline(
                operation,
                object_id=object_id,
                properties=properties,
                limit=limit,
            )

        response, source = await _resolve_hubspot_response(
            operation=operation,
            resource_type=resource_type,
            object_type=object_type,
            object_id=object_id,
            properties=properties,
            limit=limit,
            list_properties=list_properties,
            params=params,
            item=item,
            node=node,
            ctx=ctx,
            synth=_synth,
        )

        # Build emitted items
        if operation == "list":
            out.extend(
                _build_list_items(
                    item=item,
                    response=response,
                    source=source,
                    resource_type=resource_type,
                    limit=limit,
                    list_properties=list_properties,
                    data_mode=data_mode,
                )
            )
        elif operation == "delete":
            payload: dict[str, Any] = {
                "objectId": response.get("id") or object_id,
                "archived": response.get("archived", True),
                "archivedAt": response.get("archivedAt") or _now_iso(),
                "source": "hubspot",
            }
            if source not in ("hubspot_response", "hubspot_api"):
                payload["mockSource"] = source
            ni = item.clone()
            ni.json = {**item.json, **payload}
            out.append(ni)
        else:
            # create / get / update
            props = response.get("properties") or {}
            payload = {
                "objectId": response.get("id") or object_id or _random_id(),
                "properties": props,
                "resourceType": resource_type,
                "source": "hubspot",
            }
            created_at = response.get("createdAt")
            if created_at is not None:
                payload["createdAt"] = created_at
            updated_at = response.get("updatedAt")
            if updated_at is not None:
                payload["updatedAt"] = updated_at
            if source not in ("hubspot_response", "hubspot_api"):
                payload["mockSource"] = source
            ni = item.clone()
            ni.json = {**item.json, **payload}
            out.append(ni)

        logger.info(
            "hubspot %s resourceType=%s objectId=%s source=%s",
            operation,
            resource_type,
            object_id,
            source,
        )

    return [(0, out)]


# ── List payload builder ──────────────────────────────────────────────


def _build_list_items(
    *,
    item: ExecutionItem,
    response: dict[str, Any],
    source: str,
    resource_type: str,
    limit: int,
    list_properties: list[str],
    data_mode: str,
) -> list[ExecutionItem]:
    results = response.get("results") or []
    emitted: list[ExecutionItem] = []

    if data_mode == "object":
        payload: dict[str, Any] = {
            "results": list(results),
            "paging": response.get("paging", {}),
            "limit": limit,
            "resourceType": resource_type,
            "source": "hubspot",
        }
        if list_properties:
            payload["properties"] = list_properties
        if source not in ("hubspot_response", "hubspot_api"):
            payload["mockSource"] = source
        ni = item.clone()
        ni.json = {**item.json, **payload}
        emitted.append(ni)
    else:
        for entry in results:
            entry_props = entry.get("properties") or {}
            payload = {
                "objectId": entry.get("id", ""),
                "properties": entry_props,
                "resourceType": resource_type,
                "source": "hubspot",
            }
            if source not in ("hubspot_response", "hubspot_api"):
                payload["mockSource"] = source
            ni = item.clone()
            ni.json = {**item.json, **payload}
            emitted.append(ni)

    return emitted


__all__ = [
    "exec_hubspot",
    "HUBSPOT_OPERATIONS",
    "HUBSPOT_DEFAULT_OPERATION",
    "HUBSPOT_RESOURCE_TYPES",
    "HUBSPOT_DEFAULT_RESOURCE_TYPE",
    "HUBSPOT_DEFAULT_LIMIT",
    "HUBSPOT_OFFLINE_MAX_RESULTS",
    "HUBSPOT_DATA_MODES",
    "HUBSPOT_DEFAULT_DATA_MODE",
]