"""Auftragsnummer (ErfNr) im Text finden – nur Label direkt vor der Zahl."""

from __future__ import annotations

import re

# Label + optional Nr./Nummer + Zahl (z. B. „Auftrags-Nr.: 3001“, „AUFTRAG 2002“)
_ORDER_NUMBER = re.compile(
    r"(?:"
    r"erfassungsnummer|"
    r"erf[\s.\-]*nr\.?|"
    r"auftragsnummer|"
    r"auftrags[\s.\-]*nr\.?|"
    r"auftrag[\s.\-]*(?:nr|n[ro]|nummer)\.?|"
    r"auftrag"
    r")"
    r"[\s:.\-]*(\d{3,6})(?!\d)",
    re.IGNORECASE,
)


def find_order_number(text: str) -> str | None:
    """Erste Zahl direkt hinter einem Auftrags-Label, sonst None.

    Kein Fallback auf beliebige Zahlen. Ohne Label → keine Zuordnung möglich.
    """
    if not text.strip():
        return None

    match = _ORDER_NUMBER.search(text)
    if not match:
        return None

    number = match.group(1)
    return number if number.isdigit() else None
