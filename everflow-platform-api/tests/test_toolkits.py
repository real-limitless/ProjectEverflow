"""Toolkit catalog helpers."""

from pathlib import Path

from app.config import Settings
from app.services.toolkits import (
    inject_toolkit_repo,
    resolve_template_meta,
    toolkit_local_dir,
    toolkit_repo_url,
)


def test_resolve_mobile_templates_share_expo_toolkit() -> None:
    ios = resolve_template_meta("mobile-ios")
    android = resolve_template_meta("mobile-android")
    assert ios["toolkit_id"] == "mobile-expo"
    assert android["toolkit_id"] == "mobile-expo"
    assert ios["preview_device"] == "iphone-12"
    assert android["preview_device"] == "pixel-7"


def test_inject_toolkit_repo_when_configured() -> None:
    settings = Settings(
        toolkit_repo_base="https://github.com/example/everflow-toolkit-{id}.git",
    )
    repos = inject_toolkit_repo(
        [{"id": "mobile", "label": "app/mobile", "url": "", "branch": "main"}],
        template_id="mobile-ios",
        settings=settings,
        project_slug="demo",
    )
    assert repos[0]["url"] == "https://github.com/example/everflow-toolkit-mobile-expo.git"
    assert repos[0]["clone_status"] == "pending"


def test_inject_skips_when_user_url_present() -> None:
    settings = Settings(
        toolkit_repo_base="https://github.com/example/everflow-toolkit-{id}.git",
    )
    repos = inject_toolkit_repo(
        [
            {
                "id": "mobile",
                "label": "app/mobile",
                "url": "https://github.com/acme/my-app.git",
                "branch": "main",
            }
        ],
        template_id="mobile-ios",
        settings=settings,
        project_slug="demo",
    )
    assert repos[0]["url"] == "https://github.com/acme/my-app.git"


def test_toolkit_local_dir_resolves(tmp_path: Path) -> None:
    toolkit = tmp_path / "mobile-expo"
    toolkit.mkdir()
    (toolkit / "README.md").write_text("hi", encoding="utf-8")
    settings = Settings(toolkit_local_root=str(tmp_path))
    assert toolkit_local_dir(settings, "mobile-expo") == toolkit.resolve()
    assert toolkit_repo_url(settings, "mobile-expo") is None
