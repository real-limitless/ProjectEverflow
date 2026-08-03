# everflow-mcp

Stdio MCP server that lets **OpenCode** (and the Everflow Chat tab) create and manage Project Everflow resources:

- Knowledge canvases and retrieval
- Project agent definitions
- Test suites / cases
- Registered HTTP tools
- Background jobs (detached sandbox processes — e.g. spin up a dev server)
- Project / identity context

## Where it runs

**In the project microVM guest** (wired by sandbox-agent / OpenCode bootstrap), not as a host product service.

The Everflow control plane itself runs only under **Docker Compose or Podman Compose** (`./scripts/everflow`). This package is installed into guest images / harness packs; it is not a Compose service you start on the host for operators.

## Environment

| Variable | Required | Description |
|----------|----------|-------------|
| `EVERFLOW_API_URL` | yes | Platform API base (guest: tunnel `http://127.0.0.1:18765`) |
| `EVERFLOW_TOKEN` | yes | Sandbox access token (`ef_sbox_…`) |
| `EVERFLOW_PROJECT_ID` | yes | Bound project UUID |

## Unit tests / local packaging (not a product host service)

```bash
cd everflow-mcp
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
pytest
# optional stdio smoke (incomplete; needs a running Compose API + token):
# export EVERFLOW_API_URL=http://localhost:8000
# export EVERFLOW_TOKEN=ef_sbox_…
# export EVERFLOW_PROJECT_ID=…
# everflow-mcp
```

OpenCode registers this as a local MCP inside the sandbox (see sandbox-agent OpenCode ensure bootstrap).
Hosts that prefix tools with the server name expose them as `everflow_<tool>` (e.g. `everflow_list_projects`).

## Tools

### Context

- `whoami`
- `get_project`
- `list_projects` (bound project only in v1 — returns the active project)

### Knowledge

- `list_canvases` / `get_canvas` / `create_canvas` / `update_canvas` / `delete_canvas`
- `reindex_canvas` / **`knowledge_search`** (vector + lexical retrieve over indexed canvases)

**Important:** Knowledge is **not** MCP resources. OpenCode must call **`knowledge_search`**
(or Chat auto-injects retrieve hits into the prompt). Index a canvas in the Knowledge panel
first (`status=indexed`, chunk count &gt; 0). Empty MCP resources does **not** mean the store is empty.

### Agents (studio Agents panel — not OpenCode modes)

- `list_agents` / `get_agent` / `create_agent` / `update_agent` / `delete_agent`

### Tests

- `list_test_suites` / `create_test_suite`
- `create_test_case` / `update_test_case` / `delete_test_case`
- `run_test_suite`

### HTTP tools

- `list_http_tools` / `call_http_tool`

### Background jobs

Detached long-lived processes in the project sandbox (Jobs panel). Prefer these to spin up websites or dev servers instead of a blocking shell.

- `list_jobs`
- `create_job` — `title`, `command`, optional `cwd` (e.g. `npm run dev`)
- `get_job_logs` — tail stdout/stderr
- `update_job` — title/command/cwd when stopped
- `start_job` / `stop_job` / `kill_job` / `restart_job`
- `delete_job`

Requires a **running** sandbox. Sandbox tokens need the `jobs:rw` scope (included in default mint scopes).

### Browser (Playwright harness control)

Full navigate / click / snapshot tools come from the **Playwright MCP** (marketplace: **Browser (Playwright)**). Everflow MCP only controls mode and status:

- `browser_status` — enabled?, mode (`headless`|`headed`), Desktop listening, prebaked Chromium
- `browser_set_mode` — `mode=headless|headed` (headed uses the project Desktop / noVNC panel)

Default is **headless**. Install the marketplace MCP first so OpenCode loads `@playwright/mcp` via `everflow-playwright-mcp`.

## How the guest gets this package

OpenCode runs `python3 -m everflow_mcp` **inside the project microVM**. On each OpenCode ensure, the sandbox-agent:

1. Fingerprints agent-bundled sources at `/opt/everflow-mcp` (compose.dev bind-mounts `./everflow-mcp` there).
2. Compares to workspace stamp `.everflow/mcp.package.sha`.
3. If missing or stale, copies sources and `pip install --force-reinstall` into the guest, then restarts OpenCode so new tools load.

If tools look outdated after a code upgrade: recreate the sandbox-agent container (to pick up the mount / image), open Chat once (triggers ensure), or force-restart OpenCode for the project.
