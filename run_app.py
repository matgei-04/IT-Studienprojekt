# Selbst erstellt – bitte prüfen und erklären können.
"""Startpunkt der Desktop-Anwendung.

Öffnet ein natives Fenster (pywebview) mit dem Dashboard. Intern läuft dafür
ein winziger lokaler Server nur auf 127.0.0.1 (siehe app/server.py) – die
Anwendung ist trotzdem eine normale Desktop-Anwendung, kein Web-Dienst.
"""

from __future__ import annotations

import os
import sys

# Muss VOR dem Import von webview gesetzt werden: deaktiviert die GPU-
# Hardwarebeschleunigung von WebView2. Auf manchen Rechnern (Laptops mit
# zwei Grafikkarten, VMs, Remote-Desktop-Sitzungen o. Ä.) zeigt WebView2
# sonst zwar die Seite an, aktualisiert das Fenster nach Klicks aber nicht
# mehr sichtbar – Klicks werden vom Server empfangen (siehe Logs), das
# Fenster wirkt aber "eingefroren" und reagiert scheinbar nicht.
# force-device-scale-factor=1: Darstellung immer bei 100 % (kein OS-DPI-Zoom).
os.environ.setdefault(
    "WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS",
    "--disable-gpu --force-device-scale-factor=1 --high-dpi-support=1",
)

import webview

from app.server import start_server


def _gui_backend() -> str | None:
    """Windows: Edge/WebView2. macOS/Linux: Standard-Engine (Cocoa/GTK)."""
    if sys.platform.startswith("win"):
        return "edgechromium"
    return None


def main() -> None:
    _server, port = start_server()
    window = webview.create_window(
        "Name – Übersicht",
        f"http://127.0.0.1:{port}/",
        width=1280,
        height=800,
        min_size=(1024, 700),
    )

    def _lock_zoom(window):  # noqa: ARG001 – pywebview übergibt das Fenster
        # Nach jedem Laden Zoom auf 100 % setzen (falls die Engine etwas anderes will).
        try:
            window.evaluate_js(
                "try { document.body.style.zoom = '100%'; "
                "document.documentElement.style.zoom = '1'; } catch (e) {}"
            )
        except Exception:
            pass

    window.events.loaded += _lock_zoom

    gui = _gui_backend()
    if gui:
        webview.start(gui=gui)
    else:
        webview.start()


if __name__ == "__main__":
    main()
