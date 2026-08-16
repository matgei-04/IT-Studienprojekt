# Matching – Kurzüberblick

1. Extraktion liefert `IncomingDocument`
2. Suche per `order_number` → DB-Feld `ErfNr`
3. Sonst Suche über Text (Ort / Referenz)
4. Score → `confidence` (0.0–1.0)
5. Immer manuelle Bestätigung

## Gewichte

| Merkmal | Anteil |
|---------|-------:|
| Auftragsnummer | 50 % |
| Referenz | 15 % |
| Absender | 15 % |
| Empfänger | 15 % |
| Dokumenttyp | 5 % |

## Start

```bash
python run_matching.py
```

`.env` braucht: `SUPABASE_URL`, `SUPABASE_KEY`, `SCAN_DIRECTORY`, …
