"""OCR-Fallback: PDF-Seiten als Bild lesen (Tesseract)."""

from __future__ import annotations

from pathlib import Path

import fitz  # PyMuPDF
import pytesseract
from PIL import Image


def extract_text_via_ocr(pdf_path: Path, language: str = "deu") -> str:
    """Seite → Bild → Text mit Tesseract."""
    page_texts = []
    # 2x Vergrößerung = bessere Erkennung
    zoom = fitz.Matrix(2.0, 2.0)

    with fitz.open(pdf_path) as document:
        for page in document:
            pixmap = page.get_pixmap(matrix=zoom, alpha=False)
            image = Image.frombytes(
                "RGB",
                (pixmap.width, pixmap.height),
                pixmap.samples,
            )
            text = pytesseract.image_to_string(image, lang=language) or ""
            if text.strip():
                page_texts.append(text.strip())

    return _clean_text("\n".join(page_texts))


def _clean_text(text: str) -> str:
    """Doppelte Leerzeichen entfernen, leere Zeilen weglassen."""
    clean_lines = []
    for line in text.splitlines():
        line = " ".join(line.split())
        if line:
            clean_lines.append(line)
    return "\n".join(clean_lines).strip()
