# Everflow app toolkits

Cloneable (or locally seeded) starters for project create.

| Toolkit id | Path | Stack |
|------------|------|--------|
| `web-npm` | [web-npm](./web-npm) | Vite + React |
| `web-php` | [web-php](./web-php) | PHP 8.2 + Composer |
| `mobile-expo` | [mobile-expo](./mobile-expo) | Expo / React Native (+ web) |
| `desktop-gui` | [desktop-gui](./desktop-gui) | Electron shell |
| `python-api` | [python-api](./python-api) | FastAPI |
| `fullstack` | [fullstack](./fullstack) | Vite web + FastAPI |

Each folder is meant to stand alone as its own git repo later. Until published:

- Set `TOOLKIT_REPO_BASE=https://github.com/org/everflow-toolkit-{id}.git` on the API, or
- Leave unset and seed from `TOOLKIT_LOCAL_ROOT` (default: this directory).

UI optional override: `VITE_TOOLKIT_REPO_BASE` with the same `{id}` placeholder.
