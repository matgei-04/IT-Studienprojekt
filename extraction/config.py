# Selbst erstellt – bitte prüfen und erklären können.
"""Laden der Extraktions-Einstellungen aus Umgebungsvariablen / .env."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from domain.models import Settings


def load_settings(env_path: Path | None = None) -> Settings:
    """Liest SCAN_DIRECTORY, MIN_DIRECT_TEXT_LENGTH und OCR_LANGUAGE."""
    if env_path is not None:
        load_dotenv(env_path)
    else:
        load_dotenv()

    scan_raw = os.getenv("SCAN_DIRECTORY", "./sample_scans")
    min_len_raw = os.getenv("MIN_DIRECT_TEXT_LENGTH", "40")
    ocr_language = os.getenv("OCR_LANGUAGE", "deu")

    try:
        min_direct_text_length = int(min_len_raw)
    except ValueError as exc:
        raise ValueError(
            f"MIN_DIRECT_TEXT_LENGTH muss eine ganze Zahl sein, erhalten: {min_len_raw!r}"
        ) from exc

    scan_directory = Path(scan_raw).expanduser().resolve()
    return Settings(
        scan_directory=scan_directory,
        min_direct_text_length=min_direct_text_length,
        ocr_language=ocr_language,
    )
