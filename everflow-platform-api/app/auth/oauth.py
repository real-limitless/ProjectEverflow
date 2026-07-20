"""OAuth clients for GitHub and Google (enabled only when credentials are set)."""

from httpx_oauth.clients.github import GitHubOAuth2
from httpx_oauth.clients.google import GoogleOAuth2

from app.config import Settings, get_settings


def build_github_client(settings: Settings | None = None) -> GitHubOAuth2 | None:
    settings = settings or get_settings()
    if not settings.github_oauth_enabled:
        return None
    return GitHubOAuth2(settings.github_client_id, settings.github_client_secret)


def build_google_client(settings: Settings | None = None) -> GoogleOAuth2 | None:
    settings = settings or get_settings()
    if not settings.google_oauth_enabled:
        return None
    return GoogleOAuth2(settings.google_client_id, settings.google_client_secret)
