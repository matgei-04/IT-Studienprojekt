"""Ähnlichkeit zwischen Dokument und DB-Auftrag berechnen.

Jedes Merkmal ist binär: 1.0 bei exakter Übereinstimmung, sonst 0.0.
Keine Teiltreffer / Wort-Überlappungen.
"""

from __future__ import annotations

from domain.models import IncomingDocument
from matching.models import Candidate, ScoreBreakdown

# Gewichtung des Matching-Scores (Summe = 1.0)
WEIGHT_ORDER = 0.50
WEIGHT_REFERENCE = 0.15
WEIGHT_SENDER = 0.15
WEIGHT_RECEIVER = 0.15
WEIGHT_TYPE = 0.05


def normalize(value: str | None) -> str:
    """Text vereinheitlichen: klein, ohne überflüssige Leerzeichen."""
    if not value:
        return ""
    return " ".join(value.casefold().split())


def exact_in_text(document_text: str, value: str | None) -> bool:
    """True nur wenn der DB-Wert vollständig im Dokumenttext vorkommt."""
    needle = normalize(value)
    haystack = normalize(document_text)
    if not needle or not haystack:
        return False
    return needle in haystack


def address_matches(
    document_text: str,
    name: str | None,
    street: str | None,
    plz: str | None,
    city: str | None,
) -> float:
    """Adresse: 1.0 wenn alle vorhandenen Felder exakt im Text stehen, sonst 0.0."""
    parts = [name, street, plz, city]
    present = [p for p in parts if normalize(p)]
    if not present:
        return 0.0
    if all(exact_in_text(document_text, p) for p in present):
        return 1.0
    return 0.0


def score_candidate(
    document: IncomingDocument,
    candidate: Candidate,
) -> ScoreBreakdown:
    """Einen Kandidaten bewerten → total = Matching-Confidence (nur 0/1-Merkmale)."""
    result = ScoreBreakdown()
    text = document.text

    # 1) Auftragsnummer / ErfNr – exakt gleich
    if document.order_number and normalize(document.order_number) == normalize(
        candidate.erf_nr
    ):
        result.order_number = 1.0
        result.reasons.append("Auftragsnummer stimmt überein.")

    # 2) Referenz – vollständiger Text muss vorkommen
    if candidate.referenz and exact_in_text(text, candidate.referenz):
        result.reference = 1.0
        result.reasons.append("Referenz stimmt überein.")

    # 3) Absender – alle Adressfelder exakt
    result.sender = address_matches(
        text,
        candidate.sender_name,
        candidate.sender_street,
        candidate.sender_plz,
        candidate.sender_city,
    )
    if result.sender == 1.0:
        result.reasons.append("Absender stimmt überein.")

    # 4) Empfänger – alle Adressfelder exakt
    result.receiver = address_matches(
        text,
        candidate.receiver_name,
        candidate.receiver_street,
        candidate.receiver_plz,
        candidate.receiver_city,
    )
    if result.receiver == 1.0:
        result.reasons.append("Empfänger stimmt überein.")

    # 5) Dokumenttyp – exakt gleich
    if document.document_type and candidate.typ:
        if normalize(document.document_type) == normalize(candidate.typ):
            result.document_type = 1.0
            result.reasons.append("Dokumenttyp stimmt überein.")

    result.total = round(
        result.order_number * WEIGHT_ORDER
        + result.reference * WEIGHT_REFERENCE
        + result.sender * WEIGHT_SENDER
        + result.receiver * WEIGHT_RECEIVER
        + result.document_type * WEIGHT_TYPE,
        3,
    )
    return result
