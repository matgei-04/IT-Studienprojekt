"""Kandidaten-Suche in Supabase."""

from __future__ import annotations

import re
from typing import Any

from supabase import Client

from domain.models import IncomingDocument
from matching.models import Candidate


class CandidateRepository:
    """Kapselt den Zugriff auf die Spedifix-Daten."""

    def __init__(self, supabase: Client):
        self.supabase = supabase

    def find_by_order_number(self, order_number: str) -> list[Candidate]:
        """Sucht aktive Sendungen exakt über ErfNr."""
        response = (
            self.supabase.table("3100_Sdg_Haupt")
            .select("*")
            .eq("ErfNr", str(order_number))
            .eq("Storno", "0")
            .execute()
        )

        candidates = [self._build_candidate(row) for row in response.data]

        for candidate in candidates:
            self._load_addresses(candidate)

        return candidates

    def search_by_text(
        self,
        document: IncomingDocument,
        limit: int = 50,
    ) -> list[Candidate]:
        """Fallback-Suche, wenn keine eindeutige ErfNr vorhanden ist."""
        candidates: dict[str, Candidate] = {}
        tokens = self._extract_search_tokens(document.text)

        for token in tokens:
            if len(token) < 4:
                continue

            response = (
                self.supabase.table("3100_Sdg_Adressen")
                .select("*")
                .ilike("Ort", f"%{token}%")
                .limit(limit)
                .execute()
            )

            for row in response.data:
                erf_nr = row.get("ErfNr")
                if not erf_nr:
                    continue

                erf_nr = str(erf_nr)
                if erf_nr not in candidates:
                    candidates[erf_nr] = Candidate(erf_nr=erf_nr)

                self._add_address(candidates[erf_nr], row)

            response = (
                self.supabase.table("3100_Sdg_Haupt")
                .select("*")
                .ilike("Ref-1", f"%{token}%")
                .eq("Storno", "0")
                .limit(limit)
                .execute()
            )

            for row in response.data:
                erf_nr = row.get("ErfNr")
                if not erf_nr:
                    continue

                erf_nr = str(erf_nr)
                candidates[erf_nr] = self._build_candidate(row)

        result = []
        for erf_nr, candidate in list(candidates.items())[:limit]:
            if not candidate.datum:
                response = (
                    self.supabase.table("3100_Sdg_Haupt")
                    .select("*")
                    .eq("ErfNr", erf_nr)
                    .eq("Storno", "0")
                    .limit(1)
                    .execute()
                )
                if response.data:
                    candidate = self._build_candidate(response.data[0])

            self._load_addresses(candidate)
            result.append(candidate)

        return result

    def _build_candidate(self, row: dict[str, Any]) -> Candidate:
        """Erzeugt einen Candidate aus 3100_Sdg_Haupt."""
        fracht = row.get("Fracht")
        try:
            fracht_value = float(fracht) if fracht is not None else None
        except (TypeError, ValueError):
            fracht_value = None

        return Candidate(
            erf_nr=str(row.get("ErfNr", "")),
            datum=row.get("Datum"),
            typ=row.get("Typ"),
            storno=row.get("Storno"),
            lade_datum=row.get("LadeDatum"),
            entlade_datum=row.get("EntladeDatum"),
            fracht=fracht_value,
            wrg=row.get("Wrg"),
            fakt_beleg_nr=row.get("FaktBelegNr-1"),
            referenz=row.get("Ref-1"),
        )

    def _load_addresses(self, candidate: Candidate) -> None:
        """Lädt Absender und Empfänger anhand der ErfNr."""
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
        """Ordnet Adressen anhand von Art zu: 1=Absender, 2=Empfänger."""
        art = str(row.get("Art", "")).strip()

        if art == "1":
            candidate.sender_name = row.get("Name1") or row.get("Name2")
            candidate.sender_street = row.get("Strasse")
            candidate.sender_plz = row.get("PIZ")
            candidate.sender_city = row.get("Ort")

        elif art == "2":
            candidate.receiver_name = row.get("Name1") or row.get("Name2")
            candidate.receiver_street = row.get("Strasse")
            candidate.receiver_plz = row.get("PIZ")
            candidate.receiver_city = row.get("Ort")

    @staticmethod
    def _extract_search_tokens(text: str) -> list[str]:
        """Extrahiert grobe Suchbegriffe für die Fallback-Kandidatensuche."""
        words = re.findall(r"[A-Za-zÄÖÜäöüß]{4,}", text)

        stopwords = {
            "eine",
            "einer",
            "eines",
            "dieser",
            "diese",
            "dieses",
            "der",
            "die",
            "das",
            "und",
            "oder",
            "von",
            "für",
            "mit",
            "durch",
            "rechnung",
            "frachtbrief",
            "lieferschein",
            "schadensmeldung",
            "wareneingang",
            "empfänger",
            "empfaenger",
            "absender",
            "straße",
            "strasse",
            "nummer",
            "referenz",
        }

        result = []
        for word in words:
            if word.casefold() not in stopwords:
                result.append(word)

        return list(dict.fromkeys(result))
