"""Tests zur Auftragsnummer-Erkennung."""

from extraction.order_number import find_order_number


def test_find_order_number_with_erfnr_label():
    text = "ErfNr: 88421 Empfänger Musterstraße"
    assert find_order_number(text) == "88421"


def test_find_order_number_with_auftrag_label():
    text = "Auftragsnr. 1234 Sendung bereit"
    assert find_order_number(text) == "1234"


def test_find_order_number_sendung_label():
    text = "Sendungsnummer: 55667 Status unterwegs"
    assert find_order_number(text) == "55667"


def test_reject_year_as_order_number():
    text = "Dokument erstellt im Jahr 2024 ohne Auftrag"
    assert find_order_number(text) is None


def test_reject_plz_as_order_number():
    text = "Lieferadresse 80331 München"
    assert find_order_number(text) is None


def test_fallback_finds_plausible_number():
    text = "Referenz intern 7788 bearbeitet"
    assert find_order_number(text) == "7788"
