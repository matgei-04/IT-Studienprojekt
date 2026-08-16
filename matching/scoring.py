"""Berechnung der Ähnlichkeit zwischen Dokument und DB-Kandidat."""

from __future__ import annotations

import re
import unicodedata

from domain.models import IncomingDocument
from matching.models import Candidate, ScoreBreakdown

# Gewichte (später gemeinsam mit dem Team justierbar)
WEIGHT_ORDER_NUMBER = 0.50
WEIGHT_REFERENCE = 0.15
WEIGHT_SENDER = 0.15
WEIGHT_RECEIVER = 0.15
WEIGHT_DOCUMENT_TYPE = 0.05


def normalize(value: str | None) -> str:
    """Normalisiert Text für robuste Vergleiche."""
    if not value:
        return ""

    value = unicodedata.normalize("NFKD", value)
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = value.casefold()
    value = re.sub(r"[^a-z0-9äöüß ]+", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def token_similarity(left: str | None, right: str | None) -> float:
    """Berechnet Jaccard-Ähnlichkeit auf Token-Ebene."""
    left_normalized = normalize(left)
    right_normalized = normalize(right)

    if not left_normalized or not right_normalized:
        return 0.0

    if left_normalized == right_normalized:
        return 1.0

    left_tokens = set(left_normalized.split())
    right_tokens = set(right_normalized.split())

    if not left_tokens or not right_tokens:
        return 0.0

    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def contains_similarity(document_text: str, database_value: str | None) -> float:
    """Prüft, wie gut ein DB-Wert im Dokumenttext vorkommt."""
    db_value = normalize(database_value)
    text = normalize(document_text)

    if not db_value or not text:
        return 0.0

    if db_value in text:
        return 1.0

    return token_similarity(text, db_value)


def _address_score(
    document_text: str,
    name: str | None,
    street: str | None,
    plz: str | None,
    city: str | None,
) -> float:
    """Bewertet eine Adresse anhand mehrerer Felder."""
    values = [
        (name, 0.50),
        (street, 0.15),
        (plz, 0.20),
        (city, 0.15),
    ]

    available = [
        (contains_similarity(document_text, value), weight)
        for value, weight in values
        if value
    ]

    if not available:
        return 0.0

    weight_sum = sum(weight for _, weight in available)
    return sum(score * weight for score, weight in available) / weight_sum


def score_candidate(
    document: IncomingDocument,
    candidate: Candidate,
) -> ScoreBreakdown:
    """Bewertet einen Kandidaten; total = Matching-Confidence-Grundlage."""
    breakdown = ScoreBreakdown()
    text = document.text

    if document.order_number:
        if normalize(document.order_number) == normalize(candidate.erf_nr):
            breakdown.order_number = 1.0
            breakdown.reasons.append("Auftragsnummer stimmt exakt überein.")

    if candidate.referenz:
        breakdown.reference = contains_similarity(text, candidate.referenz)
        if breakdown.reference > 0:
            breakdown.reasons.append("Referenz wurde im Dokument gefunden.")

    breakdown.sender = _address_score(
        text,
        candidate.sender_name,
        candidate.sender_street,
        candidate.sender_plz,
        candidate.sender_city,
    )
    if breakdown.sender > 0:
        breakdown.reasons.append(
            f"Absenderinformationen passen (Score {breakdown.sender:.2f})."
        )

    breakdown.receiver = _address_score(
        text,
        candidate.receiver_name,
        candidate.receiver_street,
        candidate.receiver_plz,
        candidate.receiver_city,
    )
    if breakdown.receiver > 0:
        breakdown.reasons.append(
            f"Empfängerinformationen passen (Score {breakdown.receiver:.2f})."
        )

    breakdown.document_type = document_type_score(
        document.document_type,
        candidate.typ,
    )

    breakdown.total = round(
        breakdown.order_number * WEIGHT_ORDER_NUMBER
        + breakdown.reference * WEIGHT_REFERENCE
        + breakdown.sender * WEIGHT_SENDER
        + breakdown.receiver * WEIGHT_RECEIVER
        + breakdown.document_type * WEIGHT_DOCUMENT_TYPE,
        3,
    )

    return breakdown


def document_type_score(
    document_type: str | None,
    db_type: str | None,
) -> float:
    """Vergleicht Dokumenttyp und DB-Typ (aktuell nur exakt)."""
    if not document_type or not db_type:
        return 0.0

    return 1.0 if normalize(document_type) == normalize(db_type) else 0.0
