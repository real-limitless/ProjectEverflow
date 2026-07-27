"""Tests for the YouTube node executor (``n8n-nodes-base.youTube``).

Covers:

- ``youtube_response`` dict mock → envelope used per operation
- ``youtube_response`` callable mock receives ``(operation, params, item, ctx)``
- ``http_response`` fallback unwraps a JSON body
- Offline search: returns up to 3 items
- Offline get: videoId echoed, statistics present
- Offline list: returns up to 3 items
- Offline upload: id present, uploadStatus='uploaded'
- ``operation='search'`` reflected
- ``q`` default from ``$json``
- ``maxResults`` honored
- Empty ``videoId`` for get → no item
- End-to-end: Manual Trigger → youTube (search mock) → Set sees videoId and title
- Descriptor registration (CI invariant)
"""

from __future__ import annotations

from typing import Any

import pytest

from app.services.workflows.engine import EngineContext, WorkflowEngine
from app.services.workflows.graph import ExecNode
from app.services.workflows.items import ExecutionItem
from app.services.workflows.nodes.youtube import (
    YOUTUBE_DEFAULT_MAX_RESULTS,
    YOUTUBE_DEFAULT_OPERATION,
    YOUTUBE_OFFLINE_MAX_VIDEOS,
    YOUTUBE_OPERATIONS,
    exec_youtube,
)


# ── Helpers ───────────────────────────────────────────────────────────


def _node(
    params: dict[str, Any],
    *,
    type_: str = "n8n-nodes-base.youTube",
    id_: str = "yt1",
    name: str = "YouTube",
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


# ── 1. youtube_response dict mock (search) ───────────────────────────


@pytest.mark.asyncio
async def test_youtube_response_dict_mock_search_used_verbatim() -> None:
    node = _node(
        {
            "operation": "search",
            "q": "cats",
            "maxResults": 5,
        }
    )
    ctx = _ctx(
        {
            "youtube_response": {
                "items": [
                    {
                        "id": {"videoId": "yt-vid-001"},
                        "snippet": {
                            "title": "Mocked Video",
                            "description": "Mocked desc",
                            "channelId": "chan-1",
                            "publishedAt": "2025-01-15T10:00:00Z",
                        },
                    }
                ],
                "pageInfo": {"totalResults": 1, "resultsPerPage": 1},
            }
        }
    )
    out = _out_items(
        await exec_youtube(node, [ExecutionItem(json={})], ctx=ctx)
    )
    assert len(out) == 1
    p = out[0].json
    assert p["videoId"] == "yt-vid-001"
    assert p["title"] == "Mocked Video"
    assert p["description"] == "Mocked desc"
    assert p["channelId"] == "chan-1"
    assert p["publishedAt"] == "2025-01-15T10:00:00Z"
    assert p["source"] == "youTube"
    assert p["operation"] == "search"
    assert "mockSource" not in p


# ── 2. youtube_response callable mock signature ──────────────────────


@pytest.mark.asyncio
async def test_youtube_response_callable_mock_receives_args() -> None:
    captured: dict[str, Any] = {}

    def _mock(operation, params, item, ctx):
        captured["operation"] = operation
        captured["params"] = params
        captured["item"] = item
        captured["ctx"] = ctx
        return {
            "items": [
                {
                    "id": {"videoId": "mock-vid-1"},
                    "snippet": {
                        "title": "Mock",
                        "description": "d",
                        "channelId": "c",
                        "publishedAt": "2025-01-15T10:00:00Z",
                    },
                }
            ],
            "pageInfo": {"totalResults": 1, "resultsPerPage": 1},
        }

    node = _node(
        {
            "operation": "search",
            "q": "S",
            "maxResults": 5,
            "extra": "keep",
        }
    )
    ctx = _ctx({"youtube_response": _mock})
    item = ExecutionItem(json={"hint": 1})
    out = _out_items(await exec_youtube(node, [item], ctx=ctx))

    assert captured["operation"] == "search"
    assert captured["params"]["extra"] == "keep"
    assert captured["params"]["q"] == "S"
    assert captured["item"] is item
    assert captured["ctx"] is ctx

    assert len(out) == 1
    assert out[0].json["videoId"] == "mock-vid-1"


# ── 3. http_response fallback ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_http_response_fallback_unwraps_json_body() -> None:
    node = _node(
        {
            "operation": "search",
            "q": "dogs",
            "maxResults": 5,
        }
    )
    ctx = _ctx(
        {
            "http_response": {
                "status_code": 200,
                "body": {
                    "items": [
                        {
                            "id": {"videoId": "http-vid-1"},
                            "snippet": {
                                "title": "From HTTP",
                                "description": "d",
                                "channelId": "c",
                                "publishedAt": "2025-01-15T10:00:00Z",
                            },
                        }
                    ],
                    "pageInfo": {"totalResults": 1, "resultsPerPage": 1},
                },
            }
        }
    )
    out = _out_items(
        await exec_youtube(node, [ExecutionItem(json={})], ctx=ctx)
    )
    assert len(out) == 1
    assert out[0].json["videoId"] == "http-vid-1"
    assert out[0].json["title"] == "From HTTP"
    assert out[0].json["mockSource"] == "http_response"
    assert out[0].json["source"] == "youTube"


# ── 4. Offline synthetic response — search ───────────────────────────


@pytest.mark.asyncio
async def test_offline_search_returns_up_to_three_items() -> None:
    node = _node({"operation": "search", "q": "music", "maxResults": 5})
    out = _out_items(
        await exec_youtube(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    # offline cap is min(maxResults=5, YOUTUBE_OFFLINE_MAX_VIDEOS=3) = 3
    assert len(out) == YOUTUBE_OFFLINE_MAX_VIDEOS
    for i, o in enumerate(out, start=1):
        p = o.json
        assert p["source"] == "youTube"
        assert p["videoId"] == f"mock_vid_{i}"
        assert p["title"] == f"Mock Video {i}"
        assert p["description"] == f"Mock description {i}"
        assert p["channelId"] == "mock_channel"
        assert p["publishedAt"].endswith("Z")
        assert p["mockSource"] == "offline"
        assert p["operation"] == "search"


# ── 5. Offline synthetic response — get ──────────────────────────────


@pytest.mark.asyncio
async def test_offline_get_returns_video_with_id_and_statistics() -> None:
    node = _node(
        {
            "operation": "get",
            "videoId": "specific-vid-42",
        }
    )
    out = _out_items(
        await exec_youtube(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) == 1
    p = out[0].json
    assert p["videoId"] == "specific-vid-42"
    assert p["title"] == "Mock Video"
    assert p["description"] == "Mock description"
    assert p["channelId"] == "mock_channel"
    assert p["publishedAt"].endswith("Z")
    assert p["viewCount"] == "1000"
    assert p["likeCount"] == "100"
    assert p["commentCount"] == "10"
    assert p["source"] == "youTube"
    assert p["mockSource"] == "offline"
    assert p["operation"] == "get"


# ── 6. Offline synthetic response — list ─────────────────────────────


@pytest.mark.asyncio
async def test_offline_list_returns_up_to_three_items() -> None:
    node = _node(
        {
            "operation": "list",
            "channelId": "UC_mock_channel",
            "maxResults": 5,
        }
    )
    out = _out_items(
        await exec_youtube(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) == YOUTUBE_OFFLINE_MAX_VIDEOS
    for i, o in enumerate(out, start=1):
        p = o.json
        assert p["source"] == "youTube"
        assert p["videoId"] == f"mock_vid_{i}"
        assert p["title"] == f"Channel Video {i}"
        assert p["publishedAt"].endswith("Z")
        assert p["mockSource"] == "offline"
        assert p["operation"] == "list"
        assert p["channelId"] == "UC_mock_channel"


# ── 7. Offline synthetic response — upload ───────────────────────────


@pytest.mark.asyncio
async def test_offline_upload_returns_id_and_upload_status() -> None:
    node = _node(
        {
            "operation": "upload",
            "title": "My Upload",
            "description": "A test video",
            "privacyStatus": "unlisted",
        }
    )
    out = _out_items(
        await exec_youtube(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) == 1
    p = out[0].json
    assert p["videoId"].startswith("mock_upload_")
    assert p["title"] == "My Upload"
    assert p["description"] == "A test video"
    assert p["privacyStatus"] == "unlisted"
    assert p["uploadStatus"] == "uploaded"
    assert p["source"] == "youTube"
    assert p["mockSource"] == "offline"
    assert p["operation"] == "upload"


# ── 8. operation='search' reflected ──────────────────────────────────


@pytest.mark.asyncio
async def test_search_operation_reflected_in_source() -> None:
    node = _node(
        {
            "operation": "search",
            "q": "X",
            "maxResults": 1,
        }
    )
    out = _out_items(
        await exec_youtube(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert out[0].json["source"] == "youTube"
    assert out[0].json["operation"] == "search"
    assert "videoId" in out[0].json
    assert "title" in out[0].json


# ── 9. q default from $json ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_q_default_from_json() -> None:
    node = _node({"operation": "search", "maxResults": 1})
    item = ExecutionItem(json={"q": "from-json-query"})
    out = _out_items(await exec_youtube(node, [item], ctx=_ctx()))
    assert out[0].json["q"] == "from-json-query"


@pytest.mark.asyncio
async def test_q_falls_back_to_query_key() -> None:
    node = _node({"operation": "search", "maxResults": 1})
    item = ExecutionItem(json={"query": "query-key"})
    out = _out_items(await exec_youtube(node, [item], ctx=_ctx()))
    assert out[0].json["q"] == "query-key"


# ── 10. maxResults honored ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_max_results_honored_with_caps() -> None:
    node = _node(
        {
            "operation": "search",
            "q": "x",
            "maxResults": 100,
        }
    )
    out = _out_items(
        await exec_youtube(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    # offline caps at YOUTUBE_OFFLINE_MAX_VIDEOS (3)
    assert len(out) == YOUTUBE_OFFLINE_MAX_VIDEOS


@pytest.mark.asyncio
async def test_max_results_two() -> None:
    node = _node(
        {
            "operation": "search",
            "q": "x",
            "maxResults": 2,
        }
    )
    out = _out_items(
        await exec_youtube(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) == 2


@pytest.mark.asyncio
async def test_max_results_one_via_mock() -> None:
    node = _node(
        {
            "operation": "search",
            "q": "x",
            "maxResults": 1,
        }
    )
    ctx = _ctx(
        {
            "youtube_response": {
                "items": [
                    {
                        "id": {"videoId": "mock-1"},
                        "snippet": {
                            "title": "S1",
                            "description": "d",
                            "channelId": "c",
                            "publishedAt": "2025-01-15T10:00:00Z",
                        },
                    },
                    {
                        "id": {"videoId": "mock-2"},
                        "snippet": {
                            "title": "S2",
                            "description": "d",
                            "channelId": "c",
                            "publishedAt": "2025-01-16T10:00:00Z",
                        },
                    },
                ],
                "pageInfo": {"totalResults": 2, "resultsPerPage": 2},
            }
        }
    )
    out = _out_items(
        await exec_youtube(node, [ExecutionItem(json={})], ctx=ctx)
    )
    assert len(out) == 1
    assert out[0].json["videoId"] == "mock-1"


# ── 11. Empty videoId for get → no item ──────────────────────────────


@pytest.mark.asyncio
async def test_empty_video_id_for_get_skips_item() -> None:
    node = _node({"operation": "get"})
    item = ExecutionItem(json={"videoId": "", "id": ""})
    out = _out_items(await exec_youtube(node, [item], ctx=_ctx()))
    assert out == []


@pytest.mark.asyncio
async def test_empty_channel_id_for_list_skips_item() -> None:
    node = _node({"operation": "list", "maxResults": 1})
    item = ExecutionItem(json={"channelId": ""})
    out = _out_items(await exec_youtube(node, [item], ctx=_ctx()))
    assert out == []


# ── 12. Default operation is 'search' ────────────────────────────────


@pytest.mark.asyncio
async def test_default_operation_is_search() -> None:
    assert YOUTUBE_DEFAULT_OPERATION == "search"
    node = _node({"q": "x", "maxResults": 1})
    out = _out_items(
        await exec_youtube(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert out[0].json["operation"] == "search"
    assert "videoId" in out[0].json


# ── 13. dataMode='object' emits single item with items[] ─────────────


@pytest.mark.asyncio
async def test_search_data_mode_object_emits_single_item() -> None:
    node = _node(
        {
            "operation": "search",
            "q": "x",
            "dataMode": "object",
            "maxResults": 5,
        }
    )
    out = _out_items(
        await exec_youtube(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) == 1
    p = out[0].json
    assert isinstance(p["items"], list)
    assert len(p["items"]) == YOUTUBE_OFFLINE_MAX_VIDEOS
    assert p["source"] == "youTube"


# ── 14. videoId default from $json for get ───────────────────────────


@pytest.mark.asyncio
async def test_video_id_default_from_json() -> None:
    node = _node({"operation": "get"})
    item = ExecutionItem(json={"videoId": "from-json-vid-1"})
    out = _out_items(await exec_youtube(node, [item], ctx=_ctx()))
    assert out[0].json["videoId"] == "from-json-vid-1"


@pytest.mark.asyncio
async def test_video_id_falls_back_to_id_key() -> None:
    node = _node({"operation": "get"})
    item = ExecutionItem(json={"id": "id-key-vid-7"})
    out = _out_items(await exec_youtube(node, [item], ctx=_ctx()))
    assert out[0].json["videoId"] == "id-key-vid-7"


# ── 15. upload defaults from $json ───────────────────────────────────


@pytest.mark.asyncio
async def test_upload_defaults_from_json() -> None:
    node = _node({"operation": "upload"})
    item = ExecutionItem(
        json={"title": "From JSON", "description": "JSON desc"}
    )
    out = _out_items(await exec_youtube(node, [item], ctx=_ctx()))
    assert len(out) == 1
    p = out[0].json
    assert p["title"] == "From JSON"
    assert p["description"] == "JSON desc"
    assert p["privacyStatus"] == "private"


# ── 16. Descriptor registration ──────────────────────────────────────


def test_descriptor_is_registered() -> None:
    from app.services.workflows.nodes import descriptors as _  # noqa: F401
    from app.services.workflows.registry import REGISTRY, SUPPORTED_NODE_TYPES

    assert "n8n-nodes-base.youTube" in REGISTRY
    assert "n8n-nodes-base.youTube" in SUPPORTED_NODE_TYPES
    assert SUPPORTED_NODE_TYPES["n8n-nodes-base.youTube"] == "output"
    desc = REGISTRY["n8n-nodes-base.youTube"]
    assert desc.executor.endswith(":exec_youtube")
    assert desc.category == "output"
    assert set(YOUTUBE_OPERATIONS) == {"search", "get", "list", "upload"}


# ── 17. Unsupported operation raises ─────────────────────────────────


@pytest.mark.asyncio
async def test_unsupported_operation_raises() -> None:
    node = _node({"operation": "patch"})
    with pytest.raises(ValueError, match="unsupported operation"):
        await exec_youtube(node, [ExecutionItem(json={})], ctx=_ctx())


# ── 18. End-to-end: Manual Trigger → youTube (search mock) → Set ────


def _doc(nodes, connections):
    return {"name": "yt-test", "nodes": nodes, "connections": connections}


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
async def test_end_to_end_manual_youtube_set_sees_videos() -> None:
    """Manual Trigger → youTube (youtube_response mock) → Set pulls videos."""
    mocks = {
        "youtube_response": {
            "items": [
                {
                    "id": {"videoId": "e2e-vid-1"},
                    "snippet": {
                        "title": "E2E Video 1",
                        "description": "d1",
                        "channelId": "c1",
                        "publishedAt": "2025-04-01T10:00:00Z",
                    },
                },
                {
                    "id": {"videoId": "e2e-vid-2"},
                    "snippet": {
                        "title": "E2E Video 2",
                        "description": "d2",
                        "channelId": "c2",
                        "publishedAt": "2025-04-02T10:00:00Z",
                    },
                },
            ],
            "pageInfo": {"totalResults": 2, "resultsPerPage": 2},
        }
    }
    doc = _doc(
        [
            _n("t1", "Start", "n8n-nodes-base.manualTrigger"),
            _n(
                "yt1",
                "YouTube",
                "n8n-nodes-base.youTube",
                {
                    "operation": "search",
                    "q": "everflow",
                    "maxResults": 5,
                },
            ),
            _n(
                "s1",
                "Downstream",
                "n8n-nodes-base.set",
                {
                    "assignments": {
                        "assignments": [
                            {"name": "result_video_id", "value": "={{ $json.videoId }}", "type": "string"},
                            {"name": "result_title", "value": "={{ $json.title }}", "type": "string"},
                            {"name": "result_source", "value": "={{ $json.source }}", "type": "string"},
                        ]
                    }
                },
            ),
        ],
        {
            "Start": {"main": [[{"node": "YouTube", "type": "main", "index": 0}]]},
            "YouTube": {"main": [[{"node": "Downstream", "type": "main", "index": 0}]]},
        },
    )
    engine = WorkflowEngine(doc, mocks=mocks)
    result = await engine.run(trigger="manual")
    assert result.status == "success", result.error_message

    yt_step = next(s for s in result.steps if s.node_name == "YouTube")
    assert yt_step.status == "success", yt_step.error
    assert yt_step.output_count == 2
    first = yt_step.sample_output[0]
    assert first["json"]["videoId"] == "e2e-vid-1"
    assert first["json"]["title"] == "E2E Video 1"
    assert first["json"]["source"] == "youTube"

    final = result.final_items
    assert final, "expected at least one final item"
    fjson = final[0].get("json") if isinstance(final[0], dict) else None
    assert fjson is not None
    assert fjson.get("result_video_id") == "e2e-vid-1"
    assert fjson.get("result_title") == "E2E Video 1"
    assert fjson.get("result_source") == "youTube"