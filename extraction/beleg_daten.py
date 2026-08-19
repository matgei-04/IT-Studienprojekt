# Selbst erstellt – bitte prüfen und erklären können.
"""Erkennung von Belegdatum und Gesamtbetrag im Dokumenttext.

Bewusst klein gehalten: einfache Label-Suche + Regex, kein Parsing-
Framework. Sucht gezielt in der Nähe bekannter Labels (nicht einfach die
erste Zahl/das erste Datum im Text), um Verwechslungen mit anderen
Zahlen/Daten (z. B. Rechnungsnummer, Lieferdatum, Zwischensumme) zu
vermeiden.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation

# Reihenfolge = Priorität: spezifischere Labels zuerst.
_DATE_LABELS = ["rechnungsdatum", "belegdatum", "datum"]

# dd.mm.yyyy oder dd.mm.yy
_DATE_PATTERN = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{2,4})")

# Reihenfolge = Priorität: der finale Gesamtbetrag zuerst, Zwischensummen
# absichtlich nicht enthalten.
_AMOUNT_LABELS = [
    "gesamtbetrag",
    "rechnungsbetrag",
    "bruttobetrag",
    "zu zahlender betrag",
    "endbetrag",
    "gesamt",
]

# Deutsches Zahlenformat: 1.234,56 oder 1234,56 – immer genau 2 Nachkommastellen.
_AMOUNT_PATTERN = re.compile(r"(\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2})")


def _label_line_indices(lines: list[str], label: str) -> list[int]:
    """Zeilen, die das Label als eigenständiges Wort enthalten (Wortgrenzen,
    damit z. B. 'datum' nicht in 'Lieferdatum' anschlägt)."""
    pattern = re.compile(rf"\b{re.escape(label)}\b", re.IGNORECASE)
    return [i for i, line in enumerate(lines) if pattern.search(line)]


def _nearby_lines(lines: list[str], i: int) -> list[str]:
    """Label-Zeile, dann Folgezeile, dann vorherige Zeile – in dieser
    Priorität durchsucht.

    PDF-Textextraktion bringt Tabellen/Formulare manchmal durcheinander;
    Label und Wert stehen dann auf benachbarten, aber nicht immer
    nachfolgenden Zeilen. Die vorherige Zeile wird bewusst ZULETZT geprüft,
    damit ein Wert einer ANDEREN, davorstehenden Beschriftung (z. B.
    'Zwischensumme') nicht fälschlich als Treffer für das aktuelle Label
    genutzt wird, wenn die eigene/folgende Zeile bereits einen Treffer hätte.
    """
    candidates = [lines[i]]
    if i + 1 < len(lines):
        candidates.append(lines[i + 1])
    if i - 1 >= 0:
        candidates.append(lines[i - 1])
    return candidates


def find_belegdatum(text: str) -> date | None:
    """Sucht ein Datum in der Nähe von Datums-Labels (spezifischste zuerst)."""
    if not text:
        return None

    lines = text.splitlines()
    for label in _DATE_LABELS:
        for i in _label_line_indices(lines, label):
            for candidate_line in _nearby_lines(lines, i):
                match = _DATE_PATTERN.search(candidate_line)
                if match:
                    parsed = _parse_date(match)
                    if parsed:
                        return parsed
    return None


def _parse_date(match: re.Match[str]) -> date | None:
    day, month, year = match.groups()
    try:
        year_i = int(year)
        if year_i < 100:
            year_i += 2000
        return date(year_i, int(month), int(day))
    except ValueError:
        return None


def find_betrag(text: str) -> tuple[Decimal | None, str | None]:
    """Sucht den finalen Gesamtbetrag in der Nähe von Betrags-Labels.

    Rückgabe: (Betrag als Decimal, Währung oder None). Nutzt Decimal statt
    float, um Rundungsfehler bei Geldwerten zu vermeiden.
    """
    if not text:
        return None, None

    lines = text.splitlines()
    for label in _AMOUNT_LABELS:
        for i in _label_line_indices(lines, label):
            for candidate_line in _nearby_lines(lines, i):
                match = _AMOUNT_PATTERN.search(candidate_line)
                if match:
                    amount = _parse_german_amount(match.group(1))
                    if amount is not None:
                        currency = "EUR" if "€" in candidate_line or re.search(
                            r"\beur\b", candidate_line, re.IGNORECASE
                        ) else None
                        return amount, currency
    return None, None


def _parse_german_amount(raw: str) -> Decimal | None:
    """'1.234,56' -> Decimal('1234.56')."""
    normalized = raw.replace(".", "").replace(",", ".")
    try:
        return Decimal(normalized)
    except InvalidOperation:
        return None
