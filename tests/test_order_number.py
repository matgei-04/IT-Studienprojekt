"""Tests zur Auftragsnummer-Erkennung inkl. False-Positive-Filter."""

from extraction.order_number import find_order_number


def test_find_order_number_with_erfnr_label():
    text = "ErfNr: 88421 Empfänger Musterstraße"
    number, confidence = find_order_number(text)
    assert number == "88421"
    assert confidence >= 0.8


def test_find_order_number_with_auftrag_label():
    text = "Auftragsnr. 1234 Sendung bereit"
    number, confidence = find_order_number(text)
    assert number == "1234"
    assert confidence >= 0.8


def test_find_order_number_sendung_label():
    text = "Sendungsnummer: 55667 Status unterwegs"
    number, _ = find_order_number(text)
    assert number == "55667"


def test_reject_year_as_order_number():
    text = "Dokument erstellt im Jahr 2024 ohne Auftrag"
    number, confidence = find_order_number(text)
    assert number is None
    assert confidence == 0.0


def test_reject_plz_as_order_number():
    text = "Lieferadresse 80331 München"
    number, confidence = find_order_number(text)
    assert number is None
    assert confidence == 0.0


def test_fallback_finds_plausible_number():
    text = "Referenz intern 7788 bearbeitet"
    number, confidence = find_order_number(text)
    # "Referenz" ist Label → hohe Confidence; Nummer 7788
    assert number == "7788"
    assert confidence > 0.0
