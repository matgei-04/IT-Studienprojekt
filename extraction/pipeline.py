"""Orchestrierung der Extraktions-Pipeline für einzelne PDFs und Ordner."""

from __future__ import annotations

from pathlib import Path

from domain.models import IncomingDocument, Settings
from extraction.classify import classify_document_type
from extraction.ocr import extract_text_via_ocr
from extraction.order_number import find_order_number
from extraction.pdf_text import extract_direct_text


def list_pdf_files(directory: Path) -> list[Path]:
    """Listet rekursiv alle .pdf-Dateien im Ordner und Unterordnern (sortiert)."""
    if not directory.is_dir():
        raise FileNotFoundError(f"Scan-Verzeichnis nicht gefunden: {directory}")

    return sorted(
        path
        for path in directory.rglob("*.pdf")
        if path.is_file()
    )


def extract_single_document(path: Path | str, settings: Settings) -> IncomingDocument:
    """Verarbeitet ein einzelnes PDF und liefert ein IncomingDocument."""
    pdf_path = Path(path).resolve()
    notes: list[str] = []

    if not pdf_path.is_file():
        raise FileNotFoundError(f"PDF nicht gefunden: {pdf_path}")
    if pdf_path.suffix.lower() != ".pdf":
        raise ValueError(f"Keine PDF-Datei: {pdf_path}")

    direct_text = extract_direct_text(pdf_path)
    notes.append(f"Direkter Text: {len(direct_text)} Zeichen")

    used_ocr = False
    text = direct_text

    if len(direct_text) < settings.min_direct_text_length:
        notes.append(
            f"Unter MIN_DIRECT_TEXT_LENGTH ({settings.min_direct_text_length}) → OCR"
        )
        try:
            text = extract_text_via_ocr(pdf_path, language=settings.ocr_language)
            used_ocr = True
            notes.append(f"OCR-Text: {len(text)} Zeichen (lang={settings.ocr_language})")
        except Exception as exc:  # noqa: BLE001 – Pipeline soll robust weiterlaufen
            notes.append(f"OCR fehlgeschlagen: {exc}")
            text = direct_text
    else:
        notes.append("OCR nicht nötig")

    document_type, _type_confidence = classify_document_type(text)
    notes.append(f"Klassifikation: {document_type}")

    order_number, _order_confidence = find_order_number(text)
    if order_number:
        notes.append(f"Auftragsnummer: {order_number}")
    else:
        notes.append("Keine Auftragsnummer erkannt")

    return IncomingDocument(
        path=pdf_path,
        text=text,
        document_type=document_type,
        order_number=order_number,
        used_ocr=used_ocr,
        extraction_notes=notes,
    )


def extract_from_directory(settings: Settings) -> list[IncomingDocument]:
    """Verarbeitet alle PDFs im konfigurierten Scan-Verzeichnis (nur lesen)."""
    pdfs = list_pdf_files(settings.scan_directory)
    return [extract_single_document(pdf, settings) for pdf in pdfs]
