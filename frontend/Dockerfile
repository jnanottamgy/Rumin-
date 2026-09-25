# syntax=docker/dockerfile:1.7
#
# The RUMIN web server (Phase 10): the built web app, served by an unprivileged nginx that
# also terminates TLS and passes /api and /health to the API. Built from the repository
# root, because the type-check reads the API contract in docs/api/openapi.json:
#
#   docker build -f frontend/Dockerfile -t rumin-web:<version> .
#
# Behind a proxy that re-signs TLS, pass its CA bundle as a build secret (it is not kept in
# the image):  docker build --secret id=extra_ca,src=/path/to/ca-bundle.crt ...

FROM node:22.23.3-alpine AS build
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=secret,id=extra_ca,required=false \
    if [ -f /run/secrets/extra_ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/extra_ca; fi \
    && npm ci --no-audit --no-fund
COPY docs/api/openapi.json /src/docs/api/openapi.json
COPY frontend/ ./
# Type-check, then bundle. Source maps are for decoding reported stack traces: never served.
RUN npm run build && find dist -name "*.map" -delete

FROM nginxinc/nginx-unprivileged:1.30.5-alpine AS runtime
LABEL org.opencontainers.image.title="rumin-web" \
      org.opencontainers.image.description="RUMIN web app behind nginx"
COPY frontend/nginx/templates/ /etc/nginx/templates/
COPY frontend/nginx/snippets/ /etc/nginx/snippets/
COPY --from=build /src/frontend/dist/ /usr/share/nginx/html/
# Rendered at start-up from the environment: RUMIN_SERVER_NAME and RUMIN_PUBLIC_ORIGIN.
ENV RUMIN_SERVER_NAME=localhost \
    RUMIN_PUBLIC_ORIGIN=https://localhost \
    RUMIN_API_UPSTREAM=api:8000
EXPOSE 8080 8443
HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=3 \
  CMD ["wget", "-q", "-O", "/dev/null", "http://127.0.0.1:8080/nginx-health"]
