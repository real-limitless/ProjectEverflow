"""Unit tests for knowledge repo path matching and indexing walk."""

from __future__ import annotations

import pytest

from app.services.knowledge_repo import (
    DEFAULT_GLOBS,
    collect_doc_paths,
    matches_doc_path,
)


@pytest.mark.parametrize(
    "path,expected",
    [
        ("README.md", True),
        ("readme", True),
        ("docs/guide.md", True),
        ("src/docs/a.md", True),
        ("ADR/0001-record.md", True),
        ("adr/decision.md", True),
        ("openapi.yaml", True),
        ("api/openapi.json", True),
        ("runbooks/deploy.md", True),
        ("docs/runbook-prod.md", True),
        ("AGENTS.md", True),
        ("CLAUDE.md", True),
        (".github/PULL_REQUEST_TEMPLATE.md", True),
        ("package.json", False),
        ("src/app.ts", False),
        ("node_modules/pkg/README.md", True),  # basename README still matches
        ("dist/README.md", True),
        ("", False),
    ],
)
def test_matches_doc_path(path: str, expected: bool) -> None:
    assert matches_doc_path(path, DEFAULT_GLOBS) is expected


def test_custom_glob() -> None:
    assert matches_doc_path("notes/foo.txt", ["**/notes/**/*.txt"]) is True
    assert matches_doc_path("notes/foo.md", ["**/notes/**/*.txt"]) is False


class _FakeAgent:
    def __init__(self, tree: dict[str, list[dict]]) -> None:
        # path -> list of fs entries
        self.tree = tree

    async def list_fs(self, name: str, path: str = ".") -> list[dict]:
        key = path if path not in (".", "") else "."
        if key not in self.tree:
            raise Exception(f"missing {key}")
        return self.tree[key]

    async def read_fs(self, name: str, path: str) -> str:
        return f"# {path}\n"


@pytest.mark.asyncio
async def test_collect_doc_paths_nested() -> None:
    agent = _FakeAgent(
        {
            ".": [
                {"path": "README.md", "name": "README.md", "is_dir": False},
                {"path": "src", "name": "src", "is_dir": True},
                {"path": "docs", "name": "docs", "is_dir": True},
                {"path": "node_modules", "name": "node_modules", "is_dir": True},
            ],
            "src": [
                {"path": "src/app.ts", "name": "app.ts", "is_dir": False},
            ],
            "docs": [
                {"path": "docs/guide.md", "name": "guide.md", "is_dir": False},
                {"path": "docs/deep", "name": "deep", "is_dir": True},
            ],
            "docs/deep": [
                {"path": "docs/deep/more.md", "name": "more.md", "is_dir": False},
            ],
            "node_modules": [
                {"path": "node_modules/x", "name": "x", "is_dir": True},
            ],
        }
    )
    paths = await collect_doc_paths(agent, "sb-1")
    assert "README.md" in paths
    assert "docs/guide.md" in paths
    assert "docs/deep/more.md" in paths
    assert "src/app.ts" not in paths
