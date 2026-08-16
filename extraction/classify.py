"""Dokumenttyp anhand von Schlüsselwörtern bestimmen."""

from __future__ import annotations

# Welcher Typ hat welche Wörter? (mehr Treffer = dieser Typ)
TYPE_KEYWORDS = {
    "schadensmeldung": [
        "schadensmeldung",
        "schadenmeldung",
        "transportschaden",
        "beschädigt",
        "beschaedigt",
        "schadensanzeige",
    ],
    "eingangsrechnung": [
        "eingangsrechnung",
        "rechnung",
        "rechnungsnr",
        "rechnungsnummer",
        "nettobetrag",
        "umsatzsteuer",
        "mwst",
    ],
    "wareneingangsschein": [
        "wareneingangsschein",
        "wareneingang",
        "lieferschein",
        "wareneingangskontrolle",
        "empfangsbestätigung",
        "empfangsbestaetigung",
    ],
    "frachtpapier": [
        "frachtbrief",
        "frachtpapier",
        "cmr",
        "speditionsauftrag",
        "absender",
        "empfänger",
        "empfaenger",
        "frachtführer",
        "frachtfuehrer",
    ],
}


def classify_document_type(text: str) -> str:
    """Gibt den Dokumenttyp zurück oder 'unbekannt'."""
    if not text.strip():
        return "unbekannt"

    text_lower = text.casefold()
    best_type = "unbekannt"
    best_hits = 0

    for doc_type, keywords in TYPE_KEYWORDS.items():
        hits = 0
        for word in keywords:
            if word in text_lower:
                hits += 1
        if hits > best_hits:
            best_hits = hits
            best_type = doc_type

    return best_type
