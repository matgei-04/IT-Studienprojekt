"""Auftragsnummer (ErfNr) im Text finden."""

from __future__ import annotations

import re

# Wörter, die oft VOR der Nummer stehen (Reihenfolge = Priorität)
LABELS = [
    "erfassungsnummer",
    "erfnr",
    "erf-nr",
    "erf nr",
    "auftragsnummer",
    "auftragsnr",
    "auftrags nr",
    "sendungsnummer",
    "sendungsnr",
    "sendung",
    "auftrag",
    "referenznummer",
    "referenznr",
    "referenz",
]

# Beliebige 3–6-stellige Zahl im Text
ANY_NUMBER = re.compile(r"(?<!\d)(\d{3,6})(?!\d)")


def find_order_number(text: str) -> str | None:
    """
    Sucht eine Auftragsnummer.

    1) Zahl direkt hinter einem Label (z.B. ErfNr: 815)
    2) sonst erste passende Zahl im Text (ohne Jahr/PLZ)
    """
    if not text.strip():
        return None

    # Schritt 1: hinter Labels suchen
    for label in LABELS:
        pattern = re.compile(
            re.escape(label) + r"[\s:.\-]*(\d{3,6})",
            re.IGNORECASE,
        )
        match = pattern.search(text)
        if match:
            number = match.group(1)
            if _is_valid_number(number, reject_plz=False):
                return number

    # Schritt 2: Fallback – erste plausible Zahl
    for match in ANY_NUMBER.finditer(text):
        number = match.group(1)
        if _is_valid_number(number, reject_plz=True):
            return number

    return None


def _is_valid_number(number: str, reject_plz: bool) -> bool:
    """Filtert Jahreszahlen und (optional) 5-stellige PLZ heraus."""
    if not number.isdigit():
        return False

    value = int(number)

    # typische Jahre, z.B. 2024
    if len(number) == 4 and 1990 <= value <= 2035:
        return False

    # deutsche PLZ oft 5-stellig – nur im Fallback aussortieren
    if reject_plz and len(number) == 5:
        return False

    return True
