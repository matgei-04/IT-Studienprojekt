-- Speichert jedes importierte Dokument dauerhaft (Status, erkanntes
-- Belegdatum/Betrag, Verarbeitungszeitstempel). Bestätigte Zuordnungen
-- bleiben ausschließlich in DokumentZuordnung (BestaetigtAm wird von dort
-- wiederverwendet, nicht hier dupliziert).
CREATE TABLE IF NOT EXISTS "Dokumente" (
    "Id" SERIAL PRIMARY KEY,
    "DokumentPfad" VARCHAR NOT NULL UNIQUE,
    "Dateiname" VARCHAR NOT NULL,
    "DokumentTyp" VARCHAR,
    "ErkannteAuftragsnummer" VARCHAR,
    "Belegdatum" DATE,
    "Betrag" NUMERIC,
    "Waehrung" VARCHAR(3),
    "ErfNr" VARCHAR,
    "Score" NUMERIC,
    "Status" VARCHAR NOT NULL DEFAULT 'importiert',
    "Fehlermeldung" VARCHAR,
    "ImportiertAm" TIMESTAMP NOT NULL DEFAULT now(),
    "OcrAbgeschlossenAm" TIMESTAMP,
    "MatchingAbgeschlossenAm" TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_dokumente_erfnr ON "Dokumente" ("ErfNr");
CREATE INDEX IF NOT EXISTS idx_dokumente_status ON "Dokumente" ("Status");
