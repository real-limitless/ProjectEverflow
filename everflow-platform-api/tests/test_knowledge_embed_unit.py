"""Unit tests for markdown chunking and local embeddings."""

from app.services.knowledge_embed import chunk_markdown, cosine, local_embed


def test_chunk_markdown_by_heading() -> None:
    md = "# One\n\nAlpha.\n\n## Two\n\nBeta.\n"
    parts = chunk_markdown(md)
    assert len(parts) >= 2
    assert any("Alpha" in t for t, _ in parts)
    assert any("Beta" in t for t, _ in parts)


def test_local_embed_normalized_and_similar() -> None:
    a = local_embed("knowledge canvas retrieval embeddings")
    b = local_embed("knowledge canvas retrieval embeddings")
    c = local_embed("totally unrelated cooking recipes")
    assert abs(sum(x * x for x in a) - 1.0) < 1e-6
    assert cosine(a, b) > 0.99
    assert cosine(a, c) < cosine(a, b)


def test_empty_markdown() -> None:
    assert chunk_markdown("") == []
    assert chunk_markdown("   ") == []
