# IT-Studienprojekt – Spedifix Document Matcher

## Datenextraktion

Eigenständiges Python-Modul zur Extraktion von Text, Dokumenttyp und
Auftrags-/Sendungsnummer aus PDF-Scans. **Kein Matching, keine DB, keine UI.**

## Voraussetzungen

- Python 3.11+
- Tesseract OCR (System), Sprache `deu`
  - macOS: `brew install tesseract tesseract-lang`
  - Debian/Ubuntu: `sudo apt install tesseract-ocr tesseract-ocr-deu`

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # falls noch keine .env existiert
```

PDFs **nur lesen** – Dateien werden weder verschoben noch gelöscht.
Lege eingehende Dokumente in den Ordner aus `SCAN_DIRECTORY` (auch Unterordner, nur `.pdf`).

In `.env` können zusätzlich gesetzt werden:
- `SCAN_DIRECTORY`, `MIN_DIRECT_TEXT_LENGTH`, `OCR_LANGUAGE` (Extraktion)
- `SUPABASE_URL`, `SUPABASE_KEY` (Matching / Persistenz – lokal, nicht committen)

## Start (CLI)

```bash
python run_extraction.py
```

Pro Dokument erscheinen: Dateiname, Typ, `order_number`, `used_ocr`,
Textvorschau und kurze Ablaufhinweise.

## Öffentliche API (für Matching / UI)

```python
from extraction.config import load_settings
from extraction import extract_from_directory, extract_single_document

settings = load_settings()  # liest .env
docs = extract_from_directory(settings)
# oder: doc = extract_single_document("eingang/beispiel.pdf", settings)
```

### `IncomingDocument` (pro PDF)

| Feld | Bedeutung |
|------|-----------|
| `path` | Pfad zur Quelldatei |
| `text` | Extrahierter Volltext |
| `document_type` | `frachtpapier` \| `schadensmeldung` \| `eingangsrechnung` \| `wareneingangsschein` \| `unbekannt` |
| `order_number` | erkannte Nummer oder `None` |
| `used_ocr` | `True`, wenn OCR-Fallback genutzt wurde |
| `extraction_notes` | kurze Hinweise zum Ablauf |

## Pipeline (kurz)

1. PDFs im Scan-Ordner listen (rekursiv)
2. Eingebetteten PDF-Text lesen (PyMuPDF)
3. Wenn Textlänge &lt; `MIN_DIRECT_TEXT_LENGTH` → OCR (Tesseract)
4. Dokumenttyp per Schlüsselwörter
5. Auftragsnummer nur hinter Labels (Auftragsnummer / Auftrags-Nr. / ErfNr / …)
6. `IncomingDocument` zurückgeben

Ohne erkannte Auftragsnummer gibt es beim Matching **keinen** automatischen Vorschlag.

## Tests

```bash
pytest -q
```

## Dateien

| Pfad | Rolle |
|------|--------|
| `run_extraction.py` | CLI-Einstieg |
| `domain/models.py` | `IncomingDocument`, `Settings` |
| `extraction/config.py` | `.env` laden |
| `extraction/pdf_text.py` | direkter PDF-Text |
| `extraction/ocr.py` | OCR-Fallback |
| `extraction/classify.py` | Dokumenttyp |
| `extraction/order_number.py` | ErfNr / Auftragsnr. |
| `extraction/pipeline.py` | Orchestrierung / öffentliche API |

## Matching (Anbindung)

```bash
python run_matching.py   # braucht SUPABASE_URL / SUPABASE_KEY in .env
```

Matching nutzt `extract_from_directory` und liefert `MatchResult` mit
`confidence` (Matching-Score). **Immer** manuelle Bestätigung
(`needs_manual_review=True`). Details: `matching/README.md`.

Maßgeblich aus der Extraktion: `order_number`, `document_type`, `text`.
Dateien im Scan-Ordner bleiben unverändert.

## Desktop-Anwendung (Dashboard)

```bash
python run_app.py
```

Öffnet ein natives Fenster (kein Browser, keine Web-Anwendung) mit dem
Übersichts-Dashboard. Technisch besteht das aus zwei Teilen:

- `run_app.py` startet [pywebview](https://pywebview.flowrl.com/) – das ist
  einfach ein normales Desktop-Fenster, das lokales HTML/CSS anzeigt.
- Intern läuft dafür ein winziger lokaler Server nur auf `127.0.0.1`
  (`app/server.py`, reine Python-Standardbibliothek, **kein** Flask/Django o. ä.).
  Er existiert nur, damit z. B. die Tabellensortierung über echte URLs mit
  Query-Parametern funktioniert – im Netzwerk ist er nie erreichbar.

Package `app/`:

| Pfad | Rolle |
|------|--------|
| `app/data.py` | Lädt offene Dokumente live (Extraktion + Matching) und gleicht sie mit bereits bestätigten Zuordnungen aus Supabase (`DokumentZuordnung`) ab |
| `app/routes.py` | Query-Parameter lesen, Daten laden, Template rendern |
| `app/table.py` | Sortier-Links (URL-Query-Parameter) für die Tabelle |
| `app/render.py` | Jinja2-Rendering (nur die Template-Engine, kein Framework) |
| `app/server.py` | Lokaler HTTP-Server + Router |
| `app/nav.py` | Sidebar-Menüpunkte |
| `app/templates/`, `app/static/` | HTML-Templates und CSS |

**Wichtige Annahme:** `DokumentZuordnung` speichert laut Datenbankschema nur
bereits *bestätigte* Zuordnungen (keine Spalte für "offen"/"in Prüfung").
Es gibt keine eigene Tabelle für den Verarbeitungsstatus eingehender
Dokumente. Die "offene Warteschlange" wird deshalb aus den PDFs im
Scan-Ordner (`SCAN_DIRECTORY`) abzüglich der in `DokumentZuordnung` schon
bestätigten Pfade gebildet, live bewertet und pro Lauf zwischengespeichert.
"Eingegangen am" wird mangels echtem Import-Zeitstempel über das
Änderungsdatum der Datei angenähert. Sobald ein echter Import-/Bestätigen-
Workflow existiert, sollte das durch echte Zeitstempel ersetzt werden.
