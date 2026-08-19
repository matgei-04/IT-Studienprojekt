# Selbst erstellt – bitte prüfen und erklären können.
"""Ergänzt fehlende Belegdatum-/Betrags-Werte in der Tabelle "Dokumente",
ohne Originaldateien zu verändern.

Idempotent: bearbeitet nur Zeilen, bei denen Belegdatum ODER Betrag noch
fehlt UND bereits erfolgreich Text extrahiert wurde (OcrAbgeschlossenAm
gesetzt). Bereits vorhandene, plausible Werte werden nie überschrieben.
Dokumente, die noch gar keine Dokumente-Zeile haben (z. B. nach einem
frischen Checkout), werden einmalig komplett verarbeitet – dieselbe Logik
wie beim normalen Import/Anzeigen.
"""

from __future__ import annotations

import sys

from app.data import (
    PROJECT_ROOT,
    _fetch_dokumente_by_path,
    _get_supabase,
    _process_document,
    _upsert_dokument,
)
from extraction.beleg_daten import find_belegdatum, find_betrag
from extraction.config import load_settings
from extraction.pipeline import extract_single_document, list_pdf_files
from matching.candidate_search import CandidateRepository
from matching.matcher import DocumentMatcher


def main() -> int:
    settings = load_settings(PROJECT_ROOT / ".env")
    supabase = _get_supabase()
    if supabase is None:
        print("Fehler: SUPABASE_URL/SUPABASE_KEY sind in .env nicht gesetzt.", file=sys.stderr)
        return 1

    try:
        pdf_paths = list_pdf_files(settings.scan_directory)
    except FileNotFoundError as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 1

    stored = _fetch_dokumente_by_path(supabase)
    matcher = DocumentMatcher(CandidateRepository(supabase))

    neu_verarbeitet = 0
    aktualisiert = 0
    uebersprungen = 0

    for pdf_path in pdf_paths:
        key = str(pdf_path)
        row = stored.get(key)

        if row is None:
            # Noch nie verarbeitet (z. B. frischer Checkout) -> einmalig
            # komplett verarbeiten, dieselbe Logik wie beim Import.
            _process_document(pdf_path, settings, matcher, supabase)
            neu_verarbeitet += 1
            print(f"neu verarbeitet:  {pdf_path.name}")
            continue

        has_text = row.get("OcrAbgeschlossenAm") is not None
        missing_belegdatum = row.get("Belegdatum") is None
        missing_betrag = row.get("Betrag") is None

        if not has_text or not (missing_belegdatum or missing_betrag):
            uebersprungen += 1
            continue

        try:
            document = extract_single_document(pdf_path, settings)
        except Exception:  # noqa: BLE001 – einzelnes Dokument darf den Lauf nicht abbrechen
            uebersprungen += 1
            continue

        update: dict = {"DokumentPfad": key, "Dateiname": pdf_path.name}
        changed = False

        if missing_belegdatum:
            belegdatum = find_belegdatum(document.text)
            if belegdatum:
                update["Belegdatum"] = belegdatum.isoformat()
                changed = True

        if missing_betrag:
            betrag, waehrung = find_betrag(document.text)
            if betrag is not None:
                update["Betrag"] = str(betrag)
                update["Waehrung"] = waehrung
                changed = True

        if changed:
            _upsert_dokument(supabase, update)
            aktualisiert += 1
            print(f"aktualisiert:     {pdf_path.name} -> {update}")
        else:
            uebersprungen += 1

    print("-" * 60)
    print(f"Neu verarbeitet:              {neu_verarbeitet}")
    print(f"Aktualisiert (Belegdatum/Betrag ergänzt): {aktualisiert}")
    print(f"Übersprungen (nichts zu tun): {uebersprungen}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
