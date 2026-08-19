"""Kandidaten in Supabase suchen."""

from __future__ import annotations

import re
from typing import Any

from supabase import Client

from domain.models import IncomingDocument
from matching.models import Candidate


class CandidateRepository:
    """Liest Aufträge und Adressen aus der Spedifix-DB."""

    def __init__(self, supabase: Client):
        self.supabase = supabase

    def find_by_order_number(self, order_number: str) -> list[Candidate]:
        """Sucht Sendungen mit passender ErfNr (nicht storniert)."""
        response = (
            self.supabase.table("3100_Sdg_Haupt")
            .select("*")
            .eq("ErfNr", str(order_number))
            .eq("Storno", "0")
            .execute()
        )

        candidates = []
        for row in response.data:
            candidate = self._build_candidate(row)
            self._load_addresses(candidate)
            candidates.append(candidate)
        return candidates

    def search_by_text(
        self,
        document: IncomingDocument,
        limit: int = 50,
    ) -> list[Candidate]:
        """Suche über Ortsnamen / Referenz, wenn keine ErfNr da ist."""
        found: dict[str, Candidate] = {}

        for token in self._words_from_text(document.text):
            # Ort in Adressen
            places = (
                self.supabase.table("3100_Sdg_Adressen")
                .select("*")
                .ilike("Ort", f"%{token}%")
                .limit(limit)
                .execute()
            )
            for row in places.data:
                erf_nr = row.get("ErfNr")
                if not erf_nr:
                    continue
                erf_nr = str(erf_nr)
                if erf_nr not in found:
                    found[erf_nr] = Candidate(erf_nr=erf_nr)
                self._add_address(found[erf_nr], row)

            # Referenz in Haupt
            refs = (
                self.supabase.table("3100_Sdg_Haupt")
                .select("*")
                .ilike("Ref-1", f"%{token}%")
                .eq("Storno", "0")
                .limit(limit)
                .execute()
            )
            for row in refs.data:
                erf_nr = row.get("ErfNr")
                if erf_nr:
                    found[str(erf_nr)] = self._build_candidate(row)

        result = []
        for erf_nr, candidate in list(found.items())[:limit]:
            # Stammdaten nachladen, falls nur Adresse gefunden wurde
            if candidate.referenz is None and candidate.typ is None:
                main = (
                    self.supabase.table("3100_Sdg_Haupt")
                    .select("*")
                    .eq("ErfNr", erf_nr)
                    .eq("Storno", "0")
                    .limit(1)
                    .execute()
                )
                if main.data:
                    candidate = self._build_candidate(main.data[0])

            self._load_addresses(candidate)
            result.append(candidate)

        return result

    def _build_candidate(self, row: dict[str, Any]) -> Candidate:
        """Zeile aus 3100_Sdg_Haupt → Candidate."""
        return Candidate(
            erf_nr=str(row.get("ErfNr", "")),
            typ=row.get("Typ"),
            referenz=row.get("Ref-1"),
        )

    def _load_addresses(self, candidate: Candidate) -> None:
        """Absender/Empfänger zur ErfNr laden."""
        response = (
            self.supabase.table("3100_Sdg_Adressen")
            .select("*")
            .eq("ErfNr", candidate.erf_nr)
            .execute()
        )
        for row in response.data:
            self._add_address(candidate, row)

    @staticmethod
    def _add_address(candidate: Candidate, row: dict[str, Any]) -> None:
        """Art 1 = Absender, Art 2 = Empfänger."""
        art = str(row.get("Art", "")).strip()

        if art == "1":
            candidate.sender_name = row.get("Name1")
            candidate.sender_street = row.get("Strasse")
            candidate.sender_plz = row.get("Plz")
            candidate.sender_city = row.get("Ort")
        elif art == "2":
            candidate.receiver_name = row.get("Name1")
            candidate.receiver_street = row.get("Strasse")
            candidate.receiver_plz = row.get("Plz")
            candidate.receiver_city = row.get("Ort")

    @staticmethod
    def _words_from_text(text: str) -> list[str]:
        """Wörter ab 4 Buchstaben, ohne Füllwörter."""
        words = re.findall(r"[A-Za-zÄÖÜäöüß]{4,}", text)
        stopwords = {
            "eine", "einer", "eines", "dieser", "diese", "dieses",
            "oder", "durch", "rechnung", "frachtbrief", "lieferschein",
            "schadensmeldung", "wareneingang", "empfänger", "empfaenger",
            "absender", "straße", "strasse", "nummer", "referenz",
        }
        result = []
        for word in words:
            if word.casefold() not in stopwords and word not in result:
                result.append(word)
        return result
