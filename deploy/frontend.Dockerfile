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

# Template: entrypoint injects DNS resolvers from the container resolv.conf
# (Podman uses the bridge gateway; Docker uses 127.0.0.11).
COPY deploy/frontend-nginx.conf /etc/nginx/templates/default.conf.template
COPY deploy/frontend-entrypoint.sh /frontend-entrypoint.sh
RUN chmod +x /frontend-entrypoint.sh \
  && cp /etc/nginx/templates/default.conf.template /etc/nginx/conf.d/default.conf \
  && sed -i 's/__EVERFLOW_RESOLVERS__/127.0.0.11 10.89.0.1 10.88.0.1/g' /etc/nginx/conf.d/default.conf

COPY --from=build /ui/dist /usr/share/nginx/html

EXPOSE 80
ENTRYPOINT ["/frontend-entrypoint.sh"]
