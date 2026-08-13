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
Lege Beispieldokumente in `sample_scans/` (nicht rekursiv, nur `.pdf`).

In `.env` können zusätzlich gesetzt werden:
- `SCAN_DIRECTORY`, `MIN_DIRECT_TEXT_LENGTH`, `OCR_LANGUAGE` (Extraktion)
- `DATABASE_URL` (für Matching/Persistence / Supabase – lokal, nicht committen)

## Start (CLI)

```bash
python run_extraction.py
```

Pro Dokument erscheinen: Dateiname, Typ, `order_number`, `used_ocr`,
`confidence`, Textvorschau und kurze Ablaufhinweise.

## Öffentliche API (für Matching / UI)

```python
from extraction.config import load_settings
from extraction import extract_from_directory, extract_single_document

settings = load_settings()  # liest .env
docs = extract_from_directory(settings)
# oder: doc = extract_single_document("sample_scans/beispiel.pdf", settings)
```

### `IncomingDocument` (pro PDF)

| Feld | Bedeutung |
|------|-----------|
| `path` | Pfad zur Quelldatei |
| `text` | Extrahierter Volltext |
| `document_type` | `frachtpapier` \| `schadensmeldung` \| `eingangsrechnung` \| `wareneingangsschein` \| `unbekannt` |
| `order_number` | erkannte Nummer oder `None` |
| `confidence` | 0.0–1.0 Gesamtsicherheit |
| `used_ocr` | `True`, wenn OCR-Fallback genutzt wurde |
| `extraction_notes` | kurze Hinweise zum Ablauf |

## Pipeline (kurz)

1. PDFs im Scan-Ordner listen (nicht rekursiv)
2. Eingebetteten PDF-Text lesen (PyMuPDF)
3. Wenn Textlänge &lt; `MIN_DIRECT_TEXT_LENGTH` → OCR (Tesseract)
4. Dokumenttyp per Schlüsselwörter
5. Auftragsnummer per Regex (Labels wie ErfNr / Auftragsnr. bevorzugt)
6. `IncomingDocument` zurückgeben

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

## Was Matching von diesem Modul erwartet

Matching ruft `extract_from_directory(settings)` (oder `extract_single_document`)
auf und erhält eine Liste von `IncomingDocument`. Maßgeblich für die Zuordnung
sind vor allem `order_number`, `document_type`, `text` und `confidence`.
Dateien im Scan-Ordner bleiben unverändert.
