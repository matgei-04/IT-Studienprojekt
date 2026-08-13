# Selbst erstellt – bitte prüfen und erklären können.
"""Grobe Dokumenttyp-Klassifikation anhand von Schlüsselwörtern."""

from __future__ import annotations

# Reihenfolge: spezifischere Typen zuerst prüfen
_TYPE_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    (
        "schadensmeldung",
        (
            "schadensmeldung",
            "schadenmeldung",
            "transportschaden",
            "beschädigt",
            "beschaedigt",
            "schadensanzeige",
        ),
    ),
    (
        "eingangsrechnung",
        (
            "eingangsrechnung",
            "rechnung",
            "rechnungsnr",
            "rechnungsnummer",
            "nettobetrag",
            "umsatzsteuer",
            "mwst",
        ),
    ),
    (
        "wareneingangsschein",
        (
            "wareneingangsschein",
            "wareneingang",
            "lieferschein",
            "wareneingangskontrolle",
            "empfangsbestätigung",
            "empfangsbestaetigung",
        ),
    ),
    (
        "frachtpapier",
        (
            "frachtbrief",
            "frachtpapier",
            "cmr",
            "speditionsauftrag",
            "absender",
            "empfänger",
            "empfaenger",
            "frachtführer",
            "frachtfuehrer",
        ),
    ),
]


def classify_document_type(text: str) -> tuple[str, float]:
    """
    Bestimmt den Dokumenttyp per Keyword-Treffern.

    Rückgabe: (document_type, type_confidence) mit type_confidence in [0, 1].
    """
    lowered = text.casefold()
    if not lowered.strip():
        return "unbekannt", 0.0

    scores: dict[str, int] = {}
    for doc_type, keywords in _TYPE_KEYWORDS:
        hits = sum(1 for kw in keywords if kw in lowered)
        if hits:
            scores[doc_type] = hits

    if not scores:
        return "unbekannt", 0.2

    best_type = max(scores, key=scores.get)
    best_hits = scores[best_type]
    # Mehr Treffer → höhere Sicherheit, Deckel bei 1.0
    confidence = min(0.45 + 0.15 * best_hits, 1.0)
    return best_type, confidence
