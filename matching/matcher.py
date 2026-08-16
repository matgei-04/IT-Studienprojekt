"""Matching: Dokument einem Auftrag zuordnen (Vorschlag)."""

from __future__ import annotations

from domain.models import IncomingDocument
from matching.candidate_search import CandidateRepository
from matching.models import MatchResult, ScoreBreakdown
from matching.scoring import score_candidate


class DocumentMatcher:
    """
    Sucht passende Aufträge und bewertet sie.
    confidence = Matching-Score.
    needs_manual_review ist immer True.
    """

    def __init__(self, repository: CandidateRepository, min_score: float = 0.55):
        self.repository = repository
        self.min_score = min_score

    def match(self, document: IncomingDocument) -> MatchResult:
        """Kandidaten suchen → bewerten → besten Vorschlag zurückgeben."""
        candidates = []

        if document.order_number:
            candidates = self.repository.find_by_order_number(document.order_number)

        if not candidates:
            candidates = self.repository.search_by_text(document)

        if not candidates:
            return MatchResult(
                erf_nr=None,
                confidence=0.0,
                candidate=None,
                breakdown=ScoreBreakdown(
                    reasons=["Keine Kandidaten – manuelle Zuordnung nötig."]
                ),
                matched=False,
                needs_manual_review=True,
            )

        ranked = []
        for candidate in candidates:
            breakdown = score_candidate(document, candidate)
            ranked.append((breakdown.total, candidate, breakdown))

        ranked.sort(key=lambda item: item[0], reverse=True)
        best_score, best_candidate, best_breakdown = ranked[0]

        best_breakdown.reasons.append("Manuelle Bestätigung durch User nötig.")

        return MatchResult(
            erf_nr=best_candidate.erf_nr,
            confidence=best_score,
            candidate=best_candidate,
            breakdown=best_breakdown,
            matched=best_score >= self.min_score,
            needs_manual_review=True,
        )
