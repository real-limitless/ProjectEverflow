# Dev image: Vite with HMR. Source is bind-mounted at runtime.
FROM node:22-bookworm-slim

WORKDIR /ui

COPY everflow-platform-ui/package.json everflow-platform-ui/package-lock.json ./
RUN npm ci

COPY deploy/frontend-dev-entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENV HOST=0.0.0.0 \
    PORT=5173

EXPOSE 5173

ENTRYPOINT ["/entrypoint.sh"]
