"""OpenAI actions executor (clean-room n8n ``@n8n/n8n-nodes-langchain.openAi``).

Supports the four operations most commonly used in n8n templates:

- ``textCompletion`` (legacy ``/v1/completions`` endpoint)
- ``imageGeneration`` (DALL·E ``/v1/images/generations``)
- ``transcription`` (Whisper ``/v1/audio/transcriptions``)
- ``analyzeImage`` (vision via ``/v1/chat/completions`` with image content)

Real calls go through :func:`app.services.workflows.http_client.execute_http_request`
so SSRF guards, retries, and mock dispatch are shared with ``httpRequest`` and
other nodes.

Tests drive the executor via ``ctx.mocks['openai'][operation]`` — the mock
value is the parsed JSON body the real OpenAI endpoint would return for that
operation. See ``tests/test_workflows_openai_actions.py``.
"""

from __future__ import annotations

import base64
import logging
from typing import TYPE_CHECKING, Any

from app.services.workflows.http_client import HttpRequestConfig, execute_http_request
from app.services.workflows.items import ExecutionItem

if TYPE_CHECKING:
    from app.services.workflows.engine import EngineContext
    from app.services.workflows.graph import ExecNode

logger = logging.getLogger(__name__)


OPENAI_OPERATIONS: tuple[str, ...] = (
    "textCompletion",
    "imageGeneration",
    "transcription",
    "analyzeImage",
)

DEFAULT_COMPLETION_MODEL = "gpt-3.5-turbo-instruct"
DEFAULT_IMAGE_SIZE = "1024x1024"
DEFAULT_IMAGE_COUNT = 1
DEFAULT_VISION_MODEL = "gpt-4o-mini"
DEFAULT_TRANSCRIPTION_MODEL = "whisper-1"

DEFAULT_BASE_URL = "https://api.openai.com/v1"


def _openai_credential(node: "ExecNode", ctx: "EngineContext") -> dict[str, Any]:
    """Resolve the ``openAiApi`` credential attached to the node.

    Falls back to the first credential attached to the node, then to
    ``ctx.mocks['openai_api_key']`` so tests can drive the executor
    without registering a credential.
    """
    cred = ctx.resolve_credential(node, "openAiApi") or {}
    if not cred and node.credentials:
        for v in node.credentials.values():
            if isinstance(v, dict):
                cred = v
                break
    if not cred and ctx.mocks:
        mock_key = ctx.mocks.get("openai_api_key")
        if mock_key:
            cred = {"apiKey": str(mock_key)}
    return cred


def _credentials_block(cred: dict[str, Any]) -> tuple[str, str]:
    api_key = str(cred.get("apiKey") or cred.get("api_key") or "")
    base_url = str(
        cred.get("url") or cred.get("baseUrl") or cred.get("base_url") or DEFAULT_BASE_URL
    )
    return api_key, base_url


def _has_mock(ctx: "EngineContext", operation: str) -> bool:
    return bool(ctx.mocks and isinstance(ctx.mocks.get("openai"), dict)
                and operation in ctx.mocks["openai"])


def _mock_for(ctx: "EngineContext", operation: str) -> Any:
    return (ctx.mocks or {}).get("openai", {}).get(operation)


def _emit_one(item: ExecutionItem, payload: dict[str, Any]) -> list[ExecutionItem]:
    ni = item.clone()
    ni.json = {**item.json, **payload}
    return [ni]


def _emit_many(item: ExecutionItem, payloads: list[dict[str, Any]]) -> list[ExecutionItem]:
    out: list[ExecutionItem] = []
    for p in payloads:
        ni = item.clone()
        ni.json = {**item.json, **p}
        out.append(ni)
    return out


# ── Operation handlers ────────────────────────────────────────────────


async def _op_text_completion(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[ExecutionItem]:
    params = node.parameters or {}
    out: list[ExecutionItem] = []
    for item in items:
        from app.services.workflows.expression import ExpressionContext, evaluate

        ectx = ExpressionContext(item=item, node_outputs=ctx.node_outputs, now=ctx.now)
        prompt = evaluate(params.get("prompt"), ectx)
        prompt = "" if prompt is None else str(prompt)
        model = params.get("model") or DEFAULT_COMPLETION_MODEL
        if isinstance(model, dict):
            model = str(model.get("value") or model.get("name") or DEFAULT_COMPLETION_MODEL)
        options = params.get("options") if isinstance(params.get("options"), dict) else {}
        max_tokens = options.get("maxTokens") or options.get("max_tokens")
        temperature = options.get("temperature")

        if _has_mock(ctx, "textCompletion"):
            mock = _mock_for(ctx, "textCompletion")
            data = mock(prompt, item.json) if callable(mock) else mock
            if not isinstance(data, dict):
                data = {"text": str(data)}
            text = str(
                data.get("text")
                or (data.get("choices") or [{}])[0].get("text")
                or ""
            )
            usage = data.get("usage") or {}
            out.extend(
                _emit_one(
                    item,
                    {
                        "text": text,
                        "model": str(data.get("model") or model),
                        "usage": usage,
                    },
                )
            )
            continue

        cred = _openai_credential(node, ctx)
        api_key, base_url = _credentials_block(cred)
        if not api_key:
            out.extend(
                _emit_one(
                    item,
                    {
                        "text": "",
                        "model": model,
                        "usage": {},
                        "error": "No openAiApi credential configured",
                    },
                )
            )
            continue

        body: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
        }
        if max_tokens is not None and max_tokens != "":
            try:
                body["max_tokens"] = int(max_tokens)
            except (TypeError, ValueError):
                pass
        if temperature is not None and temperature != "":
            try:
                body["temperature"] = float(temperature)
            except (TypeError, ValueError):
                pass

        resp = await execute_http_request(
            HttpRequestConfig(
                url=f"{base_url.rstrip('/')}/completions",
                method="POST",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                body=body,
                body_mode="json",
                response_mode="json",
                timeout=120.0,
                retries=node.max_tries or 1,
            ),
            ctx=ctx,
        )
        data = resp.body if isinstance(resp.body, dict) else {}
        text = str(
            (data.get("choices") or [{}])[0].get("text")
            or ""
        )
        out.extend(
            _emit_one(
                item,
                {
                    "text": text,
                    "model": str(data.get("model") or model),
                    "usage": data.get("usage") or {},
                },
            )
        )
    return out


async def _op_image_generation(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[ExecutionItem]:
    params = node.parameters or {}
    out: list[ExecutionItem] = []
    for item in items:
        from app.services.workflows.expression import ExpressionContext, evaluate

        ectx = ExpressionContext(item=item, node_outputs=ctx.node_outputs, now=ctx.now)
        prompt = evaluate(params.get("prompt"), ectx)
        prompt = "" if prompt is None else str(prompt)
        size = str(params.get("size") or DEFAULT_IMAGE_SIZE)
        try:
            n = int(params.get("n") if params.get("n") is not None else DEFAULT_IMAGE_COUNT)
        except (TypeError, ValueError):
            n = DEFAULT_IMAGE_COUNT
        n = max(1, n)

        if _has_mock(ctx, "imageGeneration"):
            mock = _mock_for(ctx, "imageGeneration")
            data = mock(prompt, item.json) if callable(mock) else mock
            data = data if isinstance(data, dict) else {"data": []}
            images = data.get("data") or []
            payloads: list[dict[str, Any]] = []
            for img in images:
                if not isinstance(img, dict):
                    img = {"url": str(img)}
                payloads.append(
                    {
                        "url": img.get("url"),
                        "revisedPrompt": img.get("revised_prompt")
                        or img.get("revisedPrompt"),
                        "b64_json": img.get("b64_json") or img.get("b64Json"),
                    }
                )
            if not payloads:
                payloads = [
                    {"url": None, "revisedPrompt": None, "b64_json": None}
                ]
            out.extend(_emit_many(item, payloads))
            continue

        cred = _openai_credential(node, ctx)
        api_key, base_url = _credentials_block(cred)
        if not api_key:
            out.extend(
                _emit_many(
                    item,
                    [{"url": None, "revisedPrompt": None, "b64_json": None,
                      "error": "No openAiApi credential configured"}],
                )
            )
            continue

        body: dict[str, Any] = {
            "model": params.get("model") or "dall-e-3",
            "prompt": prompt,
            "size": size,
            "n": n,
        }
        resp = await execute_http_request(
            HttpRequestConfig(
                url=f"{base_url.rstrip('/')}/images/generations",
                method="POST",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                body=body,
                body_mode="json",
                response_mode="json",
                timeout=120.0,
                retries=node.max_tries or 1,
            ),
            ctx=ctx,
        )
        data = resp.body if isinstance(resp.body, dict) else {}
        images = data.get("data") or []
        payloads = [
            {
                "url": (img.get("url") if isinstance(img, dict) else None),
                "revisedPrompt": (img.get("revised_prompt") if isinstance(img, dict) else None),
                "b64_json": (img.get("b64_json") if isinstance(img, dict) else None),
            }
            for img in images
        ] or [{"url": None, "revisedPrompt": None, "b64_json": None}]
        out.extend(_emit_many(item, payloads))
    return out


async def _op_transcription(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[ExecutionItem]:
    params = node.parameters or {}
    bin_prop = str(params.get("binaryPropertyName") or "data")
    out: list[ExecutionItem] = []
    for item in items:
        bin_entry = (item.binary or {}).get(bin_prop)
        audio_b64 = bin_entry.data_b64 if bin_entry is not None else ""
        audio_bytes = bin_entry.to_bytes() if bin_entry is not None else b""
        mime = bin_entry.mime_type if bin_entry is not None else "application/octet-stream"
        filename = bin_entry.file_name if bin_entry is not None else "audio"

        if _has_mock(ctx, "transcription"):
            mock = _mock_for(ctx, "transcription")
            data = mock(audio_b64, item.json) if callable(mock) else mock
            data = data if isinstance(data, dict) else {"text": str(data)}
            out.extend(
                _emit_one(
                    item,
                    {
                        "text": str(data.get("text") or ""),
                        "language": data.get("language"),
                    },
                )
            )
            continue

        cred = _openai_credential(node, ctx)
        api_key, base_url = _credentials_block(cred)
        if not api_key or not audio_bytes:
            out.extend(
                _emit_one(
                    item,
                    {
                        "text": "",
                        "language": None,
                        "error": "Missing audio binary or openAiApi credential",
                    },
                )
            )
            continue

        from io import BytesIO

        files = {"file": (filename, BytesIO(audio_bytes), mime)}
        data_fields: dict[str, str] = {
            "model": str(params.get("model") or DEFAULT_TRANSCRIPTION_MODEL),
        }
        if params.get("language"):
            data_fields["language"] = str(params.get("language"))

        # Multipart upload — bypass the JSON-only HttpRequestConfig by
        # inlining the request here (httpx handles multipart natively).
        import httpx

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{base_url.rstrip('/')}/audio/transcriptions",
                headers={"Authorization": f"Bearer {api_key}"},
                files=files,
                data=data_fields,
            )
            resp.raise_for_status()
            data = resp.json()
        out.extend(
            _emit_one(
                item,
                {
                    "text": str(data.get("text") or ""),
                    "language": data.get("language"),
                },
            )
        )
    return out


async def _op_analyze_image(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[ExecutionItem]:
    params = node.parameters or {}
    bin_prop = str(params.get("binaryPropertyName") or "data")
    out: list[ExecutionItem] = []
    for item in items:
        from app.services.workflows.expression import ExpressionContext, evaluate

        ectx = ExpressionContext(item=item, node_outputs=ctx.node_outputs, now=ctx.now)
        text = evaluate(params.get("text") or params.get("prompt"), ectx)
        text = "" if text is None else str(text)
        model = params.get("model") or DEFAULT_VISION_MODEL
        if isinstance(model, dict):
            model = str(model.get("value") or model.get("name") or DEFAULT_VISION_MODEL)

        image_url = params.get("imageUrl") or params.get("url")
        if image_url and isinstance(image_url, str) and "{" in image_url:
            image_url = str(evaluate(image_url, ectx) or "")
        if not image_url:
            bin_entry = (item.binary or {}).get(bin_prop)
            if bin_entry is not None:
                image_url = (
                    f"data:{bin_entry.mime_type};base64,"
                    + bin_entry.data_b64
                )

        if _has_mock(ctx, "analyzeImage"):
            mock = _mock_for(ctx, "analyzeImage")
            data = mock(text, image_url, item.json) if callable(mock) else mock
            data = data if isinstance(data, dict) else {"analysis": str(data)}
            out.extend(
                _emit_one(
                    item,
                    {
                        "analysis": str(
                            data.get("analysis")
                            or data.get("text")
                            or (data.get("choices") or [{}])[0]
                            .get("message", {})
                            .get("content", "")
                            or ""
                        ),
                        "usage": data.get("usage") or {},
                    },
                )
            )
            continue

        cred = _openai_credential(node, ctx)
        api_key, base_url = _credentials_block(cred)
        if not api_key or not image_url:
            out.extend(
                _emit_one(
                    item,
                    {
                        "analysis": "",
                        "usage": {},
                        "error": "Missing imageUrl/binary or openAiApi credential",
                    },
                )
            )
            continue

        body: dict[str, Any] = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": text or "What's in this image?"},
                        {"type": "image_url", "image_url": {"url": image_url}},
                    ],
                }
            ],
        }
        if params.get("maxTokens") or params.get("max_tokens"):
            try:
                body["max_tokens"] = int(params.get("maxTokens") or params.get("max_tokens"))
            except (TypeError, ValueError):
                pass

        resp = await execute_http_request(
            HttpRequestConfig(
                url=f"{base_url.rstrip('/')}/chat/completions",
                method="POST",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                body=body,
                body_mode="json",
                response_mode="json",
                timeout=120.0,
                retries=node.max_tries or 1,
            ),
            ctx=ctx,
        )
        data = resp.body if isinstance(resp.body, dict) else {}
        content = (
            (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
        )
        out.extend(
            _emit_one(
                item,
                {
                    "analysis": str(content),
                    "usage": data.get("usage") or {},
                },
            )
        )
    return out


# ── Dispatch ──────────────────────────────────────────────────────────


_OPS: dict[str, Any] = {
    "textCompletion": _op_text_completion,
    "imageGeneration": _op_image_generation,
    "transcription": _op_transcription,
    "analyzeImage": _op_analyze_image,
}


async def exec_openai(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: EngineContext,
) -> list[tuple[int, list[ExecutionItem]]]:
    """OpenAI actions node — routes on ``parameters.operation``."""
    params = node.parameters or {}
    operation = str(params.get("operation") or "textCompletion")
    handler = _OPS.get(operation)
    if handler is None:
        raise ValueError(
            f"openAi: unsupported operation {operation!r}; "
            f"expected one of {OPENAI_OPERATIONS}"
        )
    out_items = await handler(node, items, ctx=ctx)
    return [(0, out_items)]


__all__ = [
    "exec_openai",
    "OPENAI_OPERATIONS",
    "DEFAULT_COMPLETION_MODEL",
    "DEFAULT_IMAGE_SIZE",
    "DEFAULT_VISION_MODEL",
    "DEFAULT_TRANSCRIPTION_MODEL",
    "DEFAULT_BASE_URL",
]
