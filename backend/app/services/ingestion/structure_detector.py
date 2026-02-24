"""
Structure detector: classifies raw extracted paragraphs into SectionTypes.

Detection is purely pattern-based (no LLM calls) to keep ingestion fast
and deterministic. The classifier applies rules in priority order and
stops at the first match.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.db.models.document import SectionType
from app.services.ingestion.docx_extractor import ExtractedParagraph

# ── Compiled patterns (module-level for performance) ─────────────────── #

# Heading style names as found in typical DOCX files
_HEADING_STYLE_RE = re.compile(r"^Heading\s*\d+$", re.IGNORECASE)

# Numbered clause: "1.", "1.1", "1.1.1", "Article 3", "Section 4.2"
_NUMBERED_CLAUSE_RE = re.compile(
    r"^(\d+\.(\d+\.)*\d*|Article\s+\d+|Section\s+[\d.]+)",
    re.IGNORECASE,
)

# Definition markers: "Means", "shall mean", "is defined as"
_DEFINITION_RE = re.compile(
    r"\b(means|shall mean|is defined as|hereinafter referred to as)\b",
    re.IGNORECASE,
)

# List markers
_LIST_RE = re.compile(r"^(\s*[-•◦▪‣●]|\s*\([a-zA-Z0-9]{1,3}\)\s|\s*[ivxlIVXL]+\.\s)")

# Appendix / Schedule
_APPENDIX_RE = re.compile(r"^(Appendix|Schedule|Annex|Exhibit)\s+[A-Z0-9]", re.IGNORECASE)

# Preamble indicators at document start
_PREAMBLE_RE = re.compile(
    r"^(THIS AGREEMENT|WHEREAS|RECITALS|PREAMBLE|BACKGROUND)", re.IGNORECASE
)


@dataclass
class StructuredSection:
    """Output of structure detection for one logical section."""

    section_type: SectionType
    heading: str | None
    text: str
    paragraph_indices: list[int] = field(default_factory=list)
    depth: int = 0


def _count_leading_dots(text: str) -> int:
    """Estimate hierarchy depth from numbering pattern (e.g. '1.2.3' → depth 2)."""
    m = _NUMBERED_CLAUSE_RE.match(text)
    if not m:
        return 0
    number_part = m.group(0)
    return max(number_part.count("."), 0)


def _classify_paragraph(para: ExtractedParagraph, is_first: bool) -> SectionType:
    """Apply priority-ordered rules to determine a paragraph's section type."""

    text = para.text.strip()
    style = para.style_name or ""

    if _HEADING_STYLE_RE.match(style):
        return SectionType.HEADING

    if is_first and _PREAMBLE_RE.match(text):
        return SectionType.PREAMBLE

    if _APPENDIX_RE.match(text):
        return SectionType.APPENDIX

    if para.is_bold and len(text) < 200:
        return SectionType.HEADING

    if _NUMBERED_CLAUSE_RE.match(text):
        return SectionType.CLAUSE

    if _DEFINITION_RE.search(text):
        return SectionType.DEFINITION

    if _LIST_RE.match(text):
        return SectionType.LIST

    return SectionType.CLAUSE


def detect_structure(paragraphs: list[ExtractedParagraph]) -> list[StructuredSection]:
    """
    Convert a flat list of ExtractedParagraphs into StructuredSections.

    Adjacent non-heading paragraphs of the same type are merged into a
    single section to avoid fragmenting continuous prose.

    Returns:
        Ordered list of StructuredSection objects.
    """
    if not paragraphs:
        return []

    sections: list[StructuredSection] = []
    current_heading: str | None = None

    for i, para in enumerate(paragraphs):
        sec_type = _classify_paragraph(para, is_first=(i == 0))
        depth = _count_leading_dots(para.text) if sec_type == SectionType.CLAUSE else 0

        if sec_type == SectionType.HEADING:
            current_heading = para.text
            sections.append(
                StructuredSection(
                    section_type=SectionType.HEADING,
                    heading=para.text,
                    text=para.text,
                    paragraph_indices=[para.paragraph_index],
                    depth=depth,
                )
            )
            continue

        # Merge with previous section if same type and not a heading
        if (
            sections
            and sections[-1].section_type == sec_type
            and sec_type not in (SectionType.HEADING, SectionType.APPENDIX)
        ):
            sections[-1].text += "\n" + para.text
            sections[-1].paragraph_indices.append(para.paragraph_index)
        else:
            sections.append(
                StructuredSection(
                    section_type=sec_type,
                    heading=current_heading if sec_type != SectionType.PREAMBLE else None,
                    text=para.text,
                    paragraph_indices=[para.paragraph_index],
                    depth=depth,
                )
            )

    return sections
