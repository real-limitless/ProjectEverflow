# Live stack screenshot capture

Captures the **running Compose product** (UI on `:3000`) — **not** Vite demo mode and **not** `npm run dev`.

Real sandboxes, Desktop, Chat, and marketplace data come from the full stack.

## Prerequisites

1. Full stack up:
   ```bash
   ./scripts/everflow start
   # or first time: ./scripts/everflow install
   ```
2. An account (bootstrap once):
   ```bash
   ./scripts/everflow setup-admin
   # or register via the UI / API
   ```
3. Playwright deps (once):
   ```bash
   cd scripts/screenshots && npm install
   ```

## Credentials

```bash
export EVERFLOW_EMAIL='you@example.com'
export EVERFLOW_PASSWORD='your-password'
export BASE_URL='http://127.0.0.1:3000'   # optional
export API_URL='http://127.0.0.1:8000'    # optional
```

Do **not** commit passwords. Use a local env file that is gitignored (e.g. `.env.screenshots.local`).

## App surfaces (batch)

```bash
node scripts/capture-screenshots.mjs --app-only
# optional: --start-stack   # runs ./scripts/everflow start first
# optional: --headed
```

Writes under `docs/screenshots/`:

| File | Surface |
|------|---------|
| `01-playground-home.png` | Playground entry (projects) |
| `02-marketplace.png` | Marketplace |
| `03-usage.png` | Usage |
| `04-overview.png` | Overview |
| `05-plans.png` | Plans |
| `06-harnesses.png` | Harnesses |

Captions: `docs/screenshots/CAPTIONS.md`

## Interactive Playground (you drive)

Open a **visible** Chromium window against the live stack. Open a project with a **running** sandbox, use Chat + Desktop / Code / Preview, then snap:

```bash
node scripts/capture-screenshots.mjs --interactive
```

### Commands

| Command | Effect |
|---------|--------|
| `snap playground/desktop-ai.png Full desktop session with agent chat` | Save PNG + caption |
| `snap playground/chat.png` | Save without new caption |
| `caption Longer description of the last shot…` | Update caption only |
| `goto /marketplace` | Navigate |
| `reload` / `quit` | Reload page / exit |

No TTY? Write one line:

```bash
echo 'snap playground/desktop.png Agent-driven full desktop in the project sandbox' \
  > docs/screenshots/.capture-cmd
```

Playground feature shots go under `docs/screenshots/playground/`.

## What we deliberately do **not** do

- `VITE_DEMO_MODE=true` / offline mock catalog
- Host `npm run dev` for screenshots
- Fake desktop placeholders

Those cannot show real microVM Desktop or live agent I/O.

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Login screen in shots | Check `EVERFLOW_EMAIL` / `EVERFLOW_PASSWORD` |
| Empty project list | Create a project in the UI or API; wait for `sandbox_status=running` |
| Desktop blank | Need KVM + `SANDBOX_MOCK=false`; open Desktop after sandbox is running |
| Port 3000 down | `./scripts/everflow start` / `status` |
