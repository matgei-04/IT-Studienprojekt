"""Datenmodelle für das Matching-Modul."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Candidate:
    """Ein möglicher Auftrag aus der Spedifix-Datenbank."""

    erf_nr: str
    datum: str | None = None
    typ: str | None = None
    storno: str | None = None
    lade_datum: str | None = None
    entlade_datum: str | None = None
    fracht: float | None = None
    wrg: str | None = None
    fakt_beleg_nr: str | None = None
    referenz: str | None = None

    sender_name: str | None = None
    sender_street: str | None = None
    sender_plz: str | None = None
    sender_city: str | None = None

    receiver_name: str | None = None
    receiver_street: str | None = None
    receiver_plz: str | None = None
    receiver_city: str | None = None


@dataclass
class ScoreBreakdown:
    """Einzelne Bestandteile des Matching-Scores."""

    order_number: float = 0.0
    reference: float = 0.0
    sender: float = 0.0
    receiver: float = 0.0
    document_type: float = 0.0
    total: float = 0.0
    reasons: list[str] = field(default_factory=list)


@dataclass
class MatchResult:
    """Ergebnis eines Matching-Vorgangs.

    confidence = Matching-Sicherheit (0.0–1.0), aus dem Gesamtscore.
    needs_manual_review ist projektbedingt immer True (User bestätigt).
    """

    erf_nr: str | None
    score: float
    confidence: float
    candidate: Candidate | None
    breakdown: ScoreBreakdown
    matched: bool
    needs_manual_review: bool
