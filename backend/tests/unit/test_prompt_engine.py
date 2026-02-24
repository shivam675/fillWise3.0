"""Unit tests for app.services.llm.prompt_engine."""
import pytest

from app.services.llm.prompt_engine import PromptEngine, extract_audit_json


MINIMAL_RULE = {
    "id": "PLN-001",
    "section_types": ["clause"],
    "instruction": "Rewrite in plain English.",
    "priority": 10,
    "preserve_numbers": True,
    "preserve_dates": True,
    "preserve_parties": True,
    "tags": [],
}


MULTI_RULE = [
    MINIMAL_RULE,
    {
        "id": "FMT-001",
        "section_types": ["heading"],
        "instruction": "Title-case headings.",
        "priority": 5,
        "preserve_numbers": False,
        "preserve_dates": False,
        "preserve_parties": False,
        "tags": [],
    },
]


@pytest.fixture()
def engine() -> PromptEngine:
    return PromptEngine()


# ─── compile ──────────────────────────────────────────────────────────────────

def test_compile_returns_nonempty_string(engine):
    prompt = engine.compile(
        section_text="The lessee shall pay the lessor the sum of USD 1,000 monthly.",
        section_type="clause",
        rules=[MINIMAL_RULE],
    )
    assert isinstance(prompt, str)
    assert len(prompt) > 50


def test_compile_includes_section_text(engine):
    text = "The licensor grants a non-exclusive licence."
    prompt = engine.compile(
        section_text=text,
        section_type="clause",
        rules=[MINIMAL_RULE],
    )
    assert text in prompt or text[:30] in prompt


def test_compile_includes_instructions(engine):
    prompt = engine.compile(
        section_text="Some clause.",
        section_type="clause",
        rules=[MINIMAL_RULE],
    )
    assert "plain English" in prompt.lower() or "PLN-001" in prompt


def test_compile_filters_by_section_type(engine):
    """Rules for 'heading' should not appear when section_type is 'clause'."""
    prompt = engine.compile(
        section_text="Some clause text.",
        section_type="clause",
        rules=MULTI_RULE,
    )
    # FMT-001 targets headings only — its instruction should be absent
    assert "Title-case" not in prompt


def test_compile_includes_matching_section_type(engine):
    prompt = engine.compile(
        section_text="DEFINITIONS",
        section_type="heading",
        rules=MULTI_RULE,
    )
    assert "Title-case" in prompt or "FMT-001" in prompt


def test_preserve_flags_mentioned(engine):
    prompt = engine.compile(
        section_text="Pay USD 5,000 by 1 Jan.",
        section_type="clause",
        rules=[MINIMAL_RULE],
    )
    assert "number" in prompt.lower() or "date" in prompt.lower() or "party" in prompt.lower()


# ─── prompt_hash determinism ──────────────────────────────────────────────────

def test_prompt_hash_is_deterministic(engine):
    h1 = engine.prompt_hash(
        section_text="Test text.",
        section_type="clause",
        rules=[MINIMAL_RULE],
    )
    h2 = engine.prompt_hash(
        section_text="Test text.",
        section_type="clause",
        rules=[MINIMAL_RULE],
    )
    assert h1 == h2


def test_prompt_hash_differs_for_different_text(engine):
    h1 = engine.prompt_hash(
        section_text="Text A.",
        section_type="clause",
        rules=[MINIMAL_RULE],
    )
    h2 = engine.prompt_hash(
        section_text="Text B.",
        section_type="clause",
        rules=[MINIMAL_RULE],
    )
    assert h1 != h2


def test_prompt_hash_is_hex_string(engine):
    h = engine.prompt_hash(
        section_text="Content.",
        section_type="clause",
        rules=[MINIMAL_RULE],
    )
    assert isinstance(h, str)
    assert all(c in "0123456789abcdef" for c in h.lower())


# ─── extract_audit_json ───────────────────────────────────────────────────────

def test_extract_audit_json_parses_valid_suffix():
    raw = 'The vendor shall pay.\n\n{"rules_applied": ["PLN-001"], "flags": [], "confidence": 0.9}'
    result = extract_audit_json(raw)
    assert result is not None
    assert result["rules_applied"] == ["PLN-001"]
    assert result["confidence"] == pytest.approx(0.9)


def test_extract_audit_json_returns_none_when_missing():
    raw = "The vendor shall pay. No JSON here at all."
    result = extract_audit_json(raw)
    assert result is None


def test_extract_audit_json_strips_trailing_json_from_text():
    raw = 'Clean rewrite text.\n{"rules_applied": [], "flags": ["AUDIT_REQUIRED"], "confidence": 0.7}'
    result = extract_audit_json(raw)
    assert result is not None
    assert "AUDIT_REQUIRED" in result["flags"]
