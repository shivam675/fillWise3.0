# FillWise 3.0

A production-grade, **local-first** web application for controlled legal document transformation using on-device LLMs via [Ollama](https://ollama.com).

Upload PDF or DOCX contracts → apply rule-based Ollama rewrites → human diff review with risk analysis → export clean DOCX. Nothing leaves your machine.

---

## Quick Start (5 commands)

```bash
git clone <repo-url> fillwise3.0 && cd fillwise3.0   # 1. clone
make env-copy                                          # 2. copy .env.example → .env  (then edit .env)
make install                                           # 3. install all dependencies
make migrate                                           # 4. run database migrations
make dev                                               # 5. start backend + frontend
```

Open **http://localhost:5173** and log in with the credentials in your `.env` (`ADMIN_USERNAME` / `ADMIN_PASSWORD`).

---

## Prerequisites

| Tool | Min version | Install |
|------|-------------|---------|
| Python | 3.11 | [python.org](https://python.org) |
| Node.js | 20 LTS | [nodejs.org](https://nodejs.org) |
| Ollama | latest | [ollama.com](https://ollama.com) |
| Docker (optional) | 24+ | [docker.com](https://docker.com) |

### Pull the default LLM model

```bash
ollama pull ministral:3b
```

---

## Configuration

All configuration is via environment variables. Copy the example file and edit it:

```bash
cp .env.example .env
# Required edits:
#   JWT_SECRET   — at least 32 random characters
#   ADMIN_PASSWORD — at least 12 characters, mixed case + symbol
```

See [.env.example](.env.example) for every available option with descriptions.

---

## Development Mode

```bash
make install       # creates backend venv + installs frontend npm deps
make migrate       # applies Alembic migrations (creates fillwise.db)
make dev           # runs uvicorn on :8000 and vite dev server on :5173
```

API documentation is served at **http://localhost:8000/docs** (Swagger UI) and **http://localhost:8000/redoc**.

### Run tests

```bash
make test              # all backend pytest + frontend vitest
make test-backend      # pytest only
make test-frontend     # vitest only
make test-e2e          # Playwright (requires running server)
```

### Lint & type-check

```bash
make check             # runs lint + type-check (full CI gate)
```

---

## Docker Mode

```bash
make env-copy          # if you haven't already
make build             # build backend + frontend images
make up                # start (SQLite mode, no extra profiles)

# PostgreSQL backend:
make up PROFILE=postgres

# Bundled Ollama container (GPU optional):
make up PROFILE=ollama
```

Services:

| Service | URL |
|---------|-----|
| Frontend | http://localhost:5173 |
| Backend API | http://localhost:8000 |
| API Docs | http://localhost:8000/docs |

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────┐
│  Browser  → React + Vite (port 5173)                         │
│             Zustand auth store, TanStack Query, Monaco Editor │
└─────────────────────┬────────────────────────────────────────┘
                      │ HTTP / WebSocket
┌─────────────────────▼────────────────────────────────────────┐
│  FastAPI (port 8000)                                          │
│  ┌──────────┐ ┌──────────┐ ┌────────┐ ┌──────────┐          │
│  │ Ingestion│ │   LLM    │ │  Risk  │ │ Assembly │          │
│  │ PDF/DOCX │ │ Prompt + │ │Analyzer│ │  DOCX    │          │
│  │ Detector │ │ Ollama   │ │TF-IDF  │ │  Export  │          │
│  └──────────┘ └──────────┘ └────────┘ └──────────┘          │
│  ┌──────────────────────────────────────────────────┐        │
│  │  SQLAlchemy async ORM + Alembic migrations       │        │
│  │  SQLite (dev) / PostgreSQL (prod)                │        │
│  └──────────────────────────────────────────────────┘        │
└──────────────────────────────────┬───────────────────────────┘
                                   │ HTTP
                         ┌─────────▼──────────┐
                         │  Ollama (port 11434)│
                         │  ministral:3b       │
                         └────────────────────┘
```

For a full architecture deep-dive see [docs/DEVELOPER_GUIDE.md](docs/DEVELOPER_GUIDE.md).

---

## Rule Files

Rule sets are YAML files in `rules/`. Two samples are provided:

- [`rules/samples/plain_language.yaml`](rules/samples/plain_language.yaml) — general plain-English rewrites
- [`rules/samples/uae_compliance.yaml`](rules/samples/uae_compliance.yaml) — UAE-jurisdiction compliance rules

Upload a YAML file via the **Rulesets** page in the UI, or via `POST /api/v1/rulesets/`.

---

## Project Layout

```
fillwise3.0/
├── backend/                  # FastAPI application
│   ├── app/
│   │   ├── api/v1/           # Route handlers
│   │   ├── config/           # Settings (Pydantic v2)
│   │   ├── core/             # Security, errors, middleware
│   │   ├── db/               # SQLAlchemy models + session
│   │   ├── schemas/          # Pydantic request/response schemas
│   │   └── services/         # Business logic
│   │       ├── assembly/     # DOCX export
│   │       ├── audit/        # Tamper-evident event log
│   │       ├── ingestion/    # PDF/DOCX parsing + structure detection
│   │       ├── llm/          # Ollama client + prompt engine
│   │       ├── review/       # Diff generation
│   │       ├── risk/         # Risk analysis (TF-IDF + regex)
│   │       └── rules/        # YAML validator + conflict detection
│   ├── alembic/              # Database migrations
│   ├── tests/
│   │   ├── unit/             # Fast isolated tests
│   │   └── integration/      # In-memory SQLite + mock Ollama
│   └── pytest.ini
├── frontend/                 # React + Vite SPA
│   └── src/
│       ├── api/              # Axios client + endpoint modules
│       ├── components/       # Shared UI components
│       ├── pages/            # Route-level page components
│       ├── stores/           # Zustand stores
│       └── types/            # TypeScript API mirrors
├── rules/                    # YAML rule libraries
│   └── samples/
├── docs/                     # Operator + developer guides
├── docker-compose.yml
├── Makefile
└── .env.example
```

---

## Security Notes

- All JWTs use HS256 with a secret you provide (≥32 chars)
- CSRF double-submit cookie on all state-changing endpoints
- bcrypt password hashing (cost factor 12)
- Audit log is SHA-256 hash-chained — any tampering is detectable via `/api/v1/audit/verify`
- Rate limiting on auth endpoints (20 req/min by default)
- No data leaves the machine — all LLM calls go to `127.0.0.1:11434`

See [docs/SECURITY_MODEL.md](docs/SECURITY_MODEL.md) for full details.

---

## License

MIT. See [LICENSE](LICENSE).
