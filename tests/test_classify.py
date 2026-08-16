"""Tests zur Dokumenttyp-Klassifikation."""

from extraction.classify import classify_document_type


def test_classify_frachtpapier():
    text = "CMR Frachtbrief Absender: Muster GmbH Empfänger: Logistik AG"
    assert classify_document_type(text) == "frachtpapier"


def test_classify_schadensmeldung():
    text = "Schadensmeldung Transportschaden: Palette beschädigt"
    assert classify_document_type(text) == "schadensmeldung"


def test_classify_eingangsrechnung():
    text = "Eingangsrechnung Rechnungsnummer 100 Nettobetrag Umsatzsteuer"
    assert classify_document_type(text) == "eingangsrechnung"


def test_classify_wareneingangsschein():
    text = "Wareneingangsschein Lieferschein Wareneingangskontrolle"
    assert classify_document_type(text) == "wareneingangsschein"


def test_classify_unbekannt():
    text = "Hallo Welt ohne relevante Fachbegriffe"
    assert classify_document_type(text) == "unbekannt"
