"""Datenzugriff: Extraktion + Matching einmalig je Dokument ausführen und
dauerhaft in der Tabelle "Dokumente" speichern, danach von dort lesen.

Warum eine eigene Tabelle (seit migrations/0001_create_dokumente.sql)?
`DokumentZuordnung` speichert laut Schema nur bereits BESTÄTIGTE
Zuordnungen. Belegdatum/Betrag sowie OCR-/Matching-Abschlusszeitstempel
müssen aber für JEDES importierte Dokument nachvollziehbar sein – dafür
gibt es "Dokumente" (siehe migrations/). Ein Dokument wird nur beim ERSTEN
Auftreten verarbeitet (Extraktion, OCR, Belegdatum-/Betrags-Erkennung,
Matching); Folgeaufrufe lesen die gespeicherten Werte, statt erneut zu
OCRen/matchen.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Literal

import fitz  # PyMuPDF – nur zur Validierung hochgeladener Dateien
from dotenv import dotenv_values
from supabase import create_client

from domain.models import Settings
from extraction.beleg_daten import find_belegdatum, find_betrag
from extraction.config import load_settings
from extraction.pipeline import extract_single_document, list_pdf_files
from matching.candidate_search import CandidateRepository
from matching.matcher import DocumentMatcher

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Schwellwerte für die Ampel-Einteilung der Confidence (siehe README).
AUTO_MATCH_THRESHOLD = 0.80
REVIEW_THRESHOLD = 0.55

Bucket = Literal["automatisch", "pruefung", "nicht_zuordenbar"]

# Freundliche Anzeigenamen für die intern verwendeten Dokumenttyp-Codes.
DOCUMENT_TYPE_LABELS: dict[str, str] = {
    "eingangsrechnung": "Rechnung",
    "frachtpapier": "Frachtbrief",
    "wareneingangsschein": "Lieferschein",
    "schadensmeldung": "Schadensmeldung",
    "unbekannt": "Unbekannt",
}


def document_type_label(code: str | None) -> str:
    return DOCUMENT_TYPE_LABELS.get(code or "unbekannt", code or "Unbekannt")


@dataclass
class ReviewItem:
    """Ein Dokument aus der offenen Warteschlange (noch nicht bestätigt)."""

    path: str
    filename: str
    received_at: datetime
    document_type: str
    order_number: str | None
    candidate_erf_nr: str | None
    partner_name: str | None
    confidence: float
    bucket: Bucket
    order_reference: str | None = None
    confidence_label: str = ""
    confidence_class: str = "danger"
    note: str | None = None
    # Aus dem Dokumenttext erkannt (NICHT vom verknüpften Auftrag!) – siehe
    # extraction/beleg_daten.py. None, wenn keine plausible Erkennung möglich war.
    belegdatum: date | None = None
    betrag: Decimal | None = None
    waehrung: str | None = None
    ocr_completed_at: datetime | None = None
    matching_completed_at: datetime | None = None


def classify_confidence(score: float, high_threshold: float = AUTO_MATCH_THRESHOLD) -> Bucket:
    """Ordnet einen Matching-Score einer der drei Ampel-Kategorien zu.

    high_threshold kommt aus den Einstellungen (get_high_confidence_threshold())
    – siehe "Matching-Regeln". REVIEW_THRESHOLD (untere Grenze) ist bewusst
    nicht konfigurierbar, nur die obere ("Hohe Übereinstimmung").
    """
    if score >= high_threshold:
        return "automatisch"
    if score >= REVIEW_THRESHOLD:
        return "pruefung"
    return "nicht_zuordenbar"


def confidence_display(
    confidence: float,
    has_candidate: bool,
    high_threshold: float = AUTO_MATCH_THRESHOLD,
) -> tuple[str, str]:
    """(Text, CSS-Klasse) für die Sicherheits-Badge eines offenen Vorschlags.

    Zentrale Stelle, damit Liste (Zuordnungen) und Detailseite (Beleg prüfen)
    exakt denselben Text/dieselbe Farbe zeigen. high_threshold: siehe
    classify_confidence().
    """
    pct = round(confidence * 100)
    if not has_candidate:
        return "Kein Kandidat", "danger"
    if confidence >= high_threshold:
        return f"Hohe Übereinstimmung · {pct}%", "success"
    if confidence >= REVIEW_THRESHOLD:
        return f"Prüfung empfohlen · {pct}%", "warning"
    return f"Unsicher · {pct}%", "danger"


def workflow_status(candidate_erf_nr: str | None, note: str | None) -> str:
    """Einheitlicher Bearbeitungsstatus für offene (noch nicht bestätigte) Dokumente."""
    if note and "Matching-Fehler" in note:
        return "Fehlerhaft"
    if candidate_erf_nr:
        return "Prüfung erforderlich"
    return "Nicht zuordenbar"


def _get_env() -> dict[str, str | None]:
    return dotenv_values(PROJECT_ROOT / ".env")


@lru_cache(maxsize=1)
def _get_supabase():
    """Erstellt den Supabase-Client EINMAL und liefert ihn danach aus dem Cache.

    Ohne Cache wurde bei jedem Aufruf (bis zu ~12 pro Seitenaufruf) ein
    komplett neuer Client samt neuer HTTP-Verbindung/TLS-Handshake zum
    Supabase-Server aufgebaut – das machte jeden Seitenwechsel mehrere
    Sekunden langsam. Die Zugangsdaten stehen fest in der .env und ändern
    sich nicht zur Laufzeit, ein einmalig erstellter Client kann daher für
    die gesamte Lebensdauer der Anwendung wiederverwendet werden.
    """
    env = _get_env()
    url = env.get("SUPABASE_URL")
    key = env.get("SUPABASE_KEY")
    if not url or not key:
        return None
    return create_client(url, key)


def get_confirmed_paths() -> tuple[set[str], str | None]:
    """Liefert die Pfade aller bereits bestätigten Dokumente aus Supabase.

    Zweiter Rückgabewert ist eine Fehlermeldung, falls die DB nicht
    erreichbar war (die Seite soll dann trotzdem laden, siehe Aufrufer).
    """
    supabase = _get_supabase()
    if supabase is None:
        return set(), "SUPABASE_URL/SUPABASE_KEY sind nicht gesetzt (.env prüfen)."

    try:
        response = supabase.table("DokumentZuordnung").select("DokumentPfad").execute()
        return {row["DokumentPfad"] for row in response.data if row.get("DokumentPfad")}, None
    except Exception as exc:  # noqa: BLE001 – Dashboard soll trotzdem laden
        return set(), f"Datenbankverbindung fehlgeschlagen: {exc}"


def _short_error(exc: Exception, limit: int = 160) -> str:
    """Kürzt Fehlermeldungen (z. B. lange HTML-Fehlerseiten von Cloudflare)."""
    text = str(exc)
    if len(text) > limit:
        text = text[:limit] + "…"
    return text


# --- Einstellungen (Singleton-Tabelle, siehe migrations/0002_*) -----------
#
# "Manuelle Bestätigung erforderlich" ist bewusst KEINE Spalte/Einstellung:
# Das ist eine fachliche Sicherheitsregel, die im Code fest verankert ist
# (matcher.py: needs_manual_review immer True; confirm_assignment() ist der
# einzige Schreibpfad nach DokumentZuordnung) und nicht deaktivierbar sein
# darf. Die Seite zeigt sie nur als festen Hinweis, kein editierbares Feld.


@dataclass
class Einstellungen:
    ocr_aktiv: bool
    matching_aktiv: bool
    schwelle_hohe_uebereinstimmung: int  # 0–100, siehe get_high_confidence_threshold()
    scan_ordner: str | None = None  # None/leer: SCAN_DIRECTORY aus der .env wird verwendet


DEFAULT_EINSTELLUNGEN = Einstellungen(
    ocr_aktiv=True, matching_aktiv=True, schwelle_hohe_uebereinstimmung=80, scan_ordner=None
)


def get_einstellungen() -> tuple[Einstellungen, str | None]:
    """Liest die (einzige) Einstellungszeile. Fällt bei fehlender DB-
    Verbindung auf sichere Standardwerte zurück (nichts wird deaktiviert)."""
    supabase = _get_supabase()
    if supabase is None:
        return DEFAULT_EINSTELLUNGEN, "SUPABASE_URL/SUPABASE_KEY sind nicht gesetzt (.env prüfen)."
    try:
        resp = supabase.table("Einstellungen").select("*").eq("Id", 1).limit(1).execute()
    except Exception as exc:  # noqa: BLE001
        return DEFAULT_EINSTELLUNGEN, f"Datenbankverbindung fehlgeschlagen: {_short_error(exc)}"
    if not resp.data:
        return DEFAULT_EINSTELLUNGEN, None
    row = resp.data[0]
    return (
        Einstellungen(
            ocr_aktiv=bool(row.get("OcrAktiv", True)),
            matching_aktiv=bool(row.get("MatchingAktiv", True)),
            schwelle_hohe_uebereinstimmung=int(row.get("SchwelleHoheUebereinstimmung", 80)),
            scan_ordner=row.get("ScanOrdner") or None,
        ),
        None,
    )


def get_high_confidence_threshold() -> float:
    """0.0–1.0 – für die Klassifikation 'Hohe Übereinstimmung' überall in
    der Anwendung (Dashboard, Zuordnungen, Dokumente, Auswertungen)."""
    einstellungen, _ = get_einstellungen()
    return einstellungen.schwelle_hohe_uebereinstimmung / 100


def _save_einstellungen(
    ocr_aktiv: bool, matching_aktiv: bool, schwelle: int, scan_ordner: str | None
) -> tuple[bool, str]:
    supabase = _get_supabase()
    if supabase is None:
        return False, "Keine Datenbankverbindung – Speichern nicht möglich."
    try:
        supabase.table("Einstellungen").upsert(
            {
                "Id": 1,
                "OcrAktiv": ocr_aktiv,
                "MatchingAktiv": matching_aktiv,
                "SchwelleHoheUebereinstimmung": schwelle,
                "ScanOrdner": scan_ordner,
                "AktualisiertAm": datetime.now().isoformat(),
            },
            on_conflict="Id",
        ).execute()
    except Exception as exc:  # noqa: BLE001
        return False, f"Speichern fehlgeschlagen: {_short_error(exc)}"
    return True, "Einstellungen wurden gespeichert."


def update_verarbeitung(ocr_aktiv: bool, matching_aktiv: bool) -> tuple[bool, str]:
    """Speichert nur die Verarbeitungs-Umschalter; alle anderen Felder bleiben
    unverändert (Read-Modify-Write, damit kein Feld versehentlich
    zurückgesetzt wird)."""
    current, warning = get_einstellungen()
    if warning:
        return False, warning
    return _save_einstellungen(
        ocr_aktiv, matching_aktiv, current.schwelle_hohe_uebereinstimmung, current.scan_ordner
    )


def update_matching_schwelle(schwelle: int) -> tuple[bool, str]:
    """Speichert nur die Schwelle; alle anderen Felder bleiben unverändert."""
    if not (0 <= schwelle <= 100):
        return False, "Die Schwelle muss eine ganze Zahl zwischen 0 und 100 sein."
    current, warning = get_einstellungen()
    if warning:
        return False, warning
    return _save_einstellungen(current.ocr_aktiv, current.matching_aktiv, schwelle, current.scan_ordner)


def update_scan_ordner(pfad: str) -> tuple[bool, str]:
    """Speichert den Import-Ordner; alle anderen Felder bleiben unverändert.

    Ein leerer Wert setzt auf SCAN_DIRECTORY aus der .env zurück. Ein
    gesetzter Wert muss ein tatsächlich vorhandener Ordner sein – sonst
    würde die App beim nächsten Scan scheinbar grundlos keine Dokumente
    mehr finden.
    """
    pfad = pfad.strip()
    resolved: str | None = None
    if pfad:
        candidate = Path(pfad).expanduser()
        if not candidate.is_dir():
            return False, f"Ordner nicht gefunden: {candidate}"
        resolved = str(candidate.resolve())

    current, warning = get_einstellungen()
    if warning:
        return False, warning
    return _save_einstellungen(
        current.ocr_aktiv, current.matching_aktiv, current.schwelle_hohe_uebereinstimmung, resolved
    )


def _load_settings_with_override() -> Settings:
    """Wie load_settings(), aber der in den Einstellungen hinterlegte
    Import-Ordner (falls gesetzt) hat Vorrang vor SCAN_DIRECTORY aus der
    .env. Wird von der App überall dort verwendet, wo der tatsächlich
    aktive Scan-Ordner gebraucht wird (CLI-Skripte wie run_extraction.py
    bleiben bewusst unverändert und nutzen weiterhin nur die .env)."""
    settings = load_settings(PROJECT_ROOT / ".env")
    einstellungen, _ = get_einstellungen()
    if einstellungen.scan_ordner:
        settings.scan_directory = Path(einstellungen.scan_ordner)
    return settings


def check_database_connection() -> tuple[bool, str]:
    """Kleine, sichere Lese-Abfrage gegen die Auftragsdatenbank – meldet nur
    Erfolg/Fehler + Anzahl, niemals Connection-String/URL/Zugangsdaten."""
    supabase = _get_supabase()
    if supabase is None:
        return False, "Keine Zugangsdaten konfiguriert (SUPABASE_URL/SUPABASE_KEY fehlen)."
    try:
        resp = supabase.table("3100_Sdg_Haupt").select("ErfNr", count="exact").limit(1).execute()
        count = resp.count if resp.count is not None else "unbekannte Anzahl"
        return True, f"Verbindung erfolgreich ({count} Auftragsdatensätze gefunden)."
    except Exception as exc:  # noqa: BLE001
        return False, f"Verbindung fehlgeschlagen: {_short_error(exc)}"


@dataclass
class DataSource:
    name: str
    status: str
    status_class: str  # "success" | "danger" | "neutral"
    beschreibung: str
    link_label: str | None = None
    link_href: str | None = None
    check_action: bool = False  # True: "Verbindung prüfen"-Button (POST) statt Link


def get_datasources() -> list[DataSource]:
    """Nur tatsächlich im Projekt vorhandene Datenquellen – keine erfundenen
    Integrationen (kein E-Mail-/Cloud-/ERP-Import)."""
    settings = _load_settings_with_override()
    env = _get_env()

    sources = [
        DataSource(
            name="Manueller Datei-Upload",
            status="Aktiv",
            status_class="success",
            beschreibung="PDF-Dateien per Drag-and-Drop oder Dateiauswahl im Eingang importieren.",
            link_label="Zum Eingang",
            link_href="/eingang",
        )
    ]

    folder_active = settings.scan_directory.is_dir()
    sources.append(
        DataSource(
            name="Lokaler Importordner",
            status="Aktiv" if folder_active else "Nicht eingerichtet",
            status_class="success" if folder_active else "neutral",
            beschreibung=(
                f"{settings.scan_directory} wird automatisch nach neuen PDFs durchsucht."
                if folder_active
                else f"Ordner nicht gefunden: {settings.scan_directory}"
            ),
        )
    )

    db_configured = bool(env.get("SUPABASE_URL") and env.get("SUPABASE_KEY"))
    sources.append(
        DataSource(
            name="Auftragsdatenbank",
            status="Verbunden" if db_configured else "Nicht eingerichtet",
            status_class="success" if db_configured else "danger",
            beschreibung="Aufträge und Adressdaten (3100_Sdg_Haupt / 3100_Sdg_Adressen).",
            check_action=db_configured,
        )
    )

    return sources


# --- Persistente Dokumentverarbeitung (Tabelle "Dokumente") ---------------
#
# Ein Dokument wird nur beim ERSTEN ERFOLGREICHEN Auftreten verarbeitet
# (Extraktion, OCR, Belegdatum-/Betrags-Erkennung, Matching) und dauerhaft
# gespeichert. Erfolgs-Zeitstempel (OcrAbgeschlossenAm/MatchingAbgeschlossenAm)
# werden ausschließlich bei erfolgreichem Abschluss des jeweiligen Schritts
# gesetzt. Eine gespeicherte Fehlerzeile (z. B. durch eine kurzzeitig nicht
# erreichbare Datenbank) gilt NICHT als abgeschlossen – bei jedem weiteren
# Aufruf wird automatisch ein neuer Verarbeitungsversuch gestartet (siehe
# _braucht_neuverarbeitung), damit ein Dokument nicht dauerhaft in einem
# Fehlerzustand hängen bleibt, obwohl die Ursache längst behoben ist.


def _braucht_neuverarbeitung(row: dict | None) -> bool:
    return row is None or row.get("Status") in ("ocr_fehler", "matching_fehler")


def _fetch_dokumente_by_path(supabase) -> dict[str, dict]:
    """Alle Dokumente-Zeilen auf einmal, indiziert nach DokumentPfad."""
    if supabase is None:
        return {}
    try:
        resp = supabase.table("Dokumente").select("*").execute()
        return {row["DokumentPfad"]: row for row in resp.data if row.get("DokumentPfad")}
    except Exception:  # noqa: BLE001 – Seite soll trotzdem laden
        return {}


def _fetch_dokument_row(supabase, path: str) -> dict | None:
    if supabase is None:
        return None
    try:
        resp = supabase.table("Dokumente").select("*").eq("DokumentPfad", path).limit(1).execute()
        return resp.data[0] if resp.data else None
    except Exception:  # noqa: BLE001
        return None


def _upsert_dokument(supabase, row: dict) -> None:
    if supabase is None:
        return
    try:
        supabase.table("Dokumente").upsert(row, on_conflict="DokumentPfad").execute()
    except Exception:  # noqa: BLE001 – Anzeige soll trotzdem funktionieren
        pass


def _process_document(pdf_path: Path, settings, matcher: DocumentMatcher | None, supabase) -> dict:
    """Verarbeitet ein Dokument genau einmal und speichert das Ergebnis.

    Reihenfolge: Extraktion/OCR -> Belegdatum/Betrag aus DEMSELBEN Text
    (kein zweiter OCR-Lauf) -> Matching. Bricht ein Schritt mit einer
    Ausnahme ab, wird NUR der jeweilige Fehlerstatus gespeichert; der
    Abschlusszeitstempel dieses Schritts bleibt leer.
    """
    row: dict = {"DokumentPfad": str(pdf_path), "Dateiname": pdf_path.name}
    einstellungen, _ = get_einstellungen()

    try:
        document = extract_single_document(pdf_path, settings, allow_ocr=einstellungen.ocr_aktiv)
    except Exception as exc:  # noqa: BLE001
        row["Status"] = "ocr_fehler"
        row["Fehlermeldung"] = _short_error(exc)
        _upsert_dokument(supabase, row)
        return row

    row["DokumentTyp"] = document.document_type
    row["ErkannteAuftragsnummer"] = document.order_number
    row["OcrAbgeschlossenAm"] = datetime.now().isoformat()

    belegdatum = find_belegdatum(document.text)
    betrag, waehrung = find_betrag(document.text)
    row["Belegdatum"] = belegdatum.isoformat() if belegdatum else None
    row["Betrag"] = str(betrag) if betrag is not None else None
    row["Waehrung"] = waehrung

    if not einstellungen.matching_aktiv:
        # Matching bewusst deaktiviert – kein Vorschlag wird erzeugt.
        # Manuelle Bestätigung bleibt davon unberührt: es gab ohnehin nie
        # eine automatische Speicherung, siehe confirm_assignment().
        row["Status"] = "matching_deaktiviert"
        row["Fehlermeldung"] = None
        _upsert_dokument(supabase, row)
        return row

    if matcher is None:
        row["Status"] = "nicht_zuordenbar"
        row["Fehlermeldung"] = "Keine Datenbankverbindung – Matching übersprungen."
        _upsert_dokument(supabase, row)
        return row

    try:
        result = matcher.match(document)
    except Exception as exc:  # noqa: BLE001
        row["Status"] = "matching_fehler"
        row["Fehlermeldung"] = _short_error(exc)
        _upsert_dokument(supabase, row)
        return row

    row["MatchingAbgeschlossenAm"] = datetime.now().isoformat()
    row["ErfNr"] = result.candidate.erf_nr if result.candidate else None
    row["Score"] = str(result.confidence)
    row["Status"] = "pruefung" if result.candidate else "nicht_zuordenbar"
    row["Fehlermeldung"] = None

    _upsert_dokument(supabase, row)
    return row


def _decimal_or_none(value) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def _review_item_from_row(row: dict, pdf_path: Path, high_threshold: float = AUTO_MATCH_THRESHOLD) -> ReviewItem:
    """Baut ein ReviewItem aus einer gespeicherten Dokumente-Zeile (keine
    erneute Extraktion/Matching nötig)."""
    status_code = row.get("Status") or "importiert"
    candidate_erf_nr = row.get("ErfNr")
    score = row.get("Score")
    confidence = float(score) if score is not None else 0.0

    note = None
    if status_code == "ocr_fehler":
        note = f"OCR-Fehler: {row.get('Fehlermeldung') or 'unbekannt'}"
    elif status_code == "matching_fehler":
        note = f"Matching-Fehler: {row.get('Fehlermeldung') or 'unbekannt'}"
    elif status_code == "matching_deaktiviert":
        note = "Matching ist in den Einstellungen deaktiviert."

    if status_code in ("ocr_fehler", "matching_fehler"):
        label, css_class = "Fehlerhaft", "danger"
    elif status_code == "matching_deaktiviert":
        label, css_class = "Matching deaktiviert", "neutral"
    else:
        label, css_class = confidence_display(confidence, candidate_erf_nr is not None, high_threshold)

    imported_raw = row.get("ImportiertAm")
    received_at = (
        datetime.fromisoformat(imported_raw) if imported_raw else datetime.fromtimestamp(pdf_path.stat().st_mtime)
    )
    ocr_raw = row.get("OcrAbgeschlossenAm")
    matching_raw = row.get("MatchingAbgeschlossenAm")
    belegdatum_raw = row.get("Belegdatum")

    return ReviewItem(
        path=str(pdf_path),
        filename=pdf_path.name,
        received_at=received_at,
        document_type=row.get("DokumentTyp") or "unbekannt",
        order_number=row.get("ErkannteAuftragsnummer"),
        candidate_erf_nr=candidate_erf_nr,
        partner_name=None,  # Lieferant/Kunde: siehe get_assignment_rows() (Auftrags-Lookup)
        confidence=confidence,
        bucket=classify_confidence(confidence, high_threshold),
        order_reference=None,
        confidence_label=label,
        confidence_class=css_class,
        note=note,
        belegdatum=date.fromisoformat(belegdatum_raw) if belegdatum_raw else None,
        betrag=_decimal_or_none(row.get("Betrag")),
        waehrung=row.get("Waehrung"),
        ocr_completed_at=datetime.fromisoformat(ocr_raw) if ocr_raw else None,
        matching_completed_at=datetime.fromisoformat(matching_raw) if matching_raw else None,
    )


def get_open_review_items() -> tuple[list[ReviewItem], str | None]:
    """Alle noch nicht bestätigten Dokumente aus dem Scan-Ordner.

    Liest verarbeitete Dokumente aus der Tabelle "Dokumente"; nur bei
    erstmaligem Auftreten wird live verarbeitet (und dabei gespeichert).
    """
    settings = _load_settings_with_override()
    confirmed_paths, warning = get_confirmed_paths()

    supabase = _get_supabase()
    matcher = DocumentMatcher(CandidateRepository(supabase)) if supabase else None
    high_threshold = get_high_confidence_threshold()

    try:
        pdf_paths = list_pdf_files(settings.scan_directory)
    except FileNotFoundError:
        return [], warning or f"Scan-Verzeichnis nicht gefunden: {settings.scan_directory}"

    stored = _fetch_dokumente_by_path(supabase)

    items: list[ReviewItem] = []
    for pdf_path in pdf_paths:
        key = str(pdf_path)
        if key in confirmed_paths:
            continue

        row = stored.get(key)
        if _braucht_neuverarbeitung(row):
            row = _process_document(pdf_path, settings, matcher, supabase)

        items.append(_review_item_from_row(row, pdf_path, high_threshold))

    return items, warning


def get_review_detail(path_str: str):
    """Vollständige Details zu einem Dokument (inkl. Kandidat + Begründungen).

    Belegdatum/Betrag/Zeitstempel kommen aus der gespeicherten Dokumente-
    Zeile (kein erneutes OCR). Für Kandidat + Begründungen (nicht
    persistiert, da nur für die Prüfseite relevant) läuft Matching einmal
    frisch – wie bisher.
    """
    pdf_path = Path(path_str)
    if not pdf_path.is_file():
        return None

    settings = load_settings(PROJECT_ROOT / ".env")
    supabase = _get_supabase()
    matcher = DocumentMatcher(CandidateRepository(supabase)) if supabase else None
    einstellungen, _ = get_einstellungen()
    high_threshold = einstellungen.schwelle_hohe_uebereinstimmung / 100

    row = _fetch_dokument_row(supabase, str(pdf_path))
    if _braucht_neuverarbeitung(row):
        row = _process_document(pdf_path, settings, matcher, supabase)

    item = _review_item_from_row(row, pdf_path, high_threshold)

    candidate = None
    reasons: list[str] = []
    if supabase is None:
        if item.note is None:
            item.note = "Keine Datenbankverbindung – Matching übersprungen."
    elif not einstellungen.matching_aktiv:
        if item.note is None:
            item.note = "Matching ist in den Einstellungen deaktiviert."
    else:
        try:
            document = extract_single_document(pdf_path, settings, allow_ocr=einstellungen.ocr_aktiv)
            result = DocumentMatcher(CandidateRepository(supabase)).match(document)
            candidate = result.candidate
            reasons = result.breakdown.reasons
        except Exception:  # noqa: BLE001 – Anzeige nutzt weiterhin die gespeicherten Werte
            pass

    confirmed = None
    if supabase is not None:
        try:
            resp = (
                supabase.table("DokumentZuordnung")
                .select("*")
                .eq("DokumentPfad", str(pdf_path))
                .limit(1)
                .execute()
            )
            if resp.data:
                confirmed = resp.data[0]
                if confirmed.get("BestaetigtAm"):
                    confirmed["BestaetigtAm"] = datetime.fromisoformat(confirmed["BestaetigtAm"])
        except Exception:  # noqa: BLE001 – Detailseite soll trotzdem laden
            pass

    if confirmed is not None:
        # Gleicher Status wie in der Zuordnungen-Liste zeigen, nicht die
        # live neu berechnete (und ggf. abweichende) Confidence-Einstufung.
        confirmed_score = confirmed.get("Score")
        pct = round(float(confirmed_score) * 100) if confirmed_score is not None else round(item.confidence * 100)
        item.confidence_label = f"Bestätigt · {pct}%"
        item.confidence_class = "success"

    return item, candidate, reasons, confirmed


def confirm_assignment(
    doc_path: str,
    erf_nr: str,
    score: float,
    document_type: str | None,
    confirmed_by: str | None = None,
) -> tuple[bool, str]:
    """Speichert eine bestätigte Zuordnung in DokumentZuordnung.

    Legt eine neue Zeile an oder aktualisiert eine vorhandene für denselben
    DokumentPfad (kein UNIQUE-Constraint in der DB, die Eindeutigkeit wird
    hier in der Anwendung sichergestellt). "Id" hat in der DB keinen
    Default/keine Sequenz, daher wird die nächste freie Id selbst ermittelt.
    """
    pdf_path = Path(doc_path)
    if not pdf_path.is_file():
        return False, "Dokument wurde nicht gefunden (evtl. verschoben oder gelöscht)."

    supabase = _get_supabase()
    if supabase is None:
        return False, "Keine Datenbankverbindung – Bestätigung nicht möglich."

    try:
        candidates = CandidateRepository(supabase).find_by_order_number(erf_nr)
    except Exception as exc:  # noqa: BLE001
        return False, f"Auftrag konnte nicht geprüft werden: {_short_error(exc)}"

    if not candidates:
        return False, f"Auftrag {erf_nr} wurde nicht gefunden oder ist storniert."

    payload = {
        "DokumentPfad": str(pdf_path),
        "ErfNr": erf_nr,
        "Score": round(score, 3),
        "DokumentTyp": document_type,
        "BestaetigtAm": datetime.now().isoformat(),
        "BestaetigtVon": confirmed_by,
    }

    try:
        existing = (
            supabase.table("DokumentZuordnung")
            .select("Id")
            .eq("DokumentPfad", str(pdf_path))
            .limit(1)
            .execute()
        )
        if existing.data:
            row_id = existing.data[0]["Id"]
            supabase.table("DokumentZuordnung").update(payload).eq("Id", row_id).execute()
        else:
            max_id_resp = (
                supabase.table("DokumentZuordnung")
                .select("Id")
                .order("Id", desc=True)
                .limit(1)
                .execute()
            )
            next_id = (max_id_resp.data[0]["Id"] + 1) if max_id_resp.data else 1
            payload["Id"] = next_id
            supabase.table("DokumentZuordnung").insert(payload).execute()
    except Exception as exc:  # noqa: BLE001
        return False, f"Speichern fehlgeschlagen: {_short_error(exc)}"

    # Dokumente-Status mitziehen (nur informativ – DokumentZuordnung bleibt
    # die eigentliche Quelle der Wahrheit für "bestätigt"; wenn das hier
    # fehlschlägt, ist die Bestätigung selbst trotzdem gültig).
    _upsert_dokument(
        supabase,
        {
            "DokumentPfad": str(pdf_path),
            "Dateiname": pdf_path.name,
            "Status": "bestaetigt",
            "ErfNr": erf_nr,
            "Score": str(round(score, 3)),
        },
    )

    return True, "Zuordnung wurde bestätigt."


def compute_kpis(items: list[ReviewItem]) -> dict[str, int]:
    """Kennzahlen für die vier Dashboard-Kacheln."""
    return {
        "neu": len(items),
        "automatisch": sum(1 for i in items if i.bucket == "automatisch"),
        "pruefung": sum(1 for i in items if i.bucket == "pruefung"),
        "nicht_zuordenbar": sum(1 for i in items if i.bucket == "nicht_zuordenbar"),
    }


def compute_today(items: list[ReviewItem]) -> dict[str, int]:
    """Wie compute_kpis, aber nur für heute eingegangene Dokumente.

    'Eingegangen' wird mangels echtem Import-Zeitstempel über das
    Änderungsdatum der Datei angenähert (siehe Modul-Docstring).
    """
    today = date.today()
    today_items = [i for i in items if i.received_at.date() == today]
    return compute_kpis(today_items)


SORT_FIELDS = {
    "document": lambda i: i.filename.casefold(),
    "date": lambda i: i.received_at,
    "order": lambda i: i.candidate_erf_nr or "",
    "confidence": lambda i: i.confidence,
}


def sort_items(items: list[ReviewItem], sort: str, direction: str) -> list[ReviewItem]:
    key_fn = SORT_FIELDS.get(sort, SORT_FIELDS["confidence"])
    return sorted(items, key=key_fn, reverse=(direction == "desc"))


@dataclass
class AssignmentRow:
    """Ein Dokument in seinem aktuellen Bearbeitungsstand (offen oder bestätigt).

    Wird von der Eingang-Seite ("Letzte Importe") und der Zuordnungen-Seite
    (Arbeitswarteschlange) gemeinsam genutzt, damit beide denselben Status
    zeigen und nicht auseinanderlaufen können.
    """

    path: str
    filename: str
    received_at: datetime
    document_type: str
    document_type_label: str
    source: str
    file_exists: bool
    partner_name: str | None
    candidate_erf_nr: str | None
    order_reference: str | None
    confidence: float | None
    status: str  # "Bestätigt" | "Prüfung erforderlich" | "Nicht zuordenbar" | "Fehlerhaft"
    confidence_label: str
    confidence_class: str
    confirmed_at: datetime | None = None
    confirmed_by: str | None = None
    # Aus dem Dokumenttext erkannt (nicht vom Auftrag) – siehe extraction/beleg_daten.py.
    belegdatum: date | None = None
    betrag: Decimal | None = None
    waehrung: str | None = None
    ocr_completed_at: datetime | None = None
    matching_completed_at: datetime | None = None


def _source_label(pdf_path: Path, scan_directory: Path) -> str:
    """Grobe Herkunftsangabe anhand des Unterordners (keine echte Quellen-DB)."""
    try:
        rel = pdf_path.relative_to(scan_directory)
    except ValueError:
        return "Unbekannt"

    parts = rel.parts
    if len(parts) <= 1:
        return "Scan-Ordner"
    if parts[0] == "eingang":
        return "Manueller Import"
    return f"Ordner: {parts[0]}"


def _confirmed_lookup_data(supabase, erf_nrs: list[str]) -> dict[str, dict]:
    """Lädt Referenz (Ref-1) und Absender/Empfänger für mehrere ErfNr in je einem Aufruf.

    Vermeidet N Einzelabfragen für N bestätigte Zuordnungen.
    """
    if not erf_nrs:
        return {}

    lookup: dict[str, dict] = {nr: {} for nr in erf_nrs}

    try:
        haupt = supabase.table("3100_Sdg_Haupt").select("ErfNr, Ref-1").in_("ErfNr", erf_nrs).execute()
        for row in haupt.data:
            nr = row.get("ErfNr")
            if nr in lookup:
                lookup[nr]["referenz"] = row.get("Ref-1")
    except Exception:  # noqa: BLE001 – Zusatzinfo, Seite soll trotzdem laden
        pass

    try:
        adr = supabase.table("3100_Sdg_Adressen").select("*").in_("ErfNr", erf_nrs).execute()
        for row in adr.data:
            nr = row.get("ErfNr")
            if nr not in lookup:
                continue
            if row.get("Art") == 1 and "partner_name" not in lookup[nr]:
                lookup[nr]["partner_name"] = row.get("Name1") or row.get("Name2")
            elif row.get("Art") == 2 and "partner_name" not in lookup[nr]:
                lookup[nr]["partner_name"] = row.get("Name1") or row.get("Name2")
    except Exception:  # noqa: BLE001
        pass

    return lookup


def get_assignment_rows() -> tuple[list[AssignmentRow], str | None]:
    """Alle bekannten Dokumente (offen + bestätigt) als einheitliche Zeilen.

    Grundlage für 'Eingang' (Letzte Importe) und 'Zuordnungen' (Arbeits-
    warteschlange). Offene Dokumente kommen aus get_open_review_items(),
    bestätigte aus DokumentZuordnung + der gespeicherten Dokumente-Zeile
    (für Belegdatum/Betrag/Zeitstempel – dieselbe Quelle wie bei offenen
    Dokumenten, damit sich beim Bestätigen keine Werte scheinbar ändern).
    """
    settings = _load_settings_with_override()
    open_items, warning = get_open_review_items()

    rows: list[AssignmentRow] = []
    for item in open_items:
        rows.append(
            AssignmentRow(
                path=item.path,
                filename=item.filename,
                received_at=item.received_at,
                document_type=item.document_type,
                document_type_label=document_type_label(item.document_type),
                source=_source_label(Path(item.path), settings.scan_directory),
                file_exists=True,
                partner_name=item.partner_name,
                candidate_erf_nr=item.candidate_erf_nr,
                order_reference=item.order_reference,
                confidence=item.confidence,
                status=workflow_status(item.candidate_erf_nr, item.note),
                confidence_label=item.confidence_label,
                confidence_class=item.confidence_class,
                belegdatum=item.belegdatum,
                betrag=item.betrag,
                waehrung=item.waehrung,
                ocr_completed_at=item.ocr_completed_at,
                matching_completed_at=item.matching_completed_at,
            )
        )

    supabase = _get_supabase()
    if supabase is not None:
        try:
            resp = supabase.table("DokumentZuordnung").select("*").execute()
            erf_nrs = list({row["ErfNr"] for row in resp.data if row.get("ErfNr")})
            extra = _confirmed_lookup_data(supabase, erf_nrs)
            dokumente = _fetch_dokumente_by_path(supabase)

            for row in resp.data:
                pfad = row.get("DokumentPfad")
                if not pfad:
                    continue
                pdf_path = Path(pfad)
                file_exists = pdf_path.is_file()

                dokument_row = dokumente.get(pfad, {})
                imported_raw = dokument_row.get("ImportiertAm")
                if imported_raw:
                    received_at = datetime.fromisoformat(imported_raw)
                elif file_exists:
                    received_at = datetime.fromtimestamp(pdf_path.stat().st_mtime)
                else:
                    received_at = datetime.fromisoformat(row["BestaetigtAm"])
                source = (
                    _source_label(pdf_path, settings.scan_directory)
                    if file_exists
                    else "Unbekannt (Datei nicht mehr vorhanden)"
                )

                score = row.get("Score")
                confidence = float(score) if score is not None else None
                erf_nr = row.get("ErfNr")
                info = extra.get(erf_nr, {})
                doc_type = row.get("DokumentTyp") or dokument_row.get("DokumentTyp")
                confirmed_at = datetime.fromisoformat(row["BestaetigtAm"]) if row.get("BestaetigtAm") else None

                belegdatum_raw = dokument_row.get("Belegdatum")
                ocr_raw = dokument_row.get("OcrAbgeschlossenAm")
                matching_raw = dokument_row.get("MatchingAbgeschlossenAm")

                rows.append(
                    AssignmentRow(
                        path=pfad,
                        filename=pdf_path.name,
                        received_at=received_at,
                        document_type=doc_type or "unbekannt",
                        document_type_label=document_type_label(doc_type),
                        source=source,
                        file_exists=file_exists,
                        partner_name=info.get("partner_name"),
                        candidate_erf_nr=erf_nr,
                        order_reference=info.get("referenz"),
                        confidence=confidence,
                        status="Bestätigt",
                        confidence_label=f"Bestätigt · {round((confidence or 0) * 100)}%",
                        confidence_class="success",
                        confirmed_at=confirmed_at,
                        confirmed_by=row.get("BestaetigtVon"),
                        belegdatum=date.fromisoformat(belegdatum_raw) if belegdatum_raw else None,
                        betrag=_decimal_or_none(dokument_row.get("Betrag")),
                        waehrung=dokument_row.get("Waehrung"),
                        ocr_completed_at=datetime.fromisoformat(ocr_raw) if ocr_raw else None,
                        matching_completed_at=datetime.fromisoformat(matching_raw) if matching_raw else None,
                    )
                )
        except Exception as exc:  # noqa: BLE001 – Seite soll trotzdem laden
            warning = warning or f"Datenbankverbindung fehlgeschlagen: {_short_error(exc)}"

    return rows, warning


ASSIGNMENT_SORT_FIELDS = {
    "document": lambda r: r.filename.casefold(),
    "date": lambda r: r.received_at,
    "status": lambda r: r.status,
    "order": lambda r: r.candidate_erf_nr or "",
    "confidence": lambda r: r.confidence if r.confidence is not None else -1.0,
}


def sort_assignment_rows(
    rows: list[AssignmentRow],
    sort: str,
    direction: str,
    prioritize_open: bool = False,
) -> list[AssignmentRow]:
    """Sortiert Zeilen. prioritize_open zeigt unbestätigte Fälle immer zuerst
    (Standardansicht der Zuordnungen-Seite: 'offene Fälle zuerst')."""
    if prioritize_open:
        return sorted(
            rows,
            key=lambda r: (r.status == "Bestätigt", r.confidence if r.confidence is not None else -1.0),
        )
    key_fn = ASSIGNMENT_SORT_FIELDS.get(sort, ASSIGNMENT_SORT_FIELDS["date"])
    return sorted(rows, key=key_fn, reverse=(direction == "desc"))


def filter_assignment_rows(
    rows: list[AssignmentRow],
    filter_key: str | None,
    query: str | None,
) -> list[AssignmentRow]:
    result = rows
    if filter_key == "pruefung":
        result = [r for r in result if r.status == "Prüfung erforderlich"]
    elif filter_key == "nicht_zuordenbar":
        result = [r for r in result if r.status in ("Nicht zuordenbar", "Fehlerhaft")]
    elif filter_key == "bestaetigt":
        result = [r for r in result if r.status == "Bestätigt"]

    if query:
        needle = query.casefold()
        result = [
            r
            for r in result
            if needle in r.filename.casefold()
            or (r.partner_name and needle in r.partner_name.casefold())
            or (r.candidate_erf_nr and needle in r.candidate_erf_nr.casefold())
        ]
    return result


def compute_import_status(rows: list[AssignmentRow]) -> dict[str, int]:
    """Kennzahlen für die 'Import-Status'-Karte auf der Eingang-Seite."""
    fehlerhaft = sum(1 for r in rows if r.status == "Fehlerhaft")
    return {
        "gesamt": len(rows),
        "abgeschlossen": sum(1 for r in rows if r.status != "Fehlerhaft"),
        # Verarbeitung läuft synchron (kein Hintergrundjob) – es gibt keinen
        # Dokumentzustand, der hier ehrlich > 0 wäre.
        "in_bearbeitung": 0,
        "fehler": fehlerhaft,
    }


_FILENAME_SAFE = re.compile(r"[^A-Za-z0-9._\- ÄÖÜäöüß]+")
MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MB


def save_uploaded_pdf(filename: str, content: bytes) -> tuple[Path | None, str | None]:
    """Validiert und speichert eine hochgeladene PDF im Scan-Ordner.

    Gibt (Pfad, None) bei Erfolg oder (None, Fehlermeldung) zurück.
    Es wird bewusst nur PDF unterstützt, weil das die einzige Datei-Art ist,
    die die vorhandene Extraktion (extraction/pdf_text.py, extraction/ocr.py)
    tatsächlich verarbeiten kann.
    """
    safe_name = Path(filename).name  # entfernt Pfadanteile (Path Traversal)
    if not safe_name.lower().endswith(".pdf"):
        return None, f"'{safe_name}': Nur PDF-Dateien werden unterstützt."

    if not content:
        return None, f"'{safe_name}': Datei ist leer."

    if len(content) > MAX_UPLOAD_BYTES:
        return None, f"'{safe_name}': Datei ist zu groß (max. {MAX_UPLOAD_BYTES // (1024 * 1024)} MB)."

    try:
        with fitz.open(stream=content, filetype="pdf") as doc:
            if doc.page_count == 0:
                return None, f"'{safe_name}': PDF enthält keine Seiten."
    except Exception:  # noqa: BLE001 – jede Art von defekter Datei
        return None, f"'{safe_name}': Datei ist beschädigt oder keine gültige PDF."

    safe_name = _FILENAME_SAFE.sub("_", safe_name)

    settings = _load_settings_with_override()
    target_dir = settings.scan_directory / "eingang"
    target_dir.mkdir(parents=True, exist_ok=True)

    target = target_dir / safe_name
    if target.exists():
        stem, suffix = target.stem, target.suffix
        counter = 1
        while target.exists():
            target = target_dir / f"{stem}_{counter}{suffix}"
            counter += 1

    target.write_bytes(content)
    return target, None


# --- Aufträge -------------------------------------------------------------
#
# Ein "Auftrag" ist eine Zeile aus 3100_Sdg_Haupt. Die dortigen Felder für
# Betrag (Fracht) und Datum werden vom Matching-Modul (Candidate) bewusst
# nicht mitgeführt – hier daher eine eigene, unabhängige Abfrage, statt das
# Matching-Modul für einen anderen Zweck zu erweitern. Es gibt kein eigenes
# "Beschreibung"-Feld in der DB; als bester verfügbarer Ersatz wird die
# Referenz (Ref-1) verwendet.


@dataclass
class Order:
    """Ein aktiver (nicht stornierter) Auftrag aus 3100_Sdg_Haupt."""

    erf_nr: str
    kunde: str | None
    beschreibung: str | None  # Ref-1 – es gibt kein eigenes Beschreibungsfeld
    betrag: float | None      # Fracht
    waehrung: str | None      # Wrg
    datum_raw: str | None
    datum: date | None        # geparst; None wenn Datum fehlt/nicht parsebar


def _parse_order_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def get_orders() -> tuple[list[Order], str | None]:
    """Alle aktiven Aufträge (Storno='0') mit abgeleitetem Kundennamen."""
    supabase = _get_supabase()
    if supabase is None:
        return [], "SUPABASE_URL/SUPABASE_KEY sind nicht gesetzt (.env prüfen)."

    try:
        haupt = supabase.table("3100_Sdg_Haupt").select("*").eq("Storno", "0").execute()
        erf_nrs = [row.get("ErfNr") for row in haupt.data if row.get("ErfNr")]
        adr = (
            supabase.table("3100_Sdg_Adressen").select("*").in_("ErfNr", erf_nrs).execute()
            if erf_nrs
            else None
        )
    except Exception as exc:  # noqa: BLE001
        return [], f"Datenbankverbindung fehlgeschlagen: {_short_error(exc)}"

    addresses: dict[str, dict[str, str | None]] = {}
    if adr is not None:
        for row in adr.data:
            nr = row.get("ErfNr")
            if nr is None:
                continue
            slot = addresses.setdefault(nr, {})
            if row.get("Art") == 1 and "sender" not in slot:
                slot["sender"] = row.get("Name1") or row.get("Name2")
            elif row.get("Art") == 2 and "receiver" not in slot:
                slot["receiver"] = row.get("Name1") or row.get("Name2")

    orders: list[Order] = []
    for row in haupt.data:
        nr = row.get("ErfNr")
        if not nr:
            continue
        addr = addresses.get(nr, {})
        fracht = row.get("Fracht")
        orders.append(
            Order(
                erf_nr=str(nr),
                kunde=addr.get("sender") or addr.get("receiver"),
                beschreibung=row.get("Ref-1"),
                betrag=float(fracht) if fracht is not None else None,
                waehrung=row.get("Wrg"),
                datum_raw=row.get("Datum"),
                datum=_parse_order_date(row.get("Datum")),
            )
        )
    return orders, None


def search_orders(query: str, limit: int = 8) -> tuple[list[Order], str | None]:
    """Einfache Freitextsuche für die manuelle Auftragsauswahl (Prüfseite,
    wenn kein automatischer Kandidat gefunden wurde). Nutzt dieselbe
    Auftragsliste wie 'Aufträge', ohne den teureren Dokumentabgleich aus
    get_order_summaries()."""
    orders, warning = get_orders()
    needle = query.strip().casefold()
    if not needle:
        return [], warning
    matches = [
        o
        for o in orders
        if needle in o.erf_nr.casefold()
        or (o.kunde and needle in o.kunde.casefold())
        or (o.beschreibung and needle in o.beschreibung.casefold())
    ]
    return matches[:limit], warning


@dataclass
class OrderSummary:
    """Ein Auftrag zusammen mit Anzahl/Status der ihm zugeordneten Dokumente."""

    order: Order
    document_count: int
    status: str  # "Vollständig" | "Prüfung erforderlich" | "Ohne Dokumente"
    documents: list[AssignmentRow]


ORDER_STATUS_CLASS = {
    "Vollständig": "success",
    "Prüfung erforderlich": "warning",
    "Ohne Dokumente": "danger",
}


def _order_status(docs: list[AssignmentRow]) -> str:
    """Zentrale Statuslogik – wird von Liste UND Detailseite genutzt.

    Vollständig: mind. ein Beleg gültig zugeordnet, keine offenen Fälle mehr.
    Prüfung erforderlich: mind. ein Beleg/Matching-Fall braucht noch eine
    Entscheidung (auch wenn daneben schon andere Belege bestätigt sind).
    Ohne Dokumente: kein Dokument verweist (vorgeschlagen oder bestätigt)
    auf diesen Auftrag.
    """
    if not docs:
        return "Ohne Dokumente"
    if any(d.status in ("Prüfung erforderlich", "Fehlerhaft") for d in docs):
        return "Prüfung erforderlich"
    if any(d.status == "Bestätigt" for d in docs):
        return "Vollständig"
    return "Ohne Dokumente"


def get_order_summaries() -> tuple[list[OrderSummary], str | None]:
    """Aufträge mit live abgeleitetem Dokumentstatus (siehe _order_status)."""
    orders, warning1 = get_orders()
    rows, warning2 = get_assignment_rows()

    by_erf_nr: dict[str, list[AssignmentRow]] = {}
    for row in rows:
        if row.candidate_erf_nr:
            by_erf_nr.setdefault(row.candidate_erf_nr, []).append(row)

    summaries = [
        OrderSummary(
            order=order,
            document_count=len(by_erf_nr.get(order.erf_nr, [])),
            status=_order_status(by_erf_nr.get(order.erf_nr, [])),
            documents=by_erf_nr.get(order.erf_nr, []),
        )
        for order in orders
    ]
    return summaries, warning1 or warning2


def get_order_detail(erf_nr: str) -> tuple[OrderSummary | None, str | None]:
    summaries, warning = get_order_summaries()
    for summary in summaries:
        if summary.order.erf_nr == erf_nr:
            return summary, warning
    return None, warning


def order_events(documents: list[AssignmentRow]) -> list[tuple[datetime, str]]:
    """Ehrliche Ereignishistorie aus echten Zeitstempeln.

    Zeigt nur Ereignisse, für die tatsächlich ein Zeitstempel gespeichert
    ist (Import, OCR-Abschluss, Matching-Abschluss, Bestätigung). Bei
    einem OCR-/Matching-Fehler fehlt der jeweilige Zeitstempel bewusst –
    es wird kein erfundenes Ereignis angezeigt.
    """
    events: list[tuple[datetime, str]] = []
    for doc in documents:
        events.append((doc.received_at, f"„{doc.filename}“ importiert"))
        if doc.ocr_completed_at:
            events.append((doc.ocr_completed_at, f"„{doc.filename}“ – Texterkennung abgeschlossen"))
        if doc.matching_completed_at:
            events.append((doc.matching_completed_at, f"„{doc.filename}“ – Matching durchgeführt"))
        if doc.confirmed_at:
            who = f" von {doc.confirmed_by}" if doc.confirmed_by else ""
            events.append((doc.confirmed_at, f"„{doc.filename}“ bestätigt{who}"))
    events.sort(key=lambda e: e[0])
    return events


ORDER_SORT_FIELDS = {
    "erf_nr": lambda s: s.order.erf_nr,
    "kunde": lambda s: (s.order.kunde or "").casefold(),
    "betrag": lambda s: s.order.betrag if s.order.betrag is not None else -1.0,
    "status": lambda s: s.status,
    "dokumente": lambda s: s.document_count,
    "datum": lambda s: s.order.datum or date.min,
}


def sort_order_summaries(summaries: list[OrderSummary], sort: str, direction: str) -> list[OrderSummary]:
    key_fn = ORDER_SORT_FIELDS.get(sort, ORDER_SORT_FIELDS["datum"])
    return sorted(summaries, key=key_fn, reverse=(direction == "desc"))


def filter_order_summaries(
    summaries: list[OrderSummary],
    status_filter: str | None,
    kunde_filter: str | None,
    date_from: date | None,
    date_to: date | None,
    query: str | None,
) -> list[OrderSummary]:
    result = summaries
    if status_filter in ORDER_STATUS_CLASS:
        result = [s for s in result if s.status == status_filter]
    if kunde_filter:
        result = [s for s in result if s.order.kunde == kunde_filter]
    if date_from:
        result = [s for s in result if s.order.datum and s.order.datum >= date_from]
    if date_to:
        result = [s for s in result if s.order.datum and s.order.datum <= date_to]
    if query:
        needle = query.casefold()
        result = [
            s
            for s in result
            if needle in s.order.erf_nr.casefold()
            or (s.order.kunde and needle in s.order.kunde.casefold())
            or (s.order.beschreibung and needle in s.order.beschreibung.casefold())
        ]
    return result


# --- Dokumente (Archiv) ----------------------------------------------------
#
# Kombiniert AssignmentRow (Datei/Status/Confidence/Belegdatum/Betrag – aus
# dem Dokument selbst, siehe extraction/beleg_daten.py) mit dem verknüpften
# Order nur für die Auftrags-Anzeige/den Link. Betrag/Belegdatum kommen
# bewusst NICHT vom Auftrag (3100_Sdg_Haupt.Fracht/Datum) – das wäre
# fachlich falsch, da Beleg und Auftrag unterschiedliche Werte haben können.


def resolve_document_path(doc_path_str: str | None) -> Path | None:
    """Löst einen Dokumentpfad sicher auf.

    Nur echte, existierende Dateien INNERHALB von SCAN_DIRECTORY werden
    akzeptiert. Verhindert, dass über den `doc`-Query-Parameter beliebige
    Dateien außerhalb des Scan-Ordners angefragt werden können.
    """
    if not doc_path_str:
        return None

    settings = _load_settings_with_override()
    try:
        candidate = Path(doc_path_str).resolve()
        scan_root = settings.scan_directory.resolve()
    except (OSError, ValueError):
        return None

    if not candidate.is_file():
        return None
    if not candidate.is_relative_to(scan_root):
        return None
    return candidate


@dataclass
class DocumentEntry:
    """Ein Archiv-Eintrag: Dokument + (falls vorhanden) verknüpfter Auftrag."""

    row: AssignmentRow
    order: Order | None


def get_document_entries() -> tuple[list[DocumentEntry], str | None]:
    """Alle Dokumente (offen + bestätigt) mit ihrem verknüpften Auftrag."""
    rows, warning1 = get_assignment_rows()
    orders, warning2 = get_orders()
    orders_by_erf_nr = {o.erf_nr: o for o in orders}

    entries = [
        DocumentEntry(
            row=row,
            order=orders_by_erf_nr.get(row.candidate_erf_nr) if row.candidate_erf_nr else None,
        )
        for row in rows
    ]
    return entries, warning1 or warning2


def compute_document_status_counts(entries: list[DocumentEntry]) -> dict[str, int]:
    """Kennzahlen für die klickbare Statusübersicht."""
    return {
        "alle": len(entries),
        "zugeordnet": sum(1 for e in entries if e.row.status == "Bestätigt"),
        "pruefung": sum(1 for e in entries if e.row.status == "Prüfung erforderlich"),
        "nicht_zuordenbar": sum(1 for e in entries if e.row.status in ("Nicht zuordenbar", "Fehlerhaft")),
    }


def filter_document_entries(
    entries: list[DocumentEntry],
    status_filter: str | None,
    doc_type_filter: str | None,
    date_from: date | None,
    date_to: date | None,
    query: str | None,
) -> list[DocumentEntry]:
    result = entries
    if status_filter == "zugeordnet":
        result = [e for e in result if e.row.status == "Bestätigt"]
    elif status_filter == "pruefung":
        result = [e for e in result if e.row.status == "Prüfung erforderlich"]
    elif status_filter == "nicht_zuordenbar":
        result = [e for e in result if e.row.status in ("Nicht zuordenbar", "Fehlerhaft")]

    if doc_type_filter:
        result = [e for e in result if e.row.document_type_label == doc_type_filter]
    if date_from:
        result = [e for e in result if e.row.received_at.date() >= date_from]
    if date_to:
        result = [e for e in result if e.row.received_at.date() <= date_to]
    if query:
        needle = query.casefold()
        result = [
            e
            for e in result
            if needle in e.row.filename.casefold()
            or (e.row.partner_name and needle in e.row.partner_name.casefold())
        ]
    return result


DOCUMENT_SORT_FIELDS = {
    "dateiname": lambda e: e.row.filename.casefold(),
    "datum": lambda e: e.row.belegdatum or date.min,
    "betrag": lambda e: e.row.betrag if e.row.betrag is not None else Decimal("-1"),
    "auftrag": lambda e: e.row.candidate_erf_nr or "",
    "confidence": lambda e: e.row.confidence if e.row.confidence is not None else -1.0,
    "status": lambda e: e.row.status,
}


def sort_document_entries(entries: list[DocumentEntry], sort: str, direction: str) -> list[DocumentEntry]:
    key_fn = DOCUMENT_SORT_FIELDS.get(sort, DOCUMENT_SORT_FIELDS["datum"])
    return sorted(entries, key=key_fn, reverse=(direction == "desc"))


def get_document_entry(doc_path_str: str) -> tuple[DocumentEntry | None, str | None]:
    """Ein einzelner Archiv-Eintrag für das Detail-Panel."""
    entries, warning = get_document_entries()
    for entry in entries:
        if entry.row.path == doc_path_str:
            return entry, warning
    return None, warning


def get_document_file_info(doc_path_str: str) -> tuple[str | None, int | None]:
    """(erkannte Belegnummer, Dateigröße in Bytes) für die Detailansicht.

    Die Belegnummer kommt aus der gespeicherten Dokumente-Zeile (kein
    erneutes OCR mehr nötig – wurde schon bei der Erstverarbeitung erkannt).
    """
    pdf_path = resolve_document_path(doc_path_str)
    if pdf_path is None:
        return None, None

    size = pdf_path.stat().st_size
    supabase = _get_supabase()
    row = _fetch_dokument_row(supabase, str(pdf_path))
    order_number = row.get("ErkannteAuftragsnummer") if row else None

    return order_number, size


# --- Auswertungen -----------------------------------------------------------
#
# Liest direkt aus der Tabelle "Dokumente" (alle Dokumente, offen und
# bestätigt – bestätigte tragen dort Status='bestaetigt', siehe
# confirm_assignment()). Grundlage für den Zeitraumfilter ist bewusst der
# Importzeitpunkt (ImportiertAm), wie vom Auftrag vorgegeben.

# Untere Grenze der Confidence-Verteilung ("mittel"/"niedrig") – bewusst
# nicht konfigurierbar (siehe Einstellungen: nur die obere Schwelle für
# "Hohe Übereinstimmung" ist eine Nutzereinstellung). Die obere Grenze wird
# dynamisch über get_high_confidence_threshold() übergeben, damit dieselbe
# Schwelle wie auf Dashboard/Zuordnungen/Dokumente genutzt wird.
CONFIDENCE_MEDIUM = 0.50


@dataclass
class DokumentStat:
    """Eine Zeile aus 'Dokumente', aufbereitet für Auswertungen/Export."""

    filename: str
    status: str  # Rohcode: importiert/ocr_fehler/matching_fehler/nicht_zuordenbar/pruefung/bestaetigt
    score: float | None
    belegdatum: date | None
    betrag: Decimal | None
    waehrung: str | None
    erf_nr: str | None
    imported_at: datetime
    matching_completed_at: datetime | None


def get_dokument_stats() -> tuple[list[DokumentStat], str | None]:
    """Alle Dokumente-Zeilen für die Auswertungsseite (ungefiltert)."""
    supabase = _get_supabase()
    if supabase is None:
        return [], "SUPABASE_URL/SUPABASE_KEY sind nicht gesetzt (.env prüfen)."

    try:
        resp = supabase.table("Dokumente").select("*").execute()
    except Exception as exc:  # noqa: BLE001
        return [], f"Datenbankverbindung fehlgeschlagen: {_short_error(exc)}"

    stats: list[DokumentStat] = []
    for row in resp.data:
        imported_raw = row.get("ImportiertAm")
        if not imported_raw:
            continue
        score = row.get("Score")
        matching_raw = row.get("MatchingAbgeschlossenAm")
        belegdatum_raw = row.get("Belegdatum")
        stats.append(
            DokumentStat(
                filename=row.get("Dateiname") or "",
                status=row.get("Status") or "importiert",
                score=float(score) if score is not None else None,
                belegdatum=date.fromisoformat(belegdatum_raw) if belegdatum_raw else None,
                betrag=_decimal_or_none(row.get("Betrag")),
                waehrung=row.get("Waehrung"),
                erf_nr=row.get("ErfNr"),
                imported_at=datetime.fromisoformat(imported_raw),
                matching_completed_at=datetime.fromisoformat(matching_raw) if matching_raw else None,
            )
        )
    return stats, None


def filter_dokument_stats(
    stats: list[DokumentStat],
    date_from: date | None,
    date_to: date | None,
) -> list[DokumentStat]:
    result = stats
    if date_from:
        result = [s for s in result if s.imported_at.date() >= date_from]
    if date_to:
        result = [s for s in result if s.imported_at.date() <= date_to]
    return result


def compute_auswertungen_kpis(stats: list[DokumentStat]) -> dict[str, int]:
    """Vier Kennzahlen mit klar definierter, zentraler Bedeutung:

    - verarbeitet: alle Dokumente im Zeitraum (jeder Ausgang).
    - bestaetigt: Status == 'bestaetigt' (echte Nutzerbestätigung).
    - manuell_geprueft: Status == 'pruefung' (Kandidat vorhanden, Entscheidung offen).
    - nicht_zuordenbar: kein nutzbarer Kandidat bzw. technischer Fehler.
    """
    return {
        "verarbeitet": len(stats),
        "bestaetigt": sum(1 for s in stats if s.status == "bestaetigt"),
        "manuell_geprueft": sum(1 for s in stats if s.status == "pruefung"),
        "nicht_zuordenbar": sum(
            1
            for s in stats
            if s.status in ("nicht_zuordenbar", "ocr_fehler", "matching_fehler", "matching_deaktiviert")
        ),
    }


def compute_confidence_distribution(stats: list[DokumentStat], high_threshold: float = AUTO_MATCH_THRESHOLD) -> dict:
    """Verteilung der Confidence-Scores – nur Dokumente MIT Score.

    Dokumente ohne Score (z. B. technischer Fehler, kein Matching gelaufen)
    werden explizit ausgeschlossen statt fälschlich als 'niedrig' gezählt.
    high_threshold kommt aus den Einstellungen (dieselbe Schwelle wie
    Dashboard/Zuordnungen/Dokumente).
    """
    scored = [s for s in stats if s.score is not None]
    hoch = sum(1 for s in scored if s.score >= high_threshold)
    mittel = sum(1 for s in scored if CONFIDENCE_MEDIUM <= s.score < high_threshold)
    niedrig = sum(1 for s in scored if s.score < CONFIDENCE_MEDIUM)
    return {
        "hoch": hoch,
        "mittel": mittel,
        "niedrig": niedrig,
        "gesamt": len(scored),
        "ohne_score": len(stats) - len(scored),
    }


def compute_quality_trend(stats: list[DokumentStat]) -> list[dict]:
    """Anteil bestätigter Zuordnungen je Zeit-Bucket (Tag oder Woche).

    Grundlage ist MatchingAbgeschlossenAm (nur tatsächlich gematchte
    Dokumente) – Tages- oder Wochen-Buckets abhängig von der Spannweite.
    """
    matched = [s for s in stats if s.matching_completed_at is not None]
    if not matched:
        return []

    dates = [s.matching_completed_at.date() for s in matched]
    span_days = (max(dates) - min(dates)).days
    weekly = span_days > 14

    def bucket_key(d: date) -> date:
        return d - timedelta(days=d.weekday()) if weekly else d

    buckets: dict[date, list[DokumentStat]] = {}
    for s in matched:
        key = bucket_key(s.matching_completed_at.date())
        buckets.setdefault(key, []).append(s)

    result = []
    for key in sorted(buckets.keys()):
        docs = buckets[key]
        confirmed = sum(1 for d in docs if d.status == "bestaetigt")
        result.append(
            {
                "label": key.strftime("%d.%m."),
                "quote": confirmed / len(docs),
                "total": len(docs),
                "confirmed": confirmed,
            }
        )
    return result
