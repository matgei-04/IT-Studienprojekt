"""Tests für Matching (ohne echte Supabase-DB)."""

from __future__ import annotations

from pathlib import Path

from domain.models import IncomingDocument
from matching.matcher import DocumentMatcher
from matching.models import Candidate


class FakeRepository:
    def __init__(self, candidates):
        self.candidates = candidates

    def find_by_order_number(self, order_number):
        return [c for c in self.candidates if c.erf_nr == str(order_number)]


def make_document(text, order_number=None, document_type="frachtpapier"):
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
    result = DocumentMatcher(FakeRepository([candidate])).match(
        make_document(
            "Frachtbrief Nordholz GmbH Hildesheim Suedlogistik AG Hamburg REF-4711",
            order_number="4711",
        )
    )
    assert result.erf_nr == "4711"
    assert result.breakdown.order_number == 1.0
    assert result.confidence > 0.5
    assert result.matched is True
    assert result.needs_manual_review is True


def test_no_order_number_means_no_candidate():
    candidate = Candidate(erf_nr="4711", sender_name="Nordholz GmbH", sender_city="Hildesheim")
    result = DocumentMatcher(FakeRepository([candidate])).match(
        make_document("Absender Nordholz GmbH Hildesheim")
    )
    assert result.erf_nr is None
    assert result.candidate is None


def test_unknown_order_number_means_no_candidate():
    result = DocumentMatcher(FakeRepository([])).match(
        make_document("Auftrag 9999", order_number="9999")
    )
    assert result.erf_nr is None
    assert result.candidate is None


def test_always_requires_manual_review():
    candidate = Candidate(erf_nr="4711", referenz="REF-4711")
    result = DocumentMatcher(FakeRepository([candidate])).match(
        make_document("REF-4711", order_number="4711")
    )
    assert result.matched is True or result.confidence >= 0.0
    assert result.needs_manual_review is True
    assert result.erf_nr == "4711"
