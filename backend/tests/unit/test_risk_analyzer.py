"""Unit tests for app.services.risk.analyzer."""
import pytest

from app.services.risk.analyzer import RiskAnalyzer, RiskSeverity


@pytest.fixture()
def analyzer() -> RiskAnalyzer:
    return RiskAnalyzer()


# ─── No findings for identical content ────────────────────────────────────────

def test_no_findings_for_identical_text(analyzer):
    text = "The vendor shall deliver 500 units by 15 March 2025."
    findings = analyzer.analyze(original=text, rewritten=text)
    assert findings == []


# ─── Numeric drift ────────────────────────────────────────────────────────────

def test_numeric_drift_critical_when_number_removed(analyzer):
    original = "The buyer shall pay USD 50,000 upon execution."
    rewritten = "The buyer shall pay the agreed sum upon execution."
    findings = analyzer.analyze(original=original, rewritten=rewritten)
    severities = {f.severity for f in findings}
    assert RiskSeverity.CRITICAL in severities


def test_numeric_drift_critical_when_number_changed(analyzer):
    original = "The penalty is 10% of the contract value."
    rewritten = "The penalty is 5% of the contract value."
    findings = analyzer.analyze(original=original, rewritten=rewritten)
    severities = {f.severity for f in findings}
    assert RiskSeverity.CRITICAL in severities


def test_numeric_preserved_no_finding(analyzer):
    original = "Deliver 100 units."
    rewritten = "The vendor must deliver 100 units."
    findings = analyzer.analyze(original=original, rewritten=rewritten)
    numeric_findings = [f for f in findings if "numeric" in f.check_name.lower() or "number" in f.check_name.lower()]
    assert numeric_findings == []


# ─── Date drift ───────────────────────────────────────────────────────────────

def test_date_drift_critical_when_date_removed(analyzer):
    original = "The agreement expires on 31 December 2026."
    rewritten = "The agreement will expire at the end of the term."
    findings = analyzer.analyze(original=original, rewritten=rewritten)
    severities = {f.severity for f in findings}
    assert RiskSeverity.CRITICAL in severities


def test_date_drift_critical_when_date_changed(analyzer):
    original = "Signed on 1 January 2024."
    rewritten = "Signed on 1 January 2025."
    findings = analyzer.analyze(original=original, rewritten=rewritten)
    severities = {f.severity for f in findings}
    assert RiskSeverity.CRITICAL in severities


# ─── Party name drift ─────────────────────────────────────────────────────────

def test_party_name_change_flagged(analyzer):
    original = 'This agreement is between ACME Corp ("Vendor") and Beta Ltd ("Buyer").'
    rewritten = 'This agreement is between ACME Corp ("Vendor") and Gamma Ltd ("Buyer").'
    findings = analyzer.analyze(original=original, rewritten=rewritten)
    assert findings  # at least one finding expected


# ─── Semantic deviation ───────────────────────────────────────────────────────

def test_semantic_deviation_high_for_unrelated_text(analyzer):
    original = "The lessor shall maintain the property in good repair throughout the tenancy."
    rewritten = "Quantum computing enables parallel processing of large data sets efficiently."
    findings = analyzer.analyze(original=original, rewritten=rewritten)
    severities = {f.severity for f in findings}
    assert RiskSeverity.HIGH in severities or RiskSeverity.CRITICAL in severities


# ─── Length anomaly ───────────────────────────────────────────────────────────

def test_length_anomaly_high_for_drastic_shortening(analyzer):
    original = " ".join(["word"] * 300)
    rewritten = "word"
    findings = analyzer.analyze(original=original, rewritten=rewritten)
    severities = {f.severity for f in findings}
    assert RiskSeverity.HIGH in severities or RiskSeverity.CRITICAL in severities


def test_length_anomaly_high_for_drastic_expansion(analyzer):
    original = "Short clause."
    rewritten = " ".join(["expanded clause content"] * 200)
    findings = analyzer.analyze(original=original, rewritten=rewritten)
    severities = {f.severity for f in findings}
    assert RiskSeverity.HIGH in severities or RiskSeverity.CRITICAL in severities


# ─── Finding structure ────────────────────────────────────────────────────────

def test_finding_has_required_fields(analyzer):
    original = "Pay USD 10,000 by 1 March."
    rewritten = "Make payment by the deadline."
    findings = analyzer.analyze(original=original, rewritten=rewritten)
    assert findings
    for f in findings:
        assert hasattr(f, "check_name")
        assert hasattr(f, "severity")
        assert hasattr(f, "description")
        assert f.severity in list(RiskSeverity)
