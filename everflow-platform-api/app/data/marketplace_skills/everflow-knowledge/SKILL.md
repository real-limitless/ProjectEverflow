---
name: everflow-knowledge
description: >-
  Retrieve and manage Project Everflow Knowledge canvases (docs, secrets, runbooks).
  Use when the user asks about project docs, passwords, API keys, tokens, config,
  "knowledge key", or when you need project-specific facts not in the workspace.
compatibility: opencode
---

# Everflow Knowledge

Project documentation and secrets live in **Knowledge canvases** on the Everflow platform
(indexed vector store). They are **not** MCP resources.

## When to use

- Questions about project docs, runbooks, passwords, keys, tokens, credentials
- User mentions a "knowledge key" or canvas name
- You need facts that are not in the workspace files

## Procedure

1. Call **`knowledge_search(query)`** with a short natural-language query.
2. If hits: quote chunk text and cite `canvas_name` (and canvas id when useful).
3. If empty: `list_canvases` → `get_canvas(canvas_id)` for likely docs.
4. To add/update docs: `create_canvas` / `update_canvas`, then **`reindex_canvas`** so search refreshes.
5. Do not claim knowledge is empty solely because MCP resources is empty.

## Tools (everflow MCP)

- `knowledge_search`, `list_canvases`, `get_canvas`
- `create_canvas`, `update_canvas`, `delete_canvas`, `reindex_canvas`
