"""CLI: Extraktion + Matching (Vorschlag immer mit manueller Bestätigung)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client

from extraction import extract_from_directory
from extraction.config import load_settings
from matching.candidate_search import CandidateRepository
from matching.matcher import DocumentMatcher


def main() -> int:
    project_root = Path(__file__).resolve().parent
    load_dotenv(project_root / ".env")

    settings = load_settings(project_root / ".env")

    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")

    if not supabase_url or not supabase_key:
        print(
            "Fehler: SUPABASE_URL und SUPABASE_KEY müssen in .env gesetzt sein.",
            file=sys.stderr,
        )
        return 1

    try:
        supabase = create_client(supabase_url, supabase_key)
    except Exception as exc:
        print(f"Supabase-Verbindung fehlgeschlagen: {exc}", file=sys.stderr)
        return 1

    repository = CandidateRepository(supabase)
    matcher = DocumentMatcher(repository=repository)

    try:
        documents = extract_from_directory(settings)
    except Exception as exc:
        print(f"Extraktion fehlgeschlagen: {exc}", file=sys.stderr)
        return 1

    if not documents:
        print("Keine PDF-Dateien gefunden.")
        return 0

    for document in documents:
        print("=" * 70)
        print(f"Dokument:              {document.path.name}")
        print(f"Dokumenttyp:           {document.document_type}")
        print(f"Erkannte ErfNr:        {document.order_number}")
        print(f"OCR verwendet:         {document.used_ocr}")
        print("-" * 70)

        try:
            result = matcher.match(document)
        except Exception as exc:
            print(f"Matching fehlgeschlagen: {exc}")
            continue

        if result.candidate is None:
            print("ERGEBNIS: KEIN MATCH")
            print("Manuelle Zuordnung erforderlich.")
            print(f"Matching Confidence:   {result.confidence:.3f}")
            continue

        print(f"Vorschlag ErfNr:       {result.erf_nr}")
        print(f"Matching Confidence:   {result.confidence:.3f}")
        print(
            "Status:                VORSCHLAG – immer manuelle Bestätigung"
        )
        print(f"Brauchbarer Treffer:   {result.matched}")

        print("-" * 70)
        print("Score-Aufschlüsselung:")
        print(f"  Auftragsnummer:      {result.breakdown.order_number:.3f}")
        print(f"  Referenz:            {result.breakdown.reference:.3f}")
        print(f"  Absender:            {result.breakdown.sender:.3f}")
        print(f"  Empfänger:           {result.breakdown.receiver:.3f}")
        print(f"  Dokumenttyp:         {result.breakdown.document_type:.3f}")
        print(f"  GESAMT/Confidence:   {result.breakdown.total:.3f}")

        print("-" * 70)
        print("Begründungen:")
        for reason in result.breakdown.reasons:
            print(f"  - {reason}")

        candidate = result.candidate
        print("-" * 70)
        print("Kandidat aus DB:")
        print(f"  ErfNr:               {candidate.erf_nr}")
        print(f"  Absender:            {candidate.sender_name}")
        print(f"  Empfänger:           {candidate.receiver_name}")
        print(f"  Referenz:            {candidate.referenz}")
        print(f"  DB Typ:              {candidate.typ}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
