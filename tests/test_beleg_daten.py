# Selbst erstellt – bitte prüfen und erklären können.
"""Tests zur Belegdatum-/Betrags-Erkennung."""

from datetime import date
from decimal import Decimal

from extraction.beleg_daten import find_belegdatum, find_betrag


def test_find_belegdatum_with_rechnungsdatum_label():
    text = "Rechnung Nr. 100\nRechnungsdatum: 12.05.2026\nFälligkeitsdatum: 26.05.2026"
    assert find_belegdatum(text) == date(2026, 5, 12)


def test_rechnungsdatum_hat_vorrang_vor_lieferdatum():
    text = "Lieferdatum: 01.05.2026\nRechnungsdatum: 12.05.2026"
    assert find_belegdatum(text) == date(2026, 5, 12)


def test_generisches_datum_label_als_fallback():
    text = "Beleg\nDatum: 03.03.2026\nUnterschrift"
    assert find_belegdatum(text) == date(2026, 3, 3)


def test_lieferdatum_loest_generisches_datum_label_nicht_aus():
    # "datum" als Teilwort von "Lieferdatum" darf nicht als generisches
    # "Datum"-Label zählen (Wortgrenzen-Regex).
    text = "Lieferdatum: 01.05.2026"
    assert find_belegdatum(text) is None


def test_kein_datum_gefunden():
    assert find_belegdatum("Kein Datum in diesem Text enthalten.") is None


def test_leerer_text_datum():
    assert find_belegdatum("") is None


def test_find_betrag_mit_gesamtbetrag_label():
    text = "Zwischensumme 1.000,00 €\nGesamtbetrag 1.497,50 €"
    amount, currency = find_betrag(text)
    assert amount == Decimal("1497.50")
    assert currency == "EUR"


def test_gesamtbetrag_hat_vorrang_vor_zwischensumme():
    text = "MwSt. (19%) 234,56 €\nGesamtbetrag 1.234,56 €"
    amount, _ = find_betrag(text)
    assert amount == Decimal("1234.56")


def test_betrag_auf_folgezeile_tabellarisch():
    text = "Gesamtbetrag\n12.450,00 €"
    amount, currency = find_betrag(text)
    assert amount == Decimal("12450.00")
    assert currency == "EUR"


def test_betrag_auf_vorheriger_zeile():
    # PDF-Textextraktion bringt Reihenfolge manchmal durcheinander: Wert
    # steht vor dem Label, nicht danach.
    text = "1.497,50 €\nGesamtbetrag"
    amount, currency = find_betrag(text)
    assert amount == Decimal("1497.50")
    assert currency == "EUR"


def test_gesamt_ohne_betrag_suffix_wird_erkannt():
    text = "Zwischensumme 1.000,00 €\nGesamt 1.100,00 €"
    amount, _ = find_betrag(text)
    assert amount == Decimal("1100.00")


def test_betrag_ohne_waehrungszeichen():
    text = "Rechnungsbetrag 320,00"
    amount, currency = find_betrag(text)
    assert amount == Decimal("320.00")
    assert currency is None


def test_kein_betrag_gefunden():
    amount, currency = find_betrag("Dieser Text enthält keine Beträge.")
    assert amount is None
    assert currency is None


def test_leerer_text_betrag():
    assert find_betrag("") == (None, None)
