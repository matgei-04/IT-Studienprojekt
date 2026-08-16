"""Pipeline-Tests mit Temp-PDF (direkter Text, ohne echtes OCR)."""

from __future__ import annotations

from pathlib import Path

import fitz
import pytest

from domain.models import Settings
from extraction.pipeline import extract_from_directory, extract_single_document


def _write_text_pdf(path: Path, text: str) -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 72), text, fontsize=11)
    doc.save(path)
    doc.close()


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        scan_directory=tmp_path,
        min_direct_text_length=40,
        ocr_language="deu",
    )


def test_extract_single_document_direct_text(tmp_path: Path, settings: Settings):
    pdf = tmp_path / "fracht.pdf"
    content = (
        "CMR Frachtbrief Absender Firma A Empfänger Firma B "
        "ErfNr: 44221 Frachtführer Test Spedition"
    )
    _write_text_pdf(pdf, content)

    result = extract_single_document(pdf, settings)

    assert result.path == pdf.resolve()
    assert result.used_ocr is False
    assert result.document_type == "frachtpapier"
    assert result.order_number == "44221"
    assert "Direkter Text" in " ".join(result.extraction_notes)
    assert "Frachtbrief" in result.text or "ErfNr" in result.text


def test_extract_from_directory_lists_pdfs_only(tmp_path: Path, settings: Settings):
    _write_text_pdf(
        tmp_path / "a.pdf",
        "Schadensmeldung Transportschaden ErfNr 99112 Palette beschädigt",
    )
    (tmp_path / "notiz.txt").write_text("kein pdf", encoding="utf-8")
    (tmp_path / "unterordner").mkdir()
    _write_text_pdf(
        tmp_path / "unterordner" / "nested.pdf",
        "Frachtbrief Absender Empfänger ErfNr 33445 Frachtführer",
    )

    docs = extract_from_directory(settings)
    assert len(docs) == 2
    by_name = {doc.path.name: doc for doc in docs}
    assert by_name["a.pdf"].document_type == "schadensmeldung"
    assert by_name["a.pdf"].order_number == "99112"
    assert by_name["nested.pdf"].document_type == "frachtpapier"
    assert by_name["nested.pdf"].order_number == "33445"
