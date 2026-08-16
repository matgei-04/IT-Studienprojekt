"""OCR-Fallback mit Tesseract für gescannte bzw. textarme PDFs."""

from __future__ import annotations

from pathlib import Path

import fitz  # PyMuPDF
import pytesseract
from PIL import Image


def extract_text_via_ocr(pdf_path: Path, language: str = "deu") -> str:
    """Rendert PDF-Seiten als Bilder und erkennt Text mit Tesseract."""
    page_texts: list[str] = []
    # 2x Zoom für bessere OCR-Qualität bei typischen Scan-Auflösungen
    matrix = fitz.Matrix(2.0, 2.0)

    with fitz.open(pdf_path) as document:
        for page in document:
            pixmap = page.get_pixmap(matrix=matrix, alpha=False)
            image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
            text = pytesseract.image_to_string(image, lang=language) or ""
            page_texts.append(text.strip())

    combined = "\n".join(part for part in page_texts if part)
    return _normalize_whitespace(combined)


def _normalize_whitespace(text: str) -> str:
    lines = [" ".join(line.split()) for line in text.splitlines()]
    return "\n".join(line for line in lines if line).strip()
