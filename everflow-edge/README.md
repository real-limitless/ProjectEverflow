# everflow-edge

Lightweight agent that runs on **deploy hosts** (VMs / bare metal) alongside Traefik and Docker Compose.

MVP (Issue 15 P3/P4): health + heartbeat stubs, sample Traefik file-provider routes, and a remote `docker compose up` path from the platform API (`deploy_remote.py`).

## Role in the deploy flow

```
Platform UI / API
    │  SSH (deploy key) + rsync compose project
    ▼
Deploy host
    ├── Traefik (file provider watches /etc/everflow/dynamic)
    ├── everflow-edge  (:9100 /health, /heartbeat)
    └── Your app stack  (docker compose -f … up -d)
```

1. Install Docker + Traefik compose on the host (`../scripts/everflow-edge-install.sh`).
2. Add the Everflow **deploy public key** to `~/.ssh/authorized_keys` for the deploy user.
3. Platform calls `POST /api/v1/projects/{id}/deploy/runs` with host credentials + routes.
4. API SSHs in, syncs the compose project, writes Traefik `Host(\`domain\`)` rules, runs `docker compose up -d`.
5. Traefik reloads the dynamic file and routes traffic to `service:port`.

## Local run (agent only)

```bash
cd everflow-edge
python -m venv .venv && source .venv/bin/activate
pip install -e .
uvicorn app.main:app --host 0.0.0.0 --port 9100
curl -s localhost:9100/health
curl -s -X POST localhost:9100/heartbeat -H 'content-type: application/json' -d '{}'
```

## Traefik sample

See [`traefik/`](traefik/):

| File | Purpose |
|------|---------|
| `traefik.yml` | Static config — file provider on `/etc/everflow/dynamic` |
| `dynamic/routes.yml.example` | `Host(\`app.example.com\`)` → `http://127.0.0.1:8080` |
| `docker-compose.yml` | Traefik + edge containers |

```bash
sudo mkdir -p /etc/everflow/dynamic
sudo cp traefik/dynamic/routes.yml.example /etc/everflow/dynamic/routes.yml
cd traefik && docker compose up -d
```

Edit `/etc/everflow/dynamic/routes.yml` (or let the platform write `.everflow/traefik-routes.yml` and sync/symlink it). Traefik watches the directory and hot-reloads.

### Route template shape

```yaml
http:
  routers:
    my-app:
      rule: "Host(`my-app.example.com`)"
      entryPoints: [web]
      service: my-app
  services:
    my-app:
      loadBalancer:
        servers:
          - url: "http://127.0.0.1:8080"
```

## Install on a bare host

```bash
# from repo root (or curl the script onto the host)
sudo ./scripts/everflow-edge-install.sh
```

Then print/add the deploy pubkey instructions the script emits.

## Platform API hook

`everflow-platform-api` exposes:

```
POST /api/v1/projects/{project_id}/deploy/runs
```

Body (MVP):

```json
{
  "host": "edge.example.com",
  "user": "everflow",
  "port": 22,
  "private_key_pem": "-----BEGIN OPENSSH PRIVATE KEY-----\\n...",
  "remote_dir": "/opt/everflow/apps/my-project",
  "compose_path": "docker-compose.yml",
  "local_workspace_hint": "/path/to/compose/project",
  "routes": [
    {"name": "web", "domain": "app.example.com", "service": "web", "port": 8080}
  ]
}
```

UI (`DeployPanel`) can call this when host keys are stored; until then, pipeline runs remain simulated in the studio store.

## Env

| Variable | Default | Meaning |
|----------|---------|---------|
| `EVERFLOW_EDGE_HOST` | `0.0.0.0` | Bind address |
| `EVERFLOW_EDGE_PORT` | `9100` | HTTP port |
| `EVERFLOW_EDGE_NODE_ID` | hostname | Node identity in heartbeat |
| `EVERFLOW_EDGE_TAGS` | `docker` | Comma-separated tags |

## Out of scope (follow-ups)

- Persistent node registration / mTLS with the platform
- DeployPanel button wired to live `deploy/runs` (needs host key storage from deploy-keys-nodes)
- TLS certificates (Let's Encrypt) on Traefik
- Podman / K8s orchestrators
