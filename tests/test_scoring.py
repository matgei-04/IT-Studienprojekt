"""Tests: Matching-Score nur mit exakten 0/1-Merkmalen."""

from pathlib import Path

from domain.models import IncomingDocument
from matching.models import Candidate
from matching.scoring import address_matches, exact_in_text, score_candidate


def test_exact_in_text_full_match_only():
    assert exact_in_text("Absender NordLog GmbH Hamburg", "NordLog GmbH") is True
    assert exact_in_text("Absender NordLog GmbH Hamburg", "NordLog") is True  # Teilstring ok
    assert exact_in_text("Absender etwas anderes", "NordLog GmbH") is False


def test_address_all_or_nothing():
    text = "NordLog GmbH Hafenstraße 12 20457 Hamburg"
    assert (
        address_matches(text, "NordLog GmbH", "Hafenstraße 12", "20457", "Hamburg") == 1.0
    )
    # Eine Komponente fehlt → 0
    assert address_matches(text, "NordLog GmbH", "Falschweg 1", "20457", "Hamburg") == 0.0


def test_score_binary_order_and_address():
    doc = IncomingDocument(
        path=Path("x.pdf"),
        text="Auftrag 4711 Absender NordLog GmbH Hafenstraße 12 20457 Hamburg",
        document_type="eingangsrechnung",
        order_number="4711",
        used_ocr=False,
    )
    candidate = Candidate(
        erf_nr="4711",
        referenz="Ref-4711",
        sender_name="NordLog GmbH",
        sender_street="Hafenstraße 12",
        sender_plz="20457",
        sender_city="Hamburg",
        typ="1",
    )
    breakdown = score_candidate(doc, candidate)
    assert breakdown.order_number == 1.0
    assert breakdown.sender == 1.0
    assert breakdown.reference == 0.0  # Ref-4711 nicht im Text
    assert breakdown.document_type == 0.0  # Typ "1" != "eingangsrechnung"
    assert breakdown.total == 0.65  # 50% + 15%


def test_partial_address_words_do_not_count():
    doc = IncomingDocument(
        path=Path("x.pdf"),
        text="Nur Hamburg steht hier, sonst nichts Passendes",
        document_type="unbekannt",
        order_number=None,
        used_ocr=False,
    )
    candidate = Candidate(
        erf_nr="999",
        sender_name="NordLog GmbH",
        sender_street="Hafenstraße 12",
        sender_plz="20457",
        sender_city="Hamburg",
    )
    breakdown = score_candidate(doc, candidate)
    assert breakdown.sender == 0.0
    assert breakdown.total == 0.0
