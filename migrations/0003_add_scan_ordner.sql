-- Konfigurierbarer Import-Ordner (Einstellungen > Datenquellen). NULL/leer
-- bedeutet: SCAN_DIRECTORY aus der .env wird weiterhin verwendet (siehe
-- app/data.py, _load_settings_with_override) – bestehende Installationen
-- ohne gesetzten Wert verhalten sich also unverändert.
ALTER TABLE "Einstellungen" ADD COLUMN IF NOT EXISTS "ScanOrdner" TEXT;
