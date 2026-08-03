# Everflow Platform UI

PatternFly **6.6.0** React app for Project Everflow — an IDE-style surface for vibe coding, workflows, deploys, and more.

This is a React port of the interactive prototype in [`../playground-v2-pf.html`](../playground-v2-pf.html).

## Stack

- React 19 + TypeScript + Vite
- `@patternfly/react-core` / `react-icons` **6.6.0**
- Zustand (dock layout + project state)
- React Router 7

## Quick start

```bash
cd everflow-platform-ui
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173).

```bash
npm run build    # production build
npm run preview  # serve dist/
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
