"""Database model registry. Import all models here so Alembic can discover them."""

from app.db.models.audit import AuditEvent
from app.db.models.document import Document, DocumentStatus, Section, SectionType
from app.db.models.job import (
    JobStatus,
    RewriteJob,
    RewriteStatus,
    RiskFinding,
    RiskSeverity,
    SectionRewrite,
)
from app.db.models.review import Review, ReviewComment, ReviewStatus
from app.db.models.ruleset import RuleConflict, Ruleset
from app.db.models.user import Role, RoleEnum, User

__all__ = [
    "AuditEvent",
    "Document",
    "DocumentStatus",
    "JobStatus",
    "Review",
    "ReviewComment",
    "ReviewStatus",
    "RewriteJob",
    "RewriteStatus",
    "RiskFinding",
    "RiskSeverity",
    "Role",
    "RoleEnum",
    "RuleConflict",
    "Ruleset",
    "Section",
    "SectionRewrite",
    "SectionType",
    "User",
]
