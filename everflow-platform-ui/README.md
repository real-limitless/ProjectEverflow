# Everflow Platform UI

PatternFly **6.6.0** React app for Project Everflow — an IDE-style surface for vibe coding, workflows, deploys, and more.

This is a React port of the interactive prototype in [`../playground-v2-pf.html`](../playground-v2-pf.html).

## Stack

- React 19 + TypeScript + Vite
- `@patternfly/react-core` / `react-icons` **6.6.0**
- Zustand (dock layout + project state)
- React Router 7

## Run with the product stack (supported)

The UI is one service in a multi-service Compose stack. **Docker Compose or Podman Compose is the only supported way to run Everflow.**

```bash
# from repository root
./scripts/everflow install
# hot reload (still Compose):
docker compose -f docker-compose.dev.yml up --build
# or: podman compose -f docker-compose.dev.yml up --build
```

| Mode | UI URL |
|------|--------|
| Prod compose | http://localhost:3000 |
| Dev compose | http://localhost:5173 |

The UI talks only to the platform API (also in Compose). Do not run the UI alone as a substitute for the product stack.

## Unit tests & local UI tooling (not a supported stack)

Host Node is optional for **package unit tests**, typecheck, and production builds of this package only — not a supported full-stack Everflow runtime.

```bash
cd everflow-platform-ui
npm install
npm test          # if configured
npx tsc --noEmit
npm run build     # production build
# optional isolated Vite only (incomplete product stack):
# npm run dev
```

## What you get (v1 demo)

| Feature | Notes |
|--------|--------|
| PatternFly Page shell | Masthead, collapsible sidebar nav, routes |
| Project tabs | Multi-project workbench (Aura Host, Callour, Everflow Core) |
| Dock layout | Horizontal/vertical splits, tab groups, sash resize, drag-to-dock |
| Panel tray | Floating / docked / chip modes; open any of 14 panel types |
| Studio panels | Chat, Preview, Knowledge, Code, Repository, Terminal, Workflows, Database, Jobs, Agents, Tools/MCPs, Env/Secrets, Tests, Deploy |
| Persistence | Layout restored from `localStorage` (`everflow-ui-layouts-v1`) |
| Detach | Panel → pop-out window via `?detach=<key>&project=<id>` |

For product install and platform overview, see the monorepo [README.md](../README.md) and [ROADMAP.md](../ROADMAP.md).

## Layout model

Dock tree nodes:

- **`group`** — tab strip + active panel body  
- **`split`** — horizontal or vertical flex children with `%` sizes  

Default layout: Chat | (Preview/Knowledge/Code/Repository over Terminal).

## Project structure

```
src/
  components/shell/      # Page, Masthead, Sidebar
  components/workbench/  # Dock engine, project/repo chrome
  components/panels/     # 14 studio panels
  components/palette/    # Panel tray
  store/                 # Zustand playground store
  data/                  # Mock projects + studio extras
  lib/                   # Pure dock tree helpers
  styles/                # PF token-based layout CSS
```

## Relation to HTML prototype

Keep `playground-v2-pf.html` as the visual/behavioral reference. Feature parity is intentional; implementation is React + PatternFly components instead of DOM string builders.
