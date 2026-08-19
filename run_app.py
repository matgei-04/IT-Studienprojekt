# Selbst erstellt – bitte prüfen und erklären können.
"""Startpunkt der Desktop-Anwendung.

Öffnet ein natives Fenster (pywebview) mit dem Dashboard. Intern läuft dafür
ein winziger lokaler Server nur auf 127.0.0.1 (siehe app/server.py) – die
Anwendung ist trotzdem eine normale Desktop-Anwendung, kein Web-Dienst.
"""

from __future__ import annotations

import os

# Muss VOR dem Import von webview gesetzt werden: deaktiviert die GPU-
# Hardwarebeschleunigung von WebView2. Auf manchen Rechnern (Laptops mit
# zwei Grafikkarten, VMs, Remote-Desktop-Sitzungen o. Ä.) zeigt WebView2
# sonst zwar die Seite an, aktualisiert das Fenster nach Klicks aber nicht
# mehr sichtbar – Klicks werden vom Server empfangen (siehe Logs), das
# Fenster wirkt aber "eingefroren" und reagiert scheinbar nicht.
os.environ.setdefault("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", "--disable-gpu")

import webview

from app.server import start_server


def main() -> None:
    _server, port = start_server()
    webview.create_window("Name – Übersicht", f"http://127.0.0.1:{port}/", width=1280, height=800, min_size=(1024, 700))
    # gui="edgechromium" erzwingen: pywebview installiert auf manchen Rechnern
    # mehrere mögliche Engines (hier zusätzlich PyQt/PySide). Ohne feste
    # Vorgabe wählt pywebview manchmal eine ältere/andere Engine, bei der die
    # Seite zwar angezeigt wird, Klicks/Formulare aber nicht funktionieren.
    webview.start(gui="edgechromium")


if __name__ == "__main__":
    main()
