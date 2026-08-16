"""Zentrale Matching-Logik."""

from __future__ import annotations

from domain.models import IncomingDocument
from matching.candidate_search import CandidateRepository
from matching.models import MatchResult, ScoreBreakdown
from matching.scoring import score_candidate


class DocumentMatcher:
    """Erzeugt Zuordnungsvorschläge für IncomingDocuments.

    Es wird immer eine manuelle Bestätigung verlangt (needs_manual_review=True).
    confidence ist die Matching-Sicherheit (0.0–1.0) aus dem Gesamtscore.
    """

    def __init__(
        self,
        repository: CandidateRepository,
        suggestion_threshold: float = 0.55,
    ):
        self.repository = repository
        # Ab diesem Score gilt der Vorschlag als „brauchbarer Treffer“ (trotzdem manuell).
        self.suggestion_threshold = suggestion_threshold

    def match(self, document: IncomingDocument) -> MatchResult:
        """Führt Kandidatensuche, Bewertung und Ranking durch."""
        candidates: list = []

        if document.order_number:
            candidates = self.repository.find_by_order_number(document.order_number)

        if not candidates:
            candidates = self.repository.search_by_text(document)

        if not candidates:
            return MatchResult(
                erf_nr=None,
                score=0.0,
                confidence=0.0,
                candidate=None,
                breakdown=ScoreBreakdown(
                    reasons=["Keine Kandidaten gefunden – manuelle Zuordnung nötig."]
                ),
                matched=False,
                needs_manual_review=True,
            )

        scored_candidates = []
        for candidate in candidates:
            breakdown = score_candidate(document, candidate)
            scored_candidates.append((breakdown.total, candidate, breakdown))

        scored_candidates.sort(key=lambda item: item[0], reverse=True)

        best_score, best_candidate, best_breakdown = scored_candidates[0]
        second_score = (
            scored_candidates[1][0] if len(scored_candidates) > 1 else 0.0
        )
        score_gap = best_score - second_score

        matched = best_score >= self.suggestion_threshold
        # Projektentscheidung: User bestätigt immer manuell.
        needs_manual_review = True

        best_breakdown.reasons.append(
            f"Score-Abstand zum zweitbesten Kandidaten: {score_gap:.3f}"
        )
        best_breakdown.reasons.append(
            "Manuelle Zuordnung erforderlich (Bestätigung durch User)."
        )

        return MatchResult(
            erf_nr=best_candidate.erf_nr,
            score=best_score,
            confidence=best_score,
            candidate=best_candidate,
            breakdown=best_breakdown,
            matched=matched,
            needs_manual_review=needs_manual_review,
        )
