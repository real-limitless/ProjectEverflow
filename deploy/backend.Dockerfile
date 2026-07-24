FROM python:3.12-slim-bookworm

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY everflow-platform-api/pyproject.toml everflow-platform-api/README.md ./
COPY everflow-platform-api/app ./app
COPY everflow-platform-api/alembic ./alembic
COPY everflow-platform-api/alembic.ini ./alembic.ini
COPY everflow-platform-api/scripts ./scripts
# App starter toolkits (seeded into sandboxes when TOOLKIT_REPO_BASE is unset)
COPY toolkits /toolkits

RUN pip install --no-cache-dir -e .

ENV DATABASE_URL=sqlite+aiosqlite:////data/everflow.db
ENV TOOLKIT_LOCAL_ROOT=/toolkits

RUN mkdir -p /data

EXPOSE 8000

COPY deploy/backend-entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
