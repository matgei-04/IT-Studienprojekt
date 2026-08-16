"""Direkte Textextraktion aus PDFs (eingebetteter Text, ohne OCR)."""

from __future__ import annotations

from pathlib import Path

import fitz  # PyMuPDF


def extract_direct_text(pdf_path: Path) -> str:
    """Liest den eingebetteten Text aller Seiten und gibt ihn bereinigt zurück."""
    pages: list[str] = []
    with fitz.open(pdf_path) as document:
        for page in document:
            page_text = page.get_text("text") or ""
            pages.append(page_text)

    combined = "\n".join(pages)
    return _normalize_whitespace(combined)


def _normalize_whitespace(text: str) -> str:
    """Kürzt übermäßige Leerzeichen, behält Zeilenumbrüche grob bei."""
    lines = [" ".join(line.split()) for line in text.splitlines()]
    return "\n".join(line for line in lines if line).strip()
