"""Matching-Modul für die automatische Dokumentzuordnung."""

from matching.matcher import DocumentMatcher
from matching.models import Candidate, MatchResult, ScoreBreakdown

__all__ = ["DocumentMatcher", "Candidate", "MatchResult", "ScoreBreakdown"]
