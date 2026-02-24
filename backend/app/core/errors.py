"""
Structured error taxonomy for FillWise.

Every application error has:
  - A stable error code (prefixed by domain)
  - An HTTP status code
  - A human-readable message template
  - An optional detail dict for machine consumers

No internal state (stack traces, DB internals) is ever surfaced to clients.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any


class ErrorCode(StrEnum):
    """Stable, versioned error codes. Never reuse a retired code."""

    # Auth
    AUTH_INVALID_CREDENTIALS = "AUTH_001"
    AUTH_TOKEN_EXPIRED = "AUTH_002"
    AUTH_TOKEN_INVALID = "AUTH_003"
    AUTH_INSUFFICIENT_PERMISSIONS = "AUTH_004"
    AUTH_USER_INACTIVE = "AUTH_005"
    AUTH_CSRF_INVALID = "AUTH_006"

    # Documents
    DOC_NOT_FOUND = "DOC_001"
    DOC_UPLOAD_FAILED = "DOC_002"
    DOC_MIME_REJECTED = "DOC_003"
    DOC_TOO_LARGE = "DOC_004"
    DOC_EXTRACTION_FAILED = "DOC_005"
    DOC_TOO_MANY_PAGES = "DOC_006"
    DOC_ALREADY_DELETED = "DOC_007"
    DOC_HASH_DUPLICATE = "DOC_008"

    # Rulesets
    RULE_NOT_FOUND = "RULE_001"
    RULE_INVALID_SCHEMA = "RULE_002"
    RULE_CONFLICTS_PRESENT = "RULE_003"
    RULE_ALREADY_ACTIVE = "RULE_004"
    RULE_VERSION_CONFLICT = "RULE_005"

    # Jobs
    JOB_NOT_FOUND = "JOB_001"
    JOB_ALREADY_RUNNING = "JOB_002"
    JOB_DOCUMENT_NOT_READY = "JOB_003"
    JOB_OLLAMA_UNAVAILABLE = "JOB_004"
    JOB_CIRCUIT_OPEN = "JOB_005"

    # Reviews
    REVIEW_NOT_FOUND = "REV_001"
    REVIEW_ALREADY_DECIDED = "REV_002"
    REVIEW_REWRITE_PENDING = "REV_003"

    # Assembly
    ASSEMBLY_PENDING_REVIEWS = "ASM_001"
    ASSEMBLY_FAILED = "ASM_002"

    # Audit
    AUDIT_CHAIN_BROKEN = "AUD_001"

    # Generic
    VALIDATION_ERROR = "GEN_001"
    INTERNAL_ERROR = "GEN_002"
    NOT_FOUND = "GEN_003"
    RATE_LIMITED = "GEN_004"


class AppError(Exception):
    """Base class for all application errors."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        http_status: int = 500,
        detail: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
        self.detail = detail or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": {
                "code": self.code.value,
                "message": self.message,
                "detail": self.detail,
            }
        }


# ── Typed convenience subclasses ──────────────────────────────────────── #


class NotFoundError(AppError):
    def __init__(
        self, entity: str, entity_id: str | None = None, code: ErrorCode = ErrorCode.NOT_FOUND
    ) -> None:
        detail = {"entity": entity}
        if entity_id:
            detail["id"] = entity_id
        super().__init__(
            code=code,
            message=f"{entity} not found",
            http_status=404,
            detail=detail,
        )


class AuthError(AppError):
    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(code=code, message=message, http_status=401)


class ForbiddenError(AppError):
    def __init__(self, message: str = "Insufficient permissions") -> None:
        super().__init__(
            code=ErrorCode.AUTH_INSUFFICIENT_PERMISSIONS,
            message=message,
            http_status=403,
        )


# Backwards-compatible alias
PermissionError = ForbiddenError  # noqa: A001


class ValidationError(AppError):
    def __init__(self, message: str, detail: dict[str, Any] | None = None) -> None:
        super().__init__(
            code=ErrorCode.VALIDATION_ERROR,
            message=message,
            http_status=422,
            detail=detail,
        )


class ConflictError(AppError):
    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(code=code, message=message, http_status=409)


class ServiceUnavailableError(AppError):
    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(code=code, message=message, http_status=503)
