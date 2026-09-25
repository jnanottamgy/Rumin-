# syntax=docker/dockerfile:1.7
#
# The RUMIN API (Phase 10): one uvicorn process (ADR 58), running as an unprivileged user
# from a read-only image. Build from backend/:
#
#   docker build -t rumin-api:<version> backend
#
# Behind a proxy that re-signs TLS, pass its CA bundle as a build secret (it is not kept in
# the image):  docker build --secret id=extra_ca,src=/path/to/ca-bundle.crt ...

ARG PYTHON_IMAGE=python:3.11-slim-bookworm

FROM ${PYTHON_IMAGE} AS build
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY pyproject.toml uv.lock ./
# The locked dependencies only (no dev tools); the application is copied, not installed.
RUN --mount=type=secret,id=extra_ca,required=false \
    if [ -f /run/secrets/extra_ca ]; then \
      export SSL_CERT_FILE=/run/secrets/extra_ca PIP_CERT=/run/secrets/extra_ca; \
    fi \
    && pip install --no-cache-dir uv==0.8.17 \
    && uv sync --frozen --no-dev --extra postgres --no-install-project \
    && rm -rf /root/.cache
COPY alembic.ini ./
COPY migrations ./migrations
COPY app ./app
RUN /opt/venv/bin/python -m compileall -q app migrations

FROM ${PYTHON_IMAGE} AS runtime
LABEL org.opencontainers.image.title="rumin-api" \
      org.opencontainers.image.description="RUMIN API: financial intelligence and economic simulation"
RUN groupadd --system --gid 10001 rumin \
    && useradd --system --uid 10001 --gid rumin --home-dir /app --no-create-home \
       --shell /usr/sbin/nologin rumin
COPY --from=build /opt/venv /opt/venv
COPY --from=build /app /app
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    RUMIN_ENVIRONMENT=production \
    RUMIN_LOG_FORMAT=json \
    FORWARDED_ALLOW_IPS=127.0.0.1
WORKDIR /app
USER rumin
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).status == 200 else 1)"]
# One process: the scenario and analyst runners, the login throttle and the metrics live
# in it (ADR 58). --proxy-headers takes the client address and scheme from the web server
# listed in FORWARDED_ALLOW_IPS; uvicorn's access log is off (the API logs each request
# with its request ID).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", \
     "--proxy-headers", "--no-access-log", "--no-server-header"]
