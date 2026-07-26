"""Vision OCR for Knowledge Reader: screenshot → Markdown via provider chat APIs."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.services.providers import (
    decrypt_row,
    list_credentials,
    scopes_from_str,
)
from app.services.web_read import WebReadError

logger = logging.getLogger(__name__)

_OCR_SYSTEM = (
    "You transcribe web page screenshots into clean Markdown for a research reader. "
    "Preserve headings, lists, and links when visible. Omit ads, nav chrome, and cookie banners. "
    "Return only Markdown — no preamble."
)

_PROVIDER_ENDPOINTS: dict[str, tuple[str, str]] = {
    # provider -> (base chat completions URL, default vision model)
    "openrouter": ("https://openrouter.ai/api/v1/chat/completions", "openai/gpt-4o-mini"),
    "openai": ("https://api.openai.com/v1/chat/completions", "gpt-4o-mini"),
}


def _credential_has_ocr(scopes_raw: str | None) -> bool:
    scopes = scopes_from_str(scopes_raw)
    return "*" in scopes or "ocr" in scopes or "chat" in scopes


async def _pick_ocr_credential(
    session: AsyncSession,
    *,
    project_id: UUID,
    user_id: UUID,
) -> tuple[str, Any] | None:
    """Prefer project credentials, then user. OpenAI-compatible providers first."""
    order = ("openrouter", "openai")
    for owner_type, owner_id in (("project", project_id), ("user", user_id)):
        rows = await list_credentials(session, owner_type=owner_type, owner_id=owner_id)
        by_provider = {r.provider: r for r in rows}
        for provider in order:
            row = by_provider.get(provider)
            if row is None:
                continue
            if not _credential_has_ocr(row.scopes):
                continue
            return provider, row
    return None


async def ocr_screenshot_to_markdown(
    session: AsyncSession,
    *,
    project_id: UUID,
    user_id: UUID,
    settings: Settings,
    image_b64: str,
    page_url: str,
    title: str = "",
    max_pages: int = 3,
) -> str:
    """Send a PNG/JPEG base64 screenshot to a vision-capable chat model."""
    raw = (image_b64 or "").strip()
    if raw.startswith("data:"):
        # data:image/png;base64,....
        if "," in raw:
            raw = raw.split(",", 1)[1]
    if not raw or len(raw) < 32:
        raise WebReadError("No screenshot available for OCR", status_code=422)

    picked = await _pick_ocr_credential(session, project_id=project_id, user_id=user_id)
    if picked is None:
        raise WebReadError(
            "No OCR-capable provider key found. Add an OpenAI or OpenRouter key "
            "with chat/ocr scope in project or user settings.",
            status_code=503,
        )
    provider, row = picked
    try:
        api_key = decrypt_row(row, settings)
    except ValueError as exc:
        raise WebReadError("Could not decrypt provider key for OCR", status_code=500) from exc

    endpoint, model = _PROVIDER_ENDPOINTS[provider]
    user_prompt = (
        f"Transcribe this web page screenshot to Markdown.\n"
        f"URL: {page_url}\n"
        f"Title hint: {title or '(unknown)'}\n"
        f"(max_pages hint: {max_pages})"
    )
    # OpenAI-compatible image message
    body: dict[str, Any] = {
        "model": model,
        "temperature": 0.1,
        "max_tokens": 4096,
        "messages": [
            {"role": "system", "content": _OCR_SYSTEM},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{raw}"},
                    },
                ],
            },
        ],
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if provider == "openrouter":
        headers["HTTP-Referer"] = settings.frontend_url or "https://everflow.local"
        headers["X-Title"] = "Everflow Knowledge Reader OCR"

    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            resp = await client.post(endpoint, headers=headers, json=body)
    except httpx.RequestError as exc:
        raise WebReadError(f"OCR provider unreachable: {exc}", status_code=502) from exc

    if resp.status_code >= 400:
        detail = resp.text[:300]
        raise WebReadError(
            f"OCR provider returned HTTP {resp.status_code}: {detail}",
            status_code=502,
        )

    try:
        payload = resp.json()
    except ValueError as exc:
        raise WebReadError("OCR provider returned invalid JSON", status_code=502) from exc

    choices = payload.get("choices") if isinstance(payload, dict) else None
    if not isinstance(choices, list) or not choices:
        raise WebReadError("OCR provider returned no choices", status_code=502)
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, list):
        # Some providers return content parts
        parts = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                parts.append(str(part.get("text") or ""))
            elif isinstance(part, str):
                parts.append(part)
        content = "\n".join(parts)
    if not isinstance(content, str) or not content.strip():
        raise WebReadError("OCR provider returned empty content", status_code=502)
    return content.strip()[:200_000]
