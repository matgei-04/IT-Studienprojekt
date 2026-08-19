-- Einzige Konfigurationszeile der Anwendung (echtes Singleton: CHECK
-- erzwingt Id=1). "Manuelle Bestätigung erforderlich" ist bewusst KEINE
-- Spalte hier – diese Regel ist im Code fest verankert (matcher.py /
-- confirm_assignment()) und nicht deaktivierbar.
CREATE TABLE IF NOT EXISTS "Einstellungen" (
    "Id" SMALLINT PRIMARY KEY DEFAULT 1,
    "OcrAktiv" BOOLEAN NOT NULL DEFAULT true,
    "MatchingAktiv" BOOLEAN NOT NULL DEFAULT true,
    "SchwelleHoheUebereinstimmung" INTEGER NOT NULL DEFAULT 80,
    "AktualisiertAm" TIMESTAMP NOT NULL DEFAULT now(),
    CONSTRAINT einstellungen_singleton CHECK ("Id" = 1),
    CONSTRAINT einstellungen_schwelle_bereich CHECK (
        "SchwelleHoheUebereinstimmung" >= 0 AND "SchwelleHoheUebereinstimmung" <= 100
    )
);

INSERT INTO "Einstellungen" ("Id") VALUES (1) ON CONFLICT ("Id") DO NOTHING;
