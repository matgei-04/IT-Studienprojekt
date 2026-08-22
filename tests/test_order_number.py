"""Tests zur Auftragsnummer-Erkennung."""

from extraction.order_number import find_order_number


def test_find_order_number_with_erfnr_label():
    assert find_order_number("ErfNr: 88421 Empfänger Musterstraße") == "88421"


def test_find_order_number_with_auftrag_label():
    assert find_order_number("Auftragsnr. 1234 Sendung bereit") == "1234"


def test_find_order_number_auftrags_nr_hyphen():
    text = "RECHNUNG\n# R-1002\nHinweise:\nAuftrags-Nr.: 815\n"
    assert find_order_number(text) == "815"


def test_find_order_number_erf_nr_dotted():
    assert find_order_number("Erf.-Nr.: 3301") == "3301"


def test_find_order_number_auftrag_nr_dot():
    assert find_order_number("Bezug: Auftrag Nr. 4711") == "4711"


def test_auftrag_bare_label():
    assert find_order_number("AUFTRAG 2002\n1.077,75 $") == "2002"


def test_no_label_means_no_number():
    """Ohne Label keine Nummer – auch nicht aus Rechnungsnr. oder Beträgen."""
    assert find_order_number("RECHNUNG\n# R-1002\nohne Auftragsbezug") is None
    assert find_order_number("Sendungsnummer: 55667") is None
    assert find_order_number("PO-4711") is None
    assert find_order_number("4711 Auftragsnummer") is None  # Label muss davor stehen
