"""Unit tests for app.services.review.diff."""
import pytest

from app.services.review.diff import (
    DiffHunk,
    diff_to_json,
    generate_diff,
    json_to_diff,
)


def test_identical_text_all_equal():
    hunks = generate_diff("The cat sat on the mat.", "The cat sat on the mat.")
    assert hunks
    assert all(h.hunk_type == "equal" for h in hunks)


def test_inserted_word():
    hunks = generate_diff("The cat sat.", "The big cat sat.")
    types = {h.hunk_type for h in hunks}
    assert "insert" in types


def test_deleted_word():
    hunks = generate_diff("The big cat sat.", "The cat sat.")
    types = {h.hunk_type for h in hunks}
    assert "delete" in types


def test_replaced_word():
    hunks = generate_diff("The cat sat.", "The dog slept.")
    types = {h.hunk_type for h in hunks}
    assert "replace" in types or ("delete" in types and "insert" in types)


def test_empty_original():
    hunks = generate_diff("", "New content here.")
    types = {h.hunk_type for h in hunks}
    assert "insert" in types


def test_empty_rewrite():
    hunks = generate_diff("Original text here.", "")
    types = {h.hunk_type for h in hunks}
    assert "delete" in types


def test_hunk_fields_present():
    hunks = generate_diff("Hello world.", "Hello earth.")
    for h in hunks:
        assert hasattr(h, "hunk_type")
        assert hasattr(h, "original_text")
        assert hasattr(h, "rewritten_text")
        assert hasattr(h, "start_char")
        assert hasattr(h, "end_char")


def test_serialization_roundtrip():
    original = "The party agrees to pay fifty thousand dollars."
    rewritten = "The party shall pay USD 50,000."
    hunks = generate_diff(original, rewritten)
    serialized = diff_to_json(hunks)
    assert isinstance(serialized, str)
    restored = json_to_diff(serialized)
    assert len(restored) == len(hunks)
    for orig_h, rest_h in zip(hunks, restored):
        assert orig_h.hunk_type == rest_h.hunk_type
        assert orig_h.original_text == rest_h.original_text
        assert orig_h.rewritten_text == rest_h.rewritten_text
        assert orig_h.start_char == rest_h.start_char
        assert orig_h.end_char == rest_h.end_char


def test_coverage_contiguous():
    """All characters in the original should be covered by hunks exactly once."""
    original = "Clause 1. The vendor shall deliver the goods by 31 December."
    rewritten = "Clause 1. The vendor must deliver the goods by 31st December."
    hunks = generate_diff(original, rewritten)
    # Reconstruct original from equal + delete hunks
    reconstructed = "".join(
        h.original_text for h in hunks if h.hunk_type in ("equal", "delete", "replace")
    )
    assert reconstructed == original
