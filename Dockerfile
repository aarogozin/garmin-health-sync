# syntax=docker/dockerfile:1.7
FROM golang:1.27-bookworm@sha256:69a7b9788769bec032d238959b61854e9ae87f57be9029ec04e9885fabf99195 AS host-helper

ARG TARGETARCH
WORKDIR /source/host_helper
COPY host_helper/go.mod host_helper/main.go ./
RUN CGO_ENABLED=0 GOOS=darwin GOARCH=${TARGETARCH} go build -trimpath -ldflags='-s -w' -o /out/health-sync-host-helper .

FROM scratch AS host-helper-export
COPY --from=host-helper /out/health-sync-host-helper /health-sync-host-helper

FROM node:24-bookworm-slim@sha256:a9f5f7c91a432850b2a8a7797adf5eadb6c733ceed61167806cee7ea7fbc29df AS frontend

WORKDIR /source/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --ignore-scripts
COPY frontend ./
RUN npm run build

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim@sha256:e5b65587bce7de595f299855d7385fe7fca39b8a74baa261ba1b7147afa78e58 AS builder

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY --from=frontend /source/src/garmin_sync/web_dist ./src/garmin_sync/web_dist
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.12-slim-bookworm@sha256:0f5b26b9518d002b6173fd61daad821fa340635ebfec5bba471013f9ca114579
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    GARMIN_SYNC_DATA_DIR=/data \
    GARMIN_SYNC_ARCHIVE_DIR=/archive \
    GARMIN_SYNC_SECRET_KEY_FILE=/run/secrets/garmin_sync_key \
    GARMIN_SYNC_BIND=0.0.0.0 \
    GARMIN_SYNC_PORT=8080 \
    GARMIN_SYNC_PUBLIC_HOST=localhost \
    GARMIN_SYNC_NO_BROWSER=1

RUN groupadd --system --gid 10001 app && useradd --system --uid 10001 --gid app app \
    && mkdir -p /data && chown app:app /data
WORKDIR /app
COPY --from=builder --chown=app:app /app /app
USER app
EXPOSE 8080
VOLUME ["/data"]
HEALTHCHECK --interval=30s --timeout=3s --start-period=40s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=2)"
ENTRYPOINT ["garmin-sync"]
CMD ["gui"]
