"""Ähnlichkeit zwischen Dokument und DB-Auftrag berechnen."""

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
    """Text vereinheitlichen: klein, ohne Sonderzeichen-Chaos."""
    if not value:
        return ""
    return " ".join(value.casefold().split())


def text_contains(document_text: str, value: str | None) -> float:
    """
    Wie gut kommt ein DB-Wert im Dokument vor?
    1.0 = exakt enthalten, sonst Anteil gemeinsamer Wörter, sonst 0.
    """
    needle = normalize(value)
    haystack = normalize(document_text)
    if not needle or not haystack:
        return 0.0
    if needle in haystack:
        return 1.0

    words_a = set(needle.split())
    words_b = set(haystack.split())
    if not words_a or not words_b:
        return 0.0
    shared = words_a & words_b
    all_words = words_a | words_b
    return len(shared) / len(all_words)


def address_score(
    document_text: str,
    name: str | None,
    street: str | None,
    plz: str | None,
    city: str | None,
) -> float:
    """Adresse bewerten: Name zählt am meisten."""
    parts = [
        (name, 0.50),
        (plz, 0.20),
        (street, 0.15),
        (city, 0.15),
    ]
    scores = []
    weights = []
    for value, weight in parts:
        if value:
            scores.append(text_contains(document_text, value) * weight)
            weights.append(weight)

    if not weights:
        return 0.0
    return sum(scores) / sum(weights)


def score_candidate(
    document: IncomingDocument,
    candidate: Candidate,
) -> ScoreBreakdown:
    """Einen Kandidaten bewerten → total = Matching-Confidence."""
    result = ScoreBreakdown()
    text = document.text

    # 1) Auftragsnummer / ErfNr
    if document.order_number and normalize(document.order_number) == normalize(
        candidate.erf_nr
    ):
        result.order_number = 1.0
        result.reasons.append("Auftragsnummer stimmt überein.")

    # 2) Referenz
    if candidate.referenz:
        result.reference = text_contains(text, candidate.referenz)
        if result.reference > 0:
            result.reasons.append("Referenz im Dokument gefunden.")

    # 3) Absender
    result.sender = address_score(
        text,
        candidate.sender_name,
        candidate.sender_street,
        candidate.sender_plz,
        candidate.sender_city,
    )
    if result.sender > 0:
        result.reasons.append(f"Absender passt ({result.sender:.2f}).")

    # 4) Empfänger
    result.receiver = address_score(
        text,
        candidate.receiver_name,
        candidate.receiver_street,
        candidate.receiver_plz,
        candidate.receiver_city,
    )
    if result.receiver > 0:
        result.reasons.append(f"Empfänger passt ({result.receiver:.2f}).")

    # 5) Dokumenttyp (nur wenn DB-Typ exakt gleich)
    if document.document_type and candidate.typ:
        if normalize(document.document_type) == normalize(candidate.typ):
            result.document_type = 1.0

    result.total = round(
        result.order_number * WEIGHT_ORDER
        + result.reference * WEIGHT_REFERENCE
        + result.sender * WEIGHT_SENDER
        + result.receiver * WEIGHT_RECEIVER
        + result.document_type * WEIGHT_TYPE,
        3,
    )
    return result
