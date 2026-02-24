"""
Rule YAML schema definition and validator.

All rule files must conform to RULE_SCHEMA. Validation is strict.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import jsonschema
import yaml

from app.core.errors import ValidationError

# Module-level constant: pairs of contradictory keyword sets for conflict detection
_NEGATION_PAIRS: list[tuple[set[str], set[str]]] = [
    ({"use", "apply", "include"}, {"remove", "exclude", "delete", "avoid"}),
]

RULE_SCHEMA: dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "FillWise Rule Set",
    "type": "object",
    "required": ["name", "version", "rules"],
    "additionalProperties": False,
    "properties": {
        "name": {"type": "string", "minLength": 3, "maxLength": 255},
        "description": {"type": "string", "maxLength": 2000},
        "version": {"type": "string", "pattern": r"^\d+\.\d+(\.\d+)?$"},
        "jurisdiction": {"type": "string", "maxLength": 100},
        "schema_version": {"type": "string"},
        "rules": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["id", "name", "instruction"],
                "additionalProperties": False,
                "properties": {
                    "id": {
                        "type": "string",
                        "pattern": r"^[a-z0-9\-_]+$",
                        "maxLength": 100,
                    },
                    "name": {"type": "string", "maxLength": 255},
                    "instruction": {"type": "string", "minLength": 10},
                },
            },
        },
    },
}


_validator = jsonschema.Draft7Validator(RULE_SCHEMA)


def validate_ruleset_dict(data: dict[str, Any]) -> list[str]:
    """
    Validate a rule set dictionary against the schema.

    Returns a list of validation error messages. Empty list = valid.
    """
    errors = sorted(_validator.iter_errors(data), key=lambda e: list(e.path))
    return [
        f"{'.'.join(str(p) for p in e.path) or 'root'}: {e.message}"
        for e in errors
    ]


def load_ruleset_from_yaml(path: Path) -> dict[str, Any]:
    """
    Load and validate a YAML rule file.

    Raises:
        ValidationError: If the file is invalid YAML or fails schema validation.
    """
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as err:
        raise ValidationError(
            f"Invalid YAML in rule file {path.name}: {err}",
            detail={"file": str(path)},
        ) from err

    if not isinstance(data, dict):
        raise ValidationError(
            f"Rule file {path.name} must be a YAML mapping",
            detail={"file": str(path)},
        )

    errors = validate_ruleset_dict(data)
    if errors:
        raise ValidationError(
            f"Rule file {path.name} failed schema validation",
            detail={"errors": errors},
        )

    return data


def compute_rules_hash(rules_data: dict[str, Any]) -> str:
    """Compute a deterministic SHA-256 hash over the canonical JSON form."""
    canonical = json.dumps(rules_data, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


def detect_rule_conflicts(rules: list[dict[str, Any]]) -> list[dict[str, str]]:
    """
    Detect conflicting rules within a single rule set.

    A conflict exists when two rules share the same scope but have
    contradictory keywords in their prompt_fragments.

    Returns a list of conflict dicts with keys rule_a_id, rule_b_id, description.
    """
    conflicts: list[dict[str, str]] = []
    seen: dict[frozenset[str], str] = {}  # scope_key -> rule_id

    for rule in rules:
        scope: frozenset[str] = frozenset(rule.get("scope", []))
        rule_id: str = rule["id"]
        prompt: str = rule.get("prompt_fragment", "").lower()

        for prev_scope_key, prev_rule_id in seen.items():
            if not scope.isdisjoint(prev_scope_key):
                prev_rule = next((r for r in rules if r["id"] == prev_rule_id), None)
                if prev_rule is None:
                    continue
                prev_prompt = prev_rule.get("prompt_fragment", "").lower()

                for pos_words, neg_words in _NEGATION_PAIRS:
                    curr_pos = any(w in prompt for w in pos_words)
                    curr_neg = any(w in prompt for w in neg_words)
                    prev_pos = any(w in prev_prompt for w in pos_words)
                    prev_neg = any(w in prev_prompt for w in neg_words)

                    if (curr_pos and prev_neg) or (curr_neg and prev_pos):
                        conflicts.append(
                            {
                                "rule_a_id": prev_rule_id,
                                "rule_b_id": rule_id,
                                "description": (
                                    f"Rules '{prev_rule_id}' and '{rule_id}' apply to "
                                    f"overlapping scopes {scope & prev_scope_key} "
                                    f"but appear to give contradictory instructions."
                                ),
                            }
                        )
                        break

        seen[scope] = rule_id

    return conflicts
