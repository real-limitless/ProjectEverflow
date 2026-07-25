"""Unit tests for marketplace catalog + pack builders (no sandbox)."""

from __future__ import annotations

import pytest

from app.services.marketplace import (
    MarketplaceError,
    build_install_pack,
    build_uninstall_pack,
    catalog_summary,
    find_item,
    get_item_content,
    is_allowed_content_url,
    load_catalog,
    public_item_fields,
    read_bundled_skill,
)


def test_catalog_loads_ecc_and_curated() -> None:
    catalog = load_catalog()
    summary = catalog_summary()
    assert summary["counts"]["skills"] >= 200
    assert summary["counts"]["commands"] >= 50
    assert summary["counts"]["mcps"] >= 10
    assert summary["counts"]["plugins"] >= 3
    assert summary["counts"]["tools"] >= 1
    plugin_ids = {p["id"] for p in catalog["plugins"]}
    assert "graphify" in plugin_ids
    assert "oh-my-opencode" in plugin_ids
    assert "headroom" in plugin_ids


def test_find_item_skill() -> None:
    item = find_item("skill", "api-design")
    assert item["kind"] == "skill"
    assert "contentUrl" in item
    assert is_allowed_content_url(item["contentUrl"])


def test_find_item_missing() -> None:
    with pytest.raises(MarketplaceError) as exc:
        find_item("skill", "does-not-exist-xyz")
    assert exc.value.status_code == 404


def test_content_url_allowlist() -> None:
    assert is_allowed_content_url(
        "https://raw.githubusercontent.com/affaan-m/ECC/main/skills/api-design/SKILL.md"
    )
    assert is_allowed_content_url(
        "https://raw.githubusercontent.com/Graphify-Labs/graphify/main/.claude/skills/graphify/SKILL.md"
    )
    assert not is_allowed_content_url("https://evil.example.com/SKILL.md")
    assert not is_allowed_content_url("http://raw.githubusercontent.com/affaan-m/ECC/main/x")


def test_uninstall_plugin_pack() -> None:
    pack = build_uninstall_pack("plugin", "oh-my-opencode")
    assert "oh-my-opencode" in pack["remove_plugins"]
    assert {"kind": "plugin", "id": "oh-my-opencode"} in pack["remove_marketplace_items"]


def test_uninstall_mcp_clears_key() -> None:
    item = find_item("mcp", list(load_catalog()["mcps"])[0]["id"])
    pack = build_uninstall_pack("mcp", item["id"], item)
    assert pack["mcp"][item["id"]] is None


def test_bundled_graphify_skill() -> None:
    text = read_bundled_skill("graphify/SKILL.md")
    assert "graphify" in text.lower()
    assert text.startswith("---")


def test_everflow_platform_skills_in_catalog() -> None:
    catalog = load_catalog()
    skill_ids = {s["id"] for s in catalog["skills"]}
    for sid in ("everflow-knowledge", "everflow-jobs", "everflow-browser"):
        assert sid in skill_ids
        item = find_item("skill", sid)
        assert item["origin"] == "everflow"
        assert item.get("contentFile")


@pytest.mark.asyncio
async def test_install_pack_everflow_knowledge_bundled() -> None:
    pack = await build_install_pack("skill", "everflow-knowledge")
    assert pack["skills"][0]["id"] == "everflow-knowledge"
    assert "knowledge_search" in pack["skills"][0]["content"]
    assert pack["skills"][0]["content"].startswith("---")


@pytest.mark.asyncio
async def test_install_pack_oh_my_opencode() -> None:
    pack = await build_install_pack("plugin", "oh-my-opencode")
    assert pack["plugin"] == ["oh-my-opencode"]
    assert any(i["id"] == "oh-my-opencode" for i in pack["marketplace_items"])


@pytest.mark.asyncio
async def test_install_pack_graphify_bundled() -> None:
    pack = await build_install_pack("plugin", "graphify")
    assert "graphify" in pack["mcp"]
    assert pack["skills"][0]["id"] == "graphify"
    assert "content" in pack["skills"][0]
    assert "graphify" in pack["skills"][0]["content"].lower()


@pytest.mark.asyncio
async def test_install_pack_playwright_browser() -> None:
    pack = await build_install_pack("mcp", "playwright")
    assert "playwright" in pack["mcp"]
    cfg = pack["mcp"]["playwright"]
    assert cfg["command"] == ["everflow-playwright-mcp"]
    assert cfg["environment"]["PLAYWRIGHT_BROWSERS_PATH"] == "/opt/everflow-browsers"
    assert any(i["id"] == "playwright" for i in pack["marketplace_items"])
    item = find_item("mcp", "playwright")
    assert item["origin"] == "everflow"
    assert "browser" in item.get("tags", [])


def test_public_item_fields() -> None:
    item = find_item("skill", "everflow-knowledge")
    pub = public_item_fields(item)
    assert pub["id"] == "everflow-knowledge"
    assert pub["kind"] == "skill"
    assert "description" in pub
    assert "contentFile" in pub


@pytest.mark.asyncio
async def test_get_item_content_bundled_skill() -> None:
    body = await get_item_content("skill", "everflow-knowledge")
    assert body["kind"] == "skill"
    assert body["id"] == "everflow-knowledge"
    assert body["content_type"] == "text/markdown"
    assert "knowledge" in body["content"].lower()
    assert body["content"].startswith("---")


@pytest.mark.asyncio
async def test_get_item_content_rejects_plugin() -> None:
    with pytest.raises(MarketplaceError) as exc:
        await get_item_content("plugin", "graphify")
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_get_item_content_missing() -> None:
    with pytest.raises(MarketplaceError) as exc:
        await get_item_content("skill", "does-not-exist-xyz")
    assert exc.value.status_code == 404
