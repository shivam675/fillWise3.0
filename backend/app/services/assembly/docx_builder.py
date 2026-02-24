"""
Assembly Engine: reconstructs a DOCX from approved section rewrites.

Rules:
  - Only sections with an APPROVED review are included.
  - If a review has edited_text, that takes precedence over the LLM output.
  - Sections without a rewrite (no job cover) use the original text.
  - A manifest paragraph is appended at the end with metadata.
  - The output DOCX is written to the export directory.
  - Any residual Markdown formatting from the LLM is converted to proper
    DOCX styles or stripped cleanly.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import structlog
from docx import Document  # type: ignore[import-untyped]
from docx.shared import Pt  # type: ignore[import-untyped]
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import get_settings
from app.core.errors import ConflictError, ErrorCode
from app.db.models.document import Section
from app.db.models.job import JobStatus, RewriteJob, SectionRewrite
from app.db.models.review import Review, ReviewStatus

if TYPE_CHECKING:
    pass

_log = structlog.get_logger(__name__)

# ── Markdown → DOCX helpers ──────────────────────────────────────────── #

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)")          # ### Heading text
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")                # **bold**
_ITALIC_RE = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)")  # *italic*
_BOLD_ITALIC_RE = re.compile(r"\*\*\*(.+?)\*\*\*")     # ***bold italic***
_BULLET_RE = re.compile(r"^[-*]\s+(.*)")                # - item  or  * item
_NUMBERED_RE = re.compile(r"^\d+\.\s+(.*)")             # 1. item
_HR_RE = re.compile(r"^---+\s*$")                       # --- horizontal rule
_FENCE_RE = re.compile(r"^```")                         # ``` code fence
_INLINE_CODE_RE = re.compile(r"`([^`]+)`")              # `code`


def _split_inline_runs(text: str) -> list[tuple[str, bool, bool]]:
    """Split a line into (text, bold, italic) runs, resolving **bold** and *italic*.

    Returns a list of (content, is_bold, is_italic) tuples.
    """
    runs: list[tuple[str, bool, bool]] = []
    # Process bold-italic first, then bold, then italic
    # Use a simple state machine approach via regex split

    # Replace bold-italic → marker, then bold → marker, then italic → marker
    # We'll walk the string with a combined pattern instead.
    pattern = re.compile(r"(\*\*\*(.+?)\*\*\*|\*\*(.+?)\*\*|\*(.+?)\*)")
    last_end = 0
    for m in pattern.finditer(text):
        # Add preceding plain text
        if m.start() > last_end:
            runs.append((text[last_end : m.start()], False, False))
        if m.group(2) is not None:  # ***bold italic***
            runs.append((m.group(2), True, True))
        elif m.group(3) is not None:  # **bold**
            runs.append((m.group(3), True, False))
        elif m.group(4) is not None:  # *italic*
            runs.append((m.group(4), False, True))
        last_end = m.end()
    if last_end < len(text):
        runs.append((text[last_end:], False, False))
    return runs or [("", False, False)]


def _add_rich_paragraph(doc: Document, text: str, style: str = "Normal") -> None:
    """Add a paragraph with inline bold/italic runs properly formatted."""
    # Strip inline code backticks first
    text = _INLINE_CODE_RE.sub(r"\1", text)
    runs = _split_inline_runs(text)
    para = doc.add_paragraph(style=style)
    for content, bold, italic in runs:
        run = para.add_run(content)
        if bold:
            run.bold = True
        if italic:
            run.italic = True


def _render_markdown_block(doc: Document, text: str) -> None:
    """Convert a block of text (potentially with Markdown) into DOCX paragraphs.

    Handles headings, bold/italic, bullet lists, numbered lists, horizontal
    rules, and code fences.  Anything unrecognised is added as a plain paragraph.
    """
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]

        # Skip horizontal rules
        if _HR_RE.match(line):
            i += 1
            continue

        # Skip code fences (and the content between them)
        if _FENCE_RE.match(line.strip()):
            i += 1
            # Skip until closing fence
            while i < len(lines) and not _FENCE_RE.match(lines[i].strip()):
                i += 1
            if i < len(lines):
                i += 1  # skip closing fence
            continue

        # Heading
        hm = _HEADING_RE.match(line)
        if hm:
            level = min(len(hm.group(1)), 4)  # DOCX supports Heading 1-4 well
            heading_text = hm.group(2).strip()
            # Strip any bold markers inside headings
            heading_text = heading_text.replace("**", "")
            para = doc.add_paragraph(heading_text)
            para.style = doc.styles[f"Heading {level}"]
            i += 1
            continue

        # Bullet list item
        bm = _BULLET_RE.match(line)
        if bm:
            _add_rich_paragraph(doc, bm.group(1), "List Bullet")
            i += 1
            continue

        # Numbered list item
        nm = _NUMBERED_RE.match(line)
        if nm:
            _add_rich_paragraph(doc, nm.group(1), "List Number")
            i += 1
            continue

        # Blank line → skip (don't add empty paragraphs)
        if not line.strip():
            i += 1
            continue

        # Regular paragraph with potential inline formatting
        _add_rich_paragraph(doc, line)
        i += 1


class AssemblyEngine:
    """
    Assembles approved rewritten sections into a final DOCX.

    Validates that all rewrites have been reviewed before proceeding.
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._settings = get_settings()

    async def assemble(self, job_id: str, requester_username: str) -> Path:
        """
        Build a DOCX from all approved sections for a completed job.

        Returns:
            Path to the exported DOCX file.

        Raises:
            ConflictError: If any sections are not yet reviewed/approved.
        """
        log = _log.bind(job_id=job_id)

        job = await self._db.get(RewriteJob, job_id)
        if job is None:
            from app.core.errors import NotFoundError
            raise NotFoundError("RewriteJob", job_id)

        if job.status != JobStatus.COMPLETED:
            raise ConflictError(
                ErrorCode.ASSEMBLY_FAILED,
                f"Job is in status '{job.status}'; assembly requires COMPLETED.",
            )

        # Load all sections in order
        section_result = await self._db.execute(
            select(Section)
            .where(Section.document_id == job.document_id)
            .order_by(Section.sequence_no)
        )
        sections: list[Section] = list(section_result.scalars().all())

        # Load all rewrites for this job
        rewrite_result = await self._db.execute(
            select(SectionRewrite).where(SectionRewrite.job_id == job_id)
        )
        rewrites_by_section: dict[str, SectionRewrite] = {
            r.section_id: r for r in rewrite_result.scalars().all()
        }

        # Load all reviews
        rewrite_ids = [r.id for r in rewrites_by_section.values()]
        reviews_by_rewrite: dict[str, Review] = {}
        if rewrite_ids:
            review_result = await self._db.execute(
                select(Review).where(Review.rewrite_id.in_(rewrite_ids))
            )
            reviews_by_rewrite = {r.rewrite_id: r for r in review_result.scalars().all()}

        # Pre-flight: ensure no PENDING reviews
        pending = [
            s.id for s in sections
            if s.id in rewrites_by_section
            and rewrites_by_section[s.id].id not in reviews_by_rewrite
        ]
        if pending:
            raise ConflictError(
                ErrorCode.ASSEMBLY_PENDING_REVIEWS,
                f"{len(pending)} section(s) have not been reviewed yet.",
            )

        non_approved = [
            s.id for s in sections
            if s.id in rewrites_by_section
            and (rw := rewrites_by_section[s.id])
            and (rev := reviews_by_rewrite.get(rw.id))
            and rev.status not in (ReviewStatus.APPROVED, ReviewStatus.EDITED)
        ]
        if non_approved:
            raise ConflictError(
                ErrorCode.ASSEMBLY_PENDING_REVIEWS,
                f"{len(non_approved)} section(s) have not been approved.",
            )

        # Build DOCX
        doc = Document()
        self._set_default_styles(doc)

        for section in sections:
            text = self._resolve_text(section, rewrites_by_section, reviews_by_rewrite)

            if section.heading and section.heading == section.original_text:
                # It's a standalone heading — strip any residual markdown bold
                clean_heading = text.replace("**", "").lstrip("# ").strip()
                para = doc.add_paragraph(clean_heading)
                para.style = doc.styles["Heading 1"]
            else:
                # Render with markdown → DOCX conversion
                _render_markdown_block(doc, text)

        # Manifest
        doc.add_paragraph("")
        manifest_para = doc.add_paragraph()
        manifest_para.add_run("Document Assembly Manifest").bold = True
        doc.add_paragraph(
            json.dumps(
                {
                    "job_id": job_id,
                    "assembled_by": requester_username,
                    "assembled_at": datetime.now(UTC).isoformat(),
                    "fillwise_version": "3.0.0",
                },
                indent=2,
            )
        )

        # Write to export dir
        output_path = self._settings.export_dir / f"{job_id}_{uuid.uuid4().hex[:8]}.docx"
        doc.save(str(output_path))
        log.info("assembly_complete", output_path=str(output_path))
        return output_path

    def _resolve_text(
        self,
        section: Section,
        rewrites: dict[str, SectionRewrite],
        reviews: dict[str, Review],
    ) -> str:
        """Determine the final text for a section, precedence: edit > rewrite > original."""
        rewrite = rewrites.get(section.id)
        if rewrite is None:
            return section.original_text

        review = reviews.get(rewrite.id)
        if review is None:
            return section.original_text

        if review.edited_text:
            text = review.edited_text
        elif rewrite.rewritten_text:
            text = rewrite.rewritten_text
        else:
            return section.original_text

        # Safety net: strip any trailing LLM metadata that slipped through
        from app.services.llm.prompt_engine import _strip_trailing_metadata
        text = _strip_trailing_metadata(text, {})
        return text

    def _set_default_styles(self, doc: Document) -> None:
        """Configure default font for the output document."""
        style = doc.styles["Normal"]
        font = style.font
        font.name = "Times New Roman"
        font.size = Pt(12)
