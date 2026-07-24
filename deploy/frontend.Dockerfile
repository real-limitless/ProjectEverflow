# Build stage
FROM node:22-bookworm-slim AS build

WORKDIR /ui
COPY everflow-platform-ui/package.json everflow-platform-ui/package-lock.json ./
RUN npm ci
COPY everflow-platform-ui/ ./

# Empty = same-origin /api (nginx proxies to backend). Required for prebuilt
# GHCR images so one image works on any host without rebuilding.
ARG VITE_API_URL=
ENV VITE_API_URL=$VITE_API_URL

RUN npm run build

# Serve stage
FROM nginx:1.27-alpine

COPY deploy/frontend-nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /ui/dist /usr/share/nginx/html

EXPOSE 80
