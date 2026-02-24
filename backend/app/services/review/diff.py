"""
Diff service: generates structured word-level diffs between original and rewritten text.

Uses difflib SequenceMatcher for O(n) performance on typical legal clause lengths.
Output is serializable to JSON and used in the review UI.
"""

from __future__ import annotations

import difflib
import json
import re
from dataclasses import asdict, dataclass


@dataclass
class DiffHunk:
    """A single diff operation block."""

    index: int
    operation: str   # "equal" | "insert" | "delete" | "replace"
    original: str
    rewritten: str


def _word_tokenize(text: str) -> list[str]:
    """
    Split text into a token stream for word-level diffing.

    Preserves whitespace as tokens so reassembly is lossless.
    """
    return re.split(r"(\s+)", text)


def generate_diff(original: str, rewritten: str) -> list[DiffHunk]:
    """
    Produce a word-level structured diff of two text strings.

    Returns:
        List of DiffHunk objects ordered by position in the original.
    """
    orig_tokens = _word_tokenize(original)
    new_tokens = _word_tokenize(rewritten)

    matcher = difflib.SequenceMatcher(
        isjunk=None, a=orig_tokens, b=new_tokens, autojunk=False
    )

    hunks: list[DiffHunk] = []
    index = 0

    for opcode, a0, a1, b0, b1 in matcher.get_opcodes():
        original_chunk = "".join(orig_tokens[a0:a1])
        rewritten_chunk = "".join(new_tokens[b0:b1])

        hunks.append(
            DiffHunk(
                index=index,
                operation=opcode,    # difflib uses: "equal", "insert", "delete", "replace"
                original=original_chunk,
                rewritten=rewritten_chunk,
            )
        )
        index += 1

    return hunks


def diff_to_json(hunks: list[DiffHunk]) -> str:
    """Serialise diff hunks to a compact JSON string for DB storage."""
    return json.dumps([asdict(h) for h in hunks], ensure_ascii=False)


def json_to_diff(raw: str) -> list[DiffHunk]:
    """Deserialise a JSON diff string back to DiffHunk objects."""
    return [DiffHunk(**h) for h in json.loads(raw)]


def has_changes(hunks: list[DiffHunk]) -> bool:
    """Return True if the diff contains any non-equal operations."""
    return any(h.operation != "equal" for h in hunks)
