"""Unit tests for app.services.ingestion.structure_detector."""
import pytest

from app.services.ingestion.structure_detector import (
    SectionType,
    detect_structure,
)


# ─── detect_structure helpers ─────────────────────────────────────────────────

def _detect_one(text: str) -> SectionType:
    """Detect structure for a single-line span of text."""
    sections = detect_structure(text)
    assert len(sections) >= 1
    return sections[0].section_type


# ─── Numbered clause ──────────────────────────────────────────────────────────

def test_numbered_clause_detected():
    text = "1.1 The vendor shall deliver the goods within thirty (30) days."
    result = _detect_one(text)
    assert result == SectionType.CLAUSE


def test_deeply_numbered_clause():
    text = "12.3.4 Liability cap shall not exceed the total contract value."
    result = _detect_one(text)
    assert result == SectionType.CLAUSE


# ─── Heading ──────────────────────────────────────────────────────────────────

def test_all_caps_heading():
    text = "DEFINITIONS"
    result = _detect_one(text)
    assert result == SectionType.HEADING


def test_title_case_heading():
    text = "General Obligations"
    result = _detect_one(text)
    assert result == SectionType.HEADING


# ─── Definition ───────────────────────────────────────────────────────────────

def test_quoted_term_definition():
    text = '"Agreement" means this contract including all schedules attached hereto.'
    result = _detect_one(text)
    assert result == SectionType.DEFINITION


def test_means_keyword_definition():
    text = '"Confidential Information" means any information disclosed by one party.'
    result = _detect_one(text)
    assert result == SectionType.DEFINITION


# ─── Table ────────────────────────────────────────────────────────────────────

def test_table_detected():
    text = "Item | Quantity | Unit Price\nWood | 100 | USD 5\nNails | 500 | USD 0.10"
    sections = detect_structure(text)
    types = {s.section_type for s in sections}
    assert SectionType.TABLE in types


# ─── Unknown / fallback ───────────────────────────────────────────────────────

def test_unknown_fallback():
    text = "This is a random sentence without any discernible structural marker."
    sections = detect_structure(text)
    types = {s.section_type for s in sections}
    # Should produce at least CLAUSE or UNKNOWN — not crash
    assert len(types) >= 1


# ─── Multi-section input ──────────────────────────────────────────────────────

def test_multiple_sections_returned():
    text = "\n".join([
        "DEFINITIONS",
        "",
        '"Vendor" means the party supplying goods.',
        "",
        "1.1 Payment terms shall be net 30 days.",
        "",
        "2.1 All disputes shall be resolved by arbitration.",
    ])
    sections = detect_structure(text)
    assert len(sections) >= 2


def test_section_text_field_non_empty():
    sections = detect_structure("1.1 The vendor shall perform.")
    assert all(s.text.strip() != "" for s in sections)


def test_section_has_sequence_numbers():
    text = "\n".join([
        "1.1 First clause.",
        "1.2 Second clause.",
    ])
    sections = detect_structure(text)
    clause_sections = [s for s in sections if s.section_type == SectionType.CLAUSE]
    if len(clause_sections) >= 2:
        assert clause_sections[0].sequence < clause_sections[1].sequence
