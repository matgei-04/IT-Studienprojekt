# Matching – Kurzüberblick

Baut auf `extraction` auf (`IncomingDocument` aus `domain.models`).

## Ablauf

1. Extraktion liefert `IncomingDocument`
2. Suche per `order_number` → DB `ErfNr` (Tabelle `3100_Sdg_Haupt`)
3. Fallback über Text (Ort/Referenz)
4. Score → `MatchResult.confidence` (0.0–1.0)
5. **Immer** `needs_manual_review=True` (User bestätigt)

## Gewichte (aktuell)

| Merkmal | Gewicht |
|---------|--------:|
| Auftragsnummer | 50 % |
| Referenz | 15 % |
| Absender | 15 % |
| Empfänger | 15 % |
| Dokumenttyp | 5 % |

Konstanten in `matching/scoring.py` (`WEIGHT_*`) – später gemeinsam justierbar.

## Start

```bash
# .env: SUPABASE_URL, SUPABASE_KEY, SCAN_DIRECTORY, …
python run_matching.py
```

## Tests (ohne echte DB)

```bash
pytest -q tests/test_matching.py
```
