"""Initial schema — all tables.

Revision ID: 0001_initial
Revises: 
Create Date: 2026-02-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # roles
    op.create_table(
        "roles",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(50), nullable=False, unique=True),
        sa.Column("description", sa.String(255), nullable=False, default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_roles_name", "roles", ["name"])

    # users
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("username", sa.String(100), nullable=False),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, default=True),
        sa.Column("role_id", sa.String(36), sa.ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("username", name="uq_users_username"),
    )
    op.create_index("ix_users_username", "users", ["username"])
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_users_role_id", "users", ["role_id"])
    op.create_index("ix_users_deleted_at", "users", ["deleted_at"])

    # documents
    op.create_table(
        "documents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("filename", sa.String(500), nullable=False),
        sa.Column("original_filename", sa.String(500), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger, nullable=False),
        sa.Column("file_hash", sa.String(64), nullable=False),
        sa.Column("page_count", sa.Integer, nullable=True),
        sa.Column("status", sa.String(50), nullable=False, default="pending"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_documents_file_hash", "documents", ["file_hash"])
    op.create_index("ix_documents_status", "documents", ["status"])
    op.create_index("ix_documents_deleted_at", "documents", ["deleted_at"])

    # sections
    op.create_table(
        "sections",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("document_id", sa.String(36), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("parent_id", sa.String(36), sa.ForeignKey("sections.id", ondelete="SET NULL"), nullable=True),
        sa.Column("sequence_no", sa.Integer, nullable=False),
        sa.Column("depth", sa.Integer, nullable=False, default=0),
        sa.Column("section_type", sa.String(50), nullable=False),
        sa.Column("heading", sa.String(500), nullable=True),
        sa.Column("original_text", sa.Text, nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("page_start", sa.Integer, nullable=True),
        sa.Column("page_end", sa.Integer, nullable=True),
        sa.Column("char_count", sa.Integer, nullable=False, default=0),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_sections_document_id", "sections", ["document_id"])
    op.create_index("ix_sections_parent_id", "sections", ["parent_id"])
    op.create_index("ix_sections_content_hash", "sections", ["content_hash"])
    op.create_index("ix_sections_section_type", "sections", ["section_type"])

    # rulesets
    op.create_table(
        "rulesets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("jurisdiction", sa.String(100), nullable=True),
        sa.Column("version", sa.String(50), nullable=False),
        sa.Column("schema_version", sa.String(20), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, default=False),
        sa.Column("rules_json", sa.Text, nullable=False),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("name", "version", name="uq_rulesets_name_version"),
    )
    op.create_index("ix_rulesets_name", "rulesets", ["name"])
    op.create_index("ix_rulesets_is_active", "rulesets", ["is_active"])
    op.create_index("ix_rulesets_jurisdiction", "rulesets", ["jurisdiction"])

    # rule_conflicts
    op.create_table(
        "rule_conflicts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("ruleset_id", sa.String(36), sa.ForeignKey("rulesets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rule_a_id", sa.String(255), nullable=False),
        sa.Column("rule_b_id", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("is_resolved", sa.Boolean, nullable=False, default=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_rule_conflicts_ruleset_id", "rule_conflicts", ["ruleset_id"])

    # rewrite_jobs
    op.create_table(
        "rewrite_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("document_id", sa.String(36), sa.ForeignKey("documents.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("ruleset_id", sa.String(36), sa.ForeignKey("rulesets.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, default="pending"),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("total_sections", sa.Integer, nullable=False, default=0),
        sa.Column("completed_sections", sa.Integer, nullable=False, default=0),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_rewrite_jobs_document_id", "rewrite_jobs", ["document_id"])
    op.create_index("ix_rewrite_jobs_status", "rewrite_jobs", ["status"])
    op.create_index("ix_rewrite_jobs_created_by", "rewrite_jobs", ["created_by"])

    # section_rewrites
    op.create_table(
        "section_rewrites",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("job_id", sa.String(36), sa.ForeignKey("rewrite_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("section_id", sa.String(36), sa.ForeignKey("sections.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, default="pending"),
        sa.Column("prompt_hash", sa.String(64), nullable=False),
        sa.Column("prompt_text", sa.Text, nullable=False),
        sa.Column("rewritten_text", sa.Text, nullable=True),
        sa.Column("model_name", sa.String(100), nullable=False),
        sa.Column("model_version", sa.String(50), nullable=True),
        sa.Column("tokens_prompt", sa.Integer, nullable=False, default=0),
        sa.Column("tokens_completion", sa.Integer, nullable=False, default=0),
        sa.Column("duration_ms", sa.Integer, nullable=False, default=0),
        sa.Column("attempt_number", sa.Integer, nullable=False, default=1),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_section_rewrites_job_id", "section_rewrites", ["job_id"])
    op.create_index("ix_section_rewrites_section_id", "section_rewrites", ["section_id"])
    op.create_index("ix_section_rewrites_status", "section_rewrites", ["status"])

    # risk_findings
    op.create_table(
        "risk_findings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("rewrite_id", sa.String(36), sa.ForeignKey("section_rewrites.id", ondelete="CASCADE"), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("score", sa.Float, nullable=False, default=0.0),
        sa.Column("detail_json", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_risk_findings_rewrite_id", "risk_findings", ["rewrite_id"])
    op.create_index("ix_risk_findings_severity", "risk_findings", ["severity"])

    # reviews
    op.create_table(
        "reviews",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("rewrite_id", sa.String(36), sa.ForeignKey("section_rewrites.id", ondelete="RESTRICT"), nullable=False, unique=True),
        sa.Column("reviewer_id", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, default="pending"),
        sa.Column("edited_text", sa.Text, nullable=True),
        sa.Column("diff_json", sa.Text, nullable=True),
        sa.Column("risk_override_reason", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_reviews_rewrite_id", "reviews", ["rewrite_id"])
    op.create_index("ix_reviews_reviewer_id", "reviews", ["reviewer_id"])
    op.create_index("ix_reviews_status", "reviews", ["status"])

    # review_comments
    op.create_table(
        "review_comments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("review_id", sa.String(36), sa.ForeignKey("reviews.id", ondelete="CASCADE"), nullable=False),
        sa.Column("parent_comment_id", sa.String(36), sa.ForeignKey("review_comments.id", ondelete="SET NULL"), nullable=True),
        sa.Column("author_id", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("hunk_index", sa.Integer, nullable=True),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("is_resolved", sa.Boolean, nullable=False, default=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_review_comments_review_id", "review_comments", ["review_id"])

    # audit_events
    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("actor_id", sa.String(36), nullable=True),
        sa.Column("actor_username", sa.String(100), nullable=True),
        sa.Column("entity_type", sa.String(100), nullable=True),
        sa.Column("entity_id", sa.String(36), nullable=True),
        sa.Column("correlation_id", sa.String(36), nullable=True),
        sa.Column("payload_json", sa.Text, nullable=True),
        sa.Column("event_hash", sa.String(64), nullable=False),
        sa.Column("prev_hash", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("event_hash", name="uq_audit_event_hash"),
    )
    op.create_index("ix_audit_events_event_type", "audit_events", ["event_type"])
    op.create_index("ix_audit_events_actor_id", "audit_events", ["actor_id"])
    op.create_index("ix_audit_events_correlation_id", "audit_events", ["correlation_id"])
    op.create_index(
        "ix_audit_events_actor_entity",
        "audit_events",
        ["actor_id", "entity_type", "entity_id"],
    )


def downgrade() -> None:
    for table in [
        "audit_events", "review_comments", "reviews", "risk_findings",
        "section_rewrites", "rewrite_jobs", "rule_conflicts", "rulesets",
        "sections", "documents", "users", "roles",
    ]:
        op.drop_table(table)
