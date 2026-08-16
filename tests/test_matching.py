"""Tests für das Matching-Modul ohne echte Supabase-Verbindung."""

from __future__ import annotations

from pathlib import Path

from domain.models import IncomingDocument
from matching.matcher import DocumentMatcher
from matching.models import Candidate


class FakeRepository:
    """Test-Repository für isolierte Matching-Tests."""

    def __init__(self, candidates):
        self.candidates = candidates

    def find_by_order_number(self, order_number):
        return [
            candidate
            for candidate in self.candidates
            if candidate.erf_nr == str(order_number)
        ]

    def search_by_text(self, document):
        return self.candidates


def make_document(
    text: str,
    order_number: str | None = None,
    document_type: str = "frachtpapier",
) -> IncomingDocument:
    return IncomingDocument(
        path=Path("test.pdf"),
        text=text,
        document_type=document_type,
        order_number=order_number,
        used_ocr=False,
    )


def test_exact_order_number_match():
    candidate = Candidate(
        erf_nr="4711",
        sender_name="Nordholz GmbH",
        sender_city="Hildesheim",
        receiver_name="Suedlogistik AG",
        receiver_city="Hamburg",
        referenz="REF-4711",
    )

    matcher = DocumentMatcher(FakeRepository([candidate]))

    document = make_document(
        "Frachtbrief Nordholz GmbH Hildesheim "
        "Suedlogistik AG Hamburg REF-4711",
        order_number="4711",
    )

    result = matcher.match(document)

    assert result.erf_nr == "4711"
    assert result.breakdown.order_number == 1.0
    assert result.confidence == result.score
    assert result.score > 0.5
    assert result.matched is True
    assert result.needs_manual_review is True


def test_no_candidate():
    matcher = DocumentMatcher(FakeRepository([]))

    result = matcher.match(make_document("unbekanntes Dokument"))

    assert result.erf_nr is None
    assert result.score == 0.0
    assert result.confidence == 0.0
    assert result.needs_manual_review is True


def test_sender_information_is_used():
    candidate = Candidate(
        erf_nr="4711",
        sender_name="Nordholz GmbH",
        sender_city="Hildesheim",
    )

    matcher = DocumentMatcher(FakeRepository([candidate]))

    result = matcher.match(make_document("Absender Nordholz GmbH Hildesheim"))

    assert result.erf_nr == "4711"
    assert result.breakdown.sender > 0
    assert result.needs_manual_review is True


def test_reference_is_used():
    candidate = Candidate(
        erf_nr="4711",
        referenz="REF-ABC-4711",
    )

    matcher = DocumentMatcher(FakeRepository([candidate]))

    result = matcher.match(make_document("Kundenreferenz REF-ABC-4711"))

    assert result.erf_nr == "4711"
    assert result.breakdown.reference > 0
    assert result.needs_manual_review is True


def test_always_requires_manual_review_even_with_strong_match():
    candidate = Candidate(
        erf_nr="4711",
        sender_name="Nordholz GmbH",
        sender_city="Hildesheim",
        receiver_name="Suedlogistik AG",
        receiver_city="Hamburg",
        referenz="REF-4711",
    )
    matcher = DocumentMatcher(FakeRepository([candidate]))
    result = matcher.match(
        make_document(
            "Frachtbrief Nordholz GmbH Hildesheim Suedlogistik AG Hamburg REF-4711",
            order_number="4711",
        )
    )
    assert result.matched is True
    assert result.needs_manual_review is True
    assert result.confidence >= 0.5
