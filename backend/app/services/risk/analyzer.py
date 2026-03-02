"""
Risk Analyzer: evaluates rewrites for compliance drift.

Three detection layers:
  1. Rule-based: numeric mutation, party name changes, date drift.
  2. Semantic deviation: TF-IDF cosine similarity.
  3. Structural: character count ratio anomaly.
"""

from __future__ import annotations

import math
import re
from collections import Counter

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.job import RiskFinding, RiskSeverity, SectionRewrite

_log = structlog.get_logger(__name__)

# Pattern matchers
_NUMBER_RE = re.compile(r"\b\d[\d,]*\.?\d*\b")
_DATE_RE = re.compile(
    r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2}|"
    r"\d{1,2}\s+(January|February|March|April|May|June|July|August|September|"
    r"October|November|December)\s+\d{4})\b",
    re.IGNORECASE,
)
_PARTY_NAME_RE = re.compile(r'"([A-Z][a-zA-Z\s]+)"')
_WORD_RE = re.compile(r"\b[a-z]+\b")


def _tokenize(text: str) -> list[str]:
    """Simple word tokenizer: lowercase, strip punctuation."""
    return _WORD_RE.findall(text.lower())


def _cosine_similarity_from_counters(
    counter_a: Counter[str], len_a: int,
    counter_b: Counter[str], len_b: int,
) -> float:
    """
    Cosine similarity using TF-weighted bag of words from pre-counted tokens.

    Returns a float in [0.0, 1.0] where 1.0 = identical.
    """
    if len_a == 0 or len_b == 0:
        return 0.0

    # Only iterate the smaller counter for dot product (sparse optimization)
    if len(counter_a) > len(counter_b):
        counter_a, counter_b = counter_b, counter_a
        len_a, len_b = len_b, len_a

    dot = 0.0
    for w, count_a in counter_a.items():
        count_b = counter_b.get(w, 0)
        if count_b:
            dot += (count_a / len_a) * (count_b / len_b)

    mag_a = math.sqrt(sum((c / len_a) ** 2 for c in counter_a.values()))
    mag_b = math.sqrt(sum((c / len_b) ** 2 for c in counter_b.values()))

    if mag_a == 0 or mag_b == 0:
        return 0.0

    return round(min(1.0, dot / (mag_a * mag_b)), 4)


class RiskAnalyzer:
    """Stateless risk analysis engine."""

    async def analyze(
        self,
        db: AsyncSession,
        rewrite: SectionRewrite,
        original_text: str,
        rewritten_text: str,
    ) -> list[RiskFinding]:
        """
        Run all analysis layers and persist findings.

        Returns the list of RiskFinding records created.
        """
        findings: list[RiskFinding] = []

        findings.extend(self._check_numeric_drift(rewrite.id, original_text, rewritten_text))
        findings.extend(self._check_date_drift(rewrite.id, original_text, rewritten_text))
        findings.extend(self._check_party_changes(rewrite.id, original_text, rewritten_text))
        findings.extend(self._check_semantic_deviation(rewrite.id, original_text, rewritten_text))
        findings.extend(self._check_length_anomaly(rewrite.id, original_text, rewritten_text))

        for finding in findings:
            db.add(finding)
        await db.flush()

        _log.info(
            "risk_analysis_complete",
            rewrite_id=rewrite.id,
            findings=len(findings),
            critical=sum(1 for f in findings if f.severity == RiskSeverity.CRITICAL),
        )
        return findings

    def _check_numeric_drift(
        self, rewrite_id: str, original: str, rewritten: str
    ) -> list[RiskFinding]:
        orig_nums = set(_NUMBER_RE.findall(original))
        new_nums = set(_NUMBER_RE.findall(rewritten))
        removed = orig_nums - new_nums
        added = new_nums - orig_nums

        findings: list[RiskFinding] = []
        if removed:
            findings.append(
                RiskFinding(
                    rewrite_id=rewrite_id,
                    severity=RiskSeverity.CRITICAL,
                    category="numeric_drift",
                    description=f"Numbers removed that were in original: {sorted(removed)[:10]}",
                    score=1.0,
                )
            )
        if added:
            findings.append(
                RiskFinding(
                    rewrite_id=rewrite_id,
                    severity=RiskSeverity.HIGH,
                    category="numeric_drift",
                    description=f"New numbers introduced not in original: {sorted(added)[:10]}",
                    score=0.8,
                )
            )
        return findings

    def _check_date_drift(
        self, rewrite_id: str, original: str, rewritten: str
    ) -> list[RiskFinding]:
        orig_dates = set(_DATE_RE.findall(original))
        new_dates = set(_DATE_RE.findall(rewritten))
        changed = orig_dates.symmetric_difference(new_dates)
        if changed:
            return [
                RiskFinding(
                    rewrite_id=rewrite_id,
                    severity=RiskSeverity.CRITICAL,
                    category="date_drift",
                    description=f"Date values changed: {list(changed)[:5]}",
                    score=1.0,
                )
            ]
        return []

    def _check_party_changes(
        self, rewrite_id: str, original: str, rewritten: str
    ) -> list[RiskFinding]:
        orig_parties = set(_PARTY_NAME_RE.findall(original))
        new_parties = set(_PARTY_NAME_RE.findall(rewritten))
        removed = orig_parties - new_parties
        if removed:
            return [
                RiskFinding(
                    rewrite_id=rewrite_id,
                    severity=RiskSeverity.CRITICAL,
                    category="party_change",
                    description=f"Party names removed: {sorted(removed)[:5]}",
                    score=1.0,
                )
            ]
        return []

    def _check_semantic_deviation(
        self, rewrite_id: str, original: str, rewritten: str
    ) -> list[RiskFinding]:
        tokens_a = _tokenize(original)
        tokens_b = _tokenize(rewritten)
        similarity = _cosine_similarity_from_counters(
            Counter(tokens_a), len(tokens_a),
            Counter(tokens_b), len(tokens_b),
        )
        deviation = 1.0 - similarity

        if deviation > 0.6:
            return [
                RiskFinding(
                    rewrite_id=rewrite_id,
                    severity=RiskSeverity.HIGH,
                    category="semantic_deviation",
                    description=(
                        f"High semantic deviation from original "
                        f"(similarity={similarity:.2f}). "
                        "Review carefully to ensure legal intent is preserved."
                    ),
                    score=deviation,
                )
            ]
        if deviation > 0.35:
            return [
                RiskFinding(
                    rewrite_id=rewrite_id,
                    severity=RiskSeverity.MEDIUM,
                    category="semantic_deviation",
                    description=f"Moderate semantic deviation (similarity={similarity:.2f}).",
                    score=deviation,
                )
            ]
        return []

    def _check_length_anomaly(
        self, rewrite_id: str, original: str, rewritten: str
    ) -> list[RiskFinding]:
        if not original:
            return []
        ratio = len(rewritten) / len(original)
        if ratio < 0.3:
            return [
                RiskFinding(
                    rewrite_id=rewrite_id,
                    severity=RiskSeverity.HIGH,
                    category="length_anomaly",
                    description=(
                        f"Rewrite is {ratio:.0%} of original length. "
                        "Significant content may have been dropped."
                    ),
                    score=1.0 - ratio,
                )
            ]
        if ratio > 3.0:
            return [
                RiskFinding(
                    rewrite_id=rewrite_id,
                    severity=RiskSeverity.MEDIUM,
                    category="length_anomaly",
                    description=(
                        f"Rewrite is {ratio:.0%} of original length. "
                        "Significant content may have been added."
                    ),
                    score=min(1.0, (ratio - 1.0) / 3.0),
                )
            ]
        return []
