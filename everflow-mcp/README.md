# everflow-mcp

Stdio MCP server that lets **OpenCode** (and the Everflow Chat tab) create and manage Project Everflow resources:

- Knowledge canvases
- Project agent definitions
- Project / identity context

## Environment

| Variable | Required | Description |
|----------|----------|-------------|
| `EVERFLOW_API_URL` | yes | Platform API base (e.g. `http://backend:8000` or `http://localhost:8000`) |
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

## Tools

- `everflow_whoami`
- `everflow_get_project`
- `everflow_list_projects` (bound project only in v1 — returns the active project)
- `everflow_list_canvases` / `everflow_get_canvas` / `everflow_create_canvas` / `everflow_update_canvas` / `everflow_delete_canvas`
- `everflow_list_agents` / `everflow_get_agent` / `everflow_create_agent` / `everflow_update_agent` / `everflow_delete_agent`
