# syntax=docker/dockerfile:1
FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

# Pango/HarfBuzz for WeasyPrint PDF rendering; fonts for report text
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.13.0 /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .
RUN uv sync --frozen --no-dev \
    # The app runs from /opt/venv; drop the base image's unused pip and bundled
    # wheels so they don't ship known-vulnerable copies of setuptools/urllib3
    && rm -rf /usr/local/lib/python3.13/site-packages/pip* \
        /usr/local/lib/python3.13/site-packages/setuptools* \
        /usr/local/lib/python3.13/ensurepip/_bundled \
        /usr/local/lib/python3.13/test/wheeldata \
        /usr/local/bin/pip* \
    && useradd --system --uid 10001 --home /app app \
    && mkdir -p /data && chown -R app /data

USER app
ENV RM_STORAGE_DIR=/data
VOLUME ["/data"]
EXPOSE 8000

# Migrations run once from the api container (see docker-compose.yml)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
