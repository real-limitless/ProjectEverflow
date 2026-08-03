# Everflow Platform API

Python **FastAPI** backend for the Everflow platform UI. Dual-database (SQLite by default, PostgreSQL via `DATABASE_URL`), JWT auth, optional GitHub/Google OAuth, and org/project CRUD.

## Product install (Docker / Podman)

The supported way to run the API in production/self-hosted is the root Compose stack
(all services in containers):

```bash
# from repository root
./scripts/everflow-install.sh
# or: docker compose up --build -d
```

Migrations run inside the backend container entrypoint. First-run admin setup is in the UI.

## Contributor quick start (SQLite, host venv)

```bash
cd everflow-platform-api

# Create venv and install (uv recommended)
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"

# Optional: copy env
cp .env.example .env

# Run migrations (Alembic — required before first start)
./scripts/migrate.sh
# or: alembic upgrade head

# Start API (http://localhost:8000)
uvicorn app.main:app --reload --port 8000
# or: ./scripts/dev.sh
```

- OpenAPI docs: [http://localhost:8000/docs](http://localhost:8000/docs)
- Health: `GET /api/v1/health`
- Ready (DB): `GET /api/v1/ready`

## PostgreSQL

```bash
export DATABASE_URL="postgresql+asyncpg://everflow:everflow@localhost:5432/everflow"
./scripts/migrate.sh
uvicorn app.main:app --reload --port 8000
```

No code changes required — the same models and **same Alembic revision chain** work on both engines.

## Database migrations (Alembic)

Schema changes ship as **versioned Alembic revisions** under `alembic/versions/`. That is the only supported way to upgrade SQLite or PostgreSQL as the platform grows.

### Everyday commands

| Action | Command |
|--------|---------|
| Apply all pending upgrades | `./scripts/migrate.sh` or `alembic upgrade head` |
| Show current revision | `alembic current` |
| Show history | `alembic history` |
| Create a revision after model edits | `./scripts/makemigration.sh "short_description"` |
| Same, raw Alembic | `alembic revision --autogenerate -m "short_description"` |
| Roll back one step | `alembic downgrade -1` |
| Roll back everything | `alembic downgrade base` |

### Workflow when you add or change models

1. Edit SQLAlchemy models in `app/models/`.
2. Register new models in `app/models/__init__.py` **and** import them in `alembic/env.py` so autogenerate sees full metadata.
3. Generate a revision:
   ```bash
   ./scripts/makemigration.sh "add_agents_table"
   ```
4. **Review** the file under `alembic/versions/` (`upgrade()` / `downgrade()`). Autogenerate can miss renames, data backfills, or dual-DB type nuances — edit by hand when needed.
5. Apply locally:
   ```bash
   ./scripts/migrate.sh
   ```
6. Commit **models + migration file together**. Deployments run `alembic upgrade head` (or `./scripts/migrate.sh`) against the target `DATABASE_URL`.

```
Developer  ── alembic upgrade head ──►  SQLite or Postgres
Staging    ── alembic upgrade head ──►  same revision chain
Production ── alembic upgrade head ──►  same revision chain
```

### Rules

- **Do not** hand-edit production databases.
- **Do not** use `Base.metadata.create_all()` for shared/dev/prod schema (tests may use it for speed; production path is Alembic only).
- App startup does **not** auto-run migrations (avoids multi-worker races). Run migrations explicitly before or as part of deploy.
- SQLite uses Alembic **batch mode** (`render_as_batch`) so `ALTER TABLE`-style upgrades work.

### Current chain

| Revision | Description |
|----------|-------------|
| `001` | Initial users, oauth accounts, organizations, projects |
| `002` | Project sandbox lifecycle columns (`sandbox_name`, `sandbox_status`, …) |

## Sandboxes

When `SANDBOX_ENABLED=true`, creating a project asks the internal **sandbox-agent**
(microsandbox control plane) to start a detached microVM. Create is **fast**: the
agent returns once the guest is up. Prefer `SANDBOX_DEFAULT_IMAGE=everflow-sandbox-guest:dev`
(build with `./deploy/build-sandbox-guest.sh`) so Claude Code / OpenCode are already
in the image; otherwise harness install runs in the background. Clients never call the
agent; they use Everflow routes:

| Method | Path |
|--------|------|
| GET | `/api/v1/projects/{id}/sandbox` |
| POST | `/api/v1/projects/{id}/sandbox/retry` |
| POST | `/api/v1/projects/{id}/sandbox/start` \| `/stop` |
| POST | `/api/v1/projects/{id}/sandbox/exec` |
| GET/PUT | `/api/v1/projects/{id}/sandbox/fs` / `fs/content` |

Env: `SANDBOX_AGENT_URL`, `SANDBOX_AGENT_TOKEN`, `SANDBOX_DEFAULT_IMAGE`, etc.
See root [docker-compose.yml](../docker-compose.yml) and [everflow-sandbox-agent](../everflow-sandbox-agent/).


## Auth

### Local JWT

```bash
# Register
curl -s -X POST http://localhost:8000/api/v1/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"you@example.com","password":"securepassword123"}'

# Login (OAuth2 password form)
curl -s -X POST http://localhost:8000/api/v1/auth/jwt/login \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d 'username=you@example.com&password=securepassword123'

# Me
curl -s http://localhost:8000/api/v1/users/me \
  -H "Authorization: Bearer <access_token>"
```

### OAuth (GitHub / Google)

Set credentials in `.env`:

```bash
GITHUB_CLIENT_ID=...
GITHUB_CLIENT_SECRET=...
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
OAUTH_REDIRECT_BASE_URL=http://localhost:8000
```

Then use:

- `GET /api/v1/auth/github/authorize`
- `GET /api/v1/auth/google/authorize`

Providers are **not mounted** when client ID/secret are empty (local JWT still works).

After OAuth, fastapi-users returns a JWT. Point your SPA at `FRONTEND_URL` and store the bearer token for API calls.

## API surface (v1)

| Method | Path | Auth |
|--------|------|------|
| GET | `/api/v1/health` | No |
| GET | `/api/v1/ready` | No |
| POST | `/api/v1/auth/register` | No |
| POST | `/api/v1/auth/jwt/login` | No |
| GET | `/api/v1/users/me` | JWT |
| GET/POST | `/api/v1/orgs` | JWT |
| GET/PATCH/DELETE | `/api/v1/orgs/{org_id}` | JWT (member / admin / owner) |
| GET/POST | `/api/v1/orgs/{org_id}/projects` | JWT (member) |
| GET/PATCH/DELETE | `/api/v1/projects/{project_id}` | JWT (member; admin for delete/rename) |

## Frontend

The UI expects the API on port **8000** with CORS for `http://localhost:5173`.

```bash
# everflow-platform-ui
echo 'VITE_API_URL=http://localhost:8000' > .env.development
npm run dev
```

## Tests

```bash
pytest
```

Uses in-memory SQLite; no external services required.

## Layout

```
app/
  main.py           # FastAPI app + CORS
  config.py         # pydantic-settings
  db/               # async engine (SQLite | Postgres)
  models/           # SQLAlchemy models
  schemas/          # Pydantic schemas
  auth/             # fastapi-users + OAuth
  api/v1/           # routers
alembic/            # migrations
tests/
```

## Related

Shipped vs planned product surface: monorepo [ROADMAP.md](../ROADMAP.md). Install and operator docs: [README.md](../README.md).
