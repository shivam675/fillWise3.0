# Security Model

FillWise 3.0 is designed for **local-only** operation. No data is transmitted to external services. This document describes all security controls.

---

## Authentication

### Credential storage

Passwords are hashed with **bcrypt** at cost factor 12. The raw password is never stored, logged, or returned via any API endpoint.

### JWT tokens

- **Algorithm**: HS256 (HMAC-SHA256)
- **Secret**: `JWT_SECRET` environment variable (operator-supplied, ≥32 characters)
- **Access token lifetime**: `JWT_ACCESS_EXPIRE_MINUTES` (default 30 min)
- **Refresh token lifetime**: `JWT_REFRESH_EXPIRE_DAYS` (default 7 days)
- Access tokens are short-lived and sent in the `Authorization: Bearer` header.
- Refresh tokens are single-use in concept — issuing a new access token does not invalidate the refresh token, but a compromised refresh token should be mitigated by revoking the user account.

### CSRF protection

All state-changing endpoints (`POST`, `PUT`, `PATCH`, `DELETE`) require the `X-CSRF-Token` header to match the value in the `csrf_token` cookie (double-submit cookie pattern). The cookie is `HttpOnly=false` (so JavaScript can read it) but `SameSite=Strict`. This defends against cross-site form submissions and cross-origin fetch attacks.

---

## Authorization (RBAC)

Four roles, applied via `require_role()` FastAPI dependency:

| Role | Capabilities |
|------|-------------|
| `admin` | All operations including user management and audit log access |
| `editor` | Upload documents, manage rulesets, create and run jobs |
| `reviewer` | View documents + jobs, perform reviews |
| `viewer` | Read-only access to documents and completed reviews |

Role checks are enforced at the route level. Service functions also validate ownership (users can only access their own documents unless they are admins).

---

## Audit Log

Every state-changing operation is recorded in the `audit_events` table. The log is **tamper-evident**:

1. Each event's canonical JSON (actor, event_type, resource, details, timestamp) is hashed with SHA-256 → `event_hash`.
2. Each event's `prev_hash` is set to the `event_hash` of the immediately preceding event.
3. The chain can be verified at any time: `GET /api/v1/audit/verify` → `{"valid": true/false, "broken_at": <id or null>}`.

Any modification to a historical event will break the hash chain at that point. This does not prevent deletion by a DBA with direct database access — for that, use PostgreSQL audit triggers or an append-only WAL setup.

---

## Transport Security

FillWise does **not** terminate TLS itself. Deploy behind a reverse proxy (nginx, Caddy, or Traefik) that:

- Redirects HTTP → HTTPS
- Sets `HSTS: max-age=31536000; includeSubDomains`
- Presents a valid certificate

The backend sets the following security headers via `SecurityHeadersMiddleware`:

| Header | Value |
|--------|-------|
| `X-Content-Type-Options` | `nosniff` |
| `X-Frame-Options` | `DENY` |
| `Referrer-Policy` | `strict-origin-when-cross-origin` |
| `Permissions-Policy` | `camera=(), microphone=(), geolocation=()` |
| `Content-Security-Policy` | `default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'` |

---

## Rate Limiting

Implemented via `slowapi` (Redis-backed in production; in-memory for development):

| Endpoint group | Default limit |
|----------------|--------------|
| `POST /auth/login` | 20 requests / minute / IP |
| `POST /auth/refresh` | 20 requests / minute / IP |
| `POST /documents/` (upload) | 10 requests / minute / IP |
| All other endpoints | 200 requests / minute / IP |

Limits are configurable via environment variables.

---

## File Upload Security

- MIME type is validated against `ALLOWED_MIME_TYPES` (not just file extension).
- File size is capped at `MAX_UPLOAD_BYTES` (default 10 MB) before reading the body.
- Uploaded files are stored with a UUID-based filename (not the original filename) to prevent path traversal.
- The original filename is stored in the `documents` table for display only.
- Files are stored in `UPLOAD_DIR`, which should be on a separate volume with `700` permissions.

---

## LLM Data Handling

- All LLM calls go to `OLLAMA_BASE_URL` (default `http://127.0.0.1:11434`) — the model runs locally.
- No document content is sent to any external API.
- Prompts are logged only in `audit_events.details` at `DEBUG` log level — turn off debug logging in production if prompt content is considered sensitive.
- Circuit breaker (3-state: CLOSED → OPEN → HALF_OPEN) prevents cascading failures if Ollama is unavailable.

---

## Dependency Security

Run `pip-audit` periodically to check for known CVEs:

```bash
pip install pip-audit
pip-audit -r backend/requirements/base.txt
```

For the frontend:

```bash
cd frontend
npm audit
```

---

## Incident Response

1. **Suspected token leakage**: Change `JWT_SECRET` in `.env` and restart the service. All existing tokens are immediately invalidated.
2. **Suspected audit log tampering**: `GET /api/v1/audit/verify` will return `{"valid": false, "broken_at": "<event_id>"}`. Preserve the database as evidence before any writes.
3. **Brute-force attack**: Rate limiter will kick in after 20 failed attempts per minute per IP. Consider adding `fail2ban` at the reverse proxy level for persistent attackers.
4. **Compromised admin account**: Delete the account via the database directly (`DELETE FROM users WHERE username = '...'`), then create a new admin via the API seed or the admin panel with a different account.
