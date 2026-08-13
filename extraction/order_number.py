# Selbst erstellt – bitte prüfen und erklären können.
"""Erkennung von Auftrags-/Sendungsnummern (ErfNr) im Dokumenttext."""

from __future__ import annotations

import re

# Labels, die typischerweise vor der Nummer stehen (bevorzugt)
_LABEL_PATTERN = re.compile(
    r"(?:"
    r"auftrags(?:nr\.?|nummer|nr)|"
    r"sendungs(?:nr\.?|nummer|nr)|"
    r"sendung|"
    r"erfnr\.?|"
    r"erf[\.\s-]?nr\.?|"
    r"auftrag|"
    r"referenz(?:nr\.?|nummer)?"
    r")"
    r"\s*[:.\-]?\s*"
    r"(\d{3,6})",
    re.IGNORECASE,
)

# Fallback: isolierte 3–6-stellige Zahl (Wortgrenzen)
_FALLBACK_NUMBER = re.compile(r"(?<!\d)(\d{3,6})(?!\d)")

# Typische False Positives: Jahreszahlen, PLZ (D), Telefonfragmente grob
_YEAR_RANGE = range(1990, 2036)
_GERMAN_PLZ = re.compile(r"^\d{5}$")


def find_order_number(text: str) -> tuple[str | None, float]:
    """
    Sucht eine Auftrags-/Sendungsnummer im Text.

    Bevorzugt Nummern hinter Labels; filtert Jahr und PLZ möglichst aus.
    Rückgabe: (Nummer oder None, confidence).
    """
    if not text.strip():
        return None, 0.0

    labeled = _LABEL_PATTERN.search(text)
    if labeled:
        candidate = labeled.group(1)
        # Mit Label: nur Jahreszahlen ausschließen (5-stellig kann ErfNr sein)
        if _is_plausible_order_number(candidate, reject_plz_like=False):
            return candidate, 0.9

    for match in _FALLBACK_NUMBER.finditer(text):
        candidate = match.group(1)
        # Ohne Label: 5-stellige Zahlen oft PLZ → vorsichtig ausschließen
        if _is_plausible_order_number(candidate, reject_plz_like=True):
            return candidate, 0.45

    return None, 0.0


def _is_plausible_order_number(value: str, *, reject_plz_like: bool) -> bool:
    """Schließt typische Non-Order-Zahlen aus (Jahre, optional PLZ-ähnlich)."""
    if not value.isdigit():
        return False
    as_int = int(value)
    if len(value) == 4 and as_int in _YEAR_RANGE:
        return False
    if reject_plz_like and _GERMAN_PLZ.match(value):
        return False
    return True
