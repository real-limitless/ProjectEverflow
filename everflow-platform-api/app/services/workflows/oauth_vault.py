"""OAuth credential vault for workflow nodes.

n8n credential type names like ``googleSheetsOAuth2Api`` or
``slackOAuth2Api`` are not the same as API-key names. The vault here
exposes:

- A canonical registry of supported OAuth providers (Google, Slack, etc.)
  with their OAuth2 endpoints and token refresh logic.
- A small store that maps a workflow's :class:`WorkflowCredential` payload
  onto the engine's :class:`EngineContext.credentials` dict, expanding
  ``accessToken`` from a stored ``refreshToken`` when needed.

This module does not perform the OAuth dance itself — the platform API
hosts the connect/callback routes. The vault's job is the runtime side:
resolve ``{type: name}`` lookups, refresh tokens, and shape the
credentials dict that nodes expect.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.services.workflows.credentials_store import decrypt_payload

logger = logging.getLogger(__name__)


# Map n8n credential type → provider id used internally
N8N_OAUTH_TYPE_TO_PROVIDER: dict[str, str] = {
    "googleSheetsOAuth2Api": "google",
    "googleDriveOAuth2Api": "google",
    "googleDocsOAuth2Api": "google",
    "googleCalendarOAuth2Api": "google",
    "googleSlidesOAuth2Api": "google",
    "googleTasksOAuth2Api": "google",
    "googleContactsOAuth2Api": "google",
    "googleBigQueryOAuth2Api": "google",
    "googleAnalyticsOAuth2Api": "google",
    "googleCloudStorageOAuth2Api": "google",
    "googleAdsOAuth2Api": "google",
    "googleTranslateOAuth2Api": "google",
    "gmailOAuth2": "google",
    "slackOAuth2Api": "slack",
    "microsoftOutlookOAuth2Api": "microsoft",
    "microsoftExcelOAuth2Api": "microsoft",
    "microsoftOneDriveOAuth2Api": "microsoft",
    "microsoftSharePointOAuth2Api": "microsoft",
    "microsoftTeamsOAuth2Api": "microsoft",
    "notionOAuth2Api": "notion",
    "githubOAuth2Api": "github",
    "gitlabOAuth2Api": "gitlab",
    "linearOAuth2Api": "linear",
    "hubspotOAuth2Api": "hubspot",
    "salesforceOAuth2Api": "salesforce",
    "pipedriveOAuth2Api": "pipedrive",
    "zendeskOAuth2Api": "zendesk",
    "typeformOAuth2Api": "typeform",
    "calendlyOAuth2Api": "calendly",
    "asanaOAuth2Api": "asana",
    "trelloOAuth2Api": "trello",
    "clickUpOAuth2Api": "clickup",
    "jiraOAuth2Api": "atlassian",
    "confluenceOAuth2Api": "atlassian",
    "airtableOAuth2Api": "airtable",
    "shopifyOAuth2Api": "shopify",
    "dropboxOAuth2Api": "dropbox",
    "boxOAuth2Api": "box",
    "stripeOAuth2Api": "stripe",
    "quickbooksOAuth2Api": "quickbooks",
    "xeroOAuth2Api": "xero",
    "twitterOAuth2Api": "twitter",
    "linkedInOAuth2Api": "linkedin",
    "facebookGraphOAuth2Api": "facebook",
    "discordOAuth2Api": "discord",
    "telegramOAuth2Api": "telegram",
    "mondayComOAuth2Api": "monday",
    "todoistOAuth2Api": "todoist",
    "supabaseOAuth2Api": "supabase",
    "firebaseAuthOAuth2Api": "google",
}


@dataclass
class OAuthProvider:
    """Configuration for a single OAuth2 provider."""

    id: str
    authorize_url: str
    token_url: str
    scopes: tuple[str, ...] = ()
    # Default port: how this provider's token-refresh JSON is shaped
    extra: dict[str, Any] = field(default_factory=dict)


# Minimal v1 registry. Each provider only needs authorize/token URLs to
# support the connect flow; scopes are best-effort.
PROVIDERS: dict[str, OAuthProvider] = {
    "google": OAuthProvider(
        id="google",
        authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
        token_url="https://oauth2.googleapis.com/token",
        scopes=(
            "https://www.googleapis.com/auth/userinfo.email",
            "openid",
        ),
    ),
    "slack": OAuthProvider(
        id="slack",
        authorize_url="https://slack.com/oauth/authorize",
        token_url="https://slack.com/api/oauth.access",
        scopes=(),
    ),
    "notion": OAuthProvider(
        id="notion",
        authorize_url="https://api.notion.com/v1/oauth/authorize",
        token_url="https://api.notion.com/v1/oauth/token",
    ),
    "github": OAuthProvider(
        id="github",
        authorize_url="https://github.com/login/oauth/authorize",
        token_url="https://github.com/login/oauth/access_token",
    ),
    "linear": OAuthProvider(
        id="linear",
        authorize_url="https://linear.app/oauth/authorize",
        token_url="https://api.linear.app/oauth/token",
    ),
    "hubspot": OAuthProvider(
        id="hubspot",
        authorize_url="https://app.hubspot.com/oauth/authorize",
        token_url="https://api.hubapi.com/oauth/v1/token",
    ),
    "microsoft": OAuthProvider(
        id="microsoft",
        authorize_url="https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        token_url="https://login.microsoftonline.com/common/oauth2/v2.0/token",
    ),
    "airtable": OAuthProvider(
        id="airtable",
        authorize_url="https://airtable.com/oauth2/v1/authorize",
        token_url="https://airtable.com/oauth2/v1/token",
    ),
    "shopify": OAuthProvider(
        id="shopify",
        authorize_url="https://{shop}.myshopify.com/admin/oauth/authorize",
        token_url="https://{shop}.myshopify.com/admin/oauth/access_token",
    ),
}


@dataclass
class OAuthTokenSet:
    access_token: str
    refresh_token: str | None = None
    expires_at: float = 0.0  # unix seconds; 0 means unknown
    scope: str = ""
    token_type: str = "Bearer"
    raw: dict[str, Any] = field(default_factory=dict)

    def is_expired(self, *, skew_seconds: int = 60) -> bool:
        if not self.expires_at:
            return False
        return time.time() >= (self.expires_at - skew_seconds)

    def to_engine_dict(self) -> dict[str, Any]:
        """Shape the dict the engine + node executors expect."""
        refresh = self.refresh_token if self.refresh_token is not None else ""
        return {
            "accessToken": self.access_token,
            "refreshToken": refresh,
            "expiresAt": self.expires_at,
            "scope": self.scope,
            "tokenType": self.token_type,
            **self.raw,
        }


def _payload_str(payload: dict[str, Any], *keys: str) -> str:
    """Return the first non-empty string value among ``keys`` (else empty)."""
    for key in keys:
        value = payload.get(key)
        if value is None:
            continue
        text = value if isinstance(value, str) else str(value)
        if text:
            return text
    return ""


def _normalize_token_payload(payload: dict[str, Any]) -> OAuthTokenSet:
    expires_in = float(payload.get("expires_in") or 0)
    token_type = _payload_str(payload, "token_type")
    return OAuthTokenSet(
        access_token=_payload_str(payload, "access_token"),
        refresh_token=payload.get("refresh_token"),
        expires_at=time.time() + expires_in if expires_in else 0.0,
        scope=_payload_str(payload, "scope"),
        token_type=token_type if token_type else "Bearer",
        raw={
            k: v
            for k, v in payload.items()
            if k not in {"access_token", "refresh_token", "expires_in", "scope", "token_type"}
        },
    )


async def exchange_code(
    provider: OAuthProvider,
    *,
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str,
) -> OAuthTokenSet:
    """Exchange an authorization code for an access + refresh token."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            provider.token_url,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
            },
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()
    return _normalize_token_payload(data)


async def refresh(
    provider: OAuthProvider,
    *,
    client_id: str,
    client_secret: str,
    refresh_token: str,
) -> OAuthTokenSet:
    """Refresh an OAuth2 access token using a refresh token."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            provider.token_url,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": client_id,
                "client_secret": client_secret,
            },
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()
    return _normalize_token_payload(data)


def provider_for_n8n_type(n8n_cred_type: str) -> OAuthProvider | None:
    """Return the OAuthProvider for an n8n-style credential type name."""
    pid = N8N_OAUTH_TYPE_TO_PROVIDER.get(n8n_cred_type)
    if pid is None:
        return None
    return PROVIDERS.get(pid)


# ── Engine-side helper ────────────────────────────────────────────────


async def resolve_engine_credentials(
    *,
    stored: dict[str, dict[str, Any]],
    client_secrets: dict[str, dict[str, str]] | None = None,
    refresh_now: bool = False,
) -> dict[str, dict[str, Any]]:
    """Expand the engine's ``credentials`` dict, refreshing expiring tokens.

    Parameters
    ----------
    stored:
        Mapping of ``{name: {credential_type, payload (decrypted)}}`` as
        loaded by the platform API. Each payload may already be a token set
        (``accessToken`` / ``refreshToken`` / ``expiresAt``) or a pre-
        decrypted dict.
    client_secrets:
        Optional per-provider ``{provider_id: {client_id, client_secret}}``
        to enable token refresh. Missing providers fall back to the
        access token as-is.
    refresh_now:
        If True, force a refresh even when the token is not yet expired
        (used in tests).
    """
    client_secrets = client_secrets or {}
    expanded: dict[str, dict[str, Any]] = {}
    for name, cred in stored.items():
        if not isinstance(cred, dict):
            continue
        ctype = str(cred.get("credential_type") or cred.get("type") or "")
        provider = provider_for_n8n_type(ctype)
        # Plain API-key credentials pass through as-is
        if provider is None:
            expanded[name] = dict(cred)
            continue
        payload = cred.get("payload")
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except (ValueError, TypeError):
                payload = {}
        if not isinstance(payload, dict):
            payload = {}
        token_type = _payload_str(payload, "tokenType", "token_type")
        tok = OAuthTokenSet(
            access_token=_payload_str(payload, "accessToken", "access_token"),
            refresh_token=payload.get("refreshToken") or payload.get("refresh_token"),
            expires_at=float(payload.get("expiresAt") or 0),
            scope=_payload_str(payload, "scope"),
            token_type=token_type if token_type else "Bearer",
            raw=payload,
        )
        if not tok.access_token:
            expanded[name] = dict(cred)
            continue
        if (refresh_now or tok.is_expired()) and tok.refresh_token:
            sec = client_secrets.get(provider.id)
            if sec and sec.get("client_id") and sec.get("client_secret"):
                try:
                    refreshed = await refresh(
                        provider,
                        client_id=sec["client_id"],
                        client_secret=sec["client_secret"],
                        refresh_token=tok.refresh_token,
                    )
                    tok = refreshed
                except Exception as exc:
                    logger.warning(
                        "OAuth refresh failed for %s/%s: %s", ctype, name, exc
                    )
        expanded[name] = {**cred, "payload": tok.to_engine_dict()}
    return expanded


__all__ = [
    "N8N_OAUTH_TYPE_TO_PROVIDER",
    "OAuthProvider",
    "PROVIDERS",
    "OAuthTokenSet",
    "exchange_code",
    "refresh",
    "provider_for_n8n_type",
    "resolve_engine_credentials",
]
