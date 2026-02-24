# Developer Guide

This guide is for engineers contributing to FillWise 3.0 or extending it.

---

## Table of Contents

1. [Project Structure](#1-project-structure)
2. [Backend Deep Dive](#2-backend-deep-dive)
3. [Frontend Deep Dive](#3-frontend-deep-dive)
4. [Adding a New API Endpoint](#4-adding-a-new-api-endpoint)
5. [Adding a New Rule Type](#5-adding-a-new-rule-type)
6. [Running Tests](#6-running-tests)
7. [Database Migrations](#7-database-migrations)
8. [Common Patterns](#8-common-patterns)

---

## 1. Project Structure

```
backend/
├── app/
│   ├── api/v1/           ← FastAPI routers (one file per domain)
│   │   ├── auth.py
│   │   ├── documents.py
│   │   ├── rulesets.py
│   │   ├── jobs.py
│   │   ├── reviews.py
│   │   ├── audit.py
│   │   ├── admin.py
│   │   └── ws.py         ← WebSocket endpoints
│   ├── config/
│   │   └── settings.py   ← Pydantic v2 Settings with validator
│   ├── core/
│   │   ├── security.py   ← JWT, bcrypt, CSRF
│   │   ├── errors.py     ← Custom exception hierarchy
│   │   ├── middleware.py ← SecurityHeaders, CorrelationID
│   │   └── deps.py       ← FastAPI dependency functions
│   ├── db/
│   │   ├── session.py    ← Async engine + get_db dependency
│   │   └── models/       ← SQLAlchemy declarative models
│   ├── schemas/          ← Pydantic v2 request/response schemas
│   └── services/
│       ├── assembly/     ← python-docx DOCX builder
│       ├── audit/        ← SHA-256 hash-chained event logger
│       ├── ingestion/    ← PDF/DOCX parsing, structure detection
│       ├── llm/          ← Ollama HTTP client, prompt engine, circuit breaker
│       ├── review/       ← Diff generation (difflib)
│       ├── risk/         ← TF-IDF + regex risk analyzer
│       └── rules/        ← YAML validator, conflict detector
├── alembic/
│   └── versions/
├── tests/
│   ├── conftest.py       ← Async fixtures, test DB, admin_client
│   ├── unit/             ← Pure unit tests (no DB/network)
│   └── integration/      ← In-memory SQLite + mock Ollama
└── pytest.ini

frontend/
├── src/
│   ├── api/              ← Axios client + per-domain endpoint functions
│   ├── components/ui/    ← EmptyState, Spinner, StatusBadge
│   ├── lib/              ← cn(), formatBytes(), formatDate()
│   ├── pages/            ← Route-level components
│   ├── stores/           ← Zustand (auth)
│   └── types/api.ts      ← TypeScript mirrors of backend schemas
├── vite.config.ts
├── tailwind.config.ts
└── playwright.config.ts
```

---

## 2. Backend Deep Dive

### Request lifecycle

```
HTTP Request
    → CorrelationIDMiddleware    (attaches X-Correlation-ID)
    → SecurityHeadersMiddleware  (adds CSP, HSTS headers)
    → SlowAPI rate limiter       (per-IP, configurable)
    → FastAPI router
        → deps.get_current_user  (JWT decode + DB lookup)
        → deps.require_role      (RBAC check)
        → Route handler
            → Service layer      (business logic)
            → AuditLogger.log()  (write audit event)
    → JSONResponse
```

### Service layer conventions

- Services are **not** FastAPI dependencies — they are plain async classes/functions.
- Each service receives an `AsyncSession` injected by the route handler.
- Services raise `app.core.errors.*` exceptions; the global exception handler converts them to HTTP responses.
- Services never import from `app.api` (no circular deps).

### Error hierarchy

```python
FillWiseError        # base
├── AuthError        # → 401
├── ForbiddenError   # → 403
├── NotFoundError    # → 404
├── ConflictError    # → 409
├── ValidationError  # → 422
└── ServiceError     # → 500
```

Raise these from service code. The global handler in `app/main.py` maps them to JSON responses with `{"detail": "...", "code": "..."}`.

---

## 3. Frontend Deep Dive

### State management

- **Server state**: TanStack Query v5 (`useQuery`, `useMutation`). All API calls go through `src/api/`.
- **Auth state**: Zustand persisted to `localStorage` (`src/stores/auth.ts`). Stores `accessToken` and `refreshToken` only. The `user` object is re-fetched on mount.
- **Local UI state**: `useState` / `useReducer` inside components.

### API client (`src/api/client.ts`)

- Single Axios instance with `withCredentials: true`.
- Request interceptor: attaches `Authorization: Bearer <token>` and `X-CSRF-Token` from the `csrf_token` cookie.
- Response interceptor: on 401, pauses the request queue, calls `/auth/refresh`, re-issues the original request. If refresh fails, logs out.

### Route protection

- `<ProtectedRoute>` — redirects to `/login` if `!isAuthenticated()`.
- `<RoleRoute roles={["admin"]}>` — renders a 403 page if the user's role is not in the list.

---

## 4. Adding a New API Endpoint

**Example**: Add `GET /api/v1/documents/{id}/word-count`

### Step 1 — Schema (if needed)

```python
# backend/app/schemas/documents.py
class WordCountResponse(BaseModel):
    document_id: uuid.UUID
    word_count: int
```

### Step 2 — Service method

```python
# backend/app/services/ingestion/document_service.py
async def get_word_count(db: AsyncSession, document_id: UUID, actor_id: UUID) -> int:
    doc = await _get_or_404(db, document_id)
    # Sum words across all sections
    result = await db.execute(
        select(func.sum(func.length(Section.text) - func.length(func.replace(Section.text, " ", "")) + 1))
        .where(Section.document_id == document_id)
    )
    return result.scalar_one_or_none() or 0
```

### Step 3 — Route handler

```python
# backend/app/api/v1/documents.py
@router.get("/{document_id}/word-count", response_model=WordCountResponse)
async def word_count(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WordCountResponse:
    count = await document_service.get_word_count(db, document_id, current_user.id)
    return WordCountResponse(document_id=document_id, word_count=count)
```

### Step 4 — Frontend API function

```typescript
// frontend/src/api/documents.ts
export async function getWordCount(documentId: string): Promise<{ word_count: number }> {
  const { data } = await apiClient.get(`/documents/${documentId}/word-count`);
  return data;
}
```

### Step 5 — Write tests

Add `test_word_count_returns_correct_value` to `tests/integration/test_documents.py`.

---

## 5. Adding a New Rule Type

Rule types determine which rules apply to which sections. Current types: `clause`, `heading`, `definition`, `recital`, `schedule`, `table`, `signature`, `preamble`, `unknown`.

**To add a new type (e.g. `indemnity`)**:

1. Add to `SectionType` enum in `backend/app/db/models/section.py`
2. Add to the Pydantic literal in `backend/app/services/rules/validator.py` (`VALID_SECTION_TYPES`)
3. Add detection logic in `backend/app/services/ingestion/structure_detector.py`
4. Create a new Alembic migration: `make migrate-new MSG="add_indemnity_section_type"`
5. Update `frontend/src/types/api.ts` → `SectionType` union
6. Update `frontend/src/components/ui/StatusBadge.tsx` to colour the new type
7. Add unit tests for detection in `tests/unit/test_structure_detector.py`

---

## 6. Running Tests

### Unit tests only

```bash
cd backend
source venv/Scripts/activate   # Windows
pytest tests/unit -v
```

### Integration tests only

```bash
pytest tests/integration -v
```

### With coverage

```bash
pytest --cov=app --cov-report=html
open htmlcov/index.html
```

### Frontend (Vitest)

```bash
cd frontend
npm run test
npm run test:coverage
```

### End-to-end (Playwright)

Requires the dev server to be running (`make dev`):

```bash
cd frontend
npx playwright test
npx playwright show-report
```

### Test fixtures summary

| Fixture | Scope | Description |
|---------|-------|-------------|
| `db_engine` | function | In-memory SQLite engine; schema created + dropped per test |
| `db_session` | function | Session with autorollback |
| `app` | function | FastAPI app with `get_db` overridden; seeds 4 roles + 1 admin user |
| `client` | function | Unauthenticated `httpx.AsyncClient` |
| `admin_client` | function | Pre-authenticated client with Bearer + CSRF headers |
| `mock_ollama` | function | Patches `OllamaClient.stream()` to yield fake tokens |

---

## 7. Database Migrations

```bash
# Apply all pending migrations
make migrate

# Create a new autogenerated migration
make migrate-new MSG="my_description"

# Always review the generated file in alembic/versions/ before committing
# Auto-generated migrations miss: check constraints, computed columns, custom types

# Rollback one step
make migrate-rollback
```

### Writing migrations manually

Generated migrations use `op.create_table` / `op.add_column`. Always add:
- `sa.Index(...)` for foreign keys and frequently filtered columns
- `sa.UniqueConstraint(...)` for business-unique combinations
- `downgrade()` that precisely reverses `upgrade()`

---

## 8. Common Patterns

### Audit logging

Every state-changing operation should log an audit event:

```python
from app.services.audit.logger import AuditLogger

async def approve_review(db, review_id, actor_id, ...):
    # ... business logic ...
    await AuditLogger(db).log(
        event_type="review.approved",
        actor_id=actor_id,
        resource_type="review",
        resource_id=review_id,
        details={"decision": "approved"},
    )
```

### Dependency injection for the current user

```python
from app.core.deps import get_current_user, require_role
from app.db.models.user import User

# Any authenticated user
async def my_route(current_user: User = Depends(get_current_user)):
    ...

# Admin only
async def admin_route(current_user: User = Depends(require_role("admin"))):
    ...
```

### Pagination

Use the shared `PaginatedResponse[T]` schema and the `paginate()` helper:

```python
from app.schemas.common import PaginatedResponse, paginate

result = await paginate(db, select(MyModel), limit=limit, offset=offset)
return PaginatedResponse[MyModelOut].model_validate(result)
```

### WebSocket progress updates

The `ws.py` router handles job progress. To push updates from a background task:

```python
from app.api.v1.ws import job_progress_queue

await job_progress_queue.put(job_id, JobProgressUpdate(...))
```
