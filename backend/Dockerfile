# ─────────────────────────────────────────────────────────────────────────────
# FillWise 3.0  ·  Backend Dockerfile
# Multi-stage build: builder installs deps, final stage is lean runtime image.
# ─────────────────────────────────────────────────────────────────────────────

# ── Stage 1: dependency builder ───────────────────────────────────────────────
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# System deps needed to compile native extensions (pdfplumber, pymupdf, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libffi-dev \
        libssl-dev \
        libxml2-dev \
        libxslt1-dev \
        zlib1g-dev \
        pkg-config \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Copy only dependency manifest first to exploit layer caching.
COPY pyproject.toml ./

# Install all runtime dependencies into a dedicated prefix so we can copy it.
RUN pip install --prefix=/runtime --no-warn-script-location . 2>&1 | tail -5


# ── Stage 2: lean runtime image ───────────────────────────────────────────────
FROM python:3.11-slim AS runtime

LABEL maintainer="FillWise Team"
LABEL org.opencontainers.image.title="FillWise Backend"
LABEL org.opencontainers.image.description="Legal document transformation API"
LABEL org.opencontainers.image.version="3.0.0"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH="/app" \
    PATH="/runtime/bin:${PATH}" \
    PYTHONWARNINGS="ignore::DeprecationWarning"

# Non-root user for security
RUN groupadd -r fillwise && useradd -r -g fillwise -d /app -s /sbin/nologin fillwise

# Runtime system deps only (shared libraries, no compilers)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libxml2 \
        libxslt1.1 \
        libssl3 \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder
COPY --from=builder /runtime /usr/local

WORKDIR /app

# Copy application source
COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini ./alembic.ini

# Create directories that will be bind-mounted; pre-create so permissions are set.
RUN mkdir -p /data/uploads /data/exports /data/logs \
    && chown -R fillwise:fillwise /app /data

USER fillwise

# Expose API port (matches default PORT env var)
EXPOSE 8000

# Health-check: ping the /health endpoint every 30 s
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Entrypoint: run migrations then start uvicorn.
# In production pass --workers $(nproc) via CMD override or WORKERS env var.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app \
     --host ${HOST:-0.0.0.0} \
     --port ${PORT:-8000} \
     --workers ${WORKERS:-1} \
     --log-config /dev/null"]
