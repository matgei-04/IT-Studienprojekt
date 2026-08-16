"""Tests zur Dokumenttyp-Klassifikation."""

from extraction.classify import classify_document_type


def test_classify_frachtpapier():
    text = "CMR Frachtbrief Absender: Muster GmbH Empfänger: Logistik AG"
    doc_type, confidence = classify_document_type(text)
    assert doc_type == "frachtpapier"
    assert confidence > 0.5


def test_classify_schadensmeldung():
    text = "Schadensmeldung Transportschaden: Palette beschädigt"
    doc_type, confidence = classify_document_type(text)
    assert doc_type == "schadensmeldung"
    assert confidence > 0.5


def test_classify_eingangsrechnung():
    text = "Eingangsrechnung Rechnungsnummer 100 Nettobetrag Umsatzsteuer"
    doc_type, _ = classify_document_type(text)
    assert doc_type == "eingangsrechnung"


def test_classify_wareneingangsschein():
    text = "Wareneingangsschein Lieferschein Wareneingangskontrolle"
    doc_type, _ = classify_document_type(text)
    assert doc_type == "wareneingangsschein"


def test_classify_unbekannt():
    text = "Hallo Welt ohne relevante Fachbegriffe"
    doc_type, confidence = classify_document_type(text)
    assert doc_type == "unbekannt"
    assert confidence < 0.5
