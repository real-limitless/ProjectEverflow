# Everflow toolkit — Full-stack monorepo

- `apps/web` — Vite + React
- `apps/api` — FastAPI

```bash
# Web
cd apps/web && npm install && npm run dev

# API (separate terminal)
cd apps/api
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Default Preview port: **5173**.
