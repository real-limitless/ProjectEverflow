# everflow-mcp

Stdio MCP server that lets **OpenCode** (and the Everflow Chat tab) create and manage Project Everflow resources:

- Knowledge canvases
- Project agent definitions
- Project / identity context

## Environment

| Variable | Required | Description |
|----------|----------|-------------|
| `EVERFLOW_API_URL` | yes | Platform API base (guest: tunnel `http://127.0.0.1:18765`; host: `http://localhost:8000`) |
| `EVERFLOW_TOKEN` | yes | Sandbox access token (`ef_sbox_…`) |
| `EVERFLOW_PROJECT_ID` | yes | Bound project UUID |

## Run

```bash
cd everflow-mcp
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
export EVERFLOW_API_URL=http://localhost:8000
export EVERFLOW_TOKEN=ef_sbox_…
export EVERFLOW_PROJECT_ID=…
everflow-mcp
```

OpenCode registers this as a local MCP (see sandbox-agent OpenCode ensure bootstrap).
Hosts that prefix tools with the server name expose them as `everflow_<tool>` (e.g. `everflow_list_projects`).

## Tools

- `whoami`
- `get_project`
- `list_projects` (bound project only in v1 — returns the active project)
- `list_canvases` / `get_canvas` / `create_canvas` / `update_canvas` / `delete_canvas`
- `list_agents` / `get_agent` / `create_agent` / `update_agent` / `delete_agent`
