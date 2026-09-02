"""Fail-closed startup checks for the privileged sandbox-agent."""

from __future__ import annotations

from app.config import Settings

NON_DEV_ENVIRONMENTS = frozenset({"production", "staging"})
_DEFAULT_TOKENS = frozenset(
    {
        "change-me",
        "dev-sandbox-token-change-me",
    }
)


def is_non_dev_environment(environment: str | None) -> bool:
    return (environment or "").strip().lower() in NON_DEV_ENVIRONMENTS


def token_is_default(value: str | None) -> bool:
    raw = (value or "").strip()
    if not raw:
        return True
    if raw in _DEFAULT_TOKENS:
        return True
    if "change-me" in raw.lower():
        return True
    return False


def assert_agent_startup(settings: Settings) -> None:
    """Refuse default tokens and mock mode outside development/test.

    sandbox-agent is a privileged control plane, not a public client API.
    """
    if not is_non_dev_environment(getattr(settings, "environment", "development")):
        return
    problems: list[str] = []
    if token_is_default(settings.sandbox_agent_token):
        problems.append("SANDBOX_AGENT_TOKEN is still a default/insecure value")
    if settings.resolve_mock():
        problems.append("SANDBOX_MOCK=true is not allowed outside development/test")
    if problems:
        raise RuntimeError(
            "Refusing to start sandbox-agent outside development/test: "
            + "; ".join(problems)
        )
