"""
Prompt compiler: assembles system and user prompts for LLM rewrites.

No prompts are hardcoded. All components are injected at compile time.
Every compiled prompt is deterministic and logged for audit purposes.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

import structlog

from app.db.models.document import SectionType

_log = structlog.get_logger(__name__)

# ── Trailing metadata stripper ────────────────────────────────────────── #

# Matches a trailing JSON block containing "rules_applied" or "confidence",
# optionally preceded by a ``---`` separator line. The LLM sometimes emits
# this even though we ask for the AUDIT_JSON: prefix.
_TRAILING_META_RE = re.compile(
    r"""
    (?:\n---\s*\n|\n\n)       # separator: ``---`` line or double newline
    \{[^{}]*                   # opening brace + any non-brace chars
    "(?:rules_applied|confidence)"   # must mention a known audit key
    [^{}]*\}\s*$               # rest of object + closing brace + trailing ws
    """,
    re.DOTALL | re.VERBOSE,
)

# Catches the fenced-code-block variant:
#   ---\n[AUDIT_JSON:]\n```json\n{...}\n```
_FENCED_AUDIT_RE = re.compile(
    r"""
    (?:\n---\s*\n|\n\n)                 # separator
    (?:\*{0,2}AUDIT_JSON:?\*{0,2}\s*\n)?  # optional AUDIT_JSON: label (possibly bold)
    ```(?:json)?\s*\n                   # opening fence
    (\{.*?\})                           # JSON object (captured, non-greedy)
    \s*```\s*$                          # closing fence
    """,
    re.DOTALL | re.VERBOSE,
)

# Same but without the --- separator (just starts after a newline)
_FENCED_AUDIT_NO_SEP_RE = re.compile(
    r"""
    \n\*{0,2}AUDIT_JSON:?\*{0,2}\s*\n  # AUDIT_JSON: label (possibly bold)
    ```(?:json)?\s*\n                   # opening fence
    (\{.*?\})                           # JSON object (captured, non-greedy)
    \s*```\s*$                          # closing fence
    """,
    re.DOTALL | re.VERBOSE,
)


def _strip_trailing_metadata(text: str, audit: dict[str, Any]) -> str:
    """Remove trailing audit metadata from the rewritten text.

    Handles bare JSON blocks, fenced code blocks with/without AUDIT_JSON
    label, and bold Markdown variants.  Parsed JSON is merged into *audit*.
    """
    original_len = len(text)

    # Try fenced-code-block patterns first (most specific)
    for pattern in (_FENCED_AUDIT_RE, _FENCED_AUDIT_NO_SEP_RE):
        m = pattern.search(text)
        if m:
            json_str = m.group(1).strip()
            try:
                parsed = json.loads(json_str)
                if isinstance(parsed, dict):
                    audit.update(parsed)
            except json.JSONDecodeError:
                pass
            text = text[: m.start()].rstrip()
            _log.debug(
                "stripped_trailing_metadata",
                chars_removed=original_len - len(text),
                variant="fenced",
            )
            # Fall through — there may also be a bare block earlier

    # Try bare JSON block pattern
    m = _TRAILING_META_RE.search(text)
    if m:
        json_start = m.group().find("{")
        json_str = m.group()[json_start:].strip()
        try:
            parsed = json.loads(json_str)
            if isinstance(parsed, dict):
                audit.update(parsed)
        except json.JSONDecodeError:
            pass
        text = text[: m.start()].rstrip()
        _log.debug(
            "stripped_trailing_metadata",
            chars_removed=original_len - len(text),
            variant="bare",
        )

    return text

# ── Base instructions (invariant) ─────────────────────────────────────── #

_BASE_SYSTEM_INSTRUCTIONS = """\
You are a legal document editor. Your task is to rewrite the provided section \
of a legal document according to the rules below.

Strict requirements:
- Preserve all legal obligations, rights, and defined terms.
- Do NOT alter party names, dates, monetary amounts, or reference numbers unless \
  a rule explicitly requires it.
- Do NOT introduce new legal obligations that are not present in the original.
- Output ONLY the rewritten section text as PLAIN TEXT.
- ABSOLUTELY NO MARKDOWN FORMATTING: do NOT use ** (bold), * (italic), \
  ### (headings), ``` (code fences), --- (horizontal rules), or any other \
  Markdown syntax. The output is inserted directly into a Word document, so \
  any such characters will appear literally.
- Do NOT output bullet lists with - or *. Write items as flowing sentences \
  or numbered clauses (1., 2., etc.).
- No commentary, no preamble, no section labels.
- If you cannot apply a rule without introducing legal risk, output the original text \
  unchanged and prefix your response with [NO-CHANGE].
- Maintain the same structural level (heading/clause/definition/etc.) as the original.
"""

_AUDIT_INSTRUCTION = """\
At the very end of your response, on ONE new line, output exactly this format \
(no code fences, no markdown, no extra whitespace, no --- separators):
AUDIT_JSON:{"rules_applied": ["<rule-id>", ...], "confidence": <0.0-1.0>}
The JSON must be on the SAME line as AUDIT_JSON: with no line break between them.
"""


@dataclass
class CompiledPrompt:
    """The output of PromptEngine.compile()."""

    system_prompt: str
    user_prompt: str
    prompt_hash: str
    applied_rule_ids: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "system_prompt": self.system_prompt,
            "user_prompt": self.user_prompt,
            "prompt_hash": self.prompt_hash,
            "applied_rule_ids": self.applied_rule_ids,
        }


class PromptEngine:
    """
    Compiles prompts from rules, section context, and safety instructions.

    Design principles:
    - Reproducible: same inputs → same hash.
    - Auditable: every prompt is stored with the rewrite record.
    - No side effects: pure function.
    """

    def compile(
        self,
        rules_json: str,
        section_type: SectionType,
        original_text: str,
        section_heading: str | None,
        jurisdiction: str | None = None,
        dependency_context: str | None = None,
    ) -> CompiledPrompt:
        """
        Compile a full prompt pair (system + user) for a section rewrite.

        Args:
            rules_json: JSON string of the activated ruleset's rules array.
            section_type: The detected type of this section.
            original_text: The verbatim original text to rewrite.
            section_heading: Heading under which this section falls (may be None).
            jurisdiction: Optional jurisdiction constraint (e.g. "UAE", "UK").
            dependency_context: Optional text from referenced clauses.

        Returns:
            CompiledPrompt with hashed prompt and applied rule IDs.
        """
        rules: list[dict[str, Any]] = json.loads(rules_json)

        # In simplified rules, all rules apply to all sections
        applicable = rules

        rule_fragments = "\n".join(
            f"[Rule {r['id']}] {r['instruction']}"
            for r in applicable
        )

        system_parts = [_BASE_SYSTEM_INSTRUCTIONS]

        if jurisdiction:
            system_parts.append(
                f"\nJurisdiction context: This document is governed under {jurisdiction} law. "
                f"All rewrites must remain compliant with {jurisdiction} legal standards.\n"
            )

        if rule_fragments:
            system_parts.append(f"\nApplicable transformation rules:\n{rule_fragments}\n")
        else:
            system_parts.append(
                "\nNo specific transformation rules apply. Preserve original intent.\n"
            )

        system_parts.append(_AUDIT_INSTRUCTION)
        system_prompt = "".join(system_parts)

        # User prompt: context + section to rewrite
        user_parts: list[str] = []

        if section_heading:
            user_parts.append(f"Section heading: {section_heading}")

        user_parts.append(f"Section type: {section_type.value}")

        if dependency_context:
            user_parts.append(
                f"Relevant context from referenced sections:\n{dependency_context}"
            )

        user_parts.append(f"\nOriginal section text:\n{original_text}")
        user_parts.append("\nRewritten section text:")
        user_prompt = "\n".join(user_parts)

        # Hash covers all inputs for reproducibility
        hash_input = json.dumps(
            {
                "system": system_prompt,
                "user": user_prompt,
                "rule_ids": [r["id"] for r in applicable],
            },
            sort_keys=True,
        )
        prompt_hash = hashlib.sha256(hash_input.encode()).hexdigest()

        _log.debug(
            "prompt_compiled",
            prompt_hash=prompt_hash,
            applicable_rules=[r["id"] for r in applicable],
            section_type=section_type.value,
        )

        return CompiledPrompt(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            prompt_hash=prompt_hash,
            applied_rule_ids=[r["id"] for r in applicable],
        )

    @staticmethod
    def extract_audit_json(raw_response: str) -> tuple[str, dict[str, Any]]:
        """
        Split the LLM response into (clean_text, audit_dict).

        The LLM is instructed to append an AUDIT_JSON: line.
        Handles multiple formats:
          1. AUDIT_JSON:{"rules_applied": ...}     (same-line, ideal)
          2. AUDIT_JSON:\\n```json\\n{...}\\n```    (fenced code block)
          3. Bare trailing JSON after --- or blank line
        """
        lines = raw_response.rstrip().split("\n")
        audit: dict[str, Any] = {}
        text_lines: list[str] = []
        skip_until_fence_close = False
        collecting_fenced_json: list[str] = []

        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            # Currently inside a fenced block after AUDIT_JSON:
            if skip_until_fence_close:
                if stripped.startswith("```"):
                    # End of fenced block — parse collected JSON
                    json_str = "\n".join(collecting_fenced_json).strip()
                    try:
                        audit = json.loads(json_str)
                    except json.JSONDecodeError:
                        _log.warning("audit_json_fenced_parse_failed", raw=json_str[:200])
                    skip_until_fence_close = False
                    collecting_fenced_json = []
                else:
                    collecting_fenced_json.append(line)
                i += 1
                continue

            if stripped.startswith("AUDIT_JSON:") or stripped.startswith("**AUDIT_JSON"):
                # Strip markdown bold wrapper if present
                json_part = stripped
                json_part = json_part.replace("**AUDIT_JSON:**", "AUDIT_JSON:")
                json_part = json_part.replace("**AUDIT_JSON**:", "AUDIT_JSON:")
                json_part = json_part.replace("**AUDIT_JSON:", "AUDIT_JSON:")
                json_part = json_part[len("AUDIT_JSON:"):].strip()

                if json_part.startswith("{"):
                    # Same-line JSON (ideal format)
                    try:
                        audit = json.loads(json_part)
                    except json.JSONDecodeError:
                        _log.warning("audit_json_parse_failed", raw=json_part[:200])
                elif json_part.startswith("```") or json_part == "":
                    # Fenced block follows on next line(s), or is on this line
                    if json_part.startswith("```"):
                        # ``` on same line as AUDIT_JSON:
                        skip_until_fence_close = True
                    elif i + 1 < len(lines) and lines[i + 1].strip().startswith("```"):
                        # ``` on next line
                        i += 1  # skip the opening fence line
                        skip_until_fence_close = True
                # Don't add AUDIT_JSON lines to output
                i += 1
                continue

            # Skip standalone opening fences that follow --- (part of audit block)
            # But only if they come right after a --- separator
            text_lines.append(line)
            i += 1

        clean_text = "\n".join(text_lines).strip()

        # Final safety net: strip trailing JSON metadata blocks
        clean_text = _strip_trailing_metadata(clean_text, audit)

        return clean_text, audit
