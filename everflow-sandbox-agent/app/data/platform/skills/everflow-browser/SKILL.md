---
name: everflow-browser
description: >-
  Control Everflow browser automation: Playwright MCP (navigate/click/snapshot)
  plus headed vs headless mode for the project Desktop panel.
compatibility: opencode
---

# Everflow Browser

Full page automation comes from the **Playwright MCP** (marketplace: **Browser (Playwright)**).
Everflow MCP only switches mode and reports status.

## When to use

- Surf or test a web UI from the agent
- User wants to **watch** the browser (headed / Desktop)
- Check whether Playwright is installed and ready

## Procedure

1. **`browser_status`** — enabled? mode (`headless`|`headed`)? Desktop listening?
2. If Playwright MCP is missing: tell the user to install **Browser (Playwright)** from Marketplace.
3. Automation: use Playwright tools (often named `playwright_*`) for navigate / click / type / snapshot.
4. **Headed (visible):** `browser_set_mode(mode="headed")` — uses project Desktop / noVNC.
5. **Headless (default):** `browser_set_mode(mode="headless")`.
6. Mode switches may **restart OpenCode** so Playwright respawns — warn the user briefly.

## Tools

- Everflow MCP: `browser_status`, `browser_set_mode`
- Playwright MCP: navigate, click, fill, snapshot, etc. (after install)
