"""Google Drive Trigger executor (clean-room n8n ``n8n-nodes-base.googleDriveTrigger``).

v1 supports the trigger behavior most commonly used in n8n templates:
poll or webhook on Google Drive file changes. The trigger fires once at
workflow start and emits one item per Drive change.

When a ``googleDriveOAuth2Api`` credential is attached and no mock is
present, real calls are made to the Google Drive Changes API via
:func:`execute_http_request`. Otherwise the executor is mock-driven with
an offline synthetic fallback.

Parameters consumed:

- ``triggerOn``  (one of ``specificFolder`` / ``watchAll`` /
  ``fileCreated`` / ``fileUpdated``; default ``watchAll``)
- ``folderId``   (string; default ``'root'``; only used when
  ``triggerOn == 'specificFolder'``)
- ``fileTypes``  (list of mime types; optional filter; echoed into the
  emitted item for downstream filtering)
- ``pollTimes``  (dict with ``item`` cron expression or
  ``mode == 'everyMinute'``; echoed only)
- ``event``      (one of ``fileCreated`` / ``fileUpdated`` /
  ``fileDeleted`` / ``fileShared``; default ``fileCreated``)

Behavior precedence (mock sources are tried in this order):

1. ``ctx.mocks['drive_changes']`` — when present, the value drives the
   trigger. A callable is invoked as ``mock(node, ctx)`` and may return
   either a dict (used as the raw changes payload) or a non-dict truthy
   value (treated as a single-change payload via the offline synth).
   A non-callable is used as the raw changes payload.
2. ``ctx.mocks['drive_response']`` — fallback (treated as ``changes``).
3. ``ctx.mocks['trigger_payload']`` — final generic trigger-payload
   fallback.
4. If a ``googleDriveOAuth2Api`` credential resolves (``accessToken``
   present), real calls are made to the Drive Changes API
   (``changes.startPageToken`` then ``changes.list``) and the response
   is used.
5. Offline synthetic Drive changes list with 3 files (default event
   ``fileCreated``).

Emitted item shape (per change):

::

    {
        "fileId":        <id>,
        "fileName":      <name>,
        "mimeType":      <mime>,
        "modifiedTime":  <iso>,
        "changeType":    <fileCreated|fileUpdated|fileDeleted|fileShared>,
        "parents":       [<id>, ...],
        "source":        "googleDriveTrigger",
        "folderId":      <folderId>,                  # only when specificFolder
        "fileTypes":     [...],                       # echoed when configured
        "event":         <event>,                     # mirror of params.event
        "triggerOn":     <triggerOn>,
        "mockSource":    <changes|offline>,           # only when not native
        "change":        <raw change entry>,          # full Drive entry
        "changes":       <raw changes list>,          # full Drive payload
    }

If items list is non-empty (upstream pre-seeded), each existing item is
passed through with the trigger context fields merged in (using
``setdefault`` so upstream values win on conflict) so downstream nodes
can still identify the trigger origin.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from app.services.workflows.http_client import HttpRequestConfig, execute_http_request
from app.services.workflows.items import ExecutionItem
from app.services.workflows.nodes._http_helpers import resolve_credential

if TYPE_CHECKING:
    from app.services.workflows.engine import EngineContext
    from app.services.workflows.graph import ExecNode

logger = logging.getLogger(__name__)


DRIVE_TRIGGER_ONS: tuple[str, ...] = (
    "specificFolder",
    "watchAll",
    "fileCreated",
    "fileUpdated",
)
DRIVE_TRIGGER_DEFAULT_TRIGGER_ON: str = "watchAll"
DRIVE_TRIGGER_DEFAULT_FOLDER_ID: str = "root"
DRIVE_TRIGGER_EVENTS: tuple[str, ...] = (
    "fileCreated",
    "fileUpdated",
    "fileDeleted",
    "fileShared",
)
DRIVE_TRIGGER_DEFAULT_EVENT: str = "fileCreated"
DRIVE_TRIGGER_OFFLINE_COUNT: int = 3


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
        for key in ("value", "name", "id", "valueName"):
            if key in value and value[key] is not None:
                return _coerce_str(value[key])
    return str(value)


def _resolve_trigger_on(params: dict[str, Any]) -> str:
    raw = params.get("triggerOn")
    if raw is None:
        return DRIVE_TRIGGER_DEFAULT_TRIGGER_ON
    s = _coerce_str(raw).strip()
    return s or DRIVE_TRIGGER_DEFAULT_TRIGGER_ON


def _resolve_folder_id(params: dict[str, Any], trigger_on: str) -> str:
    raw = params.get("folderId")
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return DRIVE_TRIGGER_DEFAULT_FOLDER_ID
    s = _coerce_str(raw).strip()
    return s or DRIVE_TRIGGER_DEFAULT_FOLDER_ID


def _resolve_event(params: dict[str, Any]) -> str:
    raw = params.get("event")
    if raw is None:
        return DRIVE_TRIGGER_DEFAULT_EVENT
    s = _coerce_str(raw).strip()
    return s or DRIVE_TRIGGER_DEFAULT_EVENT


def _resolve_file_types(params: dict[str, Any]) -> list[str]:
    raw = params.get("fileTypes")
    if raw is None:
        return []
    if isinstance(raw, (list, tuple)):
        return [_coerce_str(v).strip() for v in raw if _coerce_str(v).strip()]
    s = _coerce_str(raw).strip()
    if not s:
        return []
    # Comma-separated string → split
    return [part.strip() for part in s.split(",") if part.strip()]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _synthesize_changes() -> dict[str, Any]:
    """Offline fallback: a fake Drive ``changes.list`` payload with 3 files."""
    now = _now_iso()
    changes: list[dict[str, Any]] = []
    for i in range(1, DRIVE_TRIGGER_OFFLINE_COUNT + 1):
        file_id = f"mock_file_{i}"
        change: dict[str, Any] = {
            "fileId": file_id,
            "file": {
                "id": file_id,
                "name": f"{file_id}.txt",
                "mimeType": "text/plain",
                "modifiedTime": now,
                "parents": ["root"],
            },
            "changeType": "file",
            "time": now,
        }
        changes.append(change)
    return {
        "changes": changes,
        "newStartPageToken": "mock_token_123",
        "kind": "drive#changeList",
    }


def _changes_from_drive_response(
    raw: Any, *, event: str, source: str = "drive_response"
) -> tuple[dict[str, Any] | None, str]:
    """Coerce a mock value into a Drive changes payload.

    ``raw`` may be:

    - a dict with ``changes`` list — used directly
    - a dict with ``files`` list — wrapped as a changes payload
    - a dict with a single ``file`` / ``id`` — wrapped as one change
    - any other truthy value — ignored (returns ``None``)

    The ``source`` parameter identifies which mock key produced this value
    (e.g. ``"drive_changes"``, ``"drive_response"``, ``"trigger_payload"``)
    and is echoed in the returned tuple so callers can tag ``mockSource``.
    """
    if not isinstance(raw, dict):
        return None, ""
    if isinstance(raw.get("changes"), list):
        return dict(raw), source
    if isinstance(raw.get("files"), list):
        now = _now_iso()
        changes = []
        for entry in raw["files"]:
            if not isinstance(entry, dict):
                continue
            fid = _coerce_str(entry.get("id")) or _coerce_str(entry.get("fileId"))
            if not fid:
                continue
            changes.append(
                {
                    "fileId": fid,
                    "file": {
                        "id": fid,
                        "name": _coerce_str(entry.get("name")) or f"{fid}.txt",
                        "mimeType": _coerce_str(entry.get("mimeType"))
                        or "text/plain",
                        "modifiedTime": _coerce_str(entry.get("modifiedTime")) or now,
                        "parents": list(entry.get("parents") or ["root"]),
                    },
                    "changeType": _coerce_str(entry.get("changeType")) or "file",
                    "time": _coerce_str(entry.get("time")) or now,
                }
            )
        return (
            {
                "changes": changes,
                "newStartPageToken": _coerce_str(raw.get("newStartPageToken"))
                or "mock_token_123",
                "kind": "drive#changeList",
            },
            source,
        )
    if "file" in raw or "id" in raw or "fileId" in raw:
        now = _now_iso()
        fid = _coerce_str(raw.get("id")) or _coerce_str(raw.get("fileId"))
        file_block = raw.get("file")
        if not isinstance(file_block, dict):
            file_block = {}
        if not fid and isinstance(file_block, dict):
            fid = _coerce_str(file_block.get("id"))
        if not fid:
            return None, ""
        change = {
            "fileId": fid,
            "file": {
                "id": fid,
                "name": _coerce_str(file_block.get("name")) or f"{fid}.txt",
                "mimeType": _coerce_str(file_block.get("mimeType")) or "text/plain",
                "modifiedTime": _coerce_str(file_block.get("modifiedTime")) or now,
                "parents": list(file_block.get("parents") or ["root"]),
            },
            "changeType": _coerce_str(raw.get("changeType")) or "file",
            "time": _coerce_str(raw.get("time")) or now,
        }
        return (
            {
                "changes": [change],
                "newStartPageToken": "mock_token_123",
                "kind": "drive#changeList",
            },
            source,
        )
    return None, ""


def _build_drive_changes_request(
    cred: dict[str, Any],
    params: dict[str, Any],
) -> HttpRequestConfig | None:
    """Build a real Google Drive Changes API request config.

    Returns the config for the ``changes.startPageToken`` call (the
    entry point of the changes flow). Returns ``None`` when the
    credential has no ``accessToken``.
    """
    access_token = str(cred.get("accessToken") or "")
    if not access_token:
        return None
    return HttpRequestConfig(
        url="https://www.googleapis.com/drive/v3/changes/startPageToken",
        method="GET",
        auth="bearer",
        auth_credential={"accessToken": access_token},
        response_mode="json",
        timeout=30.0,
    )


def _envelope_from_drive_api(data: Any) -> dict[str, Any]:
    """Convert a real Drive Changes API response to the internal changes
    payload shape (matching ``_synthesize_changes()``)."""
    if not isinstance(data, dict):
        return {"changes": [], "newStartPageToken": "", "kind": "drive#changeList"}
    changes = data.get("changes")
    if not isinstance(changes, list):
        changes = []
    return {
        "changes": changes,
        "newStartPageToken": _coerce_str(data.get("newStartPageToken"))
        or _coerce_str(data.get("nextPageToken"))
        or "",
        "kind": _coerce_str(data.get("kind")) or "drive#changeList",
    }


async def _resolve_changes(
    node: "ExecNode", ctx: "EngineContext", event: str
) -> tuple[dict[str, Any], str]:
    """Pick the Drive changes payload from mocks, real API, or offline synth."""
    mocks = ctx.mocks if isinstance(ctx.mocks, dict) else {}

    dmock = mocks.get("drive_changes")
    if dmock is not None:
        if callable(dmock):
            raw = dmock(node, ctx)
        else:
            raw = dmock
        if isinstance(raw, dict):
            coerced, src = _changes_from_drive_response(raw, event=event, source="drive_changes")
            if coerced is not None:
                return coerced, src or "drive_changes"
            # dict but unrecognized shape — fall through, but tag source
            return _synthesize_changes(), "offline"
        # Non-dict truthy → wrap as a single-change payload
        fid = _coerce_str(raw) or "mock_file_change"
        now = _now_iso()
        change = {
            "fileId": fid,
            "file": {
                "id": fid,
                "name": f"{fid}.txt",
                "mimeType": "text/plain",
                "modifiedTime": now,
                "parents": ["root"],
            },
            "changeType": "file",
            "time": now,
        }
        return (
            {
                "changes": [change],
                "newStartPageToken": "mock_token_123",
                "kind": "drive#changeList",
            },
            "drive_changes",
        )

    rmock = mocks.get("drive_response")
    if rmock is not None:
        if callable(rmock):
            raw = rmock(node, ctx)
        else:
            raw = rmock
        coerced, src = _changes_from_drive_response(raw, event=event)
        if coerced is not None:
            return coerced, src

    tmock = mocks.get("trigger_payload")
    if isinstance(tmock, dict):
        coerced, src = _changes_from_drive_response(tmock, event=event, source="trigger_payload")
        if coerced is not None:
            return coerced, src or "trigger_payload"
        # Trigger payload is a single change dict
        if "file" in tmock or "id" in tmock or "fileId" in tmock:
            return _changes_from_drive_response(tmock, event=event, source="trigger_payload")[0] or _synthesize_changes(), "trigger_payload"
        # Bare changes list under a top-level "changes" key
        if isinstance(tmock.get("changes"), list):
            return dict(tmock), "trigger_payload"

    cred = resolve_credential(node, ctx, "googleDriveOAuth2Api")
    if cred:
        params = node.parameters or {}
        cfg = _build_drive_changes_request(cred, params)
        if cfg is not None:
            logger.info(
                "googleDriveTrigger real HTTP call event=%s",
                event,
            )
            try:
                token_resp = await execute_http_request(cfg, ctx=ctx)
                token_data = (
                    token_resp.body if isinstance(token_resp.body, dict) else {}
                )
                page_token = _coerce_str(token_data.get("startPageToken"))

                access_token = str(cred.get("accessToken") or "")
                changes_cfg = HttpRequestConfig(
                    url=(
                        "https://www.googleapis.com/drive/v3/changes"
                        f"?pageToken={page_token}"
                        "&includeItemsFromAllDrives=true"
                        "&supportsAllDrives=true"
                    ),
                    method="GET",
                    auth="bearer",
                    auth_credential={"accessToken": access_token},
                    response_mode="json",
                    timeout=30.0,
                )
                changes_resp = await execute_http_request(changes_cfg, ctx=ctx)
                if isinstance(changes_resp.body, dict):
                    return _envelope_from_drive_api(changes_resp.body), "drive_api"
            except Exception as exc:
                logger.warning("googleDriveTrigger HTTP call failed: %s", exc)

    return _synthesize_changes(), "offline"


def _extract_change_fields(change: dict[str, Any], event: str) -> dict[str, Any]:
    """Flatten a single Drive change entry into the trigger item fields."""
    if not isinstance(change, dict):
        change = {}
    file_block = change.get("file")
    if not isinstance(file_block, dict):
        file_block = {}
    file_id = _coerce_str(change.get("fileId")) or _coerce_str(file_block.get("id"))
    file_name = _coerce_str(file_block.get("name"))
    mime_type = _coerce_str(file_block.get("mimeType"))
    modified_time = _coerce_str(
        change.get("time")
        or file_block.get("modifiedTime")
        or file_block.get("createdTime")
    )
    change_type = _coerce_str(change.get("changeType")) or event
    parents_raw = file_block.get("parents")
    if isinstance(parents_raw, (list, tuple)):
        parents = [_coerce_str(p) for p in parents_raw if p is not None]
    elif parents_raw is None:
        parents = []
    else:
        parents = [_coerce_str(parents_raw)]
    return {
        "fileId": file_id,
        "fileName": file_name,
        "mimeType": mime_type,
        "modifiedTime": modified_time,
        "changeType": change_type,
        "parents": parents,
    }


def _change_matches_event(change_type: str, event: str, trigger_on: str) -> bool:
    """Best-effort filter — keep changes whose type matches the requested event.

    Drive's ``changeType`` is normally just ``'file'``; the real n8n node
    uses ``event``/``triggerOn`` to filter on the file's lifecycle. We
    don't have lifecycle info here, so accept anything that isn't an
    explicit mismatch.
    """
    if not change_type:
        return True
    if change_type == "file":
        return True
    return True


async def exec_google_drive_trigger(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Google Drive Trigger — emit one item per Drive change.

    See module docstring for the full resolution order and emitted
    payload shape.
    """
    params = node.parameters or {}

    trigger_on = _resolve_trigger_on(params)
    folder_id = _resolve_folder_id(params, trigger_on)
    event = _resolve_event(params)
    file_types = _resolve_file_types(params)
    poll_times = params.get("pollTimes") if isinstance(params.get("pollTimes"), dict) else {}

    changes_payload, source = await _resolve_changes(node, ctx, event)
    changes_list = changes_payload.get("changes") if isinstance(changes_payload, dict) else None
    if not isinstance(changes_list, list):
        changes_list = []

    new_start_page_token = (
        _coerce_str(changes_payload.get("newStartPageToken"))
        if isinstance(changes_payload, dict)
        else ""
    )

    out: list[ExecutionItem] = []

    for change in changes_list:
        if not isinstance(change, dict):
            continue
        flat = _extract_change_fields(change, event)
        if not _change_matches_event(
            _coerce_str(flat.get("changeType")), event, trigger_on
        ):
            continue

        base: dict[str, Any] = {
            "fileId": flat["fileId"],
            "fileName": flat["fileName"],
            "mimeType": flat["mimeType"],
            "modifiedTime": flat["modifiedTime"],
            "changeType": flat["changeType"],
            "parents": flat["parents"],
            "event": event,
            "triggerOn": trigger_on,
            "newStartPageToken": new_start_page_token,
            "pollTimes": dict(poll_times) if poll_times else {},
            "source": "googleDriveTrigger",
        }
        if trigger_on == "specificFolder":
            base["folderId"] = folder_id
        if file_types:
            base["fileTypes"] = list(file_types)
        if source not in ("offline", "drive_api"):
            base["mockSource"] = source
        # Echo the raw change for downstream debugging.
        base["change"] = dict(change)
        if out == [] and len(changes_list) == 1:
            # Only attach the full envelope on the first emitted item to
            # avoid huge payloads when there are many changes.
            base["changes"] = list(changes_list)

        out.append(ExecutionItem(json=base))

    if items and source == "offline":
        # Pass-through mode: keep upstream data, just add trigger context.
        passthrough: list[ExecutionItem] = []
        for item in items:
            merged = dict(item.json)
            merged.setdefault("fileId", "")
            merged.setdefault("fileName", "")
            merged.setdefault("mimeType", "")
            merged.setdefault("modifiedTime", "")
            merged.setdefault("changeType", event)
            merged.setdefault("parents", [])
            merged.setdefault("event", event)
            merged.setdefault("triggerOn", trigger_on)
            if trigger_on == "specificFolder":
                merged.setdefault("folderId", folder_id)
            if file_types:
                merged.setdefault("fileTypes", list(file_types))
            merged.setdefault("newStartPageToken", new_start_page_token)
            if poll_times:
                merged.setdefault("pollTimes", dict(poll_times))
            merged.setdefault("source", "googleDriveTrigger")
            if source not in ("offline", "drive_api"):
                merged.setdefault("mockSource", source)
            ni = item.clone()
            ni.json = merged
            passthrough.append(ni)
        return [(0, passthrough)]

    if not out:
        # No changes anywhere → still emit a single item so downstream
        # nodes see a run (matches behavior of other trigger executors).
        base: dict[str, Any] = {
            "fileId": "",
            "fileName": "",
            "mimeType": "",
            "modifiedTime": "",
            "changeType": event,
            "parents": [],
            "event": event,
            "triggerOn": trigger_on,
            "newStartPageToken": new_start_page_token,
            "pollTimes": dict(poll_times) if poll_times else {},
            "source": "googleDriveTrigger",
        }
        if trigger_on == "specificFolder":
            base["folderId"] = folder_id
        if file_types:
            base["fileTypes"] = list(file_types)
        if source not in ("offline", "drive_api"):
            base["mockSource"] = source
        return [(0, [ExecutionItem(json=base)])]

    logger.info(
        "googleDriveTrigger triggerOn=%s event=%s folderId=%s fileTypes=%d count=%d source=%s",
        trigger_on,
        event,
        folder_id,
        len(file_types),
        len(out),
        source,
    )

    return [(0, out)]


__all__ = [
    "exec_google_drive_trigger",
    "DRIVE_TRIGGER_ONS",
    "DRIVE_TRIGGER_DEFAULT_TRIGGER_ON",
    "DRIVE_TRIGGER_DEFAULT_FOLDER_ID",
    "DRIVE_TRIGGER_EVENTS",
    "DRIVE_TRIGGER_DEFAULT_EVENT",
    "DRIVE_TRIGGER_OFFLINE_COUNT",
]
