# Matching – Kurzüberblick

1. Extraktion liefert `IncomingDocument` (inkl. `order_number`)
2. Nur Suche per `order_number` → DB-Feld `ErfNr`
3. Ohne Nummer oder ohne DB-Treffer → keine Zuordnung (manuell möglich)
4. Score → `confidence` (0.0–1.0); Absender/Empfänger nur zur Bewertung
5. Immer manuelle Bestätigung

## Gewichte

Jedes Merkmal zählt nur **exakt** (1.0) oder **gar nicht** (0.0).

| Merkmal | Anteil | Treffer wenn |
|---------|-------:|--------------|
| Auftragsnummer | 50 % | erkannte Nummer = `ErfNr` |
| Referenz | 15 % | `Ref-1` vollständig im Dokumenttext |
| Absender | 15 % | alle Adressfelder exakt im Text |
| Empfänger | 15 % | wie Absender |
| Dokumenttyp | 5 % | Typ exakt gleich |

## Start

```bash
python run_matching.py
```

`.env` braucht: `SUPABASE_URL`, `SUPABASE_KEY`, `SCAN_DIRECTORY`, …
