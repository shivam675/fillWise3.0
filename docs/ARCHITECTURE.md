# FillWise 3.0 — System Architecture

## Overview

FillWise 3.0 is a local-first, production-grade legal document transformation platform. It ingests PDF and DOCX documents, applies configurable rule sets, rewrites sections using a local Ollama LLM (ministral-3b), performs risk analysis, and requires explicit human approval before assembling the final output. No document data ever leaves the local machine.

---

## Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────────┐
│                          CLIENT BROWSER                               │
│                  React + TypeScript + Vite + Monaco                   │
└──────────────────────────────┬───────────────────────────────────────┘
                               │ HTTP / WebSocket
┌──────────────────────────────▼───────────────────────────────────────┐
│                        FASTAPI GATEWAY                                │
│                 Auth │ Rate Limiting │ CORS │ CSRF                    │
│                  /api/v1/*  │  /ws/*  │  /health                     │
└──┬──────────────┬────────────┬────────────┬────────────┬─────────────┘
   │              │            │            │            │
   ▼              ▼            ▼            ▼            ▼
Ingestion    Content Map    Rule Engine  Rewrite Orch  Review System
Layer        Engine                     + Risk Engine
   │              │            │            │            │
   └──────────────┴────────────┴────────────┴────────────┘
                               │
                    ┌──────────▼──────────┐
                    │   SQLAlchemy ORM    │
                    │   SQLite / PgSQL    │
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │   Audit Log Store   │
                    │  (hash-chained)     │
                    └─────────────────────┘

                    ┌─────────────────────┐
                    │   Ollama Runtime    │
                    │  ministral-3b:3b    │
                    │  (localhost only)   │
                    └─────────────────────┘
```

---

## Layer Descriptions

### A. Ingestion Layer

Responsible for extracting plain-text content from PDF and DOCX files.

- `pdfplumber` is the primary PDF extractor; `pymupdf` is used as a fallback.
- `python-docx` handles DOCX files, preserving paragraph styles and table structure.
- The structure detector identifies headings, sub-headings, numbered clauses, tables, and lists using heuristics and regex patterns.
- All extracted content is stored as `Section` records with positional metadata.

### B. Content Mapping Engine

Builds a hierarchical semantic graph of the document.

- A `DocumentGraph` object stores parent-child section relationships.
- Sections are classified as: `HEADING`, `CLAUSE`, `DEFINITION`, `TABLE`, `LIST`, `PREAMBLE`, or `APPENDIX`.
- Classification is rule-assisted (pattern matching) with optional LLM confirmation.
- Dependency edges track cross-references between clauses.

### C. Rule Engine

Governs what transformations are applied and how.

- Rules are defined in YAML files conforming to a strict JSON Schema.
- Each rule has: `id`, `name`, `jurisdiction`, `version`, `active`, `conditions`, and `prompt_fragment`.
- Rule files are versioned and stored in the database; changes generate a diff and are logged.
- Conflicting rules (same scope, different instructions) are detected at load time.
- Rules are compiled dynamically into system prompt fragments at job start.

### D. Rewrite Orchestrator

Schedules and executes section rewrites via the Ollama LLM.

- Sections are processed in topological order (dependencies first).
- Each rewrite is idempotent: identical inputs produce the same job hash.
- Supports streaming tokens over WebSocket.
- Retries up to 3 times on transient failures with exponential back-off.
- Implements a simple circuit breaker: after 5 consecutive Ollama failures, jobs pause.

### E. Risk Analysis Engine

Evaluates rewritten content for compliance drift.

- Rule-based checks: numeric value mutation, party name changes, date drift.
- LLM self-review: Ollama is called again to score the rewrite against original intent.
- Semantic deviation score: cosine similarity (TF-IDF) between original and rewrite.
- Each risk finding is stored with severity: `CRITICAL`, `HIGH`, `MEDIUM`, `LOW`.

### F. Review System

Enforces human-in-the-loop approval.

- Diffs are generated with `difflib` (word-level) and stored as structured records.
- Reviewers can: `APPROVE`, `REJECT`, `EDIT`, or `REQUEST_RERUN`.
- Comment threads are attached to individual diff hunks.
- No section may be assembled without `APPROVED` status.
- Rollback restores any prior approved version.

### G. Assembly Engine

Reconstructs the final DOCX from approved sections.

- Rebuilds paragraph structure using `python-docx`.
- Preserves original styles where possible; falls back to Normal style.
- Validates all cross-references before writing output.
- Embeds a manifest block with job ID, approver, and timestamp.

### H. Audit System

Provides an immutable, tamper-resistant log.

- Each event is SHA-256 hashed with the hash of the previous event (chain).
- Events include: document upload, job start, prompt logged, section approved, assembly triggered.
- Hash chain integrity can be verified via `/api/v1/audit/verify`.

---

## Request Flow: Full Document Rewrite

```
1.  User uploads PDF/DOCX              → POST /api/v1/documents
2.  Ingestion extracts & structures     → DocumentProcessor.run()
3.  Content map built                   → DocumentGraph.build()
4.  User selects ruleset                → GET  /api/v1/rulesets
5.  User starts rewrite job             → POST /api/v1/jobs
6.  Orchestrator schedules sections     → RewriteOrchestrator.schedule()
7.  Per-section: prompt compiled        → PromptEngine.compile()
8.  Per-section: LLM call (streaming)   → OllamaClient.stream_completion()
9.  Tokens sent to browser              → WebSocket /ws/jobs/{job_id}
10. Risk analysis runs                  → RiskAnalyzer.analyze()
11. Diff generated                      → DiffService.generate()
12. Reviewer sees side-by-side diff     → GET /api/v1/reviews/{section_id}
13. Reviewer approves                   → POST /api/v1/reviews/{id}/approve
14. Audit event logged                  → AuditLogger.log()
15. All approved → assembly triggered   → AssemblyEngine.build()
16. DOCX output available               → GET /api/v1/documents/{id}/export
```

---

## Entity-Relationship Diagram

```
users ─────────────────────┐
  id                       │
  username                 │
  password_hash            │
  role_id ──────── roles   │
  is_active                │   created_by
  created_at               ▼
  updated_at           documents
                         id
   rulesets ─────────────  ruleset_id
     id                   ingestion_status
     name                 file_hash
     version              created_by ── (users.id)
     jurisdiction         created_at
     schema_version       updated_at
     content_hash         deleted_at
     is_active        
     created_by            sections
     created_at             id
     updated_at             document_id ── (documents.id)
                            parent_id   ── (sections.id)
  rule_conflicts            sequence_no
     id                    section_type
     ruleset_id            original_text
     rule_a_id             content_hash
     rule_b_id             depth
     description
                          rewrite_jobs
  review_comments            id
     id                      document_id ─ (documents.id)
     review_id               ruleset_id  ─ (rulesets.id)
     user_id                 status
     hunk_index              created_by
     body                    started_at
     created_at              completed_at
                             error_message
  section_rewrites
     id
     job_id       ─────────── (rewrite_jobs.id)
     section_id   ─────────── (sections.id)
     prompt_hash
     prompt_text
     rewritten_text
     model_name
     model_version
     tokens_used
     duration_ms
     status

  risk_findings
     id
     rewrite_id  ─── (section_rewrites.id)
     severity
     category
     description
     score

  reviews
     id
     rewrite_id  ─── (section_rewrites.id)
     reviewer_id ─── (users.id)
     status
     edited_text
     diff_json
     reviewed_at

  audit_events
     id
     event_type
     actor_id    ─── (users.id)
     entity_type
     entity_id
     payload_json
     event_hash
     prev_hash
     created_at
```

---

## Security Model

See [SECURITY.md](./SECURITY.md) for full details.

- JWT RS256 tokens; keys stored only on server filesystem.
- Role-based access: `ADMIN`, `EDITOR`, `REVIEWER`, `VIEWER`.
- All uploads sanitized; filenames normalized; MIME types validated.
- Ollama bound to `127.0.0.1` only; no external network calls.
- Secrets managed through environment variables; never in code or config files.
- CSRF double-submit cookie pattern for state-mutating endpoints.
- Rate limiting per user per endpoint (configurable).

---

## Configuration

All runtime configuration lives in environment variables, documented in `.env.example`. The `Settings` Pydantic model validates all values at startup; the server refuses to start with invalid config.

---

## Observability

- Structured JSON logging via `structlog`.
- Correlation IDs (`X-Correlation-ID`) injected into every request/response.
- `/health` endpoint exposes DB connectivity, Ollama reachability, and disk space.
- Metrics endpoint (`/metrics`) in Prometheus format.
