# n8n-compatible Workflows (Everflow native engine)

Everflow runs a **native** workflow engine that imports real n8n JSON and executes the node subset needed for flows like **Stock Agent Emailer**.

## API

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/projects/{id}/workflows` | List |
| `POST` | `/api/v1/projects/{id}/workflows/import` | Import n8n export JSON |
| `GET` | `/api/v1/projects/{id}/workflows/{wf}` | Full graph + document |
| `PATCH` | `/api/v1/projects/{id}/workflows/{wf}` | Update name/active/document |
| `DELETE` | `/api/v1/projects/{id}/workflows/{wf}` | Delete |
| `GET` | `/api/v1/projects/{id}/workflows/{wf}/export` | Round-trip n8n JSON |
| `POST` | `/api/v1/projects/{id}/workflows/{wf}/execute` | Run |
| `GET` | `/api/v1/projects/{id}/workflows/{wf}/runs` | History |
| `POST` | `/api/v1/projects/{id}/workflow-credentials` | Store encrypted secrets |

### Execute body

```json
{
  "trigger": "manual",
  "mocks": {
    "ftp_files": { "/path/file.csv": "csv,text,here\n" },
    "capture_email": true,
    "agent_output": "# Markdown research report"
  },
  "credentials": {
    "openAiApi": { "apiKey": "sk-...", "baseUrl": "https://api.openai.com/v1" },
    "ftp": { "host": "...", "user": "...", "password": "..." },
    "smtp": { "host": "...", "port": 587, "user": "...", "password": "..." }
  }
}
```

- **`mocks`**: dry-run without real FTP/SMTP/LLM (used in tests and demos).
- **`credentials`**: one-shot secrets for this run (not stored). Prefer `workflow-credentials` for persistence.

## Supported node types (Stock Agent Emailer)

Triggers, FTP, Filter, If, Set, Code (JS), Aggregate, Split Out, Split In Batches, Extract/Convert File, Data Table, Email Send, OpenAI Chat Model, Agent, MCP Client Tool.

Connection types: `main`, `ai_languageModel`, `ai_tool`.

## Acceptance fixture

`everflow-platform-api/tests/fixtures/workflows/stock_agent_emailer.json`

```bash
cd everflow-platform-api
uv run pytest tests/test_workflows_engine.py tests/test_workflows_execute_api.py -q
```

## UI

**Workflows** panel:

1. **Library** tab — list all project workflows; **New** blank canvas or **Import n8n**
2. **Open** a row → **Canvas** (React Flow, AI edges, palette)
3. **Data tables** tab — list/create/delete project tables; preview rows after runs
4. **Credentials** tab — add `openAiApi` / `ftp` / `smtp` / RapidAPI headers / MCP payloads
5. Bind wizard after import (or **Bind to workflow**)
6. **Dry run** checkbox (default on) vs live Run
7. Trigger picker: Manual / Schedule / Execute Workflow
8. **Active** switch arms the in-process schedule (UTC hour from `scheduleTrigger`)
9. **Export** downloads n8n JSON; canvas edits debounce-save via PATCH
10. Live run: background execute + poll; canvas highlights steps; **Cancel** supported

API projects call the real engine; seed/demo projects keep a local preview walk.

### Data tables API

```
GET    /projects/{id}/workflow-data-tables
POST   /projects/{id}/workflow-data-tables          { "name": "temp_table", "columns": [] }
GET    /projects/{id}/workflow-data-tables/{tid}
DELETE /projects/{id}/workflow-data-tables/{tid}
POST   /projects/{id}/workflow-data-tables/{tid}/rows  { "data": { ... } }
```

Tables are hydrated into the engine at run start and flushed back when the run finishes (create/insert/delete ops from n8n Data Table nodes persist).

## Live credentials runbook

1. Create project (API-backed), open Workflows.
2. Import `stock_agent_emailer.json` (or your export).
3. Credentials tab — create secrets (names should match n8n credential names when possible):
   - `ftp`: `{ "host", "port", "user", "password" }`
   - `smtp`: `{ "host", "port", "user", "password", "fromEmail" }`
   - `openAiApi`: `{ "apiKey", "baseUrl?" }`
   - `httpMultipleHeadersAuth`: `{ "headers": { "X-RapidAPI-Key", "X-RapidAPI-Host" } }`
4. Bind wizard → map each n8n name to a secret.
5. Uncheck **Dry run** → **Run** (Manual).
6. Optional: enable **Active** so schedule fires at `triggerAtHour` (UTC) each day.

## Scheduler notes

- In-process only (`WORKFLOWS_SCHEDULER_ENABLED`, default true except `ENVIRONMENT=test`).
- Interval: `WORKFLOWS_SCHEDULER_INTERVAL_SECONDS` (default 60).
- Multi-replica: enable on a single leader process only.
- Redis/Celery deferred; long runs use `background: true` async tasks in the API process.

## Validate / cancel / async

```http
POST /projects/{id}/workflows/{wf}/validate-run
POST /projects/{id}/workflows/{wf}/execute  {"dry_run":false,"background":true,"trigger":"manual"}
POST /projects/{id}/workflows/{wf}/runs/{run}/cancel
```
