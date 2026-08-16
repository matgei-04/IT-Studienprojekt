"""Pipeline: PDF → Text → Typ → Nummer → IncomingDocument."""

from __future__ import annotations

from pathlib import Path

from domain.models import IncomingDocument, Settings
from extraction.classify import classify_document_type
from extraction.ocr import extract_text_via_ocr
from extraction.order_number import find_order_number
from extraction.pdf_text import extract_direct_text


def list_pdf_files(directory: Path) -> list[Path]:
    """Alle PDF-Dateien im Ordner (auch Unterordner), sortiert."""
    if not directory.is_dir():
        raise FileNotFoundError(f"Scan-Verzeichnis nicht gefunden: {directory}")

    pdfs = []
    for path in directory.rglob("*.pdf"):
        if path.is_file():
            pdfs.append(path)
    return sorted(pdfs)


def extract_single_document(path: Path | str, settings: Settings) -> IncomingDocument:
    """Ein PDF auslesen und als IncomingDocument zurückgeben."""
    pdf_path = Path(path).resolve()
    notes: list[str] = []

    if not pdf_path.is_file():
        raise FileNotFoundError(f"PDF nicht gefunden: {pdf_path}")
    if pdf_path.suffix.lower() != ".pdf":
        raise ValueError(f"Keine PDF-Datei: {pdf_path}")

    # 1) Text direkt aus der PDF
    text = extract_direct_text(pdf_path)
    notes.append(f"Direkter Text: {len(text)} Zeichen")
    used_ocr = False

    # 2) Zu wenig Text? → OCR
    if len(text) < settings.min_direct_text_length:
        notes.append("Zu wenig Text → OCR")
        try:
            text = extract_text_via_ocr(pdf_path, language=settings.ocr_language)
            used_ocr = True
            notes.append(f"OCR-Text: {len(text)} Zeichen")
        except Exception as exc:  # noqa: BLE001
            notes.append(f"OCR fehlgeschlagen: {exc}")
    else:
        notes.append("OCR nicht nötig")

    # 3) Typ und Nummer
    document_type = classify_document_type(text)
    notes.append(f"Klassifikation: {document_type}")

    order_number = find_order_number(text)
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
    """Alle PDFs im Scan-Ordner verarbeiten (nur lesen)."""
    results = []
    for pdf in list_pdf_files(settings.scan_directory):
        results.append(extract_single_document(pdf, settings))
    return results
