FROM python:3.12-slim-bookworm

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY everflow-sandbox-agent/pyproject.toml everflow-sandbox-agent/README.md ./
COPY everflow-sandbox-agent/app ./app

RUN pip install --no-cache-dir -e .

# Optional real SDK (may fail on some arches; mock mode still works)
RUN pip install --no-cache-dir 'microsandbox' || true

ENV SANDBOX_MOCK=true \
    WORKSPACE_ROOT=/workspaces \
    HOST=0.0.0.0 \
    PORT=8090

EXPOSE 8090

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8090"]
