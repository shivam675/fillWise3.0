"""Unit tests for app.services.rules.validator."""
import pytest

from app.services.rules.validator import (
    compute_rules_hash,
    detect_rule_conflicts,
    validate_ruleset_dict,
    ValidationError as RulesetValidationError,
)


# ─── Minimal valid ruleset fixture ────────────────────────────────────────────

VALID_RULESET = {
    "schema_version": "1.0",
    "name": "test_ruleset",
    "version": "1.0.0",
    "description": "Test ruleset for unit tests",
    "jurisdiction": None,
    "rules": [
        {
            "id": "TEST-001",
            "section_types": ["clause"],
            "instruction": "Replace legalese with plain English.",
            "priority": 10,
            "preserve_numbers": True,
            "preserve_dates": True,
            "preserve_parties": True,
            "tags": ["plain-language"],
        }
    ],
}


# ─── validate_ruleset_dict ─────────────────────────────────────────────────────

def test_valid_ruleset_passes():
    result = validate_ruleset_dict(VALID_RULESET)
    assert result is not None


def test_missing_name_fails():
    bad = {**VALID_RULESET}
    del bad["name"]
    with pytest.raises(RulesetValidationError):
        validate_ruleset_dict(bad)


def test_missing_rules_fails():
    bad = {**VALID_RULESET, "rules": []}
    with pytest.raises(RulesetValidationError):
        validate_ruleset_dict(bad)


def test_rule_missing_id_fails():
    bad = {
        **VALID_RULESET,
        "rules": [
            {
                "section_types": ["clause"],
                "instruction": "Do something.",
                "priority": 10,
            }
        ],
    }
    with pytest.raises(RulesetValidationError):
        validate_ruleset_dict(bad)


def test_rule_missing_instruction_fails():
    bad = {
        **VALID_RULESET,
        "rules": [
            {
                "id": "TEST-002",
                "section_types": ["clause"],
                "priority": 10,
            }
        ],
    }
    with pytest.raises(RulesetValidationError):
        validate_ruleset_dict(bad)


def test_invalid_section_type_fails():
    bad = {
        **VALID_RULESET,
        "rules": [
            {
                "id": "TEST-003",
                "section_types": ["unknowntype999"],
                "instruction": "Do something.",
                "priority": 1,
            }
        ],
    }
    with pytest.raises(RulesetValidationError):
        validate_ruleset_dict(bad)


def test_invalid_schema_version_fails():
    bad = {**VALID_RULESET, "schema_version": "99.0"}
    with pytest.raises(RulesetValidationError):
        validate_ruleset_dict(bad)


# ─── compute_rules_hash ───────────────────────────────────────────────────────

def test_hash_is_deterministic():
    h1 = compute_rules_hash(VALID_RULESET["rules"])
    h2 = compute_rules_hash(VALID_RULESET["rules"])
    assert h1 == h2


def test_hash_changes_when_rules_change():
    rules_v1 = VALID_RULESET["rules"]
    rules_v2 = [
        {
            **rules_v1[0],
            "instruction": "Completely different instruction.",
        }
    ]
    assert compute_rules_hash(rules_v1) != compute_rules_hash(rules_v2)


# ─── detect_rule_conflicts ────────────────────────────────────────────────────

def test_no_conflict_for_single_rule():
    conflicts = detect_rule_conflicts(VALID_RULESET["rules"])
    assert conflicts == []


def test_conflict_detected_for_contradictory_rules():
    """Two rules that both target the same section_type and have contradictory
    instructions should be flagged as a conflict."""
    rules = [
        {
            "id": "CON-001",
            "section_types": ["clause"],
            "instruction": "Always use active voice.",
            "priority": 10,
        },
        {
            "id": "CON-002",
            "section_types": ["clause"],
            "instruction": "Always use passive voice.",
            "priority": 10,
        },
    ]
    conflicts = detect_rule_conflicts(rules)
    conflict_ids = {c["rule_a_id"] for c in conflicts} | {c["rule_b_id"] for c in conflicts}
    assert "CON-001" in conflict_ids or "CON-002" in conflict_ids


def test_different_section_types_no_conflict():
    rules = [
        {
            "id": "A-001",
            "section_types": ["heading"],
            "instruction": "Capitalise headings.",
            "priority": 5,
        },
        {
            "id": "A-002",
            "section_types": ["clause"],
            "instruction": "Use plain English.",
            "priority": 5,
        },
    ]
    conflicts = detect_rule_conflicts(rules)
    assert conflicts == []
