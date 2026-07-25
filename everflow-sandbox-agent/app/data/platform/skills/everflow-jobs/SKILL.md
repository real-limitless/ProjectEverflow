---
name: everflow-jobs
description: >-
  Run long-lived processes (dev servers, watchers) as Everflow Jobs so they survive
  the agent turn and appear in the Jobs panel. Prefer over a blocking shell.
compatibility: opencode
---

# Everflow Jobs

Use **Jobs** for detached, long-running processes inside this project sandbox.

## When to use

- Start a website or API (`npm run dev`, `uvicorn`, `docker compose up`, …)
- Keep a process running while you continue editing
- Inspect logs or restart a server the user already started via Jobs

## Procedure

1. Prefer **`create_job(title, command, cwd?)`** over `bash` with a forever process.
2. **`get_job_logs`** to verify startup (listen port, errors).
3. Lifecycle: `start_job` / `stop_job` / `kill_job` / `restart_job` / `delete_job`.
4. **`list_jobs`** when the user asks what is running.
5. Requires a **running** sandbox. If tools fail with sandbox stopped, say so.

## Examples

- Dev server: `create_job(title="dev", command="npm run dev", cwd=".")`
- Python API: `create_job(title="api", command="uvicorn app:app --host 0.0.0.0 --port 8000")`

## Do not

- Block the agent session on a never-ending shell for servers
- Invent host URLs outside what the project/Jobs/logs report
