# Selbst erstellt – bitte prüfen und erklären können.
"""Führt neue SQL-Migrationen aus migrations/ genau einmal aus.

Kein ORM/Migrationswerkzeug im Projekt (nur direkte supabase-py/psycopg2-
Aufrufe) – deshalb eine bewusst einfache Lösung: Jede *.sql-Datei wird nur
ausgeführt, wenn ihr Dateiname noch nicht in der Tabelle
"_SchemaMigrationen" steht. Idempotent: mehrfaches Ausführen ist sicher.
"""

from __future__ import annotations

import sys
from pathlib import Path

import psycopg2
from dotenv import dotenv_values

MIGRATIONS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = MIGRATIONS_DIR.parent


def main() -> int:
    cfg = dotenv_values(PROJECT_ROOT / ".env")
    database_url = cfg.get("DATABASE_URL")
    if not database_url:
        print("Fehler: DATABASE_URL ist in .env nicht gesetzt.", file=sys.stderr)
        return 1

    conn = psycopg2.connect(database_url)
    conn.autocommit = False
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS "_SchemaMigrationen" (
            "Dateiname" VARCHAR PRIMARY KEY,
            "AngewendetAm" TIMESTAMP NOT NULL DEFAULT now()
        )
        """
    )
    conn.commit()

    cur.execute('SELECT "Dateiname" FROM "_SchemaMigrationen"')
    applied = {row[0] for row in cur.fetchall()}

    sql_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    newly_applied: list[str] = []

    for path in sql_files:
        if path.name in applied:
            continue

        sql = path.read_text(encoding="utf-8")
        try:
            cur.execute(sql)
            cur.execute('INSERT INTO "_SchemaMigrationen" ("Dateiname") VALUES (%s)', (path.name,))
            conn.commit()
            newly_applied.append(path.name)
            print(f"Angewendet: {path.name}")
        except Exception as exc:  # noqa: BLE001
            conn.rollback()
            print(f"Fehler bei {path.name}: {exc}", file=sys.stderr)
            cur.close()
            conn.close()
            return 1

    if newly_applied:
        print(f"{len(newly_applied)} Migration(en) angewendet.")
    else:
        print("Keine neuen Migrationen – bereits aktuell.")

    cur.close()
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
