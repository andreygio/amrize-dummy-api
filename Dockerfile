# Builder — has pip and shell; not shipped in the final image
# hadolint ignore=DL3007
FROM cgr.dev/chainguard/python:latest-dev AS builder

WORKDIR /app

COPY requirements.txt .
RUN python -m venv /app/venv && \
    /app/venv/bin/pip install --no-cache-dir -r requirements.txt

# Runtime — CVE-free, no shell, no pip; runs as nonroot (uid 65532)
# hadolint ignore=DL3007
FROM cgr.dev/chainguard/python:latest

WORKDIR /app

COPY --from=builder /app/venv /app/venv
COPY app/ ./app/

ENV APPLICATION_NAME=hello-platform \
    ENVIRONMENT=dev \
    VERSION=1.0.0 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

USER nonroot

EXPOSE 8080

ENTRYPOINT ["/app/venv/bin/gunicorn", "--bind", "0.0.0.0:8080", \
            "--workers", "2", "--threads", "4", "app.main:app"]
