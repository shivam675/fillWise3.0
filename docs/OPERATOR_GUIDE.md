# Operator Guide

This guide is for system administrators deploying and maintaining FillWise 3.0 in a production environment.

---

## Table of Contents

1. [Environment Variables Reference](#1-environment-variables-reference)
2. [Database Management](#2-database-management)
3. [Production Hardening Checklist](#3-production-hardening-checklist)
4. [Backup Strategy](#4-backup-strategy)
5. [Log Monitoring](#5-log-monitoring)
6. [Ollama Management](#6-ollama-management)
7. [Docker Operations](#7-docker-operations)

---

## 1. Environment Variables Reference

All settings are loaded from the `.env` file (or shell environment). The canonical reference is [`.env.example`](../.env.example). Key settings by category:

### Core

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | No | `sqlite+aiosqlite:///./fillwise.db` | SQLAlchemy async DB URL. Use `postgresql+asyncpg://...` for production. |
| `JWT_SECRET` | **Yes** | — | HS256 signing key. Must be ≥32 characters. Generate with `openssl rand -hex 32`. |
| `JWT_ACCESS_EXPIRE_MINUTES` | No | `30` | Access token lifetime. |
| `JWT_REFRESH_EXPIRE_DAYS` | No | `7` | Refresh token lifetime. |
| `ADMIN_USERNAME` | No | `admin` | Bootstrap admin account created on first startup. |
| `ADMIN_PASSWORD` | **Yes** | — | Must be ≥12 chars. Change after first login. |
| `ADMIN_EMAIL` | No | `admin@localhost` | Bootstrap admin email. |

### API

| Variable | Default | Description |
|----------|---------|-------------|
| `CORS_ORIGINS` | `http://localhost:5173` | Comma-separated list of allowed frontend origins. |
| `RATE_LIMIT_AUTH` | `20/minute` | slowapi rate limit for auth endpoints. |
| `RATE_LIMIT_UPLOAD` | `10/minute` | Rate limit for document upload. |
| `HOST` | `0.0.0.0` | Uvicorn bind host. |
| `PORT` | `8000` | Uvicorn bind port. |
| `WORKERS` | `1` | Uvicorn worker count. For async SQLAlchemy, keep at 1. |
| `LOG_LEVEL` | `info` | Python logging level (`debug`, `info`, `warning`, `error`). |

### Uploads

| Variable | Default | Description |
|----------|---------|-------------|
| `UPLOAD_DIR` | `./uploads` | Directory for uploaded files. Must be writable. |
| `MAX_UPLOAD_BYTES` | `10485760` | 10 MB. Maximum uploaded file size in bytes. |
| `ALLOWED_MIME_TYPES` | `application/pdf,...` | Comma-separated MIME types accepted. |

### Ollama

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | Ollama server URL. |
| `OLLAMA_MODEL` | `ministral:3b` | Model name. Must be pulled first (`ollama pull <model>`). |
| `OLLAMA_TIMEOUT_SECONDS` | `120` | Per-request timeout. Increase for slow hardware. |
| `OLLAMA_MAX_TOKENS` | `2048` | Maximum tokens per generation request. |
| `OLLAMA_TEMPERATURE` | `0.1` | Generation temperature. Keep low (0.05–0.2) for legal rewrites. |
| `OLLAMA_CIRCUIT_BREAKER_THRESHOLD` | `5` | Failures before circuit opens. |
| `OLLAMA_CIRCUIT_BREAKER_TIMEOUT` | `60` | Seconds circuit stays open. |

### Risk Analysis

| Variable | Default | Description |
|----------|---------|-------------|
| `RISK_SEMANTIC_THRESHOLD_HIGH` | `0.7` | TF-IDF cosine similarity below this → HIGH severity. |
| `RISK_SEMANTIC_THRESHOLD_CRITICAL` | `0.4` | Below this → CRITICAL severity. |
| `RISK_LENGTH_RATIO_MIN` | `0.2` | Rewrite/original length ratio below this → HIGH. |
| `RISK_LENGTH_RATIO_MAX` | `5.0` | Above this → HIGH. |

---

## 2. Database Management

### SQLite (development / single-user)

SQLite is the default. The database file is created at the path in `DATABASE_URL` (default: `./fillwise.db`).

```bash
# Run all pending migrations
make migrate

# Rollback one migration step
make migrate-rollback

# Create a new blank migration
make migrate-new MSG="add_index_on_foo"

# Show migration history
make migrate-history
```

### PostgreSQL (recommended for production)

1. Provision a PostgreSQL 14+ database.
2. Set `DATABASE_URL=postgresql+asyncpg://user:password@host:5432/fillwise` in `.env`.
3. Run `make migrate`.

Using Docker Compose with the `postgres` profile:

```bash
make up PROFILE=postgres
```

---

## 3. Production Hardening Checklist

- [ ] `JWT_SECRET` is a random 64-char hex string (`openssl rand -hex 32`)
- [ ] `ADMIN_PASSWORD` changed from default after first login
- [ ] `DATABASE_URL` points to PostgreSQL, not SQLite
- [ ] `CORS_ORIGINS` set to your actual frontend domain (not `*`)
- [ ] `UPLOAD_DIR` is on a separate volume with limited permissions
- [ ] Reverse proxy (nginx/Caddy) terminates TLS in front of the backend
- [ ] `WORKERS=1` (async SQLAlchemy is not fork-safe; use multiple replicas instead)
- [ ] Ollama bound to `127.0.0.1` only (not exposed to network)
- [ ] `LOG_LEVEL=warning` in production (reduces volume)
- [ ] Backups scheduled (see §4)
- [ ] File descriptor limits raised (`ulimit -n 65536`)

---

## 4. Backup Strategy

### SQLite

```bash
# Hot backup (safe with WAL mode, which SQLite uses by default)
cp fillwise.db fillwise.db.bak.$(date +%Y%m%d_%H%M%S)
```

Schedule this with cron or a systemd timer. Store backups off-machine.

### PostgreSQL

```bash
pg_dump -Fc fillwise > fillwise_$(date +%Y%m%d).dump
# Restore with:
pg_restore -d fillwise fillwise_20250101.dump
```

### Upload files

Back up the `UPLOAD_DIR` alongside the database. Without the original files, document re-processing is not possible.

---

## 5. Log Monitoring

Logs stream to stdout in JSON format when `LOG_LEVEL=info`. Each log line includes:

- `correlation_id` — request trace ID (set via `X-Correlation-ID` header or auto-generated)
- `level`, `message`, `timestamp`
- Error lines include `exc_info`

### Key events to monitor

| Event | Severity | Meaning |
|-------|----------|---------|
| `auth.login.failed` | WARN | Wrong credentials — watch for brute-force |
| `ollama.circuit_open` | ERROR | LLM is unavailable — check `ollama serve` |
| `audit.chain.broken` | CRITICAL | Audit log tampered — investigate immediately |
| `upload.rejected` | WARN | Invalid file type or oversized upload attempted |

### Shipping logs to external systems

Pipe stdout to your log aggregator. Example with Loki/Promtail:

```yaml
# promtail-config.yaml
scrape_configs:
  - job_name: fillwise
    static_configs:
      - targets: [localhost]
        labels:
          app: fillwise
          __path__: /var/log/fillwise/*.log
```

---

## 6. Ollama Management

```bash
# Check Ollama is reachable
make ollama-health

# List available models
make ollama-list

# Pull / update the default model
make ollama-pull
```

If Ollama is running on a different host, set `OLLAMA_BASE_URL=http://<host>:11434` in `.env`.

**GPU support**: If your host has a CUDA GPU, Ollama auto-detects it. For the Docker Compose bundled Ollama, uncomment the `deploy.resources` block in `docker-compose.yml`.

---

## 7. Docker Operations

```bash
make build            # Build all images
make up               # Start services (SQLite + local Ollama)
make up PROFILE=postgres  # Add PostgreSQL
make up PROFILE=ollama    # Add bundled Ollama container

make down             # Stop services (keep volumes)
make down-volumes     # Stop services AND delete all data volumes
make logs             # Tail all service logs
make logs-backend     # Tail backend only
make ps               # Show service status
make restart          # Restart all services
make shell            # Open shell in backend container
```

### Health check

The backend container exposes `GET /health` → `{"status": "ok"}`. This is used by Docker's `HEALTHCHECK` directive and should be used by your load balancer.
