"""Unit tests for repo clone path resolution (no agent required)."""

from app.services.repo_clone import (
    is_cloneable_url,
    path_hint_from_label,
    path_hint_from_url,
    resolve_clone_destinations,
    repos_to_storage,
    sanitize_local_path,
)


def test_path_hint_from_url() -> None:
    assert path_hint_from_url("https://github.com/org/app.git") == "app"
    assert path_hint_from_url("https://github.com/org/my-app") == "my-app"
    assert path_hint_from_url("git@github.com:org/tooling.git") == "tooling"
    assert path_hint_from_url("") == ""
    assert path_hint_from_url(None) == ""


def test_path_hint_from_label() -> None:
    assert path_hint_from_label("org/web") == "web"
    assert path_hint_from_label("web") == "web"


def test_sanitize_local_path() -> None:
    assert sanitize_local_path(None) == "."
    assert sanitize_local_path(".") == "."
    assert sanitize_local_path("web") == "web"
    assert sanitize_local_path("../etc") == "."
    assert sanitize_local_path("/abs") == "."


def test_is_cloneable_url() -> None:
    assert is_cloneable_url("https://github.com/a/b.git")
    assert is_cloneable_url("git@github.com:a/b.git")
    assert not is_cloneable_url("")
    assert not is_cloneable_url("not-a-url")


def test_resolve_single_repo_to_named_dir() -> None:
    """Every remote gets its own directory — never workspace root."""
    repos = [
        {
            "id": "r1",
            "label": "app",
            "url": "https://github.com/org/app.git",
            "branch": "main",
        }
    ]
    out = resolve_clone_destinations(repos)
    assert len(out) == 1
    assert out[0]["dest"] == "app"
    assert out[0]["local_path"] == "app"
    assert out[0]["dest"] != "."


def test_resolve_multi_repo_to_basenames() -> None:
    repos = [
        {
            "id": "a",
            "label": "frontend",
            "url": "https://github.com/org/frontend.git",
        },
        {
            "id": "b",
            "label": "backend",
            "url": "https://github.com/org/backend.git",
        },
    ]
    out = resolve_clone_destinations(repos)
    dests = {r["id"]: r["dest"] for r in out}
    assert dests["a"] == "frontend"
    assert dests["b"] == "backend"


def test_repos_to_storage() -> None:
    stored = repos_to_storage(
        [
            {
                "id": "r1",
                "label": "app",
                "url": "https://github.com/o/a.git",
                "branch": "dev",
                "active": True,
            }
        ]
    )
    assert stored[0]["clone_status"] == "pending"
    assert stored[0]["branch"] == "dev"
    assert stored[0]["url"] == "https://github.com/o/a.git"
    assert stored[0]["local_path"] == "a"  # basename from URL, never "."


def test_resolve_ignores_dot_local_path() -> None:
    repos = [
        {
            "id": "r1",
            "label": "app",
            "url": "https://github.com/org/my-app.git",
            "local_path": ".",
        }
    ]
    out = resolve_clone_destinations(repos)
    assert out[0]["dest"] == "my-app"


def test_clone_one_always_uses_named_subdir() -> None:
    """Remotes clone into /workspace/<name>/, never workspace root."""
    import inspect
    from app.services import repo_clone as rc

    src = inspect.getsource(rc.clone_one)
    assert "cd /workspace" in src
    assert "git clone" in src
    # Must not merge into workspace root
    assert "cp -a" not in src


def test_exit_code_zero_is_success() -> None:
    """Regression: `exit_code or 1` treats 0 as failure because 0 is falsy."""
    from app.services.repo_clone import _exit_code

    assert _exit_code({"exit_code": 0}) == 0
    assert _exit_code({"exit_code": 1}) == 1
    assert _exit_code({"exit_code": None}) == 1
    assert _exit_code({}) == 1
    assert _exit_code(None) == 1
