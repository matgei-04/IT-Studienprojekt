# Selbst erstellt – bitte prüfen und erklären können.
"""Paket für PDF-Textextraktion, OCR und Dokumentanalyse."""

from extraction.pipeline import extract_from_directory, extract_single_document

__all__ = ["extract_from_directory", "extract_single_document"]
